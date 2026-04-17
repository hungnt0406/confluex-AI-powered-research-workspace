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
