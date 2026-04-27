# Weekly Journal & Change Log

Ghi lại hành trình xây dựng sản phẩm mỗi tuần — những gì đã làm, học được gì, AI giúp như thế nào.
Ngoài phần tổng kết tuần, file này cũng được dùng để log các thay đổi trong repo theo từng phiên làm việc.

> **Cập nhật mỗi cuối tuần** (trước khi tạo PR). Không cần dài, chỉ cần thật.

---

### 2026-04-26 09:42
- **Prompt/Request:**
  Fix uploaded-PDF grounding errors where local files were treated as public URLs and raw provider/download errors leaked into chat answers.
- **Changes Made:**
  - `backend/services/document_extraction.py`: Added local PDF source resolution for stored uploaded reference paths, constrained local reads to configured upload roots, and routed local PDFs through the uploaded-PDF extraction path before chunk persistence.
  - `backend/services/paper_conversations.py`, `backend/services/project_conversations.py`: Replaced raw extraction errors in prompts and fallback answers with user-safe grounding limitation messages, and filtered old internal/provider error lines from sanitized chat text.
  - `tests/test_document_extraction.py`, `tests/test_paper_conversations.py`, `tests/test_project_conversations.py`: Added regression coverage for local uploaded-PDF chunking and hidden provider/debug errors.
  - `docs/features/paper_conversations.md`, `docs/features/upload_reference_file.md`, `docs/user-journey.md`, `docs/TEST_POSTMAN.md`, `AI_WORKLOG.md`: Updated docs/logs for local uploaded-PDF grounding and user-safe extraction failure messages.
- **Notes/Status:**
  Verified with `python -m pytest tests/test_paper_conversations.py tests/test_project_conversations.py tests/test_document_extraction.py -q`, `python -m ruff check backend/services/document_extraction.py backend/services/paper_conversations.py backend/services/project_conversations.py tests/test_document_extraction.py tests/test_paper_conversations.py tests/test_project_conversations.py`, and `python -m mypy backend/services/document_extraction.py backend/services/paper_conversations.py backend/services/project_conversations.py`.

### 2026-04-26 08:44
- **Prompt/Request:**
  Stop project chat from implicitly grounding answers in the first ranked paper when the user has not selected any paper.
- **Changes Made:**
  - `backend/api/schemas/projects.py`, `backend/services/project_conversations.py`: Allowed project chat requests with `paper_ids: []`, skipped chunk retrieval when no papers are selected, generated no-selection prompts/metadata-free fallback answers, and recorded a clear selection-cleared system message.
  - `tests/test_project_conversations.py`: Added regression coverage proving an empty paper selection does not use or mention the top-ranked paper, and typed the file's pytest fixtures for strict mypy.
  - `frontend/components/ChatProvider.tsx`: Removed automatic top-paper selection after discovery or project restore, sent empty selections to project chat, and avoided duplicate restored bootstrap user turns.
  - `README.md`, `frontend/README.md`, `docs/features/paper_conversations.md`, `docs/user-journey.md`, `AI_WORKLOG.md`: Updated the shipped behavior docs and worklog for 0-to-5-paper project chat.
- **Notes/Status:**
  Verified with `pytest tests/test_project_conversations.py -q`, `python -m ruff check backend/api/schemas/projects.py backend/services/project_conversations.py tests/test_project_conversations.py`, `python -m mypy backend/api/schemas/projects.py backend/services/project_conversations.py tests/test_project_conversations.py`, and `./node_modules/.bin/tsc --noEmit` in `frontend/`.

### 2026-04-26 08:42
- **Prompt/Request:**
  Change uploaded reference-file extraction to use the same LLM document extraction path as grounded paper extraction, and remove the old upload byte-limit setting.
