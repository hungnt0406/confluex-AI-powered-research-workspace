# Writer Editor Agent — Implementation Plan

## Context

The Writer workspace today generates full section drafts via `GroundedWriterAgent` → `save_section_edit` → Monaco editor. There is no targeted, in-line revision flow. Users who want to fix a typo, generate a single paragraph, or fold in newly obtained results must either edit raw LaTeX by hand or re-run a full section draft, which is expensive, slow, and tends to discard their wording.

This plan adds a dedicated **Editor Agent** — a lean, intent-scoped revision agent that operates *only* on the current draft (no project source library, no embedding rerank). Three intents in v1:

1. **`fix_error`** — rewrite a selected span (grammar, awkward phrasing, factual tightening).
2. **`generate_paragraph`** — write one paragraph at an insertion point in the current section.
3. **`incorporate_results`** — fold user-pasted findings into a target section, optionally adding a citation to a user-supplied source.

Opt-in **Tavily web search** is layered on `generate_paragraph` and `incorporate_results`. Off by default. All other context comes from the draft itself.

Outcome: cheap, predictable, granular edits that preserve the user's prose, with a diff-preview UX (Accept / Regenerate / Refine / Discard) and automatic version history via the existing `WriterSectionVersion` snapshot path.

---

## Backend

### New file: `backend/agents/writer_editor.py` (~350 lines)

Single class `WriterEditorAgent` with three async methods, one per intent. Mirrors the shape of `WriterSectionAgent` (`backend/agents/writer_section.py:103`) but does **not** take `paper_contexts` — the draft is the only grounding.

```python
class EditIntent(StrEnum):
    FIX_ERROR = "fix_error"
    GENERATE_PARAGRAPH = "generate_paragraph"
    INCORPORATE_RESULTS = "incorporate_results"

@dataclass(frozen=True)
class TextSpan:
    start: int       # char offset in section.draft_latex
    end: int

@dataclass(frozen=True)
class NewResult:
    text: str
    source_ref: str | None
    attach_as_citation: bool

@dataclass(frozen=True)
class WebSearchHit:        # only populated when web_search=True
    title: str
    url: str
    snippet: str

@dataclass(frozen=True)
class EditPatch:
    span: TextSpan         # for generate_paragraph: span.start == span.end (insertion)
    new_text: str
    rationale: str
    web_citations: list[WebSearchHit]   # empty unless web_search was used

class WriterEditorAgent:
    async def fix_error(self, *, draft: str, span: TextSpan, instruction: str | None) -> EditPatch: ...
    async def generate_paragraph(self, *, draft: str, insertion_offset: int, topic: str,
                                 section_heading: str, web_hits: list[WebSearchHit] | None) -> EditPatch: ...
    async def incorporate_results(self, *, draft: str, target_span: TextSpan, new_results: list[NewResult],
                                  section_heading: str, web_hits: list[WebSearchHit] | None) -> EditPatch: ...
```

Implementation notes:

- LLM via existing `backend/services/llm.py` → `generate_json`. One strict JSON schema per intent. Schema requires `new_text` and `rationale`; fix_error forbids changes outside the span.
- Context window per intent (small, bounded):
  - `fix_error`: 200 tokens before + selected span + 200 tokens after.
  - `generate_paragraph`: paragraph before + paragraph after insertion + section heading + outline (section titles only).
  - `incorporate_results`: full target section text + section heading + outline.
- Offline fallback (no `OPENROUTER_API_KEY`): return a deterministic patch — e.g. the span itself with `rationale="offline_stub"` — so tests run hermetically. Matches the pattern in `writer.py:199`.
- LaTeX citation preservation: `\cite{...}` and `\citep{...}` macros inside the span are tokenized before the LLM call and restored after, so the model can't accidentally drop or invent citations. Helper lives in the new file.
- Validation step: assert `new_text` does not introduce `\cite{`/`\citep{` keys unknown to the document (cross-check `WriterDocumentSource` rows). On failure, retry once with stricter system prompt; on second failure, surface a warning to the user.

### New file: `backend/services/writer_editor.py` (~180 lines)

Thin service that glues the agent, Tavily, and `WriterSection` persistence together. Mirrors the role of `writer_documents.py` for editor calls.

```python
class WriterEditorService:
    def __init__(self, session, agent: WriterEditorAgent, tavily: TavilySearchService): ...

    async def preview(self, *, document_id, section_id, request: EditRequest) -> EditPatch:
        # 1. Load section.draft_latex
        # 2. If web_search → tavily.search(query) → top-5 hits
        # 3. Dispatch by intent → agent.<intent>()
        # 4. Return patch (NOT persisted)

    async def apply(self, *, document_id, section_id, patch: EditPatch) -> WriterSectionRead:
        # Build new_draft = draft[:span.start] + patch.new_text + draft[span.end:]
        # Delegate to existing save_section_edit() so versioning fires automatically.
```

