# Weekly Journal & Change Log

Ghi lại hành trình xây dựng sản phẩm mỗi tuần — những gì đã làm, học được gì, AI giúp như thế nào.
Ngoài phần tổng kết tuần, file này cũng được dùng để log các thay đổi trong repo theo từng phiên làm việc.

> **Cập nhật mỗi cuối tuần** (trước khi tạo PR). Không cần dài, chỉ cần thật.

---

## Template

```markdown
## Tuần N — DD/MM/YYYY

### Đã làm
-

### Khó nhất tuần này
-

### AI tool đã dùng
| Tool | Dùng để làm gì | Kết quả |
|---|---|---|
| Claude Code | | |

### Học được
-

### Nếu làm lại, sẽ làm khác
-

### Kế hoạch tuần tới
-
```

## Change Log Template

```markdown
### YYYY-MM-DD HH:MM
- **done:**
  - What was completed in this implementation step.
- **doing:**
  - What is currently in progress or expected next.
- **blocked:**
  - Any blockers, risks, or `None`.
```

---

### 2026-05-13T12:04:26+07:00
- **Request:** Make sidebar project clicks leave the Writer page and open the independent project chat workspace.
- **Files changed:** `frontend/components/Sidebar.tsx`, `frontend/README.md`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`.
- **Current status:** Added project-row routing to `/chat?project=...` from non-chat routes while preserving the existing chat-page project hydration flow, documented the split, and added a focused frontend static regression. Verification passed for the full Writer static test file and frontend TypeScript.

### 2026-05-12T21:50:14+07:00
- **Request:** Replace raw Writer attached-source UUIDs with human-readable source names in the sources panel.
- **Files changed:** `backend/api/routers/writer_documents.py`, `backend/api/schemas/writer_documents.py`, `frontend/lib/api.ts`, `frontend/components/WriterSourcesPanel.tsx`, `tests/test_writer_documents.py`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`.
- **Current status:** Added ordered `source_papers` metadata to writer document responses and updated the Writer sources panel to render attached source titles, author/year/provider context, and UUID tooltips only as fallback detail. Verification passed for focused writer pytest, targeted Ruff, and frontend TypeScript.

### 2026-05-12T11:24:45+07:00
- **Request:** Implement the frontend portion of progressive related-paper discovery for the first standard chat message.
- **Files changed:** `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `frontend/components/ContextPanel.tsx`, `tests/test_frontend_pipeline_static.py`, `JOURNAL.md`.
- **Current status:** Added a typed `streamProjectPipeline` SSE helper, changed first-message standard chat to create the project, consume `/projects/{id}/run/stream`, populate papers on the `papers` event, patch individual papers on `summary`, reconcile on `done`, then start the existing project chat stream with `paperIds: []` while keeping the composer busy. Related-paper cards now show a compact `Summary pending` state for ranked unsummarized papers while preserving summary toggles and summary-error rendering. Verification passed for `uv run pytest tests/test_frontend_pipeline_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`; the broader Deep Search static suite still has its existing unrelated `deep_research_max` assertion mismatch.

### 2026-05-12T11:48:21+07:00
- **Request:** Integrate the backend and frontend progressive related-paper pipeline changes from subagents and verify the full handoff plan.
- **Files changed:** `backend/agents/pipeline.py`, `backend/agents/reader.py`, `backend/api/routers/projects.py`, `backend/api/schemas/projects.py`, `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `frontend/components/ContextPanel.tsx`, `tests/test_projects.py`, `tests/test_quota_enforcement.py`, `tests/test_searcher_reader.py`, `tests/test_frontend_pipeline_static.py`, `README.md`, `frontend/README.md`, `docs/feature-map.md`, `JOURNAL.md`.
- **Current status:** Aligned the streaming `papers` event contract across backend and frontend, confirmed ranked papers are emitted before summaries, kept `/projects/{id}/run` compatible, preserved stream credit debit/refund behavior, and documented the first-message progressive pipeline flow. Verification passed for focused backend/frontend pytest, targeted Ruff, backend mypy, and frontend TypeScript. `tests/test_frontend_deep_search_static.py` still has its pre-existing static assertion mismatch that expects only `if (chatMode === "deep_search")` while the code supports `deep_research_max` too.

### 2026-05-12T11:57:43+07:00
- **Request:** Remove the "Summary pending" badge from related-paper cards because it overflowed the context panel.
- **Files changed:** `frontend/components/ContextPanel.tsx`, `tests/test_frontend_pipeline_static.py`, `frontend/README.md`, `JOURNAL.md`.
- **Current status:** Removed the pending-summary pill so ranked papers without summaries render as normal paper cards until the summary toggle appears. Updated the frontend static regression and README wording. Verification passed for `uv run pytest tests/test_frontend_pipeline_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

### 2026-05-10T21:33:54+07:00
- **Request:** Push the changed and new files from `feature/writer-workspace-mvp`, create PRs, and merge them into `main` following `PULL_REQUEST.md`.
- **Files changed:** All remaining changed/new files on `feature/writer-workspace-mvp`; committed one file per commit and grouped PRs into two-file batches.
- **Current status:** Focused pytest, frontend TypeScript, and targeted Ruff checks passed. Batches #311 through #334 were pushed, opened, and merged into `main`; final batch includes this journal entry and `tests/test_writer_section_agent.py` while keeping the source branch.

### 2026-05-10T17:49:39+07:00
- **Request:** Add a Beta tag to the Writer button.
- **Files changed:** `frontend/components/Sidebar.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`
- **Current status:** Added a compact `Beta` badge beside the expanded sidebar Writer nav item and updated the collapsed Writer icon aria/title text to "Writer beta". Verified with `python3 -m pytest tests/test_frontend_writer_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

### 2026-05-10T17:40:48+07:00
- **Request:** Make the Writer "Using the top 7 source papers..." notice appear after a 2-second delay.
- **Files changed:** `frontend/components/WriterQuestionsPanel.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`
- **Current status:** Added delayed warning rendering in the Writer questions panel and clear pending timers on section changes or new drafts. Verified with `python3 -m pytest tests/test_frontend_writer_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

### 2026-05-10T17:39:01+07:00
- **Request:** Add a clickable logo in the Writer document workspace top-left that returns to the chat workspace.
- **Files changed:** `frontend/components/WriterWorkspace.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`
- **Current status:** Added the Confluex mark as the first header control in the Writer workspace, linking to `/chat?project=...` for the document project. Verified with `python3 -m pytest tests/test_frontend_writer_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