- **Changes Made:**
  - `backend/services/document_extraction.py`: Added `extract_uploaded_pdf(...)`, which sends local PDFs to OpenRouter as base64 PDF data URLs when configured and falls back to the existing local PDF extraction path.
  - `backend/services/reference_files.py`, `backend/api/routers/projects.py`, `backend/config.py`, `.env.example`: Replaced the old upload parser integration with the shared extraction service and removed the upload byte-limit setting/read cap.
  - `tests/test_document_extraction.py`, `tests/test_reference_files.py`: Added coverage for uploaded PDF base64 extraction, reference upload metadata creation from extracted text, duplicate handling, validation, and extraction failure persistence.
  - `docs/feature-map.md`, `docs/features/upload_reference_file.md`, `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md`, `AI_WORKLOG.md`: Updated docs/logs for the new upload extraction path and removed size-limit references.
- **Notes/Status:**
  Verified with `python -m pytest tests/test_document_extraction.py tests/test_reference_files.py -q`, `python -m ruff check backend/services/document_extraction.py backend/services/reference_files.py backend/api/routers/projects.py backend/config.py tests/test_document_extraction.py tests/test_reference_files.py`, and `python -m mypy backend/services/document_extraction.py backend/services/reference_files.py backend/api/routers/projects.py backend/config.py`.

### 2026-04-25 19:04
- **Prompt/Request:**
  Implement the frontend chat PDF upload plan using the frontend agent team.
- **Changes Made:**
  - `frontend/lib/api.ts`, `frontend/components/ChatProvider.tsx`: Added typed multipart reference-file upload support, dedicated composer upload state, inline upload notices, project-first upload flow for empty chat state, uploaded-paper tracking, and explicit empty-selection persistence so projects no longer silently fall back to the top paper after reopen.
  - `frontend/components/ChatWorkspace.tsx`, `frontend/components/ContextPanel.tsx`: Replaced the disabled composer upload placeholder with a working PDF picker, added the no-project topic prompt, surfaced inline upload feedback near the composer, marked uploaded papers in Related Papers and selected-paper chips, and highlighted the most recently uploaded paper card.
  - `frontend/README.md`, `docs/feature-map.md`, `docs/user-journey.md`, `AI_WORKLOG.md`: Updated the shipped frontend/docs/logs for composer upload behavior, uploaded-paper markers, and the selected-paper restore fix.
- **Notes/Status:**
  Verified with `./node_modules/.bin/tsc --noEmit` in `frontend/`.

### 2026-04-24 12:40
- **Prompt/Request:**
  Move the upload icon down by 2px in the main chat composer.
- **Changes Made:**
  - `frontend/components/ChatWorkspace.tsx`: Added a `2px` downward offset to the upload button so it sits slightly lower without changing the rest of the composer row layout.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this micro-alignment tweak.
- **Notes/Status:**
  Verifying with `./node_modules/.bin/tsc --noEmit` in `frontend/`.

### 2026-04-24 12:37
- **Prompt/Request:**
  Follow-up report that the upload icon, composer text, and send button were still not visually straight on the same row.
- **Changes Made:**
  - `frontend/components/ChatWorkspace.tsx`: Changed the composer row from bottom-aligned to center-aligned and adjusted the textarea line-height/padding so the placeholder and typed text sit visually centered between the left upload button and right send button.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this alignment correction.
- **Notes/Status:**
  Verifying with `./node_modules/.bin/tsc --noEmit` in `frontend/`.

### 2026-04-24 12:30
- **Prompt/Request:**
  Clarify that the upload button and the composer text should be on the same line in the main chat input.
- **Changes Made:**
  - `frontend/components/ChatWorkspace.tsx`: Reworked the composer from a stacked layout into a single horizontal row so the upload button, textarea placeholder/input text, and send button share one line; also switched back to the native textarea placeholder for that inline layout.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this composer row-layout correction.
- **Notes/Status:**
  Verifying with `./node_modules/.bin/tsc --noEmit` in `frontend/`.