Key reuse:

- `backend/services/writer_documents.py:591` `save_section_edit` — already snapshots prior version into `WriterSectionVersion` (capped at `MAX_SECTION_VERSIONS`). Editor applies just call this; no new version mechanism.
- `backend/services/tavily.py` `TavilySearchService.search()` and `is_configured()` — reused unchanged.
- `backend/services/llm.py` `generate_json` — reused unchanged.

### Router additions: `backend/api/routers/writer_documents.py`

Two new endpoints, scoped under the existing section path:

```
POST  /writer/documents/{doc_id}/sections/{section_id}/edit         -> EditPatchResponse
POST  /writer/documents/{doc_id}/sections/{section_id}/edit/apply   -> WriterSectionRead
```

Splitting preview from apply keeps the apply step dumb and auditable (frontend holds the patch in memory between the two calls). Apply revalidates the patch is still applicable (span still in-bounds against the current `draft_latex`); if not, returns 409 and the frontend re-runs preview.

Credit gating via existing `backend/api/dependencies.py` `require_credits`:

| Endpoint | Feature tag | Credits (no web) | Credits (web) |
|---|---|---|---|
| `/edit` fix_error | `writer_editor_fix` | 1 | n/a |
| `/edit` generate_paragraph | `writer_editor_generate` | 2 | 4 |
| `/edit` incorporate_results | `writer_editor_incorporate` | 3 | 5 |
| `/edit/apply` | `writer_editor_apply` | 0 (free) | 0 |

Admin bypass already handled by `require_credits` (`dependencies.py:185`).

### Schemas: `backend/api/schemas/writer_documents.py`

Append:

```python
class TextSpanSchema(BaseModel): start: int; end: int
class NewResultSchema(BaseModel): text: str; source_ref: str | None; attach_as_citation: bool = False
class EditRequest(BaseModel):
    intent: Literal["fix_error", "generate_paragraph", "incorporate_results"]
    instruction: str | None = None     # required for generate_paragraph (topic) and incorporate_results
    span: TextSpanSchema | None = None # required for fix_error and incorporate_results
    insertion_offset: int | None = None # required for generate_paragraph
    new_results: list[NewResultSchema] = []
    web_search: bool = False
    web_query: str | None = None
class WebCitationSchema(BaseModel): title: str; url: str; snippet: str
class EditPatchResponse(BaseModel):
    span: TextSpanSchema
    new_text: str
    rationale: str
    web_citations: list[WebCitationSchema] = []
```

Pydantic validator on `EditRequest` enforces the per-intent required-fields matrix; returns 422 with a clear message instead of a downstream `None` deref.

### DB

**No schema changes.** Reuses `WriterSection.draft_latex` and `WriterSectionVersion` (already in `backend/db/models.py:618` and `:649`). Versioning fires through the existing `save_section_edit` path.

### Tests: `tests/test_writer_editor.py` (new)

Six tests, all hermetic (no live LLM, no live Tavily):

1. `fix_error` happy path → patch returned, citations inside span preserved.
2. `generate_paragraph` at end-of-section insertion → new paragraph appended; no spurious `\cite` keys.
3. `incorporate_results` with `attach_as_citation=True` → patch references the user-supplied source.
4. `incorporate_results` with web_search=True (Tavily stubbed) → `web_citations` populated.
5. Apply endpoint re-validates span; returns 409 when span is stale (simulated by editing draft between preview and apply).
6. Offline fallback (no OPENROUTER key) → deterministic stub patch, no exception.

Plus router-level tests in `tests/test_writer_documents.py`: credit gating (insufficient credits → 402), admin bypass, auth required.

---

## Frontend

### New component: `frontend/components/WriterEditorOverlay.tsx` (~400 lines)

The single overlay component that owns all editor-agent UI surfaces. Renders inside `WriterWorkspace.tsx` as a sibling of the Monaco editor.

Responsibilities:

