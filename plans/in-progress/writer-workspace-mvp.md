# LaTeX Writer Workspace — MVP Plan

## Context

We want a dedicated writing workspace where a researcher inside a project can produce a full IMRaD research paper in LaTeX, guided by the agent. The current `/projects/{id}/writer/generate` endpoint produces a one-shot Markdown/LaTeX blob from selected papers — useful, but it doesn't support the iterative "topic → outline → section-by-section drafting with grounded citations" workflow we want.

This MVP adds that workflow as an extension of the existing writer pipeline. Decisions already made:

- **IMRaD only** for the first slice (one paper-type template).
- **Source-only LaTeX editor** in the browser (Monaco). Export `.tex` + `.bib`.
- **PDF preview deferred** — users compile locally (Overleaf / local TeX) until v1.1 ships Render + tectonic compile.
- **Auto-fetch PDFs** when arXiv / OA links are available; user uploads only when paywalled.
- **Tavily** is a research/discovery aid, not a citation source — restricted to academic domains.
- **Grounding contract**: every claim must be supported by an in-document source. Unsupported claims are written but tagged `\todo{citation needed}` — user must resolve before export.

Intended outcome: the user opens a project, says "write a paper about X", answers section-typed questions, the agent drafts each section grounded in attached PDFs, and the user gets a `.tex` + `.bib` package ready to compile in Overleaf.

## Scope (MVP)

**In:**
- New writer workspace route (`/writer/[documentId]`) with Monaco LaTeX editor, outline navigator, source/citation panel.
- Topic + thesis input → IMRaD outline proposal → per-section drafting loop.
- Predetermined per-section question slots (IMRaD-specific).
- Auto-fetch arXiv PDFs when available; user upload fallback (reuses existing `reference-files` flow).
- Tavily search filtered to academic domains, used for paper-discovery only (cap 2 calls/section, cache by query).
- Low-confidence claim tagging (`\todo{}`) emitted by writer agent and surfaced in QA list.
- Export `.tex` + `references.bib` as a downloadable bundle.
- Auto-save per section.
- Section-level version snapshots (last 5 per section).

**Out (deferred):**
- PDF preview / Render + tectonic compile (v1.1).
- Survey / position / theoretical paper templates (v1.2).
- Cross-section consistency QA pass.
- `.docx` export.
- Figures/tables UX (user inserts raw `\includegraphics` / `tabular` for now).
- Multi-template / journal-specific preambles (NeurIPS, ACL, IEEEtran).
- Streaming draft generation.
- Replacing the existing `/writer/generate` endpoint — it stays as-is for backward compatibility.

## Architecture

The MVP **extends** the existing writer system, it does not replace it.

```
Existing (keep as-is):
  /projects/{id}/writer/generate   → one-shot WriterOutput

New (add alongside):
  /projects/{id}/writer/documents              → CRUD WriterDocument
  /writer/documents/{id}/outline               → propose / edit outline
  /writer/documents/{id}/sections/{sid}/...    → per-section flow
  /writer/documents/{id}/sources/...           → suggest, auto-fetch, upload
  /writer/documents/{id}/qa                    → low-confidence + citation report
  /writer/documents/{id}/export                → .tex + .bib bundle
```

### Reuse map (existing code we call, do not re-implement)

| Need | Existing | Path |
|---|---|---|
| Grounded section drafting | `GroundedWriterAgent.generate()` | `backend/agents/writer.py:124` |
| LaTeX citation formatting (`\cite{}`, BibTeX, `escape_latex_text`) | `CitationFormatter` | `backend/services/citations.py:24` |
| PDF chunking + embeddings | `PaperDocumentExtractionService.ensure_document_chunks()` | `backend/services/document_extraction.py:22` |
| Cosine chunk retrieval per section | `WriterOutputService._load_relevant_chunks()` | `backend/services/writer_outputs.py` |
| User PDF upload + `Paper` linkage | `ReferenceFileService.create_reference_file()` | `backend/services/reference_files.py:184` |
| Structured LLM JSON output | `OpenRouterStructuredOutputService.generate_json()` | `backend/services/llm.py` |
| Tavily web search | `TavilySearchService.search()` | `backend/services/tavily.py` (extend with `include_domains`) |
| arXiv search + PDF URL | `backend/services/arxiv.py` | (use `pdf_url` field already on `Paper`) |
| Credit gating | `require_credits` | `backend/api/dependencies.py` |
| Frontend auth wrapper | `AuthProvider` | `frontend/components/AuthProvider.tsx` |
| Project sidebar | `Sidebar` | `frontend/components/Sidebar.tsx` |
| Resizable side panel | `ContextPanel` | `frontend/components/ContextPanel.tsx` |
| Reference upload UX | `uploadProjectReferenceFile()` | `frontend/lib/api.ts:706` |

