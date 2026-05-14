# Writer Document Chat — Implementation Plan

## Context

The Writer workspace today supports two ways to change a draft:
1. Generate a full section via `GroundedWriterAgent`.
2. Targeted span/insert edits via `WriterEditorAgent` (selection toolbar + `+` button) → preview/apply patch flow.

Both operate on **one section at a time**. Cross-section instructions ("tighten Related Work", "make the tone more formal throughout", "add a transition between sections 2 and 3", "the abstract and conclusion contradict each other — reconcile them") have no clean expression. Users currently either edit by hand or re-run full section drafts.

This plan adds a **document-level chat box** that takes natural-language change requests and proposes patches across one or more sections. Patches render Cursor/Antigravity-style — red strikethrough for removed text, green for added text, per-hunk Accept / Reject, plus Accept All and Undo at the chat-turn level. Accepted patches go through the existing `WriterDocumentService.save_section_edit()` path, so versioning and the stale-span 409 guard are reused unchanged.

**Decisions captured up front:**
- **Scope:** multi-section from day one.
- **LLM provider:** add Xiaomi MiMo as a configurable provider alongside OpenRouter; refactor `llm.py` to dispatch by provider. Chat defaults to Xiaomi.
- **Prompt caching:** none available on Xiaomi — context is built compact each turn (outline + referenced sections + sliding chat window). The full draft is **not** re-sent every turn.
- **Credit gating:** charge per chat turn (preview). Apply remains free, matching the existing editor.
- **UI placement:** floating draggable panel, default-docked at the bottom of the editor pane.
- **Chat persistence:** server-side session-scoped with TTL (Redis if available, else in-memory). Survives reload within the window; not durable in the DB.

---

## Backend

### LLM provider refactor: `backend/services/llm.py`

Today `OpenRouterStructuredOutputService` is hard-wired to OpenRouter. Introduce a thin provider abstraction so the chat agent can target Xiaomi while the existing pipeline stays on OpenRouter.

```python
class LlmProvider(StrEnum):
    OPENROUTER = "openrouter"
    XIAOMI = "xiaomi"

class StructuredOutputClient(Protocol):
    def is_configured(self) -> bool: ...
    async def generate_json(self, *, system_prompt: str, user_prompt: str,
                            schema: dict, max_tokens: int = 1024,
                            feature: str = "...", temperature: float = 0) -> dict: ...
    async def generate_chat(self, *, messages: list[ChatMessage],
                            max_tokens: int = 2048, temperature: float = 0.2,
                            feature: str) -> ChatCompletion: ...
```

- Keep `OpenRouterStructuredOutputService` (rename internally if needed, keep the public alias). Add `generate_chat` returning `{content, usage}` for free-form chat replies.
- Add `XiaomiStructuredOutputService` in `backend/services/llm_xiaomi.py`. Assume OpenAI-compatible `POST {base}/chat/completions` until docs confirm otherwise. Honor structured output via `response_format={"type":"json_schema",...}` if the provider supports it; otherwise fall back to `json_object` + `_JSON_FENCE_RE` parsing (already in `llm.py:11`).
- Factory `get_structured_client(provider: LlmProvider | None = None)` reads `settings.writer_chat_provider` (default `xiaomi`); other call sites stay on `OPENROUTER` by passing the explicit enum.
- Config: add to `backend/config.py` (and `.env.example`): `XIAOMI_API_BASE`, `XIAOMI_API_KEY`, `XIAOMI_CHAT_MODEL`, `WRITER_CHAT_PROVIDER` (default `xiaomi`), `WRITER_CHAT_MAX_TOKENS` (default `4096`).
- Offline fallback: `is_configured()` returns `False` when the relevant env vars are absent, and the agent returns a deterministic stub patch (same pattern as `writer.py:199`).
- Usage logging: `backend/services/ai_usage.py` already centralizes this — add a `collect_xiaomi_usage` analogous to `collect_openrouter_usage` so admin token dashboards keep working.

### New file: `backend/agents/writer_chat.py` (~400 lines)

The chat agent. One async entry method that takes the conversation, the document state, and returns a structured `ChatTurnResponse` containing an assistant reply plus zero-or-more proposed patches across sections.