1. **Selection toolbar** — listens to Monaco's `onDidChangeCursorSelection`. When a non-empty selection exists, computes screen coordinates via `editor.getScrolledVisiblePosition` and renders a floating toolbar above the selection: `[✎ Fix] [✦ Edit…] [+ Add results]`.
2. **Gutter insertion caret** — on `onDidChangeCursorPosition` with an empty selection landing between paragraphs (blank-line detection on the line above/below), shows a thin `+` button in the editor margin. Click opens a small popover: topic input, 🌐 toggle, [Generate].
3. **Pending patch state** — holds at most one `EditPatch` at a time. Renders the diff popover anchored to `patch.span` screen coordinates.
4. **Diff popover** — custom card (matches existing modal/popover styling in `WriterSourcesPanel.tsx` and `AssembleModal`):
   - Strikethrough for removed text (muted), highlighted background for new text.
   - Why line (one sentence from `patch.rationale`).
   - Web citations (if any) rendered as small URL chips.
   - Actions: `✓ Accept`, `↻ Regenerate`, `✎ Refine`, `✕ Discard`.
5. **Add-results modal** — full modal matching `AssembleModal` pattern. Fields: findings textarea, source field, "Cite this source" checkbox, target-section radio (defaults to current section / current selection), 🌐 web search toggle, Preview button.
6. **Pending indicator chip** — if a patch is pending and the user clicks away, a floating chip in the corner: `1 pending suggestion · Review`.

Internal state (React `useState`, matches existing pattern):

```ts
const [selection, setSelection] = useState<MonacoSelection | null>(null);
const [pendingPatch, setPendingPatch] = useState<EditPatch | null>(null);
const [activeFlow, setActiveFlow] = useState<"none" | "fix" | "edit-prompt" | "generate" | "add-results">("none");
const [isLoading, setIsLoading] = useState(false);
const [lastRequest, setLastRequest] = useState<EditRequest | null>(null); // for Refine/Regenerate
```

Accept action:

```ts
async function onAccept(patch: EditPatch) {
  await applyWriterEdit(documentId, sectionId, patch, token);
  await refreshSection();   // re-fetch section.draft_latex; Monaco re-syncs via existing prop flow
  setPendingPatch(null);
}
```

Refine reopens the prompt input prefilled with `lastRequest.instruction`; Regenerate re-POSTs the same request; Discard just clears `pendingPatch`.

### Touch: `frontend/components/WriterWorkspace.tsx`

Minimal changes:

- Import and render `<WriterEditorOverlay editor={monacoEditorRef.current} section={activeSection} ... />` inside the editor column (`WriterWorkspace.tsx:640` area).
- Expose the Monaco editor instance via a ref (already partly there via `onMount`); pass it to the overlay.
- Suppress auto-save (`handleEditorChange` at line 309) while a patch is pending — Monaco content is still the saved version, but we don't want the debounced save to race with the apply endpoint.

### Touch: `frontend/lib/api.ts`

Two new client functions next to `saveSectionEdit` (~line 900):

```ts
export async function previewWriterEdit(
  documentId: string, sectionId: string, body: EditRequest, token: string
): Promise<EditPatchResponse>;

export async function applyWriterEdit(
  documentId: string, sectionId: string, patch: EditPatchResponse, token: string
): Promise<WriterSectionRead>;
```

Both use the existing `ApiError` + `Authorization: Bearer` patterns. `previewWriterEdit` surfaces 402 (insufficient credits) via the existing `isInsufficientCreditsError` helper so the UI can show the existing credits-low banner.

### Styling

All Tailwind, reusing the project's tokens (`surface-container`, `on-surface`, `primary`, `outline/20`) and conventions:

- Floating toolbar: `absolute rounded-full border border-outline/20 bg-surface-container shadow-lg px-1 py-1 flex gap-1`.
- Diff popover: `rounded-2xl border border-outline/20 bg-surface shadow-xl max-w-md`.
- Added text: `bg-emerald-50 text-emerald-900 dark:bg-emerald-900/20 dark:text-emerald-100`.
- Removed text: `line-through text-on-surface-variant`.
- Web-search chip: `inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 px-2 py-0.5 text-[11px]` with the existing Material Symbols globe icon.

### Frontend tests: `tests/test_frontend_writer_static.py` (extend)

Static checks (matching existing test style):

- `WriterEditorOverlay` is imported and rendered by `WriterWorkspace`.
- New API functions `previewWriterEdit` and `applyWriterEdit` are exported from `lib/api.ts`.
- Diff styling tokens are present.

(Full interaction tests are deferred to the `frontend-qa-tester` Playwright pass after the slice lands.)

---

## Phased delivery

Three PRs, each shippable on its own. Each PR includes its backend slice + matching UI surface + tests, so main is never in a half-feature state.