## Data model

Three new tables. Existing `Paper` and `ReferenceFile` tables are reused as-is — auto-fetched arXiv PDFs and user uploads both land as `Paper` rows scoped to the project, the writer document just references their IDs.

### `writer_documents`
- `id` (PK, str/uuid)
- `project_id` (FK → projects)
- `title` (str)
- `topic` (text) — user's research topic input
- `thesis` (text, nullable) — one-sentence contribution
- `paper_type` (str) — `"imrad"` for MVP
- `citation_style` (str) — defaults from `project.citation_format`
- `preamble` (text, nullable) — LaTeX preamble; default IMRaD template applied on create
- `source_paper_ids_json` (list[str]) — papers in scope for this document
- `bib_text` (text, nullable) — last-assembled bibtex (cached on assemble/export)
- `status` (str) — `outline | drafting | ready | exported`
- `created_at`, `updated_at`

### `writer_sections`
- `id` (PK)
- `writer_document_id` (FK)
- `section_type` (str) — `abstract | intro | related_work | methods | results | discussion | conclusion`
- `order_index` (int)
- `title` (str)
- `outline_text` (text, nullable) — agent's outline notes
- `user_inputs_json` (jsonb) — answers to section-typed questions: `{question_key: answer_text}`
- `draft_latex` (text, nullable) — current LaTeX, user-editable
- `low_confidence_spans_json` (jsonb) — `[{text, reason, suggested_query}]`
- `cited_paper_ids_json` (list[str])
- `status` (str) — `planned | awaiting_input | drafted | user_edited`
- `updated_at`

### `writer_section_versions` (last 5 per section)
- `id`, `writer_section_id` (FK), `draft_latex`, `created_at`
- Trim to 5 newest on insert.

### Migration

New Alembic revision `backend/db/migrations/versions/20260509_01_writer_workspace.py` (follow the date-prefixed naming convention from recent migrations). Create the three tables; no changes to existing tables.

## Backend changes

### New: `backend/services/writer_documents.py`
Owner of the new flow. Functions (signatures sketch):

- `create_document(session, user, project_id, topic, thesis, paper_type)` → creates document with default IMRaD outline placeholders (7 empty sections).
- `propose_outline(session, document_id)` → calls LLM with topic+thesis, returns proposed `outline_text` per section (does not persist until user approves).
- `apply_outline(session, document_id, outline_by_section)` → persist approved outline.
- `section_questions(section_type)` → returns the predetermined question registry (see below).
- `submit_section_inputs(session, section_id, answers)` → store `user_inputs_json`, set `status=awaiting_input`.
- `suggest_sources(session, document_id, section_id, query)` → search Semantic Scholar + arXiv + filtered Tavily, dedup against existing project papers, return ranked candidates with `pdf_available: bool`.
- `attach_source(session, document_id, candidate)` → if arXiv/OA: download PDF via `httpx`, persist as `ReferenceFile` (reuse `ReferenceFileService`), trigger `ensure_document_chunks()`. If paywalled: return marker requiring upload.
- `draft_section(session, section_id)` → runs grounded draft (see below), persists `draft_latex` + `low_confidence_spans_json`, snapshots prior version into `writer_section_versions`.
- `save_section_edit(session, section_id, draft_latex)` → persist user edit, snapshot prior version, set `status=user_edited`.
- `assemble(session, document_id)` → concatenate sections in order, format references via `CitationFormatter`, return `{tex, bib}`.
- `export_bundle(session, document_id)` → return tar/zip of `paper.tex` + `references.bib` + `qa_report.json`.

### New: `backend/agents/writer_section.py`
Thin adapter around the existing `GroundedWriterAgent.generate()` that:

1. Builds a per-section instruction from `outline_text` + section-typed `user_inputs_json` + section-type prompt template.
2. Pulls top-k chunks across `source_paper_ids` via existing cosine retrieval.
3. Calls `GroundedWriterAgent` with `output_target="latex"`, `citation_mode="latex_cite"`.
4. **Post-processes the result** to detect unsupported sentences: any sentence in `WriterBodyBlock` whose `paper_ids` is empty gets wrapped as `<sentence> \todo{citation needed: <reason>}` and added to `low_confidence_spans_json`. This is the new piece — hardcode the rule rather than asking the LLM to self-flag.

### Section question registry (hardcoded, IMRaD)
Lives in `backend/agents/writer_section.py` as a constant:

```
abstract        → (generated last from other sections, no questions)
intro           → ["What problem does this paper address?",
                   "What is the research gap?",
                   "What is your one-sentence contribution?",
                   "Who is the target audience?"]
related_work    → ["Which 3-5 lines of prior work matter most?",
                   "Any specific papers/authors to cover?",
                   "What gap does your work fill that prior work doesn't?"]
methods         → ["What dataset(s) did you use?",
                   "What model/algorithm/approach?",
                   "What are the baselines?",
                   "What is the evaluation metric?"]
results         → ["Paste your key numbers / table / main finding.",
                   "What is the headline result?"]
discussion      → ["What is your interpretation?",
                   "What are the limitations?",
                   "Why does this matter?"]
conclusion      → ["One-sentence takeaway?",
                   "Future work directions?"]
```

### Extend: `backend/services/tavily.py`
Add `include_domains: list[str] | None = None` to `search()`, pass through to Tavily payload. Add a default academic-domain whitelist constant: `arxiv.org, semanticscholar.org, scholar.google.com, acm.org, ieee.org, openreview.net, aclanthology.org, nature.com, sciencedirect.com`. `writer_documents.suggest_sources()` always passes this whitelist.

### Extend: `backend/services/arxiv.py` (small helper)
Add `download_pdf(arxiv_id_or_url) -> bytes` that fetches the arXiv PDF directly. Used by `attach_source` for auto-fetch.

### New router: `backend/api/routers/writer_documents.py`
Mounted at `/projects/{project_id}/writer/documents` and `/writer/documents/{id}/...`. All endpoints behind `CurrentUser`. Credit gating via `require_credits` on:
- `POST /writer/documents/{id}/outline/propose` (LLM call)
- `POST /writer/documents/{id}/sections/{sid}/draft` (LLM + chunks)
- `POST /writer/documents/{id}/sources/suggest` (Tavily + SS + arXiv)

Endpoints:
```
POST   /projects/{project_id}/writer/documents
GET    /projects/{project_id}/writer/documents
GET    /writer/documents/{id}
PATCH  /writer/documents/{id}                    # title, thesis, preamble
DELETE /writer/documents/{id}

POST   /writer/documents/{id}/outline/propose
PUT    /writer/documents/{id}/outline             # apply edited outline

GET    /writer/documents/{id}/sections/{sid}/questions
PUT    /writer/documents/{id}/sections/{sid}/inputs
POST   /writer/documents/{id}/sections/{sid}/draft
PATCH  /writer/documents/{id}/sections/{sid}      # user manual edit
GET    /writer/documents/{id}/sections/{sid}/versions
POST   /writer/documents/{id}/sections/{sid}/revert/{version_id}

POST   /writer/documents/{id}/sources/suggest     # body: section_id, query
POST   /writer/documents/{id}/sources/attach      # body: candidate (auto-fetch or upload-required marker)
POST   /writer/documents/{id}/sources/upload      # multipart, fallback path
DELETE /writer/documents/{id}/sources/{paper_id}

GET    /writer/documents/{id}/qa
POST   /writer/documents/{id}/assemble
GET    /writer/documents/{id}/export              # zip of .tex + .bib + qa_report.json
```

### Schemas: `backend/api/schemas/writer_documents.py`
Pydantic models mirroring the table columns plus request/response DTOs for each endpoint.

## Frontend changes

### New route: `frontend/app/writer/[documentId]/page.tsx`
- Wrapped in `AuthProvider` and `ChatProvider` (or a leaner `WriterProvider` if `ChatProvider` carries too much chat-specific state — start by reusing, refactor only if it gets in the way).
- Layout: 3 columns
  - **Left (20%)**: outline navigator — section list, status pills (planned / awaiting input / drafted / edited), click to focus.
  - **Center (50%)**: Monaco editor in LaTeX mode, single section at a time. Auto-save (debounced 1s).
  - **Right (30%)**: tabs — `Sources` (in-scope papers, add/upload buttons), `Questions` (section-typed prompts + answer fields), `QA` (low-confidence flags + missing-citation list).
- Top bar: document title (editable), citation style display, **Assemble** + **Export** buttons.

### New route: `frontend/app/writer/page.tsx` (index)
List of writer documents grouped by project + "New Paper" button.

### New API helpers in `frontend/lib/api.ts`
One helper per endpoint above. Mirror the existing `streamProjectConversation` / `uploadProjectReferenceFile` style. No streaming for MVP.

### Sidebar wiring (`frontend/components/Sidebar.tsx`)
Add "Writer" link below "Plans", scoped to the active project. Surfaces the project's writer documents.

### Editor choice
**Monaco** (`@monaco-editor/react`) with LaTeX language registered. CodeMirror is a viable alternative; Monaco picked for VS-Code-grade UX out of the box and since the bundle size hit (~600KB gz) is acceptable for a desktop-first writing tool.

## Low-confidence tag spec

LaTeX form: `\todo{citation needed: <short reason>}` using the `todonotes` package. Document preamble (default IMRaD template) includes:
```latex
\usepackage[colorinlistoftodos,prependcaption,textsize=tiny]{todonotes}
\newcommand{\unsupported}[1]{\todo[color=red!30]{unsupported: #1}}
```