### 2026-05-10T17:34:37+07:00
- **Request:** Add a Writer page button to return to the chat workspace.
- **Files changed:** `frontend/app/writer/page.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`
- **Current status:** Added a secondary "Back to Chat" header action that preserves the active project with `/chat?project=...` when available. Verified with `python3 -m pytest tests/test_frontend_writer_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

### 2026-05-10T16:45:18+07:00
- **Request:** Stop `mimo-v2.5-pro` requests from using the OpenRouter base URL/provider route; use Xiaomi MiMo URL instead.
- **Files changed:** `backend/config.py`, `backend/services/llm.py`, `backend/services/project_conversations.py`, `backend/services/paper_conversations.py`, `backend/services/document_extraction.py`, `backend/services/deep_search.py`, `tests/test_app_config.py`, `JOURNAL.md`, `AI_WORKLOG.md`
- **Current status:** Added model-aware LLM routing so `mimo-*` and `xiaomi/*` model ids resolve to `XIAOMI_MIMO_BASE_URL` and `XIAOMI_MIMO_API_KEY` only, never `OPENROUTER_BASE_URL`/`OPENROUTER_API_KEY`. Project chat, paper chat, structured output, document extraction, and Deep Search now use that routing. Focused checks pass: `python3 -m pytest tests/test_app_config.py tests/test_llm_embeddings.py tests/test_project_conversations.py tests/test_paper_conversations.py tests/test_document_extraction.py -q`, `python3 -m pytest tests/test_deep_search.py::test_deep_search_openrouter_usage_events_are_flushed tests/test_deep_search.py::test_deep_search_structured_output_truncation_falls_back_without_failing -q`, targeted `ruff`, and targeted `mypy`. The broader Deep Search file still has existing unrelated failures around the slow-planning timing test and Tavily `advanced` vs `basic` expectation.

### 2026-05-10T15:49:17+07:00
- **Request:** Fix chat answers that show raw LaTeX delimiters like `$$...$$` and `$T_k$` instead of rendered math.
- **Files changed:** `frontend/components/ChatWorkspace.tsx`, `frontend/app/layout.tsx`, `frontend/package.json`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`
- **Current status:** Added KaTeX rendering for display and inline math in chat Markdown, imported KaTeX CSS through the app layout, and added a static regression. Verified with `source ~/miniconda3/bin/activate agents && uv run pytest tests/test_frontend_deep_search_static.py::test_frontend_chat_markdown_renders_latex_math -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`. The full frontend static file still has an unrelated existing Deep Search mode assertion mismatch.

### 2026-05-10T15:45:31+07:00
- **Request:** Identify the project chat live-stream timeout that causes fallback answers and extend it.
- **Files changed:** `backend/config.py`, `backend/services/project_conversations.py`, `tests/test_project_conversations.py`, `.env.example`, `README.md`, `docs/features/paper_conversations.md`, `docs/feature-map.md`, `JOURNAL.md`, `AI_WORKLOG.md`
- **Current status:** The first-token wait was using `EXTERNAL_API_TIMEOUT_SECONDS` (20 seconds). Added `PROJECT_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` with a 60-second default and wired project chat streaming to use it before falling back. Verified with `source ~/miniconda3/bin/activate agents && uv run pytest tests/test_project_conversations.py -q` and targeted `ruff check`.

### 2026-05-10T14:38:32+07:00
- **Request:** Fix Writer UI after clicking Writer: the page showed "No project selected" while also showing draft loading skeletons, and `/writer?project=...` did not reliably restore the active project.
- **Files changed:** `frontend/app/writer/page.tsx`, `frontend/components/ChatProvider.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`
- **Current status:** Writer now clears document loading state when no project is active, only shows skeletons while a project is actually loading, restores the route `project` query parameter before falling back to localStorage, and avoids clearing saved active-project state before restore. Verified with `python3 -m pytest tests/test_frontend_writer_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

### 2026-05-10T14:38:00+07:00
- **Request:** Investigate why uploading `/Users/hungcucu/Desktop/2504.20670v1.pdf` produced a garbled paper answer.
- **Files changed:** `backend/services/document_extraction.py`, `backend/services/reference_files.py`, `backend/services/paper_conversations.py`, `backend/services/project_conversations.py`, `tests/test_document_extraction.py`, `tests/test_reference_files.py`, `tests/test_paper_conversations.py`, `tests/test_project_conversations.py`, `docs/features/upload_reference_file.md`, `README.md`, `JOURNAL.md`, `AI_WORKLOG.md`
- **Current status:** Verified the supplied PDF extracts cleanly through the updated upload path (9 pages, 9 text blocks, FBRT-YOLO title, coherent abstract, authors `Yao Xiao`, `Tingfa Xu`, `Yu Xin`, `Jianan Li`). Uploaded/local PDFs now prefer local PyMuPDF extraction before live parser fallback, uploaded-paper metadata infers simple header author lines, and chat prompts use metadata directly for bibliographic questions. Focused checks pass: `source ~/miniconda3/bin/activate agents && uv run pytest tests/test_reference_files.py tests/test_document_extraction.py tests/test_paper_conversations.py tests/test_project_conversations.py -q`; targeted `ruff check` passes.

## 2026-05-10T10:00:00+07:00
- **Request:** Fix output token truncation in paper Q&A — long table responses were cut off mid-row.
- **Files changed:** `backend/services/paper_conversations.py`
- **Current status:** Raised `DEFAULT_MAX_ANSWER_TOKENS` from 800 → 2048. Both paper conversations and project conversations (which import the same constant) benefit.

## 2026-05-09T00:00:00+07:00
- **Request:** Implement Deep Research Max adaptive loop mode (new third chat mode with up to 4 adaptive search iterations, LLM gap-analysis decider, `ResearchState` accumulator, `deciding` thinking phase, mode-specific 5× credit cost). Post-commit fixes: raise report token cap from 1 800 to 4 000 to stop mid-table truncation; raise `deep_search_max_results_per_query` 5 → 10 and `deep_search_max_web_searches` 5 → 8; switch Tavily from `basic` to `advanced` search depth so the full result set is returned.
- **Files changed:** `backend/services/deep_search.py`, `backend/db/models.py`, `backend/db/migrations/versions/20260509_01_deep_search_mode.py`, `backend/api/schemas/projects.py`, `backend/api/routers/pipeline.py`, `backend/api/routers/projects.py`, `backend/config.py`, `backend/services/tavily.py`, `backend/agents/reader.py`, `backend/agents/searcher.py`, `backend/services/llm.py`, `backend/services/document_extraction.py`, `.env.example`, `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `frontend/lib/api.ts`, `tests/test_deep_search.py`, `plans/in-progress/deep-research-max-mode.md`, `JOURNAL.md`, `AI_WORKLOG.md`, `CLAUDE.md`, `.codex/AGENTS.md`
- **Current status:** Feature committed as `6d617b9` on `feature/deep-research-max-mode`. Post-commit config/service tweaks (token cap, result counts, search depth) are uncommitted. 22 targeted Deep Search tests pass (1 pre-existing timing test excluded). Standard mode path is unchanged.

### 2026-05-08T15:20:11+07:00
- **Request:** SePay payments work (money received, transactions logged in dashboard) but the user's credit balance never updates — find the root cause first, then fix.
- **Files changed:** `backend/api/schemas/payments.py`, `tests/test_sepay_webhook.py`, `AI_WORKLOG.md`, `AGENTS.md`, `.codex/AGENTS.md`, `JOURNAL.md`
- **Current status:** Root cause was that SePay sends `id` as a JSON number, but `SepayWebhookPayload.transaction_id: str` rejected it under pydantic v2's strict-string default — every real delivery failed with HTTP 422 before reaching settlement. Two upstream SePay-config issues also blocked delivery initially (virtual-account filter scoped to a sub-account the QR didn't target, and the "skip if no payment code" toggle requiring SePay-side code-prefix registration); the user relaxed those during diagnosis. Fix adds `coerce_numbers_to_str=True` to the webhook schema's `model_config` and a regression test that posts SePay's exact production payload shape (integer `id`, `subAccount`, BIDV gateway). Verified with `.venv/bin/pytest tests/test_sepay_webhook.py -x -q` (5 passed). Awaiting redeploy to Render and a re-fire of the failed delivery from SePay's WebHooks Log.

### 2026-05-07T14:11:33+07:00
- **Request:** Apply `PULL_REQUEST.md` workflow to the modified admin usage files.
- **Files changed:** `frontend/app/admin/usage/components.tsx`, `frontend/app/admin/usage/users/page.tsx`, `JOURNAL.md`
- **Current status:** Committed the two admin usage files separately, pushed `hung`, opened and merged PR #263 into `main` while keeping `hung`. Verified the frontend TypeScript check with a temporary tsbuildinfo file. Added this repository log entry as a follow-up per agent rules; local detail reference updated in ignored `AI_WORKLOG.md`.

### 2026-05-06T12:58:00+07:00
- **Request:** Help me improve the diagrams that will be rendered by mermaid in docs/backend-diagram.md and check the rendered markdown visually.
- **Files changed:** `docs/backend-diagram.md`
- **Current status:** Implemented global stylistic changes to the mermaid flowcharts by defining and applying semantic classDefs. Addressed layout clutter by splitting the monolithic API Routes diagram into two independent flowcharts (Auth/Admin and Projects/Pipeline), converting layout to LR (Left-to-Right), and deduplicating shared dependency nodes.

###  2026-05-06T11:47:29+07:00
- **Request:** Review and update stale documentations for this project to match the current implementation (citation graph import).
- **Files changed:** `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md`, `docs/user-journey.md`
- **Current status:** Updated the backend architecture diagram to include the `POST /projects/{project_id}/papers/import-citation` endpoint. Added a test case for importing citation graph papers in the Postman API guide. Updated the user journey to reflect the new feature in the frontend where users can view and import papers from the citation graph.

### 2026-05-06T08:46:19+07:00
- **Request:** Fix UI bug where the date range popover is partially hidden by the left sidebar in the admin usage dashboard.
- **Files changed:** `frontend/app/admin/usage/components.tsx`
- **Current status:** Investigated with the browser agent, reproducing the clipped popover bug. The underlying cause was the popover's `right-0` absolute positioning making it overflow the left edge of the `overflow-y-auto` container `div.flex-1`, causing it to be visually clipped right where the sidebar is located. Fixed by changing `right-0` to `left-0` to keep the popover bounded correctly on the right within its scrollable container.

### 2026-05-05 23:45
- **done:**
  - Updated CI workflow to use a dedicated test database name and added `TEST_DATABASE_URL` for reliable Postgres testing in GitHub Actions.
  - Verified backend integration and static frontend regressions for the new citation graph paper import feature.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `.github/workflows/ci.yml`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Pushing final changes to the remote branch.
- **blocked:**
  - None.

### 2026-05-05 22:17
- **done:**
  - Updated `AGENTS.md` with current Deep Search citation behavior and ownership notes for future agents.
  - Documented that sentence-level source buttons use named Markdown links, source notes, a body-level preview portal, and clickable multi-source preview rows.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `AGENTS.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Session handoff guidance is up to date.
- **blocked:**
  - None.

### 2026-05-05 22:00
- **done:**
  - Made Deep Search citation previews stay open during cursor handoff from the chip to the preview.
  - Enabled clicking individual source rows inside multi-source citation previews.
  - Added static regression coverage for the interactive portal preview behavior.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `frontend/components/ChatWorkspace.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Frontend TypeScript, targeted frontend static tests, and touched-file whitespace verification passed.
- **blocked:**
  - None.

### 2026-05-05 21:40
- **done:**
  - Fixed Deep Search citation previews so they render through a body-level portal with fixed viewport positioning and a high z-index.
  - Added static regression coverage that citation previews use `createPortal`, `document.body`, fixed overlay positioning, and viewport measurement.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `frontend/components/ChatWorkspace.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Frontend TypeScript and frontend static tests passed.
- **blocked:**
  - Full `git diff --check` is blocked by an unrelated `.gitignore` blank-line change already present in the worktree.

### 2026-05-05 21:19
- **done:**
  - Removed untracked backup/failed-patch files, local Deep Search debug output logs, and one-off root debugging scripts requested for cleanup.
  - Deleted `curl_output.txt`, which contained a local Bearer JWT in captured debug output.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: deleted untracked cleanup artifacts only.
- **doing:**
  - Verified the requested files are no longer present in the workspace.
- **blocked:**
  - None.

### 2026-05-05 21:00
- **done:**
  - Implemented sentence-level Deep Search source buttons by tightening writer citation rules and feeding streamed/persisted source notes into the chat Markdown citation renderer.
  - Added source `note` serialization for Deep Search run reads and frontend DTOs.
  - Added focused backend and frontend static regressions for cited answer sentences, source note payloads, and source-aware citation rendering.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `backend/services/deep_search.py`, `backend/api/schemas/projects.py`, `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`, `README.md`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Targeted regressions, frontend type checking, focused backend mypy, focused Python lint, and whitespace verification passed with the local Python/Node tools.
- **blocked:**
  - `uv` is not installed in this shell, so `uv run ...` quality gates could not be executed directly.
  - The broader focused pytest command still hits a pre-existing Deep Search slow-progress timeout outside this feature path.

### 2026-05-05 20:39
- **done:**
  - Updated `AGENTS.md` with project-specific context, shipped capabilities, likely next work, code ownership pointers, and canonical docs.
  - Kept the existing mandatory agent workflow and repository rules intact.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `AGENTS.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Documentation whitespace verification passed.
- **blocked:**
  - None.

### 2026-05-05 17:05
- **done:**
  - Rendered named Markdown citations in answer bodies as compact source pills with hover/focus source previews.
  - Kept final `## Sources` bullets as normal Markdown links.
  - Added static frontend coverage for citation hover previews.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `frontend/components/ChatWorkspace.tsx`, `tests/test_frontend_deep_search_static.py`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Frontend TypeScript, frontend static tests, and whitespace verification passed.
- **blocked:**
  - None.

### 2026-05-05 16:47
- **done:**
  - Removed duplicate `Accept` header keys from the frontend SSE stream request helpers.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `frontend/lib/api.ts`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Frontend TypeScript and whitespace verification passed.
- **blocked:**
  - None.

### 2026-05-05 16:38
- **done:**
  - Replaced the Deep Search final-answer citation contract with named Markdown links and clean Markdown `## Sources` bullets.
  - Removed legacy source-card/data-source-id handling from the chat Markdown renderer.
  - Updated deterministic citation verification to recognize named Markdown links by URL.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `backend/services/deep_search.py`, `frontend/components/ChatWorkspace.tsx`, `frontend/components/ChatProvider.tsx`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`, `README.md`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Focused citation-format tests, frontend static tests, Python Ruff, and whitespace verification passed.
- **blocked:**
  - Full frontend TypeScript is still blocked by pre-existing duplicate `Accept` header keys in `frontend/lib/api.ts`.

### 2026-05-05 16:10
- **done:**
  - Added chat transcript rendering for grounded-source Markdown links as compact source chips.
  - Added parsing and rendering for Perplexity-style `<div class="source-card" data-source-id="...">` source-card blocks.
  - Updated Deep Search report-writing instructions and local fallback report formatting to emit clickable source citations and source-card blocks when source URLs are available.
  - Added frontend/backend regression coverage and documented the chat citation rendering behavior.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `frontend/components/ChatWorkspace.tsx`, `backend/services/deep_search.py`, `tests/test_frontend_deep_search_static.py`, `tests/test_deep_search.py`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Focused citation/source-card regressions, frontend static checks, Ruff, and whitespace verification passed.
- **blocked:**
  - Full frontend TypeScript remains blocked by pre-existing duplicate `Accept` header keys in `frontend/lib/api.ts`; full Deep Search test coverage remains blocked by existing async timeout/type-check issues in the dirty Deep Search progress path.

### 2026-05-05 15:57
- **done:**
  - Disabled default MCP server loading in `.codex/config.toml` by commenting out all configured MCP server sections.
  - Updated Codex persistent instructions so MCP use is opt-in and only used when explicitly requested with the matching server enabled.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `.codex/config.toml`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the Codex config parses and whitespace is clean.
- **blocked:**
  - None.

### 2026-05-05 15:52
- **done:**
  - Added a dedicated `frontend-qa-tester` sub-agent for Codex and Claude workflows.
  - Registered the Codex role in `.codex/config.toml` and documented it in `.codex/AGENTS.md`.
  - The agent focuses on frontend regression coverage, Playwright-style E2E flow testing, accessibility checks, and verification for the Next.js frontend.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `.codex/agents/frontend-qa-tester.toml`, `.claude/agents/frontend-qa-tester.md`, `.codex/config.toml`, `.codex/AGENTS.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the agent configuration and whitespace.
- **blocked:**
  - None.

### 2026-05-05 10:16
- **done:**
  - Added `WORKFLOW.md`, a repo-level checklist for AI agents handling prompts that change code.
  - Covered prompt classification, required context, success criteria, surgical implementation, testing, verification, docs/log updates, PR rules, and final response expectations.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `WORKFLOW.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verifying the documentation-only change with whitespace checks.
- **blocked:**
  - None.

### 2026-05-03 22:01
- **done:**
  - Implemented heartbeat-driven `stage_update` streaming for Deep Search slow operations (planning, project evidence, summarization, verification).
  - Each slow `await` now runs inside an `asyncio.create_task` + `asyncio.shield` + `asyncio.wait_for(timeout=4)` loop that emits `stage_update` activity events every ~4 seconds so the UI stays responsive.
  - Added `except Exception: break` in all heartbeat loops so task-level exceptions (e.g. `StructuredOutputError`) still reach their fallback handlers instead of bubbling through the heartbeat.
  - Added backend test `test_deep_search_heartbeat_during_slow_planning_emits_stage_updates` verifying ≥2 `stage_update` events between `stage_start` and `stage_complete` for a simulated 9-second planner.
  - Added backend test `test_deep_search_no_invented_source_chips_when_no_candidates` verifying `sources=[]` on `stage_start`/`stage_update` events.
  - Added frontend static test `test_frontend_deep_search_accepts_heartbeat_stage_update_events` verifying the frontend handles all heartbeat-related fields.
  - Changed files: `backend/services/deep_search.py`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`.
- **doing:**
  - All 27 tests pass. Ruff, mypy, TypeScript, and git diff checks pass.
- **blocked:**
  - None.

### 2026-05-03 21:39
- **done:**
  - Fixed Deep Search live progress streaming so activity events are emitted before slow stages and during academic/web provider loops.
  - Added the required compatibility activity schema with `type`/`event_type`, `message`/`detail`, and runtime source chips with UI `type` plus backend `source_type`.
  - Updated the frontend activity reducer to normalize compatibility fields, append source chips from `data.sources`, and keep final answer tokens separate.
  - Added regression tests for activity schema, allowed event types, source chip mapping, source-found phases, and academic stage ordering before a fake slow search completes.
  - Detail reference: `AI_WORKLOG.md`.
  - Changed files: `backend/services/deep_search.py`, `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Running the requested focused pytest, Ruff, mypy, frontend TypeScript, and whitespace checks.
- **blocked:**
  - None.

### 2026-05-03 17:34
- **done:**
  - Updated Deep Search `activity` payloads to follow the live progress narrator contract with `event_type` values for `stage_start`, `stage_update`, `source_found`, `stage_complete`, and `finalizing`.
  - Aligned activity stage labels with the requested research-dashboard stages while keeping source chips tied only to real runtime sources.
  - Updated tests and docs for the narrator payload contract.
  - Changed files: `backend/services/deep_search.py`, `frontend/lib/api.ts`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with focused Deep Search tests, Ruff, mypy, frontend TypeScript, and whitespace checks.
- **blocked:**
  - None.

### 2026-05-03 17:13
- **done:**
  - Removed the Deep Search planner timeout configuration and restored the planner to a direct `_plan_questions(...)` call.
  - Removed the timeout-specific regression test and documentation references while keeping the Deep Search `activity` stream updates.
  - Changed files: `backend/config.py`, `backend/services/deep_search.py`, `tests/test_deep_search.py`, `.env.example`, `README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with focused Deep Search tests, Ruff, mypy, frontend TypeScript, and whitespace checks.
- **blocked:**
  - None.

### 2026-05-03 16:55
- **done:**
  - Added Deep Search `activity` stream events so the frontend thinking panel can show research-log notes and source chips as evidence is discovered, instead of only static phase labels.
  - Added backend and frontend regression coverage for activity events and documented the live research trace behavior.
  - Changed files: `backend/services/deep_search.py`, `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`, `README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with focused Deep Search backend/frontend tests, Ruff, mypy on touched backend files, and whitespace checks.
- **blocked:**
  - None.

### 2026-05-03 16:29
- **done:**
  - Changed the Deep Search thinking panel to show the full research path immediately while the user waits for the answer.
  - Added a pending thinking-step state so future phases are visible but muted, while stream `status` events move the active phase through the list.
  - Updated frontend static coverage and docs for the full thinking path behavior.
  - Changed files: `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `tests/test_frontend_deep_search_static.py`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend static test and frontend TypeScript.
- **blocked:**
  - None.

### 2026-05-03 16:15
- **done:**
  - Fixed Deep Search streaming UX so the final answer bubble is created only after the first streamed token or final `done` event instead of showing an empty assistant row during retrieval.
  - Added a live elapsed timer, pulsing active phase, and progress shimmer to the `Show thinking` panel so long backend phases do not look frozen.
  - Added optional padding to Deep Search SSE frames so small `status` updates are less likely to be buffered until the end of the run.
  - Kept streamed source events visible in both the thinking panel and right context panel before the report starts.
  - Updated frontend static coverage and Deep Search docs for the live thinking behavior.
  - Changed files: `backend/api/routers/projects.py`, `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `frontend/app/globals.css`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with focused Deep Search backend/frontend tests, frontend TypeScript, Ruff, mypy on the touched router, and whitespace checks.
- **blocked:**
  - None.

### 2026-05-02 17:23
- **done:**
  - Changed Deep Search composer submissions to create a pending research plan card first, with `Edit plan` and `Start research` actions.
  - Moved actual Deep Search execution behind plan approval while preserving project creation, related-paper discovery preflight, source capture, and report streaming.
  - Added an expandable `Show thinking` panel driven by Deep Search `status` and `source` stream events.
  - Updated docs and static frontend coverage for the new plan approval and thinking UI.
  - Changed files: `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `tests/test_frontend_deep_search_static.py`, `README.md`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend static test and frontend TypeScript.
- **blocked:**
  - None.

### 2026-05-02 16:47
- **done:**
  - Added a thin divider line between Related Papers and Deep Search Sources in the split context panel.
  - Updated frontend static coverage to pin the separator.
  - Changed files: `frontend/components/ContextPanel.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend static test and frontend TypeScript.
- **blocked:**
  - None.

### 2026-05-02 16:43
- **done:**
  - Changed the split context panel ratio so Related Papers uses two thirds of the available panel height and Deep Search Sources uses one third.
  - Updated frontend static coverage to pin the 2:1 split ratio while keeping independent section scrollbars.
  - Changed files: `frontend/components/ContextPanel.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend static test and frontend TypeScript.
- **blocked:**
  - None.

### 2026-05-02 16:33
- **done:**
  - Split the context panel into fixed Related Papers and Deep Search Sources regions when both lists are present.
  - Added independent scroll containers to each context-panel list so long related-paper or source lists do not push the other section away.
  - Updated frontend static coverage for the split-scroll context panel layout.
  - Changed files: `frontend/components/ContextPanel.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend static test and frontend TypeScript.
- **blocked:**
  - None.

### 2026-05-02 11:08
- **done:**
  - Fixed the misleading Deep Search finalization error where a completed run could stream through `Verifying` and then fail with `Deep search run could not be loaded.`
  - Changed Deep Search success/failure finalization to update the run row directly by id instead of depending on a fragile ORM reload helper during the SSE stream.
  - Added backend regression coverage for completing a Deep Search run even when the reload helper is unavailable.
  - Changed files: `backend/services/deep_search.py`, `tests/test_deep_search.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused Deep Search backend tests, Ruff, and mypy on the touched service.
- **blocked:**
  - None.

### 2026-05-02 11:01
- **done:**
  - Updated Deep Search submissions to ensure the related-paper discovery pipeline runs before streaming when the project has no discovered related papers yet.
  - Preserved the two-part right context panel order with `Related Papers` above `Deep Search Sources`.
  - Updated frontend static coverage and Deep Search frontend docs for the combined related-paper/source panel behavior.
  - Changed files: `frontend/components/ChatProvider.tsx`, `tests/test_frontend_deep_search_static.py`, `frontend/README.md`, `docs/features/deep_search.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused Deep Search frontend static test and frontend TypeScript.
- **blocked:**
  - None.

### 2026-05-01 23:56
- **done:**
  - Reduced Deep Search source favicon sizes in the right context panel.
  - Updated frontend static coverage to pin the smaller source icon dimensions.
  - Changed files: `frontend/components/ContextPanel.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend regression, frontend TypeScript, and `git diff --check`.
- **blocked:**
  - None.

### 2026-05-01 23:34
- **done:**
  - Added favicon-style source images to Deep Search source cards in the right context panel.
  - Uses each source URL hostname to load a small favicon image, with a local article icon fallback for missing or failed favicons.
  - Extended frontend static coverage for favicon rendering in Deep Search source cards.
  - Changed files: `frontend/components/ContextPanel.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend regression, frontend TypeScript, and `git diff --check`.
- **blocked:**
  - None.

### 2026-05-01 23:26
- **done:**
  - Moved Deep Search source display from inline answer chips into the right context panel as a `Deep Search Sources` section, matching the existing related-paper sidebar pattern.
  - Exposed a deduped `deepSearchSources` list from chat state and kept the context panel open when sources exist even if no ranked papers are present.
  - Removed the inline Deep Search source chip strip under assistant answers.
  - Changed files: `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `frontend/components/ContextPanel.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend regression, frontend TypeScript, and `git diff --check`.
- **blocked:**
  - None.

### 2026-05-01 22:29
- **done:**
  - Hardened restored chat sorting against malformed timestamps by replacing raw `Date.parse(...)` subtraction with a finite sort key and stable index tiebreaker.
  - Added frontend static regression coverage for invalid timestamp handling in restored chat sorting.
  - Changed files: `frontend/components/ChatProvider.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend regression, frontend TypeScript, and `git diff --check`.
- **blocked:**
  - None.

### 2026-05-01 22:22
- **done:**
  - Fixed restored chat ordering so Deep Search answers are restored as turn-paired messages anchored to the run start time instead of the completion time.
  - Merged restored normal conversation messages and restored Deep Search messages chronologically to prevent stacked user questions after refresh.
  - Extended the frontend static regression to cover restored message ordering.
  - Changed files: `frontend/components/ChatProvider.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend regression, frontend TypeScript, and `git diff --check`.
- **blocked:**
  - None.

### 2026-05-01 22:09
- **done:**
  - Fixed project refresh restoration so completed Deep Search runs are fetched from `/deep-search-runs`, converted back into assistant messages, and rendered with saved source chips.
  - Suppressed the empty-paper placeholder when a project has a restored Deep Search answer but no ranked papers.
  - Added static frontend regression coverage for restoring completed Deep Search runs after refresh.
  - Changed files: `frontend/components/ChatProvider.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend regression, frontend TypeScript, and `git diff --check`.
- **blocked:**
  - None.

### 2026-05-01 17:41
- **done:**
  - Fixed Deep Search progress rows so `Deep Search run started` and phase messages are tracked as transient status messages and removed when the final report completes.
  - Added static frontend regression coverage for clearing Deep Search progress after completion.
  - Changed files: `frontend/components/ChatProvider.tsx`, `tests/test_frontend_deep_search_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with the focused frontend static regression, frontend TypeScript, and `git diff --check`.
- **blocked:**
  - None.

### 2026-05-01 17:29
- **done:**
  - Fixed Deep Search live structured-output failures so OpenRouter truncation in planning, source summarization, or verification falls back to local deterministic behavior instead of failing the whole run.
  - Reused the captured run id for final persistence/reload to avoid stale ORM access during streamed completion.
  - Added regression coverage for truncated structured output completing successfully with fallback warnings.
  - Changed files: `backend/services/deep_search.py`, `tests/test_deep_search.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with targeted Deep Search tests, Ruff, mypy on the touched service, and `git diff --check`.
- **blocked:**
  - None for this fix.

### 2026-05-01 17:02
- **done:**
  - Implemented Deep Search mode from `plans/deep-search-mode.md`: persisted runs/sources, Tavily fallback, project/academic evidence collection, SSE run/status/source/token/done/error events, report streaming, source chips, QA flags, and usage telemetry.
  - Added backend coverage for stream persistence, ownership, Tavily request/failure behavior, failed runs, OpenRouter usage events, source deduplication, and verifier flags.
  - Updated docs and configuration for the new API surface and `DEEP_SEARCH_*` settings.
  - Changed files: `.env.example`, `README.md`, `AI_WORKLOG.md`, `JOURNAL.md`, `backend/config.py`, `backend/db/models.py`, `backend/db/migrations/versions/20260501_01_deep_search.py`, `backend/services/tavily.py`, `backend/services/deep_search.py`, `backend/api/dependencies.py`, `backend/api/schemas/projects.py`, `backend/api/routers/projects.py`, `database_schema.sql`, `docs/feature-map.md`, `docs/features/deep_search.md`, `frontend/README.md`, `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`, `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`.
- **doing:**
  - Verified targeted checks; see `AI_WORKLOG.md` for command details.
- **blocked:**
  - Full `python -m mypy backend/` is still blocked by the pre-existing untyped Google auth call in `backend/api/routers/auth.py:85`.

### 2026-05-01 16:38
- **done:**
  - Saved the Deep Search mode implementation plan for the planned Tavily-backed research mode.
  - Changed files: `plans/deep-search-mode.md`, `JOURNAL.md`.
- **doing:**
  - Plan is saved for future implementation; no code changes were made.
- **blocked:**
  - None.

### 2026-04-30 10:22
- **done:**
  - Replaced the browser-native user search clear control with a custom neutral clear button.
  - Increased the clear button hit target and added accessible focus/hover states.
  - Changed files: `frontend/app/admin/usage/components.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `git diff --check`.
- **blocked:**
  - None.

### 2026-04-30 10:18
- **done:**
  - Added a subtle hover lift, shadow, color transition, active press state, and disabled cursor state to the primary login button.
  - Changed files: `frontend/app/login/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `git diff --check`.
- **blocked:**
  - None.

### 2026-04-30 10:11
- **done:**
  - Changed the Google Sign-In GIS button from pill-shaped to rectangular so it visually matches the existing `Sign in` button shape.
  - Rendered the Google button at the login form content width instead of the previous fixed 300px width.
  - Changed files: `frontend/app/login/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `git diff --check`.
- **blocked:**
  - None.

### 2026-04-30 00:38
- **done:**
  - Implemented Google Sign-In (OAuth 2.0) across the full stack.
  - Backend: new `POST /auth/google` endpoint verifying Google ID tokens via `google-auth` library, auto-registration and account linking logic, guarded email login for password-less users.
  - Database: Alembic migration adding `auth_provider`, `google_sub` columns to users table, made `hashed_password` nullable for OAuth-only accounts.
  - Frontend: Google Identity Services button on login page, `loginWithGoogle` in AuthProvider, TypeScript type declarations for GIS.
  - Fixed login page font consistency (`font-ui text-on-surface` on `<main>`).
  - Changed files: `backend/config.py`, `backend/db/models.py`, `backend/db/migrations/versions/20260430_01_google_auth.py`, `backend/api/routers/auth.py`, `backend/api/schemas/auth.py`, `frontend/app/layout.tsx`, `frontend/components/AuthProvider.tsx`, `frontend/app/login/page.tsx`, `frontend/types/google-gsi.d.ts`, `.env`, `.env.example`, `pyproject.toml`, `JOURNAL.md`.
- **doing:**
  - Verified: `ruff check` passes, `tsc --noEmit` passes, `alembic upgrade head` succeeded.
- **blocked:**
  - None.

---

### 2026-04-30 00:04
- **done:**
  - Applied the existing thin custom scrollbar styling to the admin usage log scroll container.
  - Extended the shared scrollbar utility to keep horizontal table scrolling thin and minimal too.
  - Changed files: `frontend/app/admin/usage/components.tsx`, `frontend/app/globals.css`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with `cd frontend && ./node_modules/.bin/tsc --noEmit`, `cd frontend && npm run build`, and `git diff --check`.
- **blocked:**
  - None.

### 2026-04-30 00:00
- **done:**
  - Made the shared admin usage log table render inside a fixed-height scroll area.
  - Kept the log table header sticky so column labels remain visible while scrolling long selected-range logs.
  - Changed files: `frontend/app/admin/usage/components.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with `cd frontend && ./node_modules/.bin/tsc --noEmit`, `cd frontend && npm run build`, and `git diff --check`.
- **blocked:**
  - None.

### 2026-04-29 23:54
- **done:**
  - Stacked `Top projects` above the global dashboard log instead of rendering the two panels side by side.
  - Kept the global dashboard log title as `Recent activity` while preserving `User log` on selected-user analysis.
  - Changed the admin usage summary to return all matching log rows for the selected range instead of capping recent events at 25.
  - Changed files: `backend/services/ai_usage.py`, `frontend/app/admin/usage/page.tsx`, `README.md`, `frontend/README.md`, `tests/test_admin.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with `python -m pytest tests/test_admin.py -q`, `python -m ruff check backend/services/ai_usage.py tests/test_admin.py`, `cd frontend && ./node_modules/.bin/tsc --noEmit`, `cd frontend && npm run build`, and `git diff --check`.
- **blocked:**
  - None.

### 2026-04-29 23:43
- **done:**
  - Renamed the admin usage recent-event table to `User log` in the UI.
  - Added admin-only prompt display for project chat usage rows by reading the matching persisted user message at response time, without storing prompts in `ai_usage_events`.
  - Changed files: `backend/services/ai_usage.py`, `backend/api/schemas/admin.py`, `backend/api/routers/admin.py`, `frontend/lib/api.ts`, `frontend/app/admin/usage/components.tsx`, `frontend/app/admin/usage/users/page.tsx`, `README.md`, `frontend/README.md`, `tests/test_admin.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified with `python -m pytest tests/test_admin.py -q`, `python -m ruff check backend/services/ai_usage.py backend/api/schemas/admin.py backend/api/routers/admin.py tests/test_admin.py`, `cd frontend && ./node_modules/.bin/tsc --noEmit`, `cd frontend && npm run build`, and `git diff --check`.
- **blocked:**
  - None.

### 2026-04-29 23:36
- **done:**
  - Updated recent `AI_WORKLOG.md` admin UI entries so the `Prompt/Request` field preserves exact user prompt text instead of only paraphrased summaries.
  - Changed files: `AI_WORKLOG.md`, `JOURNAL.md`.
- **doing:**
  - Verified the documentation-only change with `git diff --check`.
- **blocked:**
  - None.

### 2026-04-29 23:32
- **done:**
  - Moved `Projects used` above `Recent activity` on `/admin/usage/users` by removing the side-by-side two-column grid for those sections.
  - Changed files: `frontend/app/admin/usage/users/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the frontend layout change with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `cd frontend && npm run build`.
- **blocked:**
  - None.

### 2026-04-29 23:26
- **done:**
  - Replaced the admin usage date-range preset dropdown with a shared popover picker that keeps 7-day, 30-day, and all-time presets.
  - Added custom calendar range selection for `/admin/usage` and `/admin/usage/users`, including one-day ranges by selecting the same date twice or double-clicking the date.
  - Changed files: `frontend/app/admin/usage/components.tsx`, `frontend/README.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the frontend change with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `cd frontend && npm run build`.
- **blocked:**
  - None.

### 2026-04-29 23:14
- **done:**
  - Fixed the `/admin/usage/users` searchable user picker so outside blur closes the listbox without discarding the typed search query.
  - Added keyboard navigation for filtered user results with ArrowDown/ArrowUp, active descendant ARIA state, and Enter selection from the highlighted option.
  - Changed files: `frontend/app/admin/usage/components.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the frontend change with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `cd frontend && npm run build`.
- **blocked:**
  - None.

### 2026-04-29 23:00
- **done:**
  - Replaced the selected-user native dropdown on `/admin/usage/users` with a searchable combobox that filters loaded users by email or user id.
  - Kept the existing selected-user URL behavior and admin token usage API contract unchanged.
  - Changed files: `frontend/app/admin/usage/components.tsx`, `frontend/README.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the frontend change with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `cd frontend && npm run build`.
- **blocked:**
  - The first sandboxed `npm run build` hit the known Turbopack port-binding restriction; rerunning the same command outside the sandbox passed.

### 2026-04-28 15:39
- **done:**
  - Changed the `/admin/usage` daily trend to render the API-provided daily rows for the selected date range instead of defaulting to a hardcoded seven-day window.
  - Hardened `DailyTrend` SVG math for empty and single-point datasets by avoiding unnecessary division and closing the area fill from the actual first and last plotted points.
  - Changed files: `frontend/app/admin/usage/page.tsx`, `frontend/app/admin/usage/components.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the change with `cd frontend && ./node_modules/.bin/tsc --noEmit`.
- **blocked:**
  - None.

### 2026-04-28 15:30
- **done:**
  - Removed the `Admin` badge from the shared admin usage page header, which updates both `/admin/usage` and `/admin/usage/users`.
  - Changed files: `frontend/app/admin/usage/components.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the change with `cd frontend && ./node_modules/.bin/tsc --noEmit`.
- **blocked:**
  - None.

### 2026-04-28 15:21
- **done:**
  - Removed the `useRouter` dependency from `/admin/usage/users` query-string updates to avoid callback identity churn in the selected-user loading effect.
  - Changed selected-user loading so `loadUsersAndSelectedUsage` fetches the computed user's filtered usage directly instead of calling another state-dependent loader.
  - Added request sequencing to ignore stale user-list and selected-user usage responses when date ranges or users change quickly.
  - Changed files: `frontend/app/admin/usage/users/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verified the fix with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `cd frontend && npm run build`.
- **blocked:**
  - The first sandboxed `npm run build` hit a Turbopack port-binding restriction; rerunning the same command outside the sandbox passed.

### 2026-04-28 14:36
- **done:**
  - Split the admin monitor into `/admin/usage` for the global dashboard and `/admin/usage/users` for selected-user analysis.
  - Extracted shared admin access, route navigation, date range controls, loading/error/empty states, KPI cards, trend chart, breakdown panels, project table, and recent events table into reusable admin usage components.
  - Changed `/admin/usage/users` to load `/admin/token-usage` first without `user_id`, default to the top token user, then load the selected user's filtered usage while preserving `?user_id=...` in the URL.
  - Updated frontend docs and feature ownership for the new route.
  - Changed files: `frontend/app/admin/usage/page.tsx`, `frontend/app/admin/usage/users/page.tsx`, `frontend/app/admin/usage/components.tsx`, `frontend/README.md`, `docs/feature-map.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Verification completed with `cd frontend && ./node_modules/.bin/tsc --noEmit`, `cd frontend && npm run build`, and `python -m pytest tests/test_admin.py -q`.
- **blocked:**
  - Manual browser verification with real admin/non-admin sessions was not run in this environment.
  - The first sandboxed `npm run build` hit a Turbopack port-binding restriction; rerunning the same command outside the sandbox passed.

### 2026-04-28 14:16
- **done:**
  - Changed the `/admin/usage` daily usage trend from bars to a line graph.
  - Set the admin dashboard default date range to the last 7 days ending on the current day.
  - Filled missing daily chart points with zero values so the graph always shows exactly seven days.
  - Changed files: `frontend/app/admin/usage/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Daily usage trend now visualizes the current seven-day window as a line chart.
- **blocked:**
  - None.

### 2026-04-28 14:06
- **done:**
  - Fixed the `/admin/usage` daily usage trend bars by giving each bar a stable chart height context and visible minimum height.
  - Added compact token labels and a clearer zero-token state for the daily trend chart.
  - Changed files: `frontend/app/admin/usage/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Daily trend now renders visible bars whenever daily token totals are present.
- **blocked:**
  - None.

### 2026-04-28 13:53
- **done:**
  - Replaced the `/admin/usage` date segmented control with a dropdown matching the user and project filter controls.
  - Changed files: `frontend/app/admin/usage/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Admin filters now use consistent dropdown interactions.
- **blocked:**
  - None.

### 2026-04-28 14:05
- **done:**
  - Added a Connected-Papers-style citation neighborhood graph as a "Graph" tab inside the right-hand `ContextPanel`, picking one seed paper from the project and rendering ~30 nodes (seed + up to 10 cited-by + up to 20 references) as a force-directed graph with year-encoded colors and citation-count-encoded node sizes.
  - Extended `backend/services/semantic_scholar.py` to request `citingPaper.citationCount` and `citedPaper.citationCount`, propagated `citation_count` through `normalize_related_paper_payload`, and added the field to `CitationGraphPaperRead` so the frontend can size graph nodes proportionally.
  - Updated `tests/test_services.py` and `tests/test_paper_citations.py` to assert the new `citation_count` field on related papers; verified `tests/test_paper_citations.py::test_get_paper_citation_graph_returns_semantic_scholar_payload` passes locally with the new schema.
  - Built `frontend/components/CitationGraph.tsx` using `react-force-graph-2d` with `next/dynamic({ ssr: false })` and added a `fetchPaperCitationGraph` helper plus `CitationGraph` / `CitationGraphPaper` types in `frontend/lib/api.ts`.
  - Refactored `frontend/components/ContextPanel.tsx` into a tabbed Papers / Graph layout while preserving the existing paper list, summary expansion, and paper selection behavior.
  - Documented the visualization in `docs/features/paper_citation_graph.md`, updated the citation graph row in `docs/feature-map.md`, and refreshed the API surface note in `README.md` and the file map in `frontend/README.md`.
  - Changed files: `backend/services/semantic_scholar.py`, `backend/api/schemas/projects.py`, `tests/test_services.py`, `tests/test_paper_citations.py`, `frontend/package.json`, `frontend/lib/api.ts`, `frontend/components/CitationGraph.tsx`, `frontend/components/ContextPanel.tsx`, `docs/features/paper_citation_graph.md`, `docs/feature-map.md`, `README.md`, `frontend/README.md`, `JOURNAL.md`.
- **doing:**
  - v1 ships without persistence: every tab open issues a fresh Semantic Scholar lookup via the existing `/citation-graph` endpoint.
- **blocked:**
  - `npm install react-force-graph-2d` must be run by the next contributor — the dependency is pinned to `^1.29.1` in `frontend/package.json`, but no package manager was available in this session to run the install.
  - Full `tests/test_services.py` runs on Windows hang on a pre-existing `RequestWindowLimiter` semaphore-leak across pytest event loops; targeted runs of the citation-graph tests pass.

### 2026-04-28 11:32
- **done:**
  - Removed the Confluex logo/wordmark from the `/admin/usage` page header next to `Token Usage Monitor`.
  - Left sidebar branding unchanged.
  - Changed files: `frontend/app/admin/usage/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Admin page header is now title-first without duplicate branding.
- **blocked:**
  - None.

### 2026-04-28 11:20
- **done:**
  - Added a dedicated sidebar to `/admin/usage` with navigation for `Usage Dashboard` and `User Analysis`.
  - Added a user analysis section with top-user bars, user count/request stats, token share, and credit spend by account.
  - Added a compact mobile admin navigation bar so the admin sections remain reachable on small screens.
  - Changed files: `frontend/app/admin/usage/page.tsx`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **doing:**
  - Admin monitoring remains read-only and uses the existing `/admin/token-usage` response.
- **blocked:**
  - None.

### 2026-04-28 09:48
- **done:**
  - Implemented the admin token usage monitoring plan from `plans/in-progress/admin-token-usage-monitoring.md` using coordinated agent review.
  - Added `ADMIN_EMAILS`, admin access control, `/admin/access`, `/admin/token-usage`, global usage aggregation, admin response schemas, and focused admin tests.
  - Added the `/admin/usage` frontend dashboard, admin sidebar navigation, and removed token usage fetching/rendering from the chat context panel.
  - Updated current-state docs and config examples. See `AI_WORKLOG.md` for the detailed file-level record.
- **doing:**
  - Admin usage monitoring is implemented as read-only v1 over existing `ai_usage_events`; budgets, alerts, and exports remain out of scope.
- **blocked:**
  - `uv` is not installed in this environment, so verification used `python -m ...` equivalents.
  - Repo-wide `python -m ruff check .` is blocked by pre-existing issues under `.claude/skills/ui-ux-pro-max`.
  - A full `python -m pytest tests/ -x` run hung near `tests/test_services.py`; focused and broad non-hung checks passed.

### 2026-04-27 22:56
- **done:**
  - Saved the admin token usage monitoring design plan under `plans/in-progress/`, including the existing-app visual design constraints and Stitch prompt.
  - Added the new plan to the `plans/README.md` roadmap.
  - Changed files: `plans/in-progress/admin-token-usage-monitoring.md`, `plans/README.md`, `JOURNAL.md`.
- **doing:**
  - Plan is ready for implementation handoff.
- **blocked:**
  - None.

### 2026-04-27 00:20
- **done:**
  - Fixed model output formatting: the local fallback answer in `_generate_local_answer` was embedding raw conversation history (with `| user:` / `| assistant:` pipe-separated turns) into the user-visible response via `_format_recent_history`. Removed all `## Conversation Context` sections from the three fallback branches since conversation history is already visible in the chat UI. Renamed `## Limits` to `## Next Steps` with cleaner user-facing copy. Added bold formatting to paper titles in fallback output.
  - Changed files: `backend/services/project_conversations.py`, `JOURNAL.md`.
- **doing:**
  - Verified fix in browser — fallback answers now show clean headings and no raw context leakage.
- **blocked:**
  - None.

### 2026-04-26 17:18
- **done:**
  - Hardened main chat streaming after user reported the model output was not streaming reliably.
  - Added OpenRouter `stream_options.include_usage`, no-buffer SSE response headers, and a first-token timeout fallback so a provider stream that stalls before content does not leave the UI stuck on an empty assistant turn.
  - Expanded project conversation tests for no-buffer headers, stream options, and pre-token provider stall fallback.
  - Changed files: `backend/services/project_conversations.py`, `backend/api/routers/projects.py`, `tests/test_project_conversations.py`, `JOURNAL.md`.
- **doing:**
  - Verification completed with `.venv/bin/pytest tests/test_project_conversations.py tests/test_llm_embeddings.py -x`, `ruff check .`, `mypy backend/`, and `npm run build`.
- **blocked:**
  - Live browser/provider streaming could not be fully reproduced inside the sandbox because local uvicorn binding and direct provider streaming probes were unreliable here.

### 2026-04-26 16:28
- **done:**
  - Implemented project-scoped main chat streaming over backend-proxied SSE while keeping the existing synchronous conversation endpoints intact.
  - Added shared project conversation turn preparation/persistence, OpenRouter streaming chunk parsing, usage flushing from final streaming usage, local fallback streaming, and frontend token-by-token rendering.
  - Updated docs for the new streaming API surface and frontend wiring.
  - Changed files: `backend/services/project_conversations.py`, `backend/api/routers/projects.py`, `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `tests/test_project_conversations.py`, `tests/test_frontend_config.py`, `README.md`, `docs/feature-map.md`, `docs/features/paper_conversations.md`, `docs/user-journey.md`, `frontend/README.md`, `JOURNAL.md`.
- **doing:**
  - Verification completed with `.venv/bin/pytest tests/test_project_conversations.py tests/test_llm_embeddings.py -x`, `ruff check .`, `mypy backend/`, and `npm run build`.
- **blocked:**
  - `AI_WORKLOG.md` was not present in this checkout, so this journal entry is the local detail record for the repository changes.

### 2026-04-26 16:00
- **done:**
  - Docked the frontend token usage card at the bottom of the right context panel while allowing the related-paper list to scroll independently.
  - Changed files: `frontend/components/ContextPanel.tsx`, `JOURNAL.md`.
- **doing:**
  - Frontend build verification completed with `npm run build`.
- **blocked:**
  - None.

### 2026-04-26 15:07
- **done:**
  - Added frontend guardrails for the Turbopack dev-memory issue: `npm run dev:bounded` for a 10 GB user-systemd scope, `npm run dev:reset` for stale dev cache cleanup, README usage notes, and a pytest check that keeps `turbopack.root` pinned to `frontend/`.
  - Changed files: `frontend/package.json`, `frontend/README.md`, `tests/test_frontend_config.py`, `JOURNAL.md`.
- **doing:**
  - Verification completed with `.venv/bin/pytest tests/test_frontend_config.py` and `npm run build`.
- **blocked:**
  - None.

### 2026-04-26 15:03
- **done:**
  - Reset the stale Turbopack dev cache at `frontend/.next/dev` before the bounded manual dev-memory test.
  - Rechecked that `frontend/next.config.mjs` keeps `turbopack.root` fixed to `frontend/` and that `frontend/package.json` dev scripts were left unchanged.
  - Changed files: `JOURNAL.md`; ignored cache files under `frontend/.next/dev` were removed.
- **doing:**
  - Frontend config verification completed with `npm run build`; the bounded `systemd-run --user` `/login` compile remains a manual terminal test.
- **blocked:**
  - Codex cannot reliably run the requested user-systemd scoped dev server from this sandbox.

### 2026-04-26 14:53
- **done:**
  - Set the Next.js Turbopack workspace root explicitly to `frontend/` to avoid dev-server root inference from `/home/tungnguyen/package-lock.json`.
  - Changed files: `frontend/next.config.mjs`, `JOURNAL.md`.
- **doing:**
  - Frontend config verification completed with `npm run build`; dev/browser compile should be checked manually outside Codex because it is the OOM trigger path.
- **blocked:**
  - Automated `next dev` login-page verification was intentionally avoided after the OOM risk was confirmed by the user.

### 2026-04-26 12:23
- **done:**
  - Added project-scoped OpenRouter token usage telemetry with `AIUsageEvent`, Alembic migration, collector service, aggregate API, frontend usage card, tests, and docs.
  - Changed files: `backend/db/models.py`, `backend/db/migrations/versions/20260426_01_ai_usage_events.py`, `backend/services/ai_usage.py`, OpenRouter client/service call sites, project router/schemas, frontend chat/context files, tests, and docs/schema files.
- **doing:**
  - Running focused backend/frontend checks for the telemetry implementation.
- **blocked:**
  - None.

### 2026-04-26 12:51
- **done:**
  - Added optional PostgreSQL-backed pytest execution through `TEST_DATABASE_URL`, including a safety guard for dedicated test database names and CI wiring to run tests against Postgres.
  - Changed files: `.github/workflows/ci.yml`, `.env.example`, `tests/conftest.py`, `README.md`, and `docs/feature-map.md`.
- **doing:**
  - Verification completed with default test DB path; Postgres path is ready for a local/CI database named with `test` or `pytest`.
- **blocked:**
  - No local Postgres server is available in this sandbox, so the actual Postgres test path is wired and documented but not locally exercised here.

## Tuần 3 — 18/04/2026

### Đã làm
- Hoàn thiện Phase 3 paper understanding trên backend: grounding PDF, lưu `paper_documents` / `paper_chunks`, hội thoại nhiều lượt cho từng paper, và read APIs cho conversation.
- Sửa lỗi thực tế gây `500` khi tạo paper conversation: NUL bytes trong chunk content và rollback transaction làm mất conversation vừa tạo.
- Điều chỉnh dedup search để ưu tiên `pdf_url` groundable hơn.
- Thiết kế lại và triển khai Phase 3 Writer + QA theo hướng user-invoked: writer outputs được persist, format citations/references cho `docs` và `latex`, có QA flags và read API để lấy lại artifact đã sinh.
- Cập nhật `README.md`, `AI_WORKLOG.md`, và repo verification để phản ánh flow mới.

### Khó nhất tuần này
- Grounding PDF ngoài đời thật không ổn định: nhiều `pdf_url` từ Semantic Scholar trỏ sang publisher pages không tải được như PDF thật.
- Debug lỗi transaction và encoding trong flow async SQLAlchemy khó hơn các lỗi logic thuần vì cần tái hiện đúng trạng thái request thật từ Postman.
- Writer flow cần vừa additive với kiến trúc cũ vừa không kéo writer vào discovery graph luôn-on.

### AI tool đã dùng
| Tool | Dùng để làm gì | Kết quả |
|---|---|---|
| OpenAI Codex | Triển khai Phase 3C-3F, debug lỗi `500`, triển khai Writer + QA, thêm migration/tests/docs | Hoàn thành backend writer flow và ổn định paper understanding flow |

### Học được
- Với paper grounding, direct PDF URLs quan trọng hơn source preference; arXiv-style URLs đáng tin cậy hơn publisher landing pages.
- Invalid API key nên degrade gracefully sớm; nếu không, warning chain sẽ làm output có vẻ “đúng API” nhưng chất lượng grounding rất kém.
- Với các flow có side effects, nested transaction giúp cô lập bước dễ fail mà không rollback toàn bộ request.

### Nếu làm lại, sẽ làm khác
- Thêm health/migration check cho startup sớm hơn để tránh case code mới chạy trên schema cũ.
- Tách fallback logic cho writer/document extraction sớm hơn khi OpenRouter key sai hoặc PDF download fail.
- Chốt rõ hơn từ đầu rằng writer là flow user-triggered riêng, không phải node mặc định của discovery pipeline.

### Kế hoạch tuần tới
- Thêm export/download endpoints cho writer outputs (`.bib`, `.tex`, text references).
- Làm frontend writer workspace thật thay vì chỉ cập nhật shell copy.
- Cải thiện writer quality khi chỉ có metadata fallback và bổ sung QA checks tinh hơn cho unsupported synthesis.

## Tuần 2 — 12/04/2026

### Đã làm
- Hoàn thành Phase 1 foundation: FastAPI async backend, auth, projects, pipeline scaffolding, Alembic, tests, và frontend shell tối thiểu.
- Hoàn thành Phase 2 Searcher + Reader: query expansion, multi-source retrieval, ranking bằng embeddings, summaries có structured output, và paginated paper listing API.
- Bắt đầu Phase 3A bằng cách persist provider metadata (`source_paper_id`, `source_url`, `pdf_url`) trên `papers`.

### Khó nhất tuần này
- Dựng đồng thời async FastAPI, SQLAlchemy async, Alembic, auth, test fixtures, và CI mà vẫn giữ codebase additive.
- Chuẩn hóa dữ liệu từ nhiều nguồn paper khác nhau nhưng không phá vỡ API contract hiện có.

### AI tool đã dùng
| Tool | Dùng để làm gì | Kết quả |
|---|---|---|
| OpenAI Codex | Scaffold backend/frontend, implement Phase 1-2, thêm tests và migrations | Hoàn thành nền tảng repo và search/reader pipeline đầu tiên |

### Học được
- Offline fallbacks rất quan trọng để repo vẫn test/run được khi không có live API keys.
- Search pipeline chỉ ổn khi contract paper metadata đủ chặt giữa services, agents, DB, và API schemas.

### Nếu làm lại, sẽ làm khác
- Bổ sung journal/worklog discipline ngay từ đầu thay vì backfill sau.
- Thiết kế schema cho các phase sau sớm hơn để tránh phải suy luận lại khi nối từ search sang paper understanding.

### Kế hoạch tuần tới
- Triển khai grounding PDF, chunks, và paper conversation persistence.
- Nối retrieval-based Q&A lên selected paper trước khi mở rộng sang writer workflow.

## Repo Change Log

### 2026-04-20 22:05
- **done:**
  - Identified "missing basic features" for the research tool (Export, Advanced Settings, SSE Progress, Paper Management).
  - Reorganized the `plans/` directory into `completed/` and `in-progress/` subdirectories.
  - Broke down the new implementation plan into focused phases: Phase 4A (Export), Phase 4B (Advanced Settings), and Phase 4C (UI Refinements).
  - Updated `plans/README.md` to reflect the new repository roadmap.
- **doing:**
  - Ready to begin implementation of Phase 4A (Export Infrastructure).
- **blocked:**
  - None.

### 2026-04-20 21:15
- **done:**
  - Tested the Next.js frontend UI on `localhost:3000`.
  - Verified landing page design, example topic interaction, and custom research queries.
  - Confirmed successful integration with the FastAPI backend and live paper search services.
  - Captured screenshots of the functional UI and verified result relevance for technical topics.
- **doing:**
  - The UI is confirmed stable and functional for core discovery flows.
- **blocked:**
  - None.

### 2026-04-20 11:20
- **done:**
  - Updated `AGENTS.md` with an explicit repository entry workflow for AI coding agents so they read repo rules, current-state docs, feature mapping, implementation files, and related tests before editing.
  - Added a concise set of working principles to `AGENTS.md` covering thinking before coding, simplicity, surgical changes, and goal-driven execution.
  - Reworded the principles to reduce failure modes such as over-questioning, under-defensive code, or rigid tests-first behavior on tasks where narrower verification is more appropriate.
- **doing:**
  - The repo now gives future agents a clearer operational path for how to enter, reason about, implement, and verify changes.
- **blocked:**
  - None.

### 2026-04-20 10:55
- **done:**
  - Rebuilt `docs/feature-map.md` as the canonical current-state traceability map for this repo and aligned it to the real backend/frontend/test surface.
  - Updated `README.md`, `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md`, `docs/user-journey.md`, and `frontend/README.md` to remove stale ownership references, fix current-vs-planned wording, and add a clearer documentation spine.
  - Added `docs/features/paper_conversations.md` and `docs/features/writer_outputs.md` so the shipped paper-Q&A and writer features now have dedicated deep-dive docs alongside the existing reference-file doc.
- **doing:**
  - Running a consistency sweep for stale paths, missing references, and doc/API mismatches after the documentation realignment.
- **blocked:**
  - None.

### 2026-04-18 00:25
- **done:**
  - Updated `JOURNAL.md` so the weekly summaries follow the file's own `## Tuần N — DD/MM/YYYY` template and section headings exactly.
  - Added missing Week 2 and Week 3 summaries derived from the existing repo change log so the weekly view matches the implementation history already recorded below.
- **doing:**
  - The weekly summary format is now aligned with the documented template while preserving the detailed session-by-session repo change log.
- **blocked:**
  - None.

### 2026-04-17 21:47
- **done:**
  - Implemented the first Phase 3 writer + QA backend slice with a persisted `writer_outputs` model and `20260417_01_phase_3_writer_outputs.py` migration.
  - Added `POST /projects/{project_id}/writer/generate` and `GET /projects/{project_id}/writer/outputs/{output_id}` plus additive schemas for writer requests, paper snapshots, citation artifacts, warnings, and machine-readable QA flags.
  - Added `backend/agents/writer.py`, `backend/agents/qa.py`, `backend/services/citations.py`, and `backend/services/writer_outputs.py` to support user-invoked grounded writing, deterministic citation/reference formatting, BibTeX / thebibliography generation, and rule-based QA validation.
  - Updated the discovery pipeline boundary so the always-on graph now stops at `searcher -> reader`, refreshed the minimal frontend landing page copy, updated `README.md`, and added focused writer API coverage in `tests/test_writer_outputs.py`.
  - Verified the change with focused checks plus repo-wide validation: `python -m ruff check backend tests`, `python -m mypy backend/`, and `pytest tests/ -x` (`47 passed, 3 skipped`).
- **doing:**
  - Writer generation is now persisted and retrievable, with citation/reference artifacts generated from the selected papers only and QA checks enforced before the response is returned.
- **blocked:**
  - Optional download/export endpoints and a real project-level frontend writer workspace are still open follow-up work.

### 2026-04-17 20:56
- **done:**
  - Rewrote `plans/phase-3-writer-qa.md` to change Phase 3 from an always-on auto-drafting pipeline into a user-invoked writer workflow driven by selected papers plus a free-form instruction.
  - Defined the new product direction for grounded writing requests such as related work, reference sections, LaTeX-ready citations, doc-friendly references, BibTeX output, and other custom writing tasks constrained to the selected papers.
  - Updated the Phase 3 plan to specify the writer request model, dedicated writer endpoint, formatting/export responsibilities, QA checks for citation/reference integrity, frontend writer workspace, and the workflow split between discovery (`searcher -> reader`) and on-demand writing (`writer -> qa`).
- **doing:**
  - The plan now reflects the intended UX and backend contract for the writer feature; implementation can follow this revised Phase 3 spec.
- **blocked:**
  - None.

### 2026-04-16 23:35
- **done:**
  - Fixed paper-conversation `500` failures caused by NUL bytes surviving into extracted chunk content and breaking PostgreSQL UTF-8 inserts during on-demand grounding.
  - Updated `backend/services/document_extraction.py` to strip `\x00` during normalization and to isolate extraction persistence inside a nested transaction so extraction failures no longer roll back a just-created conversation.
  - Updated `backend/services/paper_conversations.py` and `tests/test_document_extraction.py` to keep the request flow stable after extraction failures and to cover the NUL-byte regression explicitly.
  - Verified the exact failing local record now succeeds for project `9439a7ce-3137-41fc-93ad-041469a2503d` and paper `039c5c0d-875b-431e-bb54-4c2e95e96907`, creating 21 chunks and a grounded conversation instead of returning `500`.
  - Re-ran repo checks with `python -m ruff check backend tests`, `python -m mypy backend/`, and `pytest tests/ -x` (`43 passed, 3 skipped`).
- **doing:**
  - The paper conversation flow now preserves conversation creation even when extraction fails mid-request and cleanly falls back when grounding is unavailable.
- **blocked:**
  - None.

### 2026-04-16 23:13
- **done:**
  - Updated search candidate deduplication in `backend/agents/searcher.py` to prefer the more groundable `pdf_url` instead of using a hard Semantic Scholar source bias during duplicate resolution.
  - Added a regression test in `tests/test_searcher_reader.py` covering a duplicate pair where a Semantic Scholar publisher-style URL loses to a direct arXiv PDF URL.
  - Verified with focused checks (`python -m ruff check backend/agents/searcher.py tests/test_searcher_reader.py`, `python -m mypy backend/agents/searcher.py`, `pytest tests/test_searcher_reader.py -x`) and broader checks (`python -m ruff check backend tests`, `python -m mypy backend/`, `pytest tests/ -x`) with final suite result `42 passed, 3 skipped`.
- **doing:**
  - Duplicate paper selection now leans toward grounding-friendly sources, which should reduce cases where a publisher-blocked Semantic Scholar record is chosen over an open arXiv equivalent.
- **blocked:**
  - None.

### 2026-04-16 21:19
- **done:**
  - Implemented Phase 3E follow-up paper Q&A with `POST /projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}/messages`, including recent-history loading, new chunk retrieval for each follow-up, persisted user/assistant turns, and explicit `updated_at` refresh for active conversations.
  - Implemented Phase 3F read APIs with `GET /projects/{project_id}/papers/{paper_id}/conversations` and `GET /projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}`, plus additive summary/detail schemas for persisted paper conversations.
  - Added focused API coverage for follow-up turns, list/detail reads, mismatched paper/conversation access, and cross-user ownership checks; updated `README.md`; verified with `python -m ruff check backend tests`, `python -m mypy backend/`, and `pytest tests/ -x` (`41 passed, 3 skipped`).
- **doing:**
  - Phase 3E and 3F are now in place on the backend; the next remaining work for this track is frontend integration or any further UX/API polish built on these persisted conversation endpoints.
- **blocked:**
  - None.

### 2026-04-16 13:56
- **done:**
  - Implemented Phase 3C conversation persistence with new `paper_conversations` and `paper_messages` tables plus ORM relationships on `papers`.
  - Added `backend/services/paper_conversations.py` to create first-turn paper conversations, trigger chunk extraction on demand, retrieve top-k grounded chunks by cosine similarity, and fall back to metadata-only answers when grounding fails.
  - Added `POST /projects/{project_id}/papers/{paper_id}/conversations`, updated the API schemas, added focused conversation tests, and verified with `ruff check backend tests`, `mypy backend/`, a broad non-reference-files pytest pass (`28 passed, 3 skipped`), and `alembic upgrade head` on the local PostgreSQL database.
- **doing:**
  - Phase 3E follow-up messages and Phase 3F conversation read APIs can now reuse the persisted conversation/message tables and paper conversation service.
- **blocked:**
  - A full local `pytest tests/ -x` run is still gated by the current Python environment missing `fitz` for the pre-existing `tests/test_reference_files.py` module.

### 2026-04-16 10:43
- **done:**
  - Implemented Phase 3B paper-grounding infrastructure for backend-only use: new settings, `paper_documents` / `paper_chunks` ORM models, and the `20260416_01_phase_3b_paper_grounding.py` Alembic migration.
  - Added `backend/services/document_extraction.py` with OpenRouter PDF extraction, `native -> cloudflare-ai` retry, fixed-size chunking, embedding persistence, and a deterministic local PDF parsing fallback when live extraction is unavailable.
  - Added `tests/test_document_extraction.py` and verified with `ruff check backend tests`, `mypy backend/`, targeted document-extraction tests, a broad non-reference-files pytest pass (`24 passed, 3 skipped`), and `alembic upgrade head` on the local PostgreSQL database.
- **doing:**
  - Phase 3C conversation persistence and Phase 3D paper Q&A endpoints can now build on `PaperDocumentExtractionService.ensure_document_chunks(...)`.
- **blocked:**
  - A full local `pytest tests/ -x` run is still gated by the current Python environment missing `fitz` for the pre-existing `tests/test_reference_files.py` module.

### 2026-04-15 15:52
- **done:**
  - Updated `JOURNAL.md` so implementation logs follow the required `done` / `doing` / `blocked` structure.
  - Backfilled the major implementation milestones already completed in the repo using `AI_WORKLOG.md` as the detailed reference.
- **doing:**
  - Future repository changes should be appended here with the same three fields.
- **blocked:**
  - None.

### 2026-04-14 10:00
- **done:**
  - Implemented Phase 3A foundation for paper understanding by persisting provider metadata on `papers`.
  - Extended Semantic Scholar and arXiv normalization to keep provider IDs, source URLs, and PDF URLs.
  - Updated Searcher persistence and added tests covering metadata normalization and storage.
  - Verified with lint, mypy, targeted tests, full test suite, and Alembic migration checks.
- **doing:**
  - Phase 3A foundation is in place for later paper-enrichment and understanding flows.
- **blocked:**
  - Local Alembic verification required escalated access because the sandbox blocked the PostgreSQL connection.

### 2026-04-11 23:00
- **done:**
  - Implemented Phase 2 Searcher/Reader pipeline from `plans/phase-2-searcher-reader.md`.
  - Added query expansion, multi-source retrieval, dedup/filtering, embedding-based ranking, structured summaries, and LangGraph reader-warning routing.
  - Replaced the placeholder run flow with a real `POST /projects/{id}/run` execution path and added paginated `GET /projects/{id}/papers`.
  - Added configuration, schema, migrations, services, and tests for the new pipeline behavior.
  - Verified with `alembic upgrade head`, `ruff check backend tests`, `mypy backend/`, and `pytest tests/ -x` with `13 passed, 3 skipped`.
- **doing:**
  - The pipeline supports deterministic offline fallbacks when live Anthropic/OpenAI keys are not configured.
- **blocked:**
  - None for local implementation. Live API and eval coverage remain opt-in and were skipped by design.

### 2026-04-11 17:51
- **done:**
  - Implemented Phase 1 foundation from `plans/phase-1-foundation.md`.
  - Created the FastAPI backend scaffold, auth/project/pipeline routes, async DB layer, initial Alembic migration, source service clients, CI setup, tests, and the minimal Next.js frontend shell.
  - Added monorepo tooling and environment setup files including `pyproject.toml`, `.pre-commit-config.yaml`, `alembic.ini`, and `.env.example`.
  - Verified with migrations, lint, typing, tests, and frontend build checks.
- **doing:**
  - Phase 1 established the base architecture that later phases now build on.
- **blocked:**
  - Frontend dependency audit reported one high-severity vulnerability, but the build itself passed.

## Tuần 1 — 05/04/2026

### Đã làm
- **Thiết kế Kiến trúc RAG-First**: Xây dựng kế hoạch chi tiết (`PLAN.md` và `implementation_plan.md`) tập trung vào việc giảm thiểu chi phí API bằng cách chỉ dùng LLM ở bước tổng hợp cuối cùng.
- **Tái cấu trúc Project**: Chuyển đổi từ code mẫu sang cấu trúc module chuyên nghiệp (`src/pipeline`, `src/sources`, `src/indexing`, `src/db`, `src/auth`).
- **Thiết lập Database**: Cài đặt PostgreSQL v17, cấu tạo Schema với 5 bảng chính và khởi tạo thành công qua SQLAlchemy.
- **Phát triển UI Shell**: Hoàn thiện khung ứng dụng Streamlit với hệ thống Multi-page, giao diện Dark mode cao cấp và tích hợp Authentication (admin/admin123).
- **Scaffolding Pipeline**: Định nghĩa `PipelineState` và các wrapper cho Embedding (all-MiniLM-L6-v2) và Vector Store (ChromaDB).

### Khó nhất tuần này
- Cấu hình PostgreSQL trên macOS gặp lỗi `Connection refused` do dịch vụ Brew không tự chạy — xử lý bằng cách khởi tạo và chạy thủ công qua `pg_ctl`.
- Đảm bảo tính nhất quán của dữ liệu khi truyền qua các node trong LangGraph (đã giải quyết bằng Pydantic `PipelineState`).

### AI tool đã dùng
| Tool | Dùng để làm gì | Kết quả |
|---|---|---|
| Gemini (Antigravity) | Lập kế hoạch, sinh code kiến trúc, cấu hình DB và UI | Hoàn thành toàn bộ Phase 1 trong nửa ngày |

### Học được
- Cách tối ưu chi phí RAG bằng cách tách biệt bước lọc (Embedding-based) và bước tổng hợp (LLM-based).
- Quản lý session và auth trong Streamlit kết hợp với PostgreSQL.
- Tầm quan trọng của việc thiết kế `PipelineState` chặt chẽ ngay từ đầu để tránh bug khi mở rộng pipeline.

### Nếu làm lại, sẽ làm khác
- Sẽ kiểm tra version PostgreSQL của Homebrew kỹ hơn trước khi install để tránh xung đột version cũ.

### Kế hoạch tuần tới
- Triển khai 3 API Client: Semantic Scholar, arXiv và PubMed.
- Xây dựng logic xử lý rate limit và retry thông minh cho các nguồn dữ liệu học thuật.
- Bắt đầu thực hiện Stage 1 & 2 của pipeline (Search & Filter).

---
- [2026-05-03 15:33] Diagnosed and fixed the "stuck until finished" UI issue in Deep Search.
  - Increased `SSE_FLUSH_PADDING` from 2048 to 8192 bytes. Discovered that 2048 bytes was insufficient to flush 4K/8K proxy buffers (like Nginx) which would hold the stream chunks hostage until the connection closed, creating the illusion of a frozen UI.
  - Implemented the `asyncio.wait_for` + `asyncio.shield` heartbeat pattern in `academic_search` and `web_search` phases. Previously, these phases performed long-running network calls (10-20 seconds per query) without emitting heartbeats, causing genuine UI stalls. Now they yield heartbeat padding and status updates every 4 seconds.
- [2026-05-05 23:00] Implemented Citation Graph UX/UI improvements requested from browser inspection.
  - Changed files: `backend/api/routers/projects.py`, `backend/api/schemas/projects.py`, `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`, `frontend/components/CitationGraph.tsx`, `tests/test_projects.py`, `tests/test_frontend_deep_search_static.py`, `README.md`, `frontend/README.md`, `docs/features/paper_citation_graph.md`, `JOURNAL.md`.
  - Added project-library import for citation graph papers with dedupe, workspace graph caching/prefetch, in-app node previews, project membership badges, staged loading copy, and semantic list view fallback.
  - Status: implementation complete; targeted pytest, Ruff, and frontend TypeScript verification passed.
- [2026-05-05 23:08] Refined Citation Graph visual styling for the app's light UI.
  - Changed files: `frontend/components/CitationGraph.tsx`, `JOURNAL.md`.
  - Replaced the hardcoded dark graph surface with a semantic light surface, converted canvas label pills to frosted white with dark text, darkened reference/cited-by node hues, softened the seed glow, and changed graph links to neutral slate.
  - Status: implementation complete; targeted static frontend test and TypeScript verification passed.
- [2026-05-05 23:16] Improved Citation Graph force simulation spacing.
  - Changed files: `frontend/components/CitationGraph.tsx`, `JOURNAL.md`.
  - Added a D3 collision force, increased node repulsion, deferred custom force wiring to avoid initialization races, and moved zoom-to-fit to `onEngineStop`.
  - Status: implementation complete; targeted static frontend test and TypeScript verification passed.

## 2026-05-06T08:46:19+07:00
- **Request:** Fix UI bug where the date range popover is partially hidden by the left sidebar in the admin usage dashboard.
- **Files changed:** `frontend/app/admin/usage/components.tsx`
- **Current status:** Investigated with the browser agent, reproducing the clipped popover bug. The underlying cause was the popover's `right-0` absolute positioning making it overflow the left edge of the `overflow-y-auto` container `div.flex-1`, causing it to be visually clipped right where the sidebar is located. Fixed by changing `right-0` to `left-0` to keep the popover bounded correctly on the right within its scrollable container.

## 2026-05-06T16:43:00+07:00
- **Request:** Save the deployment plan for the Vercel frontend, Render backend, and Render Postgres setup.
- **Files changed:** `plans/vercel-render-deployment-plan.md`, `JOURNAL.md`
- **Current status:** Added a dashboard-first deployment plan covering Render Postgres, Render FastAPI service settings, persistent upload disk, Vercel frontend settings, environment variables, CORS finalization, and production smoke tests.

## 2026-05-07T00:00:00+07:00
- **Request:** Create a pricing page following the Confluex design handoff (`ui_design_pricing_page/`) and add a "Plans" button to the sidebar chat page linking to it.
- **Files changed:** `frontend/app/pricing/page.tsx` (new), `frontend/components/Sidebar.tsx`
- **Current status:** Created a full-featured standalone pricing page at `/pricing` with billing toggle (monthly/annual), 4 plan cards (Free, Student, Researcher Pro, Lab/Team), comparison table, add-ons section, FAQ accordion, and footer CTA — all faithfully ported from the HTML/JSX design reference. Added a `workspace_premium` "Plans" link to both the expanded and collapsed states of the sidebar footer. Subsequent tweaks: fixed scrolling (body is `h-screen overflow-hidden`; changed page wrapper to `h-screen overflow-y-auto`), replaced `check_circle` icon with `check` (16px, FILL 1, wght 500) in the comparison table, and replaced the hero section with the large Noto Serif headline design from the design screenshot.

## 2026-05-06T16:54:27+07:00
- **Request:** Implement `plans/vercel-render-deployment-plan.md`.
- **Files changed:** `backend/config.py`, `backend/main.py`, `.env.example`, `README.md`, `frontend/README.md`, `docs/backend-diagram.md`, `docs/feature-map.md`, `tests/test_app_config.py`, `JOURNAL.md`
- **Current status:** Added `CORS_ALLOWED_ORIGINS` as the backend deployment config surface, kept local frontend origins as defaults, wired FastAPI CORS middleware to parsed settings, documented the Render/Vercel deployment env expectations, and added focused CORS regression coverage. Verification passed for focused pytest, Ruff, touched-file mypy, frontend TypeScript, and frontend production build. Full backend pytest and full backend mypy are blocked by existing unrelated failures in `tests/test_deep_search.py::test_deep_search_streams_academic_stage_start_before_slow_search_completes` and `backend/api/routers/auth.py`.

## 2026-05-07T15:30:07+07:00
- **Request:** Implement `plans/in-progress/sepay-credits-topup.md` on a new `ai/sepay-credits-topup` branch after checkpointing the current workspace.
- **Files changed:** `.env.example`, `backend/config.py`, `backend/db/models.py`, `backend/db/migrations/versions/20260507_01_add_credits_and_payments.py`, `backend/api/dependencies.py`, `backend/api/routers/auth.py`, `backend/api/routers/projects.py`, `backend/api/routers/payments.py`, `backend/api/routers/webhooks.py`, `backend/api/schemas/payments.py`, `backend/main.py`, `backend/services/credits.py`, `backend/services/fx.py`, `backend/services/payment_orders.py`, `backend/services/sepay.py`, `database_schema.sql`, `frontend/app/login/page.tsx`, `frontend/app/billing/`, `frontend/app/chat/page.tsx`, `frontend/components/ChatProvider.tsx`, `frontend/components/Sidebar.tsx`, `frontend/lib/api.ts`, `README.md`, `frontend/README.md`, `docs/backend-diagram.md`, `docs/feature-map.md`, `tests/conftest.py`, `tests/test_credits.py`, `tests/test_payment_orders.py`, `tests/test_sepay_webhook.py`, `tests/test_quota_enforcement.py`, `JOURNAL.md`.
- **Current status:** Checkpoint commit `fc192d6` was created before implementation. Added Sepay/VietQR credit packs, payment orders, webhook settlement, credit ledger operations, signup grants, HTTP 402 quota enforcement with debit/refund guards, billing/checkout/success UI, sidebar balance polling, login return-path handling, insufficient-credit top-up UX, schema/docs sync, and regression tests. Per follow-up feedback, kept the previous pricing page design but rewired its paid plan CTAs to the matching SePay checkout packs. Detailed agent activity remains in `AI_WORKLOG.md`. Verification passed for the new payment/credit/quota tests, the broader affected backend subset, targeted Ruff, backend mypy, frontend TypeScript, and frontend production build; full Ruff and full pytest are still blocked by pre-existing checkpointed `.claude` lint/syntax issues and the existing Deep Search progress timing test.

## 2026-05-07T22:23:40+07:00
- **Request:** Allow admins to have effectively infinite credits.
- **Files changed:** `backend/api/dependencies.py`, `backend/api/routers/payments.py`, `backend/api/schemas/payments.py`, `frontend/app/billing/page.tsx`, `frontend/components/Sidebar.tsx`, `frontend/lib/api.ts`, `tests/test_payment_orders.py`, `tests/test_quota_enforcement.py`, `README.md`, `frontend/README.md`, `docs/feature-map.md`, `JOURNAL.md`.
- **Current status:** Added an `ADMIN_EMAILS` credit bypass so allowlisted admins can use paid endpoints with zero balance and without ledger debits. Exposed the unlimited flag from `/payments/balance` so the sidebar and billing page show admin credit access consistently. Added regression coverage for the bypass and documented the behavior alongside the existing billing/pricing docs. Verification passed for `python -m pytest tests/test_quota_enforcement.py tests/test_payment_orders.py -x`, targeted Ruff, targeted mypy, and frontend TypeScript.

## 2026-05-07T23:39:28+07:00
- **Request:** Before stopping the session, update Claude and Codex agent instruction docs.
- **Files changed:** `CLAUDE.md`, `.codex/AGENTS.md`, `JOURNAL.md`.
- **Current status:** Updated both agent-facing docs with the current SePay/VietQR billing routes, credit ledger/quota ownership, pricing checkout routing, and `ADMIN_EMAILS` unlimited-credit bypass behavior.

## 2026-05-09T(session)
- **Request:** Series of Deep Research Max quality and reliability fixes: (1) show per-iteration web sources in the thinking panel; (2) improve planner to generate dimension-based research questions (Gemini-quality); (3) fix offline fallback producing grammatically broken questions; (4) diagnose and reduce frequent planner fallbacks caused by silent MiMo JSON key mismatches; (5) fix paper summary `relevance` field validation failure; (6) raise report writer token cap from 4,000 to 8,000.
- **Files changed:** `backend/services/deep_search.py`, `backend/api/routers/pipeline.py`, `backend/agents/reader.py`, `frontend/components/ChatProvider.tsx`, `tests/test_deep_search.py`
- **Current status:** All changes applied on `feature/deep-research-max-mode`. Ruff/mypy clean. 21 deep search tests pass (2 pre-existing failures excluded). Key improvements: web sources appear per-iteration in real-time during streaming; max mode planner uses a dimension-decomposition prompt allowing up to 8 named questions; all fallback paths use grammatically safe generic phrasing; planner and pipeline fallbacks now log warnings; paper summaries never fail due to a missing `relevance` key; reports no longer truncate at ~4k tokens.

## 2026-05-09T(session-2)
- **Request:** Implement writer workspace MVP from plans/in-progress/writer-workspace-mvp.md — new branch `feature/writer-workspace-mvp`.
- **Files changed:**
  - `backend/db/models.py` — added `WriterDocument`, `WriterSection`, `WriterSectionVersion` models; added `writer_documents` relationship to `Project`.
  - `backend/db/migrations/versions/20260509_02_writer_workspace.py` — Alembic migration for 3 new tables.
  - `backend/services/tavily.py` — added `ACADEMIC_DOMAINS` constant and `include_domains` param to `search()`.
  - `backend/services/arxiv.py` — added `download_pdf()` helper.
  - `backend/agents/writer_section.py` — new per-section IMRaD drafting agent with low-confidence tagging.
  - `backend/services/writer_documents.py` — new writer document service (CRUD, outline, draft, assemble, export).
  - `backend/api/schemas/writer_documents.py` — Pydantic DTOs for all endpoints.
  - `backend/api/routers/writer_documents.py` — new router with all writer document endpoints.
  - `backend/main.py` — registered writer_documents router.
  - `database_schema.sql` — appended new tables.
  - `tests/test_writer_documents.py` — 25 tests (service + router).
  - `tests/test_writer_section_agent.py` — 16 tests.
  - Frontend: `frontend/lib/api.ts`, `frontend/components/Sidebar.tsx`, `frontend/app/writer/page.tsx`, `frontend/app/writer/[documentId]/page.tsx`, `frontend/components/WriterWorkspace.tsx`, `frontend/components/WriterOutlinePanel.tsx`, `frontend/components/WriterSourcesPanel.tsx`, `frontend/components/WriterQuestionsPanel.tsx`, `frontend/components/WriterQAPanel.tsx`.
- **Current status:** Backend complete, all 41 new tests pass, ruff/mypy clean, migration applies cleanly. Frontend implementation in progress.

## 2026-05-10T10:19:45+07:00
- **Request:** Continue demo-fix pass for Writer Workspace after source attach/draft issues: verify auto Tavily drafting, PDF/manual source attach, inline `\cite{}` rendering, free-form notes, empty-body fallback, and top-k 7 retrieval.
- **Files changed:** `backend/services/writer_documents.py`, `backend/agents/writer_section.py`, `backend/api/routers/writer_documents.py`, `backend/api/schemas/writer_documents.py`, `backend/services/arxiv.py`, `frontend/lib/api.ts`, `frontend/components/WriterSourcesPanel.tsx`, `frontend/components/WriterQuestionsPanel.tsx`, `tests/test_writer_documents.py`, `tests/test_writer_section_agent.py`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`.
- **Current status:** Added focused regression coverage for metadata-only source attach when PDF fetch fails, repeated source attach dedupe, auto-Tavily draft dedupe by source URL, notes-aware section instructions, application-side `\cite{paper_id}` insertion, assemble-time BibTeX key substitution, empty LLM body fallback, frontend attach payload/optimistic state wiring, and same-project validation for direct uploaded-paper attach. Verification passed for the focused Writer pytest suite, targeted Ruff, targeted backend mypy, and frontend TypeScript.

## 2026-05-10T10:32:47+07:00
- **Request:** Fix Writer assemble output where draft text contained `\cite{paper_uuid}` entries but the assembled references did not include the matching BibTeX entries.
- **Files changed:** `backend/services/writer_documents.py`, `tests/test_writer_documents.py`, `JOURNAL.md`.
- **Current status:** Assemble now parses citation commands from drafted sections, loads matching same-project papers even if they are missing from `source_paper_ids_json`, backfills the document source list, substitutes UUID citations to deterministic BibTeX keys for `\cite`, `\citep`, and related commands, and warns for unresolved UUID-like citations. Verification passed for focused Writer pytest, targeted Ruff, and targeted backend mypy.

## 2026-05-10T11:17:51+07:00
- **Request:** Implement `plans/in-progress/llmranker.md` for the Writer source ranker.
- **Files changed:** `backend/services/writer_documents.py`, `backend/api/routers/writer_documents.py`, `backend/config.py`, `.env.example`, `tests/test_writer_documents.py`, `README.md`, `docs/feature-map.md`, `JOURNAL.md`.
- **Current status:** Added MiMo-only source ranking for Writer source suggestions and auto-draft supplemental sources. Manual suggestions now retrieve 7 arXiv plus 12 Tavily candidates, auto-draft retrieves 12 Tavily candidates, local filtering drops missing/duplicate/already-attached sources, MiMo ranks the normalized pool when `XIAOMI_MIMO_API_KEY` is present, and deterministic local ranking fills gaps or handles missing/failed MiMo without falling back to OpenRouter. Focused Writer pytest and targeted Ruff passed.

## 2026-05-10T11:34:04+07:00
- **Request:** Diagnose why Writer section drafts generated repeated generic text and long UUID citation chains across sections.
- **Files changed:** `backend/agents/writer_section.py`, `tests/test_writer_section_agent.py`, `JOURNAL.md`.
- **Current status:** Fixed the writer section offline/error path so it no longer reuses the generic `GroundedWriterAgent` fallback for every IMRaD section. Section drafting now caps source contexts at 7, replaces generic or empty provider output with section-specific deterministic fallback blocks, and renders multi-paper support as one grouped LaTeX citation command. Added regression coverage for section-specific fallback text, source caps, and grouped citations. Verification passed for focused writer document/section pytest, targeted Ruff, and targeted mypy.

## 2026-05-10T16:35:43+07:00
- **Request:** Diagnose and stop paper-chat answers that end with malformed numeric/punctuation tails such as `provided and22,,21..2...`.
- **Files changed:** `backend/services/paper_conversations.py`, `backend/services/project_conversations.py`, `tests/test_paper_conversations.py`, `tests/test_project_conversations.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Identified this as live provider degeneration after an otherwise normal answer, not the deterministic fallback. Added a shared sanitizer that removes obvious numeric/punctuation suffixes before chat output is persisted or rendered in both selected-paper and project conversation paths, and added regression tests for both. Verification passed for the focused sanitizer tests, targeted Ruff, and the full paper/project conversation pytest subset.

## 2026-05-10T23:02:00+07:00
- **Request:** Fix the Writer new-document modal crash when creating a new writer project, reported as a Next.js `insertBefore` runtime `NotFoundError`.
- **Files changed:** `frontend/app/writer/page.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`.
- **Current status:** Replaced the modal submit button's conditional spinner/text insertion with stable mounted spinner and label nodes that toggle `hidden` and `aria-busy`, avoiding React DOM insertion during the submitting transition. Added a static regression test for the stable loading DOM. Verification passed for `python -m pytest tests/test_frontend_writer_static.py -q` and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

## 2026-05-10T23:11:00+07:00
- **Request:** Diagnose why Writer section drafting showed "No source papers attached" even though auto-search was expected when no sources were attached.
- **Files changed:** `backend/services/writer_documents.py`, `tests/test_writer_documents.py`, `README.md`, `JOURNAL.md`.
- **Current status:** Confirmed the draft path only auto-fetched Tavily sources and swallowed provider warnings, so missing/empty Tavily results fell through to the section agent with zero paper contexts. Added an arXiv auto-fetch fallback for no-Tavily-source drafts, preserved search warnings when no source can be found, documented the fallback, and added focused regression coverage. Verification passed for `conda run -n agents uv run pytest tests/test_writer_documents.py -x`.

## 2026-05-10T23:18:00+07:00
- **Request:** Fix arXiv auto-search failures caused by `301 Moved Permanently` redirects from `http://export.arxiv.org`.
- **Files changed:** `backend/services/arxiv.py`, `tests/test_services.py`, `JOURNAL.md`.
- **Current status:** Switched the arXiv API client to the HTTPS export endpoint and enabled redirect following for owned search clients. Added a regression test proving arXiv search uses `https://export.arxiv.org/api/query`. Focused arXiv and writer fallback tests pass.

## 2026-05-10T23:42:00+07:00
- **Request:** Add backend logging for invalid Writer source-ranker provider output so MiMo/Xiaomi response-shape issues are diagnosable.
- **Files changed:** `backend/services/writer_documents.py`, `tests/test_writer_documents.py`, `JOURNAL.md`.
- **Current status:** Added safe warning logs when the source ranker returns an invalid `ranked_candidates` shape or unknown candidate IDs. Logs include top-level keys and value types/counts, not raw candidate/source content. Extended the invalid-MiMo-output regression to assert the structured log metadata. Verification passed for focused Writer pytest, targeted Ruff, and targeted mypy.

## 2026-05-11T00:02:00+07:00
- **Request:** Accept Writer source-ranker provider responses that use `candidates` instead of `ranked_candidates`.
- **Files changed:** `backend/services/writer_documents.py`, `tests/test_writer_documents.py`, `JOURNAL.md`.
- **Current status:** Updated the source-ranker parser to treat a valid top-level `candidates` list as an alias for `ranked_candidates`, preventing the fallback warning for MiMo responses that use the input field name in their output. Added regression coverage proving alias payloads drive provider ordering without invalid-output logs while malformed payloads still warn and fall back. Verification passed for the full Writer document pytest file, targeted Ruff, and targeted mypy.

## 2026-05-11T23:14:43+07:00
- **Request:** Diagnose Writer section draft fallback warning and determine whether Xiaomi MiMo was the cause.
- **Files changed:** `backend/agents/writer.py`, `backend/agents/writer_section.py`, `backend/config.py`, `backend/services/llm.py`, `.env.example`, `README.md`, `tests/test_llm_embeddings.py`, `tests/test_writer_section_agent.py`, `JOURNAL.md`.
- **Current status:** Confirmed the current Writer prompt hit MiMo response issues: the full section prompt exceeded the old 20-second timeout, and MiMo sometimes returned narrative text without required `paper_ids`. Added a writer-specific 60-second timeout, routed section drafts through that writer timeout, removed ambiguous "reference only" section prompt wording, and repaired narrative blocks that omit `paper_ids` by citing the selected source set with a warning instead of discarding the draft. A live non-mutating retry against the same document now returns a MiMo draft with no section fallback warning. Verification passed for focused Writer/LLM pytest, targeted Ruff, and targeted mypy.

## 2026-05-11T23:30:44+07:00
- **Request:** Push the current changed files, create PRs following `PULL_REQUEST.md`, and merge them into `main`.
- **Files changed:** `tests/test_frontend_writer_static.py`, `JOURNAL.md`.
- **Current status:** Installed the repository pre-push hook, reviewed the pending Writer-related diffs, fixed a Ruff import-order issue found during PR preparation, and began the required per-file commit and PR merge workflow.

## 2026-05-12T11:34:16+07:00
- **Request:** Implement the backend portion of the progressive related-papers pipeline: keep `POST /projects/{id}/run`, add `POST /projects/{id}/run/stream` SSE, split ranking from summaries, and preserve credit semantics.
- **Files changed:** `backend/agents/pipeline.py`, `backend/agents/reader.py`, `backend/api/routers/projects.py`, `backend/api/schemas/projects.py`, `tests/test_projects.py`, `tests/test_quota_enforcement.py`, `tests/test_searcher_reader.py`, `README.md`, `docs/feature-map.md`, `JOURNAL.md`.
- **Current status:** Added a request-scoped discovery stream that emits `status`, `papers`, `summary`, `done`, and `error`; ranking now commits `status=ranked` before summaries, while summaries persist one paper at a time as `summarized` or `summary_error`. `/projects/{id}/run` still returns the same blocking response shape, and the focused backend verification passed with targeted pytest, Ruff, and backend mypy.

## 2026-05-12T22:45:16+07:00
- **Request:** Prevent an in-flight project chat response from being interrupted or redirected when the user opens another project.
- **Files changed:** `frontend/components/ChatProvider.tsx`, `frontend/README.md`, `tests/test_frontend_deep_search_static.py`, `tests/test_frontend_pipeline_static.py`, `JOURNAL.md`.
- **Current status:** Added per-project chat snapshots, project-scoped stream updates, cached project reactivation, and active-project busy tracking so standard chat and Deep Search streams continue updating their originating project while another project is visible. Verification passed for frontend TypeScript and the focused frontend static regression tests.

## 2026-05-13T10:11:30+07:00
- **Request:** Make the Writer workspace independent from projects using the cleaner long-term model, without pushing changes.
- **Files changed:** `backend/db/models.py`, `backend/db/migrations/versions/20260513_01_standalone_writer_documents.py`, `database_schema.sql`, `backend/services/writer_documents.py`, `backend/services/reference_files.py`, `backend/api/routers/writer_documents.py`, `backend/api/schemas/writer_documents.py`, `backend/api/schemas/projects.py`, `frontend/lib/api.ts`, `frontend/app/writer/page.tsx`, `frontend/components/WriterWorkspace.tsx`, `frontend/components/WriterSourcesPanel.tsx`, `tests/test_writer_documents.py`, `tests/test_frontend_writer_static.py`, `README.md`, `frontend/README.md`, `docs/feature-map.md`, `docs/features/writer_outputs.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Writer documents are now user-owned and can be created/listed without an active project. Added `writer_document_sources`, direct writer PDF upload, standalone/user-owned source papers, optional project-paper import with source copying, and compatibility for existing project-backed document routes. Frontend Writer no longer blocks on active project and uploads PDFs directly to the writer document. Verification passed for focused Writer backend/static tests.

## 2026-05-13T17:10:00+07:00
- **Request:** Understand the project and implement suitable evaluation metrics for the AI agents and AI chatbot.
- **Files changed:** `backend/eval/__init__.py`, `backend/eval/metrics.py`, `backend/services/deep_search.py`, `tests/test_eval_metrics.py`, `tests/test_search_quality.py`, `README.md`, `JOURNAL.md`.
- **Current status:** Added a deterministic `backend.eval.metrics` module (golden search hit/recall, Reader summary success and field coverage, Deep Search citation-warning rate via `verify_report_claims`, paper-chat format/grounding-leak and lexical support scores, Writer QA severity counts and health score). Exposed `count_report_claim_sentences` for consistent denominators. Refactored opt-in `tests/test_search_quality.py` to use the shared search helpers. Verification passed for Ruff, mypy on `backend/eval` and `deep_search`, and `pytest tests/test_eval_metrics.py`.

## 2026-05-13T17:22:10+07:00
- **Request:** Save and implement the Writer section-outline approval plan so section drafts, especially research Methods drafts, follow an approved paper-type outline before generation.
- **Files changed:** `plans/in-progress/section-outline-approval-before-draft.md`, `backend/agents/writer_section.py`, `backend/services/writer_documents.py`, `backend/api/routers/writer_documents.py`, `backend/api/schemas/writer_documents.py`, `frontend/lib/api.ts`, `frontend/app/writer/page.tsx`, `frontend/components/WriterQuestionsPanel.tsx`, `tests/test_writer_section_agent.py`, `tests/test_writer_documents.py`, `tests/test_frontend_writer_static.py`, `README.md`, `frontend/README.md`, `docs/feature-map.md`, `docs/features/writer_outputs.md`, `JOURNAL.md`.
- **Current status:** Saved the implementation plan, added section-level outline propose/approve APIs, blocked section drafting until an outline is approved, made `paper_type=research` Methods outlines render required LaTeX subsections, and gated the frontend Draft action behind outline approval. Focused backend and frontend static tests are passing; full focused verification and TypeScript checks are next.

## 2026-05-13T18:45:00+07:00
- **Request:** How to run test sample prompts to get outputs of all evaluation metrics.
- **Files changed:** `scripts/run_eval_metric_samples.py`, `README.md`, `JOURNAL.md`.
- **Current status:** Added `scripts/run_eval_metric_samples.py` to print JSON sample outputs for every eval helper without DATABASE_URL or API keys; documented the command in README. Verified with Ruff and a local script run.

## 2026-05-13T20:00:00+07:00
- **Request:** Update `JOURNAL.md` for pull request (consolidated branch summary).
- **PR summary — deterministic agent/chat evaluation metrics:** Introduced `backend/eval/` with pure metrics for Searcher golden hit and mean recall, Reader summary success and field coverage, Deep Search report citation hygiene (`verify_report_claims` + `citation_warning_rate`), paper-chat answer shape / page mentions / chunk–score leak detection and lexical grounding support (`token_jaccard`, `paper_chat_grounding_support`), and Writer QA severity counts plus health score. Added `count_report_claim_sentences()` on `deep_search` for verifier-aligned denominators. Refactored opt-in `tests/test_search_quality.py` to use shared search helpers. Added `scripts/run_eval_metric_samples.py` and README pointer for local metric demos without Postgres or API keys.
- **Files changed (full PR list):** `backend/eval/__init__.py`, `backend/eval/metrics.py`, `backend/services/deep_search.py`, `tests/test_eval_metrics.py`, `tests/test_search_quality.py`, `scripts/run_eval_metric_samples.py`, `README.md`, `JOURNAL.md`.
- **Suggested verification before merge:** `uv run ruff check backend/eval scripts/run_eval_metric_samples.py tests/test_eval_metrics.py tests/test_search_quality.py backend/services/deep_search.py`; `uv run mypy backend/eval`; `uv run pytest tests/test_eval_metrics.py -q`; optional `uv run python scripts/run_eval_metric_samples.py`; optional live search eval `RUN_EVAL_TESTS=1 uv run pytest tests/test_search_quality.py -m eval` (requires network and working academic search).

## 2026-05-14T12:40:00+07:00
- **Request:** Fix local Next.js dev warning blocking cross-origin dev resources when opening the app through the LAN IP.
- **Files changed:** `frontend/next.config.mjs`, `JOURNAL.md`.
- **Current status:** Added `192.168.1.3` to `allowedDevOrigins` so `http://192.168.1.3:3000` can load Next dev resources such as HMR during local LAN testing. Restart `npm run dev` for the config change to apply.

## 2026-05-14T12:37:00+07:00
- **Request:** Create the local frontend environment file for testing the landing page and app locally.
- **Files changed:** `frontend/.env.local`, `JOURNAL.md`.
- **Current status:** Added `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` so the Next.js frontend points at the local FastAPI backend during `npm run dev`.

## 2026-05-13T20:35:42+07:00
- **Request:** Fix survey Methods outline approval after the UI showed the old generic one-line fallback as an approved outline.
- **Files changed:** `backend/agents/writer_section.py`, `backend/services/writer_documents.py`, `frontend/components/WriterWorkspace.tsx`, `frontend/components/WriterQuestionsPanel.tsx`, `tests/test_writer_documents.py`, `tests/test_frontend_writer_static.py`, `README.md`, `frontend/README.md`, `docs/features/writer_outputs.md`, `JOURNAL.md`.
- **Current status:** Added survey-specific Methods outline templates with review-protocol subsections, made survey/research Methods require `\subsection{...}` before drafting, and updated the UI so generic Methods one-liners are not treated as approved outlines. Verification passed with focused Writer backend/static pytest, frontend TypeScript, and targeted Ruff.

## 2026-05-13T20:57:40+07:00
- **Request:** Apply the same structured-outline behavior to Writer Results sections.
- **Files changed:** `backend/agents/writer_section.py`, `backend/services/writer_documents.py`, `frontend/components/WriterQuestionsPanel.tsx`, `tests/test_writer_documents.py`, `tests/test_writer_section_agent.py`, `tests/test_frontend_writer_static.py`, `README.md`, `frontend/README.md`, `docs/features/writer_outputs.md`, `JOURNAL.md`.
- **Current status:** Added research and survey Results subsection templates, made generic one-line Results outlines fail the approval gate for research/survey papers, and updated fallback drafting to preserve approved Results subsections. Verification passed with focused Writer backend/static pytest, frontend TypeScript, and targeted Ruff.

## 2026-05-13T21:05:44+07:00
- **Request:** Make the Writer right-side Questions/Sources/QA panel larger, about 40% of the screen.
- **Files changed:** `frontend/components/WriterWorkspace.tsx`, `frontend/app/writer/[documentId]/page.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`.
- **Current status:** Updated the loaded Writer workspace and loading skeleton to use a 40vw right panel with 360px/640px bounds. Verification passed with frontend static pytest, frontend TypeScript, and targeted Ruff.

## 2026-05-13T22:20:44+07:00
- **Request:** Make the Writer right-side Questions/Sources/QA panel adjustable by the user.
- **Files changed:** `frontend/components/WriterWorkspace.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`.
- **Current status:** Replaced the fixed loaded Writer right panel width with a resizable panel initialized from 40% viewport width, including mouse drag and keyboard arrow resizing with min/max bounds. Verification passed with frontend static pytest, frontend TypeScript, and targeted Ruff.

## 2026-05-13T22:30:41+07:00
- **Request:** Fix the Deep Search/discovery failure shown as `SearchQuery query String should have at most 255 characters` when a long research prompt is used.
- **Files changed:** `backend/agents/searcher.py`, `tests/test_searcher_reader.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Added a regression for the reported long high-speed tracking prompt and changed fallback query composition to reserve room for suffix terms before creating `SearchQuery` models. Verification passed for the focused regression, full `tests/test_searcher_reader.py`, and targeted Ruff.

## 2026-05-14T00:00:00+07:00
- **Request:** Integrate the Claude-designed landing page (`frontend/landing-page/`) into the Next.js app.
- **Files changed:** `frontend/app/page.tsx`, `frontend/app/landing.css`, `frontend/components/landing/LandingPage.tsx`.
- **Current status:** Ported `sections.jsx` + `app.jsx` to a typed React client component (`LandingPage`); scoped the landing CSS under `.landing-root` so the existing chat/billing/writer shells keep their Tailwind layout; the body's `h-screen overflow-hidden` classes are temporarily stripped while the landing is mounted so the page can scroll. Root `/` now renders the landing for unauthenticated visitors and redirects authenticated users to `/chat`. CTA links route to internal `/chat`, `/writer`, `/pricing` (replacing the old `confluex.vercel.app` external URL); the dev-only `TweaksPanel` was dropped. Frontend deps are not installed in this workspace, so typecheck/build were not executed — please run `npm install && npm run build` (or open `/` with `npm run dev`) to verify.

## 2026-05-14T00:30:00+07:00
- **Request:** Add small-win animations to the hero chat preview on the landing page (typewriter greeting, cycling suggestion chips, blinking composer caret).
- **Files changed:** `frontend/components/landing/LandingPage.tsx`, `frontend/app/landing.css`.
- **Current status:** `ChatPreview` is now stateful — the greeting types out at ~28ms/char (preserving the `<em>precise focal point</em>` styling and exposing the full text via `aria-label`), the suggestion chip pool expanded to 6 entries with one slot rotating every 2.6s (fade-in keyframe via the `chip-fade` class), and the composer placeholder gained a blinking caret. All animations are gated by a `usePrefersReducedMotion` hook plus a `@media (prefers-reduced-motion: reduce)` CSS guard, so the greeting renders fully and chips stop cycling when reduced motion is requested. Frontend deps still aren't installed locally; visual verification needs `npm install && npm run dev`.

## 2026-05-14T01:00:00+07:00
- **Request:** Integrate the landing-page components with the app's auth/chat logic (don't dead-end CTAs at protected routes).
- **Files changed:** `frontend/components/landing/LandingPage.tsx`, `frontend/components/ChatWorkspace.tsx`, `frontend/app/landing.css`.
- **Current status:** Added a `useAuthedHref` helper that mirrors `app/pricing/page.tsx` — when `useAuth()` reports a token, CTAs route directly to their target; otherwise they go through `/login?next=<target>` (which `login/page.tsx` already accepts). Wired into the TopNav, Hero, and Footer "Start a review" buttons (label switches to "Open workspace" when signed-in) plus the footer's Research workspace / Writer beta links. The hero `ChatPreview` suggestion chips are now real `<button>`s — clicking one drops the topic into `sessionStorage('landing.topic')` and routes through the auth-aware chat href; `ChatWorkspace` reads that key on mount, seeds the composer draft, and clears it. Pricing nav link stays as the in-page anchor `#pricing` (the footer's Plans link still routes to the standalone `/pricing` page). No backend changes; verification needs `npm run dev` since frontend deps aren't installed in this workspace.

## 2026-05-14T01:30:00+07:00
- **Request:** Audit the landing-page integration for bugs.
- **Files changed:** `frontend/app/landing.css`, `frontend/components/landing/LandingPage.tsx`.
- **Current status:** Found and fixed three issues. (1) **Critical Tailwind collision:** `landing.css` declared `.h-1`, `.h-2`, `.h-3` (and `.h-display`) as global serif-typography rules; Next.js CSS imports are app-wide, so those selectors were overriding Tailwind's `h-1`/`h-2`/`h-3` height utilities used by `ChatWorkspace.tsx:323`, `ChatWorkspace.tsx:858`, `WriterOutlinePanel.tsx:105`, and `WriterQuestionsPanel.tsx:287` — turning thin progress bars / skeleton lines into giant serif headings across the chat and writer surfaces. Scoped them under `.landing-root` so they only apply on the landing page. (2) **Body-class restoration was fragile:** `useEffect` saved `body.className` whole and reassigned it on cleanup, which could clobber any concurrent classes and behaved oddly under React 18 strict-mode double-invocation. Switched to `classList.add/remove` for just `h-screen` and `overflow-hidden`, recording which were present at mount. (3) **Typewriter SSR flash:** initial `typed` state was 0, so the SSR/initial paint showed an empty greeting before the interval ticked. Initialised to full length and only reset-to-zero after `hasMounted && !reduced`, so reduced-motion users and slow-JS clients see the full sentence immediately while motion-OK users still get the typewriter. Other potential issues considered and accepted: tiny landing flash for already-authenticated users (fixed redirect happens within one tick), and `useAuthedHref` returning the bare target while `!ready` (chat-page fallback still routes them through `/login`). No collisions found for other landing-only class names (`.lede`, `.body`, `.brand-mark`, `.wordmark`, `.nav`, `.hero`, etc.) when grepped across `frontend/app` and `frontend/components`.

## 2026-05-14T02:00:00+07:00
- **Request:** Fix the landing page rendering as washed-out / not scrollable.
- **Files changed:** `frontend/app/landing.css`, `frontend/components/landing/LandingPage.tsx`.
- **Current status:** Two regressions from the earlier integration. (1) Landing styles reference `var(--primary)`, `var(--background)`, `var(--on-surface)`, `var(--secondary-container)`, etc., but those tokens live in `frontend/tailwind.config.ts` (Tailwind theme) — they are NOT exposed as CSS custom properties. So every `var(--…)` in landing.css resolved to nothing, the dark hero rendered without a background, italics lost their forest-green colour, etc. Restored the full `:root` block (surfaces, text, brand, sage, outline, radii, spacing, type, motion) so each token has a real value. (2) Body scroll was locked because `frontend/app/globals.css` has `html, body { height: 100% }` in addition to the `h-screen overflow-hidden` Tailwind classes on `<body>`; stripping the classes wasn't enough. Added a `.landing-active` class that gets toggled on both `<html>` and `<body>` while the landing is mounted; landing.css declares `html.landing-active, body.landing-active { height: auto !important; overflow: visible !important; }`. The useEffect still removes the legacy `h-screen` / `overflow-hidden` classes and restores them on unmount.

## 2026-05-14T02:15:00+07:00
- **Request:** Top-nav items rendering pale/invisible against a light backdrop.
- **Files changed:** `frontend/app/landing.css`.
- **Current status:** The nav uses cream `#F2F3EC` text/wordmark/button while in its `.nav-on-dark` state (default at the top of the page), intended to overlay the dark forest-green hero. But the original `.nav { position: sticky; top: 0; background: transparent }` keeps the nav in document flow, so its 64px row sits above the hero with the light body background showing through — cream text on near-white was invisible. Switched to `position: fixed; top: 0; left: 0; right: 0;` so the nav genuinely overlays the hero (which already has 88px top padding, enough to clear the 64px bar). Scrolled-state behaviour (`.nav-scrolled` swaps to translucent paper with dark text) is unchanged.

## 2026-05-14T02:30:00+07:00
- **Request:** Landing page still not scrollable.
- **Files changed:** `frontend/components/landing/LandingPage.tsx`.
- **Current status:** The class-based override (`.landing-active { height: auto !important; overflow: visible !important }`) plus `body.classList.remove("h-screen", "overflow-hidden")` should have unlocked scroll, but evidently didn't in the user's browser (likely either the dev server hadn't picked up the new CSS, or the `!important`-on-element-selector cascade was being beaten by something I missed). Swapped the approach for the most defensive override possible: in the `LandingPage` mount effect, write `height: auto !important; overflow: auto !important` directly to `document.body.style` and `document.documentElement.style` via `setProperty(..., "important")`. Inline styles with `!important` cannot be beaten by any external CSS rule. The cleanup snapshots `body.className`, `body.style.cssText`, and `html.style.cssText` at mount and restores them verbatim on unmount, so the chat/billing/writer shells get their full-viewport lock back when the user navigates away.

## 2026-05-14T10:20:19+07:00
- **Request:** Implement the Writer Editor Agent plan with subagents.
- **Files changed:** `backend/agents/writer_editor.py`, `backend/services/writer_editor.py`, `backend/api/routers/writer_documents.py`, `backend/api/schemas/writer_documents.py`, `frontend/components/WriterEditorOverlay.tsx`, `frontend/components/WriterWorkspace.tsx`, `frontend/lib/api.ts`, `tests/test_writer_editor.py`, `tests/test_frontend_writer_static.py`, `README.md`, `frontend/README.md`, `docs/feature-map.md`, `docs/features/writer_outputs.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Added draft-only editor previews for `fix_error`, `generate_paragraph`, and `incorporate_results`, optional Tavily web citations, credit gating, stale-patch conflict checks, and apply-through-`save_section_edit` versioning. Added the Monaco overlay for selection fixes, prompted edits, paragraph insertion, result incorporation, diff preview, accept/regenerate/refine/discard, plus typed API helpers. Subagents were started but did not return usable patches, so the implementation was completed locally. Focused backend, frontend static, TypeScript, Ruff, and targeted mypy checks passed.

## 2026-05-14T10:39:21+07:00
- **Request:** Fix long Writer editor suggestions overflowing the screen.
- **Files changed:** `frontend/components/WriterEditorOverlay.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Constrained the diff preview card to a viewport-relative max height, made the old/new text area scroll internally, preserved action buttons in a fixed footer, and wrapped long LaTeX/citation strings. Focused frontend static and TypeScript checks passed.

## 2026-05-14T10:44:07+07:00
- **Request:** Let Writer editor suggestions overlay the adjacent right panel.
- **Files changed:** `frontend/components/WriterEditorOverlay.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Moved the Writer editor overlay into a `document.body` portal with fixed viewport coordinates derived from Monaco's DOM node, so diff previews can extend over the Questions/Sources/QA panel instead of being clipped by the editor column. Focused frontend static and TypeScript checks passed.

## 2026-05-14T11:35:27+07:00
- **Request:** Explain and fix paraphrase edits returning the same text.
- **Files changed:** `backend/agents/writer_editor.py`, `tests/test_writer_editor.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Added paraphrase no-op detection for Writer editor selected-span edits. When a paraphrase/rewrite instruction returns unchanged text, the agent retries once with a stricter prompt; if the provider still returns a no-op, it uses a conservative deterministic paraphrase fallback instead of showing the same text as a suggestion. Focused paraphrase regression tests passed.

## 2026-05-14T12:13:44+07:00
- **Request:** Fix the paraphrase fallback still producing the same high-speed tracking paragraph.
- **Files changed:** `backend/agents/writer_editor.py`, `tests/test_writer_editor.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Expanded deterministic paraphrase substitutions for the high-speed tracking paragraph and replaced the raw `paraphrase_fallback` rationale with a user-facing explanation. Added a regression using the reported paragraph and verified the fallback changes prose while preserving citation keys.

## 2026-05-14T12:26:40+07:00
- **Request:** Fix paragraph generation preview showing the prompt instead of generated content.
- **Files changed:** `backend/agents/writer_editor.py`, `tests/test_writer_editor.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Added prompt-echo detection for `generate_paragraph`. If the provider returns the topic/instruction itself or an imperative prompt, the agent now replaces it with a deterministic introduction paragraph built from the requested topic and shows a normal generation rationale.

## 2026-05-14T12:34:45+07:00
- **Request:** Fix Writer editor preview UI showing large blank space before generated paragraph text.
- **Files changed:** `frontend/components/WriterEditorOverlay.tsx`, `tests/test_frontend_writer_static.py`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Trimmed patch text only for preview rendering so generated paragraph insertion newlines no longer create empty vertical space in the diff card, while the actual patch payload remains unchanged for apply.

## 2026-05-14T15:33:34+07:00
- **Request:** Update `CLAUDE.md` and `.codex/AGENTS.md` with the Writer Editor Agent changes.
- **Files changed:** `CLAUDE.md`, `.codex/AGENTS.md`, `JOURNAL.md`, `AI_WORKLOG.md`.
- **Current status:** Added project guidance for the Writer Editor Agent ownership, preview/apply endpoints, credit/versioning behavior, stale-patch validation, citation preservation, paraphrase no-op handling, paragraph prompt-echo fallback, and portal-based overlay UI constraints.