```python
@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str
    proposed_patches: list[EditPatch]  # empty for user messages

@dataclass(frozen=True)
class SectionPatch:
    section_id: str
    section_title: str
    span: TextSpan
    original_text: str       # for stale-span guard (matches EditPatch contract)
    new_text: str
    rationale: str

@dataclass(frozen=True)
class ChatTurnResponse:
    reply: str
    patches: list[SectionPatch]

class WriterChatAgent:
    def __init__(self, *, client: StructuredOutputClient | None = None) -> None: ...

    async def respond(
        self,
        *,
        document_outline: list[SectionRef],         # id, title, char count
        included_sections: list[SectionContent],    # id, title, draft_latex
        known_citation_keys: set[str],
        chat_history: list[ChatMessage],            # last N turns, see context budget
        user_message: str,
    ) -> ChatTurnResponse: ...
```

**Context strategy (no caching available):**

1. **Outline always sent:** `[{id, title, length, position}]` for every section. Cheap, lets the model name targets.
2. **Section content sent selectively.** Two heuristics combined:
   - **Mentioned-by-name:** any section whose title appears in the new user message OR in the latest assistant reply.
   - **Recent edits:** sections touched by the user (last 3) — read from the in-memory state passed by the service.
   - Cap: at most 4 sections by content per turn. If more are needed, the assistant reply asks the user to narrow scope ("Which sections specifically?") rather than silently truncating.
3. **Chat history:** sliding window — last 6 turns, prior turns collapsed to one-line summaries the agent emits in each response (`summary_for_history` field, dropped from UI).
4. **Patch contract:** the agent must return `original_text` for each patch — this is the exact substring it expects to find at `[span.start, span.end)`. The service re-verifies before returning to the client; on mismatch, it retries one regeneration with the corrected context.

**JSON schema returned by the LLM call** (strict where supported):

```json
{
  "reply": "string",
  "summary_for_history": "string (<=140 chars)",
  "patches": [
    {
      "section_id": "string",
      "span": {"start": 0, "end": 0},
      "original_text": "string",
      "new_text": "string",
      "rationale": "string"
    }
  ]
}
```

**Citation guard:** reuse the `\cite{}` tokenizer planned for `writer_editor.py` (already in `backend/agents/writer_editor.py`). Reject patches that introduce unknown citation keys; retry once with stricter prompt; on second failure, drop the offending patch from the response and surface a non-fatal warning in `reply`.

**Offline fallback:** when no provider is configured, return `ChatTurnResponse(reply="Chat is offline; configure XIAOMI_API_KEY to enable.", patches=[])`. Keeps tests hermetic.

### New file: `backend/services/writer_chat.py` (~250 lines)

Glue between router, agent, and session store.

```python
class WriterChatService:
    def __init__(self, *, agent: WriterChatAgent, session_store: ChatSessionStore,
                 writer_document_service: WriterDocumentService) -> None: ...

    async def post_message(
        self, *, session: AsyncSession, document_id: str, user_id: str,
        chat_id: str | None, user_message: str,
    ) -> ChatTurnRead:
        # 1. Resolve/create chat session in session_store (returns chat_id)
        # 2. Load document outline + currently-edited section(s) from DB
        # 3. Decide which sections to include (heuristics above)
        # 4. agent.respond(...) → patches with original_text guards
        # 5. Re-verify each patch's original_text against current draft; drop stale
        # 6. Persist user + assistant turn in session_store with TTL
        # 7. Return ChatTurnRead

    async def get_chat(self, *, document_id: str, user_id: str, chat_id: str) -> ChatRead: ...

    async def accept_patch(
        self, *, session: AsyncSession, document_id: str, user_id: str,
        chat_id: str, message_id: str, patch_index: int,
    ) -> WriterSectionRead:
        # Fetch patch from session_store → delegate to WriterDocumentService.save_section_edit()
        # Mark patch as applied in session_store (for UI strikethrough on accepted items)

    async def reject_patch(...): ...   # marks patch rejected; no DB write
    async def undo_patch(...):
        # Restore from WriterSectionVersion snapshot created by save_section_edit
```

**Session store: `backend/services/chat_session_store.py` (~150 lines)**

Interface:

```python
class ChatSessionStore(Protocol):
    async def get(self, chat_id: str) -> ChatSession | None: ...
    async def put(self, chat_id: str, session: ChatSession, ttl_seconds: int) -> None: ...
    async def list_for_document(self, document_id: str, user_id: str) -> list[ChatSessionMeta]: ...
    async def delete(self, chat_id: str) -> None: ...
```