Stored shape in `low_confidence_spans_json`:
```json
[{"section_id": "...", "text": "exact sentence text",
  "reason": "no chunk matched 'retrieval-augmented'",
  "suggested_query": "retrieval augmented generation domain QA",
  "char_offset": 1234}]
```

Export QA report (`qa_report.json`) lists every unresolved tag. Frontend QA tab surfaces them with one-click "search for sources for this claim" → routes to `sources/suggest`.

**Export gate**: `assemble` endpoint succeeds with warnings; user gets a confirm dialog ("3 unresolved citation gaps — export anyway?") rather than a hard block. Hard-blocking would frustrate users mid-draft.

## Files to add / modify

**Add:**
- `backend/db/migrations/versions/20260509_01_writer_workspace.py`
- `backend/db/models.py` — append `WriterDocument`, `WriterSection`, `WriterSectionVersion` (extend, don't replace existing).
- `backend/services/writer_documents.py`
- `backend/agents/writer_section.py`
- `backend/api/routers/writer_documents.py`
- `backend/api/schemas/writer_documents.py`
- `tests/test_writer_documents.py` (RED-first per CLAUDE.md TDD)
- `tests/test_writer_section_agent.py`
- `frontend/app/writer/page.tsx`
- `frontend/app/writer/[documentId]/page.tsx`
- `frontend/components/WriterWorkspace.tsx`
- `frontend/components/WriterOutlinePanel.tsx`
- `frontend/components/WriterSourcesPanel.tsx`
- `frontend/components/WriterQuestionsPanel.tsx`
- `frontend/components/WriterQAPanel.tsx`

**Modify:**
- `backend/services/tavily.py` — add `include_domains` param + academic-whitelist constant.
- `backend/services/arxiv.py` — add `download_pdf()` helper.
- `backend/main.py` — register new router.
- `backend/api/dependencies.py` — add credit cost constants for new endpoints if not already covered.
- `frontend/lib/api.ts` — new helpers.
- `frontend/components/Sidebar.tsx` — add Writer link.
- `database_schema.sql` — append new tables (per CLAUDE.md sync rule).
- `JOURNAL.md` — log entry per CLAUDE.md repo conventions.

## Verification

End-to-end smoke (do these manually before declaring done):
1. `uv run alembic upgrade head` succeeds; new tables exist.
2. `uv run pytest tests/test_writer_documents.py tests/test_writer_section_agent.py -x` passes (TDD: write these first).
3. Quality gates: `uv run ruff check . && uv run mypy backend/ && uv run pytest tests/ -x` green.
4. **Offline parity** (per CLAUDE.md hard requirement): with `OPENROUTER_API_KEY` unset, `propose_outline` and `draft_section` return deterministic offline content; whole test suite still passes.
5. Frontend dev test (start backend + `cd frontend && npm run dev`):
   - Create writer document with topic "retrieval-augmented generation for clinical QA".
   - Outline proposed; edit one section title; save.
   - Click Methods section → answer the 4 predetermined questions.
   - "Suggest sources" returns arXiv + filtered Tavily candidates.
   - Click an arXiv result → PDF auto-fetched, becomes a `Paper` in the project, chunks generated.
   - Click "Draft section" → LaTeX appears in Monaco; at least one `\todo{citation needed}` if any chunk match is weak; QA panel lists it.
   - Edit draft manually → auto-save fires; reload page → edit persists.
   - Add a paywalled paper via upload fallback → drafts cite it.
   - Click Assemble → returns combined `.tex` + `.bib`.
   - Click Export → downloads zip; open in Overleaf and confirm it compiles to a clean PDF (this is the manual MVP success criterion since we deferred in-app preview).
6. Negative paths:
   - Try drafting a section with zero attached sources → agent refuses cleanly with a structured error, not a hallucinated draft.
   - Try exporting with unresolved `\todo` tags → confirm dialog appears with count.

## Recommended build order (TDD)

1. Migration + models + factories (1).
2. `writer_documents.py` service with offline-friendly `create_document` + `apply_outline` + tests.
3. `writer_section.py` agent + low-confidence tagging + tests against `GroundedWriterAgent`'s offline path.
4. Tavily `include_domains` + arXiv `download_pdf` + tests.
5. `suggest_sources` + `attach_source` (auto-fetch + upload fallback) + tests.
6. Router + schemas + auth + credit gating + tests against TestClient.
7. Frontend: API helpers → outline + sections panel → Monaco editor → sources/questions/QA panels → assemble + export.
8. Manual E2E walkthrough above.
9. `JOURNAL.md` entry, conventional commit, PR per repo conventions.