### 2026-04-24 12:26
- **Prompt/Request:**
  Remove the voice chat button from the main chat composer and align the "Ask a grounded question..." text with the upload button.
- **Changes Made:**
  - `frontend/components/ChatWorkspace.tsx`: Removed the disabled `mic` action from the composer controls and adjusted the textarea/placeholder left padding so the composer text starts on the same gutter as the upload button.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this composer layout tweak.
- **Notes/Status:**
  Verified with `./node_modules/.bin/tsc --noEmit` in `frontend/`.

### 2026-04-24 12:01
- **Prompt/Request:**
  Add a hover-only little `X` icon to each selected-paper chip in the chatbox so users can unselect a paper directly from the selected-papers strip.
- **Changes Made:**
  - `frontend/components/ChatWorkspace.tsx`: Updated the selected-papers strip to render chip-level remove buttons that call the existing paper-selection toggle, with the `X` icon hidden by default and revealed on hover or focus.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this chip-unselect UX improvement.
- **Notes/Status:**
  Verified with `./node_modules/.bin/tsc --noEmit` in `frontend/`.

### 2026-04-24 10:30
- **Prompt/Request:**
  Follow-up bug report that paper-selection status lines were appearing repeatedly in the chat transcript and that the 5-paper cap could leak across different chats instead of staying isolated.
- **Changes Made:**
  - `frontend/components/ChatProvider.tsx`: Stopped appending local selection-change status bubbles on every paper toggle, filtered persisted backend `system` messages out of restored transcript rendering, cleared stale paper/message state at the start of project switching, and normalized the selection-limit check against the current chat’s available papers so old chat selections no longer count toward the new chat’s 5-paper cap.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this chat-selection isolation fix.
- **Notes/Status:**
  Verified with `./node_modules/.bin/tsc --noEmit` in `frontend/`. This was a focused frontend state/UX fix; I did not rerun the backend checks from the earlier multi-paper implementation step.

### 2026-04-24 10:17
- **Prompt/Request:**
  Implement `plans/multi-paper-chat-selection.md` so the main chat can use a user-selected set of papers instead of a fixed top paper, and show the selected papers in the chatbox.
- **Changes Made:**
  - `backend/services/project_conversations.py`, `backend/api/routers/projects.py`, `backend/api/schemas/projects.py`, `backend/api/dependencies.py`, `backend/db/models.py`, `backend/db/migrations/versions/20260424_01_project_conversations.py`, `database_schema.sql`: Added project-scoped multi-paper grounded conversations with selected-paper persistence, new routes, new schemas, and new persistence tables while keeping the existing per-paper conversation flow intact.
  - `tests/test_project_conversations.py`: Added focused coverage for project-scoped multi-paper conversation creation, follow-up selection changes, validation errors, and ownership checks.
  - `frontend/components/ChatProvider.tsx`, `frontend/components/ContextPanel.tsx`, `frontend/components/ChatWorkspace.tsx`, `frontend/lib/api.ts`: Reworked the chat workspace to persist selected paper ids per project in localStorage, submit project-scoped conversation requests with `paper_ids`, support multi-select paper cards, append selection-change status notes in the transcript, and show selected papers above the composer.
  - `README.md`, `frontend/README.md`, `docs/feature-map.md`, `docs/user-journey.md`, `docs/features/paper_conversations.md`, `AI_WORKLOG.md`: Updated the docs and required repo logs for the new selected-paper chat flow.
- **Notes/Status:**
  Verified with `pytest tests/test_project_conversations.py -q`, `pytest tests/test_paper_conversations.py -k 'test_create_paper_conversation_returns_first_turn_with_retrieved_chunk' -q`, `python -m ruff check backend/api/dependencies.py backend/api/routers/projects.py backend/api/schemas/projects.py backend/db/models.py backend/services/project_conversations.py tests/test_project_conversations.py`, `python -m mypy backend/api/dependencies.py backend/api/routers/projects.py backend/api/schemas/projects.py backend/db/models.py backend/services/project_conversations.py`, and `./node_modules/.bin/tsc --noEmit` in `frontend/`. All passed.