Two implementations behind the same interface:

- `InMemoryChatSessionStore` — module-level dict + asyncio lock + TTL eviction on access. Always-on, used by tests and dev.
- `RedisChatSessionStore` — uses the existing Redis client if `REDIS_URL` is set. Key shape: `writer-chat:{chat_id}` → JSON-encoded `ChatSession`. TTL refreshed on each turn.

Factory `get_chat_session_store()` returns Redis when configured, else in-memory. Default TTL: 24 hours, sliding (refreshed each turn).

`ChatSession` schema (in-memory dataclass; JSON-serialized for Redis):

```python
@dataclass
class ChatSession:
    id: str
    document_id: str
    user_id: str
    messages: list[ChatMessageRecord]   # role, content, message_id, patches (each w/ applied/rejected flag), created_at
    last_active_at: datetime
    history_summary: str                 # rolling summary of dropped-history turns
```

### Router: `backend/api/routers/writer_documents.py` additions

```
POST   /writer/documents/{doc_id}/chat                            -> ChatRead       # create chat session
GET    /writer/documents/{doc_id}/chats                           -> list[ChatMeta] # list active sessions (rare; mainly for reload)
GET    /writer/documents/{doc_id}/chat/{chat_id}                  -> ChatRead       # rehydrate on reload
POST   /writer/documents/{doc_id}/chat/{chat_id}/message          -> ChatTurnRead   # send user turn → assistant reply + patches
POST   /writer/documents/{doc_id}/chat/{chat_id}/message/{msg_id}/patch/{idx}/accept  -> WriterSectionRead
POST   /writer/documents/{doc_id}/chat/{chat_id}/message/{msg_id}/patch/{idx}/reject  -> {ok: true}
POST   /writer/documents/{doc_id}/chat/{chat_id}/message/{msg_id}/patch/{idx}/undo    -> WriterSectionRead
```

**Credit gating** (via `backend/api/dependencies.py` `require_credits`):

| Endpoint | Feature tag | Credits |
|---|---|---|
| `POST .../message` | `writer_chat_turn` | `WRITER_CHAT_TURN_CREDITS = 3` |
| `POST .../accept`, `.../reject`, `.../undo` | n/a | 0 (free) |
| `POST /chat`, `GET /chat/{id}` | n/a | 0 (free) |

Admin bypass already handled (`dependencies.py:185`).

**Acceptance flow re-uses the existing apply path:**
- Each `accept` builds an `EditPatch` (`backend/agents/writer_editor.py`) from the stored `SectionPatch`.
- Delegates to `WriterDocumentService.save_section_edit()` which already snapshots into `WriterSectionVersion`, so undo just restores from the most recent matching version.
- Stale span returns 409 → frontend strikes the patch through with a "draft changed, ask again" note.

### Schemas: `backend/api/schemas/writer_documents.py` additions

```python
class ChatSectionPatchSchema(BaseModel):
    section_id: str
    section_title: str
    span: TextSpanSchema
    original_text: str
    new_text: str
    rationale: str
    status: Literal["pending", "applied", "rejected", "stale"]

class ChatMessageSchema(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    patches: list[ChatSectionPatchSchema] = []
    created_at: datetime

class ChatRead(BaseModel):
    id: str
    document_id: str
    messages: list[ChatMessageSchema]
    last_active_at: datetime

class ChatTurnRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

class ChatTurnRead(BaseModel):
    chat_id: str
    user_message: ChatMessageSchema
    assistant_message: ChatMessageSchema
```

### DB

**No schema changes.** Reuses `WriterSection.draft_latex` and `WriterSectionVersion`. Chat state lives entirely in `ChatSessionStore`.

### Tests: `tests/test_writer_chat.py` (new, ~12 cases)

All hermetic (stub provider, in-memory store):