**PR 1 — `fix_error` end-to-end** (smallest vertical slice; validates the whole architecture)
- `WriterEditorAgent.fix_error` + offline stub + JSON schema + citation tokenizer.
- `WriterEditorService` with preview/apply (apply is generic from day one).
- Both router endpoints (`/edit`, `/edit/apply`) with intent dispatch — only `fix_error` enabled; other intents return 501.
- `WriterEditorOverlay`: selection toolbar with **Fix** button + diff popover + Accept/Discard. No Edit popover, no caret, no modal yet.
- Tests: hermetic fix_error happy path + apply 409 staleness + credit gating.

**PR 2 — `generate_paragraph`**
- Add `generate_paragraph` intent handler + schema.
- Add gutter caret + Generate popover with topic input.
- 🌐 web search toggle wired (Tavily plumbing lands here).
- Tests: generate with and without web hits; Tavily stubbed.

**PR 3 — `incorporate_results`**
- Add `incorporate_results` intent handler + schema.
- Add `Add results` button to selection toolbar + full add-results modal.
- Tests: with and without `attach_as_citation`; web search variant.

After PR 3: Playwright pass via `frontend-qa-tester` covering all three flows end-to-end.

---

## Critical files

**Modify**
- `backend/api/routers/writer_documents.py` — two endpoints + credit constants.
- `backend/api/schemas/writer_documents.py` — request/response schemas.
- `backend/services/writer_documents.py` — no logic changes; just confirms `save_section_edit` is reusable as-is for apply.
- `frontend/components/WriterWorkspace.tsx` — mount overlay, expose Monaco ref, gate auto-save during pending patch.
- `frontend/lib/api.ts` — two new client functions + types.
- `tests/test_writer_documents.py` — credit-gating cases for new endpoints.
- `tests/test_frontend_writer_static.py` — static checks for new component/exports.
- `JOURNAL.md`, `AI_WORKLOG.md`, `docs/features/writer_outputs.md`, `docs/feature-map.md` — per repo convention.

**Create**
- `backend/agents/writer_editor.py`
- `backend/services/writer_editor.py`
- `frontend/components/WriterEditorOverlay.tsx`
- `tests/test_writer_editor.py`

---

## Reused utilities (do not re-implement)

- LLM structured calls: `backend/services/llm.py` `generate_json` and `is_configured`.
- Web search: `backend/services/tavily.py` `TavilySearchService.search`, `is_configured`.
- Version snapshot: `backend/services/writer_documents.py:591` `save_section_edit` (auto-creates `WriterSectionVersion`).
- Credit gating: `backend/api/dependencies.py` `require_credits` (admin bypass included).
- DB models: `WriterSection`, `WriterSectionVersion` in `backend/db/models.py:618`/`:649` — no schema changes.
- Frontend error helper: `lib/api.ts` `ApiError`, `isInsufficientCreditsError`.
- Frontend modal/popover styling: existing `AssembleModal` and `WriterSourcesPanel` patterns.

---

## Verification

After each PR:

```bash
uv run ruff check .
uv run mypy backend/
uv run pytest tests/ -x
cd frontend && npm run build
```

Per-PR manual checks:

**PR 1 (fix_error)**
1. `uv run uvicorn backend.main:app --reload` and `cd frontend && npm run dev`.
2. Open a writer document, select a sentence in the Monaco editor.
3. Floating toolbar appears with ✎ Fix. Click it.
4. Diff popover shows old (strikethrough) and new (highlighted) text plus a one-line rationale.
5. Click Accept → section refreshes, draft updates, `WriterSectionVersion` row created (verify via the existing version-history endpoint).
6. Run again with `OPENROUTER_API_KEY` unset → confirm offline stub returns without error.
7. Run with a non-admin user at zero balance → confirm 402 surfaces as the existing credits-low banner.

**PR 2 (generate_paragraph)**
1. Place cursor on a blank line between paragraphs → gutter `+` appears.
2. Open Generate popover, enter a topic, leave 🌐 off → paragraph inserts at correct offset; surrounding text untouched.
3. Toggle 🌐 on with `TAVILY_API_KEY` set → web citation chips render below the rationale. With key unset → request still succeeds, `web_citations` is empty, no crash.
4. Verify credit debit is the higher amount when web=on.

**PR 3 (incorporate_results)**
1. Select a paragraph → toolbar `+ Add results` opens the modal.
2. Paste findings, supply a source string, check Cite this → preview returns a patch that mentions the source.
3. Accept → draft updates, version snapshot created.
4. Repeat with target-section radio set to a different section → patch targets that section's span correctly.

Final pass: `frontend-qa-tester` Playwright run on all three flows; `security-reviewer` and `code-reviewer` agents on the diff before each merge.