### 2026-04-24 09:56
- **Prompt/Request:**
  Save the agreed implementation plan for multi-paper chat selection into the `plans/` folder.
- **Changes Made:**
  - `plans/multi-paper-chat-selection.md`: Added a decision-complete implementation plan for replacing fixed top-paper chat grounding with project-scoped multi-paper selection, new project conversation APIs, browser-local selection persistence, and matching test/doc work.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entries for this planning artifact.
- **Notes/Status:**
  Plan-only repository update. No runtime code, schema, or tests were changed in this step.

### 2026-04-22 09:25
- **Prompt/Request:**
  "the context panel expand by default is 50% of the screen, now just do 30%"
- **Changes Made:**
  - `frontend/components/ContextPanel.tsx`: Reduced the initial context-panel width from 50% of the viewport to 30% while preserving the existing drag-resize behavior and all recent paper-card layout tweaks.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this UI-default adjustment.
- **Notes/Status:**
  Verifying with `./node_modules/.bin/tsc --noEmit` in `frontend/`. I did not run `npm run lint` because the repo still has the known `next lint` configuration issue unrelated to this change.

### 2026-04-22 09:31
- **Prompt/Request:**
  Follow-up report that chat answers still show literal markdown headings like `## Evidence` inline in the rendered response.
- **Changes Made:**
  - `frontend/components/ChatWorkspace.tsx`: Normalized inline markdown headings onto their own lines before block parsing so section headers like `## Evidence` render as actual headings even when the model emits them after preceding text on the same line.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this markdown-rendering fix.
- **Notes/Status:**
  Verifying with `./node_modules/.bin/tsc --noEmit` in `frontend/`. I did not run `npm run lint` because the repo still has the known `next lint` configuration issue unrelated to this fix.

### 2026-04-22 11:37
- **Prompt/Request:**
  Follow-up investigation that a Semantic Scholar paper page showed an open-access PDF in the browser, but grounded paper answers still fell back to abstract-only metadata because the stored project paper had no `pdf_url`.
- **Changes Made:**
  - `backend/services/paper_conversations.py`: Added a Semantic Scholar exact-lookup fallback before PDF chunk extraction. When a Semantic Scholar paper has no stored `pdf_url`, the conversation service now resolves the paper by `source_paper_id`, backfills `pdf_url` plus citation/reference counts when available, and then retries grounding.
  - `tests/test_paper_conversations.py`: Added a regression test proving that a conversation can recover a missing `pdf_url` from Semantic Scholar details and proceed with chunk extraction instead of staying in metadata-only fallback.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this grounding fix.
- **Notes/Status:**
  Verified with `pytest tests/test_paper_conversations.py -q`, `python -m mypy backend/`, and `python -m ruff check backend/services/paper_conversations.py tests/test_paper_conversations.py`. All passed.

### 2026-04-22 11:48
- **Prompt/Request:**
  Follow-up report that the conversation endpoint still failed to recover a PDF for a paper whose Semantic Scholar page URL was known and visibly open-access in the browser.
- **Changes Made:**
  - `backend/services/paper_conversations.py`: Expanded the Semantic Scholar PDF backfill logic to try the stored Semantic Scholar page URL as an exact `URL:` lookup candidate, not just the stored `source_paper_id`, before falling back to metadata-only answers.
  - `tests/test_paper_conversations.py`: Added a regression test covering a Semantic Scholar paper with `pdf_url=None` and `source_paper_id=None` but a valid Semantic Scholar `source_url`, proving that the conversation flow can still recover the PDF and proceed with chunk extraction.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this Semantic Scholar URL fallback fix.