1. Create chat session → empty `messages` list, valid `chat_id`.
2. Post message with offline provider → assistant reply is the offline stub, `patches=[]`, credits not debited (offline gate inside `require_credits`).
3. Post message with stubbed provider returning a single-section patch → patch's `original_text` matches current draft, `status="pending"`.
4. Post message with stubbed multi-section response → patches across two sections returned in order.
5. Accept patch → `WriterSection.draft_latex` updated, `WriterSectionVersion` snapshot created, patch status becomes `applied`.
6. Reject patch → no DB write, status becomes `rejected`.
7. Undo patch → previous `WriterSectionVersion` restored, draft reverted; only the latest version, no chain undo.
8. Stale-span guard: simulate user editing section between message and accept → accept returns 409, patch marked `stale`.
9. Citation guard: stubbed agent returns patch with unknown `\cite{xyz}` → patch dropped from response, `reply` mentions the dropped change.
10. Context budget: chat with >6 turns → only last 6 sent to agent (assert via spy on `agent.respond` kwargs); older turns appear in `history_summary`.
11. Credit gating: non-admin user at 0 credits → 402 on `/message`; admin bypass → 200.
12. Session TTL: in-memory store evicts after TTL; subsequent `GET /chat/{id}` → 404.

Plus router-level tests in `tests/test_writer_documents.py`: auth required, 403 for cross-user access, 404 for nonexistent doc/chat.

---

## Frontend

### New component: `frontend/components/WriterChatPanel.tsx` (~550 lines)

The floating chat panel. Owns position, drag, message list, input, and per-patch diff UI.

**Behavior:**

- **Default position:** docked to the bottom of the editor column, full editor-column width minus 32px margins. State: `{ mode: "docked-bottom" | "floating", x, y, width, height }`. Persisted to `localStorage` keyed by `writer-chat-panel:{userId}`.
- **Drag handle:** a thin header bar with the title and close/dock buttons. Dragging it switches `mode` to `floating`. A "Dock to bottom" button restores the default.
- **Resize:** drag the top edge to grow the panel upward when docked; corner handle when floating.
- **Collapse to chip:** when closed, leaves a small `💬 Chat` pill in the bottom-right corner, click to reopen at last position.

**Message list:**

- Each message bubble: user (right-aligned, primary tint) or assistant (left-aligned, surface-container).
- Assistant messages with patches render the reply text, then a stack of **PatchCard** components — one per patch.

**PatchCard (Cursor/Antigravity style):**

```
┌────────────────────────────────────────────────┐
│ ● Related Work · line 4–7                      │  ← header: section title + line range
│                                                │
│ - Object tracking in video streams is a foun-  │  ← red strikethrough block
│ - dational task in computer vision, with...    │
│ + Object tracking is foundational in computer  │  ← green highlight block
│ + vision, with applications spanning sports... │
│                                                │
│ Why: tightened phrasing while keeping cites.   │  ← rationale
│                                                │
│ [✓ Accept]  [✕ Reject]                         │
└────────────────────────────────────────────────┘
```

- Red block: `bg-rose-50 dark:bg-rose-950/30 text-rose-900 dark:text-rose-100 line-through` with a `-` gutter character.
- Green block: `bg-emerald-50 dark:bg-emerald-950/30 text-emerald-900 dark:text-emerald-100` with a `+` gutter.
- Long blocks are word-wrapped, not horizontally scrolled (this is prose, not code).
- Section title is clickable → scrolls Monaco to the patch's span and briefly flashes the affected range.
- After Accept: card stays in the message thread, but compresses to a one-line "Accepted" stripe with an `Undo` button (active for the duration of the chat session — undo replays via the version snapshot).
- After Reject: card compresses to "Rejected" stripe, no undo.
- Stale state (server returns 409 on accept): card flips to a `Stale — draft changed` stripe, no actions; the user is invited to ask again.

**Bulk actions per assistant message:**

- If a message has 2+ pending patches: `Accept all` and `Reject all` buttons at the bottom of the message. `Accept all` calls accept endpoints sequentially; if any returns 409, that one becomes `stale` and the others still apply.

**Input area:**

- Multiline textarea, auto-grows to 6 lines max. Enter to send, Shift+Enter for newline.
- "Send" button. Disabled while a turn is in flight. Spinner inside the bubble for the in-flight assistant message.
- Shows credit cost preview ("3 credits per turn") under the textarea, matching the existing editor preview pattern.

**State (React):**

```ts
const [chatId, setChatId] = useState<string | null>(null);
const [messages, setMessages] = useState<ChatMessage[]>([]);
const [draft, setDraft] = useState("");
const [isSending, setIsSending] = useState(false);
const [panelState, setPanelState] = useState<PanelState>(loadPanelState);
const [pendingAcceptByPatch, setPendingAcceptByPatch] = useState<Set<string>>(new Set());
```

**Rehydration on mount:** if `localStorage` has a `chatId` for this document and `GET /chat/{id}` returns 200, restore the thread. On 404 (TTL expired), start fresh.

### Touch: `frontend/components/WriterWorkspace.tsx`

- Render `<WriterChatPanel documentId={...} sections={sections} onScrollToSection={...} onAfterPatchAccepted={refreshDocument} />` as a sibling of the editor column, positioned absolutely within a `relative` parent.
- Pass `onScrollToSection(sectionId, span)` so PatchCard's "click section title" can drive Monaco. Reuse the existing `monacoEditorRef`.
- After any patch accept/undo, call the existing `refreshDocument` (already used by the editor overlay accept path) so Monaco re-syncs.
- Suspend auto-save while an accept is in flight, same gate the editor overlay uses.

### Touch: `frontend/lib/api.ts`

Six new client functions near the existing `previewWriterEdit` / `applyWriterEdit`:

```ts
export async function createWriterChat(documentId, token): Promise<ChatRead>;
export async function getWriterChat(documentId, chatId, token): Promise<ChatRead>;
export async function sendWriterChatMessage(documentId, chatId, content, token): Promise<ChatTurnRead>;
export async function acceptWriterChatPatch(documentId, chatId, messageId, patchIndex, token): Promise<WriterSectionRead>;
export async function rejectWriterChatPatch(documentId, chatId, messageId, patchIndex, token): Promise<{ok: true}>;
export async function undoWriterChatPatch(documentId, chatId, messageId, patchIndex, token): Promise<WriterSectionRead>;
```

All reuse `ApiError`, `Authorization: Bearer`, and `isInsufficientCreditsError` (so 402 surfaces as the existing credits-low banner).

### Styling

Tailwind, reusing existing tokens (`surface`, `surface-container`, `on-surface`, `primary`, `outline/20`). Match the project's existing modal/card patterns from `WriterSourcesPanel` and `AssembleModal`. New tokens are limited to the diff colors above — rose/emerald, both light and dark.

Floating panel container: `fixed rounded-2xl border border-outline/20 bg-surface shadow-2xl flex flex-col` with computed `inset` based on `panelState`.

### Frontend tests: `tests/test_frontend_writer_static.py` (extend)

Static checks (matching existing style):

- `WriterChatPanel` is imported and rendered by `WriterWorkspace`.
- Six new API client functions are exported from `lib/api.ts`.
- Diff colors (`bg-rose-50`, `bg-emerald-50`) appear in `WriterChatPanel`.
- `localStorage.getItem('writer-chat-panel:` appears in `WriterChatPanel` (persistence wired).

Full interactive coverage deferred to a `frontend-qa-tester` Playwright pass after the slice lands.

---

## Phased delivery

Two PRs, each shippable on its own.

**PR 1 — provider refactor + single-section chat MVP**
- LLM provider abstraction in `llm.py`; `XiaomiStructuredOutputService` in `llm_xiaomi.py`; config keys.
- `WriterChatAgent`, `WriterChatService`, in-memory `ChatSessionStore` (Redis impl deferred).
- All router endpoints, but the agent only proposes patches in the user's currently-open section. Multi-section context plumbing is wired; the system prompt forbids cross-section patches for now to keep the surface small.
- `WriterChatPanel` rendering chat thread + single-section PatchCards + Accept/Reject/Undo + docked-bottom default. No floating/drag yet.
- Tests: hermetic agent stub, accept/reject/undo, credit gating, stale guard.

**PR 2 — full multi-section + floating panel + Redis**
- Remove the single-section restriction in the chat agent's system prompt.
- Add multi-section heuristics (mentioned-by-name + recent-edits) and the 4-section cap.
- `RedisChatSessionStore` + factory; `REDIS_URL` config.
- Floating/drag/resize panel mode + `localStorage` persistence.
- Tests: multi-section response, context cap, Redis path (gated by `REDIS_URL`).

After PR 2: `frontend-qa-tester` Playwright pass; `security-reviewer` + `code-reviewer` on the diff.

---

## Critical files