- **Notes/Status:**
  Verified with `pytest tests/test_paper_conversations.py -q`, `python -m mypy backend/services/paper_conversations.py`, and `python -m ruff check backend/services/paper_conversations.py tests/test_paper_conversations.py`. All passed.

### 2026-04-22 12:09
- **Prompt/Request:**
  Change the metadata-only fallback answer so it still answers from the abstract when needed, but ends with a clear note telling the user that the PDF could not be accessed for grounding and that they can visit the stored paper page URL and upload the PDF for deeper follow-up questions.
- **Changes Made:**
  - `backend/services/paper_conversations.py`: Added a deterministic post-processing step that appends an `## Access Note` section whenever chunk grounding is unavailable and the paper has a `source_url`, covering both live-model answers and the local fallback path.
  - `tests/test_paper_conversations.py`: Extended the metadata-fallback regression test to assert that the response now includes the source URL and the upload guidance text.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this fallback-answer UX improvement.
- **Notes/Status:**
  Verified with `pytest tests/test_paper_conversations.py -q`, `python -m mypy backend/services/paper_conversations.py`, and `python -m ruff check backend/services/paper_conversations.py tests/test_paper_conversations.py`. All passed.

### 2026-04-22 12:14
- **Prompt/Request:**
  Follow-up that the new `Access Note` section rendered with heading-sized bold text because the markdown structure was getting flattened.
- **Changes Made:**
  - `backend/services/paper_conversations.py`: Fixed `_sanitize_user_visible_text(...)` to preserve markdown block newlines instead of collapsing double newlines into spaces, so appended sections like `## Access Note` keep their body text on normal paragraph lines.
  - `tests/test_paper_conversations.py`: Added a regression test asserting that the sanitizer now preserves markdown block structure for headings and paragraphs.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this formatting fix.
- **Notes/Status:**
  Verified with `pytest tests/test_paper_conversations.py -q`, `python -m mypy backend/services/paper_conversations.py`, and `python -m ruff check backend/services/paper_conversations.py tests/test_paper_conversations.py`. All passed.

### 2026-04-22 12:17
- **Prompt/Request:**
  "make the url clickable"
- **Changes Made:**
  - `frontend/components/ChatWorkspace.tsx`: Added automatic link rendering for bare `http://` and `https://` URLs inside chat message text, so the access note URL now renders as a clickable anchor without changing the backend answer text.
  - `JOURNAL.md`, `AI_WORKLOG.md`: Added the required repo log entry for this chat-link rendering improvement.
- **Notes/Status:**
  Verified with `./node_modules/.bin/tsc --noEmit` in `frontend/`. I did not run `npm run lint` because the repo still has the known `next lint` configuration issue unrelated to this change.

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

### 2026-04-20 13:02
- **done:**
  - Implemented `GET /projects/{project_id}/papers/{paper_id}/citation-graph` to return both the papers that cite an exact paper and the papers it references, using strict Semantic Scholar resolution through stored Semantic Scholar ids, `ARXIV:` ids, `URL:` arXiv links, or `DOI:` values.
  - Added `backend/services/paper_citations.py`, extended `backend/services/semantic_scholar.py` with exact paper, citations, and references lookups, and wired the new route, schemas, and dependency into the projects API.
  - Added focused coverage in `tests/test_paper_citations.py`, `tests/test_projects.py`, and `tests/test_services.py`, then updated `README.md`, `docs/feature-map.md`, `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md`, and `docs/features/paper_citation_graph.md`.
- **doing:**
  - The feature is implemented and documented. `AI_WORKLOG.md` remains the detailed reference for this session if more follow-up notes are needed.
- **blocked:**
  - None.

### 2026-04-20 11:31
- **done:**
  - Removed the Codex `Stop` hook from `.codex/hooks.json` because `codex-cli 0.121.0` rejected the logger's generic `{"status":"logged"}` response as invalid stop-hook JSON.
  - Kept Codex prompt logging on `UserPromptSubmit`, which still preserves automatic prompt logging for Codex sessions in this repo.