**Modify**
- `backend/services/llm.py` — provider abstraction, `generate_chat` method.
- `backend/config.py`, `.env.example` — Xiaomi + chat config keys.
- `backend/services/ai_usage.py` — Xiaomi usage collector.
- `backend/api/routers/writer_documents.py` — chat endpoints + credit constants.
- `backend/api/schemas/writer_documents.py` — chat schemas.
- `frontend/components/WriterWorkspace.tsx` — mount panel, wire scroll callback.
- `frontend/lib/api.ts` — six client functions + types.
- `tests/test_writer_documents.py` — auth/permission tests for new endpoints.
- `tests/test_frontend_writer_static.py` — static checks.
- `JOURNAL.md`, `AI_WORKLOG.md`, `docs/features/writer_outputs.md`, `docs/feature-map.md` — per repo convention.

**Create**
- `backend/services/llm_xiaomi.py`
- `backend/agents/writer_chat.py`
- `backend/services/writer_chat.py`
- `backend/services/chat_session_store.py`
- `frontend/components/WriterChatPanel.tsx`
- `tests/test_writer_chat.py`

---

## Reused utilities (do not re-implement)

- Apply / versioning: `WriterDocumentService.save_section_edit()` (`backend/services/writer_documents.py:591`) — handles `WriterSectionVersion` snapshots automatically.
- Citation guard: existing `\cite{}` tokenization logic in `backend/agents/writer_editor.py`.
- Credit gating: `backend/api/dependencies.py` `require_credits` (admin bypass included).
- DB models: `WriterSection`, `WriterSectionVersion` — no schema changes.
- Stale-span 409 pattern: same contract as `WriterEditorService.apply` (`backend/services/writer_editor.py:96`).
- Frontend error helpers: `lib/api.ts` `ApiError`, `isInsufficientCreditsError`.
- Existing modal/popover styling tokens: `AssembleModal`, `WriterSourcesPanel`.
- Tavily search (if web search added later): `backend/services/tavily.py`.

---

## Open questions for implementation

1. **Xiaomi API surface.** The docs page didn't render via WebFetch. Before PR 1 lands, confirm:
   - Is `POST {base}/chat/completions` the right endpoint? Auth header `Authorization: Bearer {key}` or proprietary?
   - Does it support `response_format={"type":"json_schema",...}`? If not, fall back to `json_object` + fence-strip (already in `llm.py:11`).
   - Streaming SSE format — needed only if PR 2 adds streamed replies (not in this plan).
   - Model name for `XIAOMI_CHAT_MODEL` and max context.
2. **History summarization.** The agent returns `summary_for_history` per turn — fine for short threads, but for very long sessions we may want a separate summarization pass. Defer to a follow-up if real usage shows long-session quality drift.
3. **Web search integration.** Out of scope for this plan; Tavily is already plumbed via the editor agent, so adding a `🌐` toggle to the chat input later is a small addition.
4. **Streaming.** Not in MVP. The chat-turn endpoint returns the full response. Add SSE in a follow-up if turn latency becomes painful.

---

## Verification

After each PR:

```bash
uv run ruff check .
uv run mypy backend/
uv run pytest tests/ -x
cd frontend && npm run build
```

**PR 1 manual checks**
1. `uv run uvicorn backend.main:app --reload`, `cd frontend && npm run dev`.
2. Open a writer document; chat panel appears docked at bottom.
3. Type "tighten the second paragraph" with that section open → assistant reply + one PatchCard with red/green diff.
4. Click section title in PatchCard → Monaco scrolls and flashes the span.
5. Accept → draft updates, version snapshot created (verify via the existing version-history endpoint).
6. Undo → draft reverts to prior snapshot.
7. Reject → no DB change.
8. Edit Monaco between turn and accept → accept returns 409, card flips to "Stale".
9. Run with `XIAOMI_API_KEY` unset → assistant returns the offline stub; no credit debit; UI shows "Chat is offline".
10. Non-admin user at zero balance → 402 surfaces as the existing credits-low banner.

**PR 2 manual checks**
11. Ask "make the abstract and conclusion consistent" → two PatchCards in one assistant message, one per section; Accept All applies both; Undo unwinds the most recent.
12. Drag the panel header → switches to floating; resize from corner; reload page → position restored from `localStorage`.
13. With `REDIS_URL` set → chat survives backend restart within TTL; without `REDIS_URL` → uses in-memory store, lost on restart.
14. Send 8 turns in one chat → spy assertion or visible behavior confirms only last 6 turns are sent to the LLM; `history_summary` covers earlier turns.

Final pass: `frontend-qa-tester` Playwright on all flows; `security-reviewer` and `code-reviewer` on the diff before each merge.