- **doing:**
  - The shared logger remains unchanged because the failure was specific to Codex stop-hook output handling, not JSON syntax or logging writes.
- **blocked:**
  - None.

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

### 2026-04-20 23:30
- **done:**
  - Shifted the citation/reference stats cluster 5px to the right in the `ContextPanel` lower metadata row without moving the expand button.
- **doing:**
  - The spacing tweak is in place and ready for a frontend typecheck.
- **blocked:**
  - None.

### 2026-04-20 23:28
- **done:**
  - Reworked the `ContextPanel` paper-card metadata layout so author/year stays on its own line, citation/reference stats move below it, and the expand button now sits on that same lower row.
- **doing:**
  - The layout tweak is in place and ready for a frontend typecheck.
- **blocked:**
  - None.

### 2026-04-20 23:22
- **done:**
  - Removed the inline dot separator between the citation and reference groups in the `ContextPanel` metadata row, while keeping the larger separator between author/year and the stats.
- **doing:**
  - The visual tweak is in place and ready for a frontend typecheck.
- **blocked:**
  - None.

### 2026-04-20 23:21
- **done:**
  - Increased the inline metadata dot separators in the `ContextPanel` paper-card row to a much larger size and tightened the citation/reference icon spacing so the icons sit closer to the count numbers.
- **doing:**
  - The visual polish tweak is in place and ready for a frontend typecheck.
- **blocked:**
  - None.

### 2026-04-20 23:18
- **done:**
  - Added dot separators in the `ContextPanel` paper-card metadata line so author/year, citation count, and reference count are visually separated inline.
- **doing:**
  - The visual tweak is in place and ready for a frontend typecheck.
- **blocked:**
  - None.

### 2026-04-20 23:16
- **done:**
  - Adjusted the `ContextPanel` paper-card layout so citation and reference counts sit inline with the author/year metadata instead of on their own row.
- **doing:**
  - The visual tweak is in place and ready for a frontend typecheck.
- **blocked:**
  - None.

### 2026-04-20 23:03
- **done:**
  - Fixed the Semantic Scholar search request so it actually requests `citationCount` and `referenceCount` on the search endpoint instead of only reading those fields in the normalizer.
  - Added a service-level regression assertion in `tests/test_services.py` proving the search path now returns non-null `citation_count` and `reference_count` when Semantic Scholar includes them.
- **doing:**
  - The code path is corrected; existing persisted paper rows still need a fresh `POST /projects/{id}/run` to repopulate the newly requested upstream counts.
- **blocked:**
  - None.

### 2026-04-20 22:46
- **done:**
  - Added persisted `citation_count` and `reference_count` fields to `papers`, including a new Alembic revision, ORM/model updates, shared provider DTO updates, and search-time persistence from Semantic Scholar results.
  - Extended `GET /projects/{project_id}/papers` to expose the two counts on `ProjectPaperRead`, then updated the right-side `ContextPanel` to replace the relevance bar with citation/reference metadata and a chevron disclosure for structured summaries.
  - Added focused regression coverage in `tests/test_searcher_reader.py` and `tests/test_projects.py`, updated `database_schema.sql`, and synced the affected frontend/manual docs.
- **doing:**
  - The feature is implemented and locally verified; `AI_WORKLOG.md` is the detailed reference for commands, touched files, and the one lint/tooling caveat in this session.
- **blocked:**
  - `npm run lint` in `frontend/` currently fails because `next lint` is treated as an invalid directory argument under the repo's current Next.js setup, so lint verification remains blocked by existing tooling rather than this feature change.

### 2026-04-20 22:29
- **done:**
  - Added a Codex frontend agent team in `.codex/config.toml` with dedicated `frontend_architect`, `frontend_implementer`, and `frontend_ux_reviewer` roles.
  - Created `.codex/agents/frontend-architect.toml`, `.codex/agents/frontend-implementer.toml`, and `.codex/agents/frontend-ux-reviewer.toml`, all pinned to `gpt-5.4` with `xhigh` reasoning and frontend-specific instructions.
  - Wired the frontend roles to the requested design skills from `.claude/skills/ui-ux-pro-max` and `.agents/skills/frontend-design`, alongside supporting frontend verification and framework skills where appropriate.
- **doing:**
  - The repo now has a frontend-focused Codex team setup for planning, implementation, and UX review without changing application runtime code.
- **blocked:**
  - None.

### 2026-04-20 13:46
- **done:**
  - Implemented project deletion with `DELETE /projects/{project_id}` in `backend/api/routers/projects.py`, including best-effort cleanup of stored reference PDFs after the project and its cascaded records are removed.
  - Added focused project-delete coverage in `tests/test_projects.py` for owned-project deletion, filesystem cleanup, and `404` handling on unowned projects.
  - Wired the frontend sidebar delete action in `frontend/components/ChatProvider.tsx` and `frontend/components/Sidebar.tsx`, then updated `README.md`, `docs/TEST_POSTMAN.md`, `docs/backend-diagram.md`, and `docs/user-journey.md`.
- **doing:**
  - The delete-project feature is implemented and verified; `AI_WORKLOG.md` is the detailed reference for commands and touched files in this session.
- **blocked:**
  - None.

### 2026-04-20 12:05
- **done:**
  - Added `.codex/agents/external-researcher.toml` as a new read-only Codex role for searching external knowledge with `gpt-5.4` at `xhigh` reasoning.
  - Registered `external_researcher` in `.codex/config.toml` alongside the existing docs and backend roles.
  - Configured the role to use `exa-search`, `deep-research`, `documentation-lookup`, and `market-research`, with a quick-lookup-first default and explicit source-citation behavior.
- **doing:**
  - The Codex team config now includes a dedicated external research agent for broader web/doc discovery without changing application runtime code.
- **blocked:**
  - None.

### 2026-04-20 11:45
- **done:**
  - Added a Codex backend agent team in `.codex/config.toml` with dedicated `backend_implementer` and `backend_reviewer` roles.
  - Created `.codex/agents/backend-implementer.toml` and `.codex/agents/backend-reviewer.toml`, both pinned to `gpt-5.4` with `xhigh` reasoning and backend-specific instructions.
  - Wired the backend roles to the repo's relevant skills: `backend-patterns`, `coding-standards`, `tdd-workflow`, `api-design`, `security-review`, `verification-loop`, and `documentation-lookup` when needed.
- **doing:**
  - The repo now has a backend-focused Codex team setup for implementation and review work without changing application runtime code.
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

### 2026-04-21 13:39
- **done:**
  - Added `PATCH /projects/{id}` so saved chats/projects can be renamed without affecting their persisted papers, conversations, or writer outputs.
  - Replaced the sidebar row trash action with a hover/focus overflow menu using `more_horiz`, offering `Rename` and `Delete`.
  - Added inline sidebar rename editing plus targeted docs/test updates for the new project-rename flow.
- **doing:**
  - The chat sidebar now supports in-place project organization while preserving the recent `ContextPanel` paper-card layout and citation/reference UI state.
- **blocked:**
  - None for this change. Frontend lint remains separately blocked by the existing `next lint` repo/tooling issue.

### 2026-04-21 13:49
- **done:**
  - Removed native browser `required` validation from the sidebar rename input so empty rename attempts no longer show the default warning tooltip.
  - Kept the existing fallback behavior: if the submitted rename is empty, the UI exits rename mode and restores the previous project title.
- **doing:**
  - The sidebar rename flow now stays consistent with the app’s custom interaction pattern instead of falling back to browser-native form UI.
- **blocked:**
  - None for this follow-up. Frontend lint is still separately blocked by the existing `next lint` repo/tooling issue.

### 2026-04-21 14:37
- **done:**
  - Clamped the resizable context panel so it cannot grow large enough to collapse the main chat workspace into an unusable width.
  - Added a resize-safe width recalculation for the context panel and marked the chat workspace as `min-w-0` so the flex layout behaves correctly under panel resizing.
- **doing:**
  - The chat composer now keeps a usable width even when the related-papers panel is dragged wider.
- **blocked:**
  - None for this UI fix. Frontend lint is still separately blocked by the existing `next lint` repo/tooling issue.

### 2026-04-21 14:42
- **done:**
  - Reverted the hard context-panel width clamp so users can still drag the related-papers panel wide.
  - Replaced the composer’s native multiline placeholder with a custom single-line overlay that truncates with ellipsis when the chat area gets squeezed.
- **doing:**
  - The chat composer now degrades by shortening placeholder copy instead of forcing an earlier resize stop on the context panel.
- **blocked:**
  - None for this follow-up. Frontend lint is still separately blocked by the existing `next lint` repo/tooling issue.

### 2026-04-21 15:45
- **done:**
  - Restored the last-open project after page refresh using user-scoped local storage state.
  - Rehydrated the latest saved grounded paper conversation when reopening a project, so persisted user/model follow-up turns are visible again after reload.
  - Filtered the synthetic bootstrap prompt used for the first auto-grounding call so the restored thread matches the user-facing chat transcript more closely.
- **doing:**
  - The frontend now treats persisted paper conversations as reloadable chat state instead of rebuilding only the topic-summary shell.
- **blocked:**
  - None for this fix. Frontend lint is still separately blocked by the existing `next lint` repo/tooling issue.

### 2026-04-21 15:51
- **done:**
  - Added assistant-message markdown rendering in the chat workspace for headings, paragraphs, ordered lists, unordered lists, inline bold/italic/code, and fenced code blocks.
  - Kept status messages on the simpler plain-text path so the markdown formatter only affects substantive assistant content.
- **doing:**
  - Assistant responses now render structured paper summaries and sectioned answers with readable formatting instead of showing raw markdown syntax.
- **blocked:**
  - None for this UI fix. Frontend lint is still separately blocked by the existing `next lint` repo/tooling issue.

### 2026-04-21 16:20
- **done:**
  - Tightened the grounded paper-Q&A prompt so the model is explicitly told to answer the current question directly, prefer retrieved chunks over generic paper summary behavior, and refuse unsupported claims instead of guessing.
  - Updated the deterministic fallback answer shape to foreground a direct answer/evidence/limits structure instead of loose prose.
  - Added a focused regression test covering the new question-focused prompt instructions.
- **doing:**
  - Grounded paper answers should now stay closer to the user’s exact question instead of drifting into broad paper summaries.
- **blocked:**
  - None for this backend fix.

### 2026-04-21 16:39
- **done:**
  - Removed internal retrieval labels and similarity scores from the grounded paper-answer prompt so the model no longer sees `Chunk N` / `score=...` markers.
  - Kept only page numbers in the prompt and deterministic fallback evidence formatting, which matches what users can actually interpret.
  - Added regression assertions that the prompt no longer contains chunk labels or retrieval scores.
- **doing:**
  - Grounded answers now expose human-meaningful page references without leaking backend retrieval implementation details.
- **blocked:**
  - None for this backend polish fix.

### 2026-04-21 16:43
- **done:**
  - Sanitized recent conversation history before it is re-sent to the model so older assistant turns cannot reintroduce internal `Chunk N` labels into new grounded answers.
  - Sanitized the final persisted grounded answer text itself, stripping chunk labels and retrieval scores while preserving page references.
  - Added a focused regression test for the new user-visible text sanitizer.
- **doing:**
  - Grounded answers now remove internal retrieval labels even if they were present in prior conversation turns.
- **blocked:**
  - None for this backend cleanup fix.

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
