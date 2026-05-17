# Worklog

Ghi lại các quyết định kỹ thuật, phân công công việc theo sprint (kiểu Kanban TO DO / DOING / DONE), và brainstorming của nhóm dự án **Automated Literature Review**.

> Cập nhật **bất cứ khi nào** nhóm ra quyết định kỹ thuật quan trọng, mở sprint mới, hoặc thay đổi hướng đi.

**Thành viên nhóm**
- **Trần Ngọc Hùng** (`hungnt`) — Backend infrastructure, auth, billing/SePay, admin dashboard, CI/CD, schema & migrations.
- **Trần Gia Khánh** (`khanhtg`) — LangGraph pipeline, paper search & ranking, Deep Search, paper/project chat, citation graph, reference upload.
- **Nguyễn Tùng Lâm** (`lamnt`) — Writer agent, writer documents & editor overlay, writer chat panel, frontend workspace, documentation.

---

## Mục lục

- [Template](#template)
- [Quyết định kỹ thuật (ADR)](#quyết-định-kỹ-thuật-adr)
- [Phân công công việc theo sprint](#phân-công-công-việc-theo-sprint)
- [Brainstorming](#brainstorming)
- [Bug & sự cố quan trọng](#bug--sự-cố-quan-trọng)

---

## Template

### Quyết định kỹ thuật

```markdown
### [ADR-N] Tiêu đề quyết định — DD/MM/YYYY

**Bối cảnh:** Vấn đề cần giải quyết là gì?

**Các lựa chọn đã xem xét:**
- Option A: ...
- Option B: ...

**Quyết định:** Chọn option nào và tại sao.

**Hệ quả:** Những gì bị ảnh hưởng / trade-off.
```

### Phân công (Kanban)

```markdown
### Sprint N — DD/MM → DD/MM/YYYY

| Task | Người phụ trách | Thời gian | Trạng thái | Ghi chú |
|---|---|---|---|---|
| | | | TO DO / DOING / DONE | |
```

### Brainstorming

```markdown
### Brainstorm: [Chủ đề] — DD/MM/YYYY

**Câu hỏi:** ...

**Các ý tưởng:**
- Ý tưởng 1: ...
- Ý tưởng 2: ...

**Kết luận:** ...
```

---

## Quyết định kỹ thuật (ADR)

### [ADR-1] LangGraph cho pipeline Searcher → Reader → Writer → QA — 20/04/2026

**Bối cảnh:** Cần điều phối nhiều agent bất đồng bộ (tìm bài, đọc tóm tắt, viết, QA) với state dùng chung và khả năng thêm nhánh điều kiện (ví dụ: cảnh báo khi ranking trả ít bài).

**Các lựa chọn đã xem xét:**
- **Option A — Tự viết orchestrator bằng `asyncio`:** Linh hoạt nhất nhưng phải tự quản lý state, retry, branching.
- **Option B — LangChain `Chain`/`Runnable`:** Sẵn ecosystem nhưng khó express conditional branching và phải dùng nhiều syntactic sugar.
- **Option C — LangGraph:** Mô hình graph rõ ràng, state TypedDict dùng chung, dễ thêm node và edge điều kiện.

**Quyết định:** Chọn Option C. Tách `backend/agents/state.py` (state) khỏi `graph.py` (wiring) và các node (`searcher.py`, `reader.py`, `writer.py`, `qa.py`). External I/O (HTTP, LLM, PDF) nằm trong `backend/services/`, agent nodes chỉ orchestrate.

**Hệ quả:** Khi thêm Deep Search và Writer Document Chat, không phải reorganize toàn bộ pipeline — chỉ thêm service và router mới mà không đụng vào graph chính.

---

### [ADR-2] OpenRouter làm LLM gateway + deterministic offline fallback — 22/04/2026

**Bối cảnh:** Cần gọi nhiều provider LLM (OpenAI GPT, Xiaomi MiMo, Claude) với một interface chung, đồng thời đảm bảo test/CI/dev chạy được khi không có API key.

**Các lựa chọn đã xem xét:**
- **Option A — Gọi trực tiếp từng provider SDK:** Phải quản lý nhiều client, key, schema khác nhau.
- **Option B — LangChain LLM abstraction:** Phụ thuộc nặng vào LangChain; phiên bản hay thay đổi.
- **Option C — OpenRouter + thin wrapper trong `backend/services/llm.py`:** Một API key, schema OpenAI-compatible, dễ swap model. Cộng thêm offline fallback trả về kết quả deterministic.

**Quyết định:** Chọn Option C. Tất cả LLM call qua `services/llm.py`. Khi `OPENROUTER_API_KEY` không có → service trả về kết quả tóm tắt/đáp án mặc định nhưng đúng schema. Embeddings cũng đi qua `services/embeddings.py` với cosine ranking fallback.

**Hệ quả:** Test suite hermetic, CI không cần secret. Khi cần Xiaomi MiMo riêng cho `mimo-*` model → thêm model-aware routing (xem ADR-8) mà không phá vỡ contract.

---

### [ADR-3] SePay/VietQR cho credit top-up thay vì Stripe — 25/04/2026

**Bối cảnh:** Người dùng chính là sinh viên/nhà nghiên cứu Việt Nam. Stripe không hỗ trợ tài khoản cá nhân ở Việt Nam mà không có pháp nhân; thẻ tín dụng quốc tế cũng không phổ biến trong sinh viên.

**Các lựa chọn đã xem xét:**
- **Option A — Stripe Checkout:** Trải nghiệm tốt nhưng cần pháp nhân, fee cao, mất 7-14 ngày T+ settlement.
- **Option B — MoMo/ZaloPay API:** Phải đăng ký merchant, phê duyệt thủ tục dài.
- **Option C — SePay + VietQR (chuyển khoản ngân hàng VN):** QR mã hóa metadata `reference_code` (`ORD...`), webhook khi tiền vào. T+0 settlement, phí gần như bằng 0.

**Quyết định:** Chọn Option C. `payment_orders` lưu USD + VND snapshot + FX rate + QR payload; webhook `/webhooks/sepay` xác thực API key, idempotent qua `sepay_transaction_id` unique.

**Hệ quả:** Người dùng nhập số tiền VND theo QR là xong. Hỗ trợ admin allowlist (`ADMIN_EMAILS`) để bypass credit gating cho team nội bộ. Nếu mở rộng quốc tế sau này sẽ phải thêm Stripe — nhưng đó là bài toán tương lai.

---

### [ADR-4] LLM-generated Deep Search plan thay vì hardcoded steps — 07/05/2026

**Bối cảnh:** Deep Search plan card hiển thị nội dung cố định bất kể người dùng nhập topic gì. Mọi topic đều thấy cùng 3 bullet point chung chung, không có giá trị thực với người dùng.

**Các lựa chọn đã xem xét:**
- **Option A — Hardcoded template với string interpolation:** Đơn giản, không cần gọi API thêm. Nhưng chỉ nhúng câu hỏi vào 1 bullet, phần còn lại vẫn generic.
- **Option B — LLM call từ frontend (client-side):** Nhanh, không cần backend thêm. Nhưng lộ API key, khó kiểm soát cost, không nhất quán với kiến trúc hiện tại.
- **Option C — Backend endpoint `POST /pipeline/deep-search/plan`:** Gọi `OpenRouterStructuredOutputService` với structured JSON output, fallback về hardcoded khi thiếu key. Frontend hiển thị skeleton loading trong lúc chờ.

**Quyết định:** Chọn Option C. Phù hợp với kiến trúc layered hiện tại (I/O trong `services/`, HTTP trong `routers/`). Offline fallback đảm bảo CI và môi trường không có key vẫn chạy được. UX không bị block vì plan card xuất hiện ngay với skeleton, rồi swap sang nội dung thật.

**Hệ quả:** Thêm ~1 LLM call mỗi lần user submit Deep Search (trước khi run). Cost nhỏ, dùng model rẻ nhất của OpenRouter. Skeleton shimmer animation thêm vào `globals.css`. `DeepSearchPlanMessage.status` mở rộng thêm `"generating"`.

---

### [ADR-5] Tavily làm web search backbone cho Deep Search — 01/05/2026

**Bối cảnh:** Deep Search cần evidence từ web ngoài Semantic Scholar/arXiv. Đã thử Bing/Google Custom Search nhưng quota gói free quá thấp và phải tự parse HTML.

**Các lựa chọn đã xem xét:**
- **Option A — Bing Web Search API:** Quota giới hạn ở gói free, kết quả phải tự crawl để lấy snippet đủ dài.
- **Option B — Tự crawl bằng Playwright headless:** Robust nhưng chậm, hay bị block, mất công maintain selector.
- **Option C — Tavily Search API:** API chuyên cho LLM (trả snippet + URL chuẩn JSON), search depth `advanced` cho full result set.

**Quyết định:** Chọn Option C. Khi `TAVILY_API_KEY` thiếu → skip web search, persist warning, nhưng academic/project evidence vẫn chạy bình thường. Mặc định dùng `search_depth: advanced`.

**Hệ quả:** Deep Search có degraded mode rõ ràng. Citation hygiene của report được kiểm bởi verifier prompt và verification flags trong `qa_flags_json`.

---

### [ADR-6] Monaco editor + LaTeX-as-source-of-truth cho Writer — 02/05/2026

**Bối cảnh:** Writer cần produce paper format export được (IEEE/APA/Chicago). Đã cân nhắc Markdown nhưng equation và bibliography phức tạp hơn.

**Các lựa chọn đã xem xét:**
- **Option A — TipTap/ProseMirror với Markdown serialization:** UX rất tốt nhưng equation và `\thebibliography` phải custom node phức tạp.
- **Option B — TipTap render từ LaTeX (LaTeX là source of truth):** Hybrid — UI rich, raw vẫn là LaTeX. Risk: round-trip parser dễ vỡ.
- **Option C — Monaco Editor edit LaTeX trực tiếp + targeted edit overlay:** LaTeX nguyên bản, người dùng vẫn edit thoải mái, agent edit qua span-based patches với stale-preview guard.

**Quyết định:** Chọn Option C. `WriterEditorOverlay` portal qua `document.body`, dùng Monaco viewport coordinates. Một operation `edit` mở open-ended: chọn span → revise, không chọn → insert at offset.

**Hệ quả:** `WriterSectionVersion` lưu snapshot sau mỗi accepted apply. Stale span → HTTP 409 với `original_text` trong response. Preview cost credit nhưng apply free.

---

### [ADR-7] Writer documents user-owned thay vì project-owned — 09/05/2026

**Bối cảnh:** Ban đầu writer outputs thuộc về project. Nhưng users muốn viết related-work/survey paper từ source của nhiều project hoặc PDF rời, không cần tạo project trước.

**Các lựa chọn đã xem xét:**
- **Option A — Giữ `writer_outputs` gắn cứng với project:** Đơn giản nhưng buộc tạo project rỗng cho mỗi paper.
- **Option B — Document user-owned hoàn toàn (bỏ link project):** Mất khả năng auto-import papers từ project.
- **Option C — `writer_documents` user-owned + optional `project_id` (ON DELETE SET NULL):** Compatibility cho cả 2 luồng.

**Quyết định:** Chọn Option C. `writer_document_sources` là junction; `source_origin` phân biệt manual upload, search attach, hay import từ project. Section drafts gated trên approved outline.

**Hệ quả:** Writer survive khi project bị xóa. Frontend tách `/writer` route hoàn toàn khỏi `/chat`. Project chat và Writer là hai workspace độc lập, share auth + papers.

---

### [ADR-8] Model-aware LLM routing cho Xiaomi MiMo — 10/05/2026

**Bối cảnh:** Khi dùng `mimo-v2.5-pro` qua OpenRouter, request đi qua base URL OpenRouter và bị các provider route filter chặn. Cần force MiMo requests đi thẳng tới Xiaomi base URL.

**Các lựa chọn đã xem xét:**
- **Option A — Thêm prefix manual mỗi chỗ gọi:** Dễ miss, không centralize.
- **Option B — Cấu hình per-feature:** Phức tạp, mỗi feature phải tự biết khi nào dùng MiMo.
- **Option C — Model-aware routing trong `services/llm.py`:** Resolve `mimo-*` / `xiaomi/*` model id sang `XIAOMI_MIMO_BASE_URL` + `XIAOMI_MIMO_API_KEY`. Tự động cho mọi caller.

**Quyết định:** Chọn Option C. Project chat, paper chat, structured output, document extraction, Deep Search dùng cùng routing.

**Hệ quả:** Adding provider mới sau này chỉ cần extend routing table. Provider failure fallback về local deterministic ranking trong writer source ranker khi `XIAOMI_MIMO_API_KEY` missing.

---

## Phân công công việc theo sprint

Bảng follow format Kanban: **TO DO** (chưa bắt đầu) → **DOING** (đang làm) → **DONE** (đã merge vào `main`).

### Sprint 1 — 20/04 → 26/04/2026 (Foundation)

| Task | Người phụ trách | Thời gian | Trạng thái | Ghi chú |
|---|---|---|---|---|
| Setup FastAPI app + pydantic-settings config | Hùng | 20/04 → 21/04 | DONE | `backend/main.py`, `backend/config.py` |
| JWT auth (register/login) + `users` schema | Hùng | 21/04 → 23/04 | DONE | Hashed password với bcrypt |
| SQLAlchemy 2.0 async models + Alembic baseline | Hùng | 22/04 → 24/04 | DONE | 18 bảng, UUID PK string(36) |
| Semantic Scholar service + dedup logic | Khánh | 21/04 → 23/04 | DONE | `services/semantic_scholar.py` |
| arXiv service + query expansion | Khánh | 23/04 → 25/04 | DONE | `services/arxiv.py` |
| LangGraph state + Searcher node | Khánh | 24/04 → 26/04 | DONE | `agents/state.py`, `agents/searcher.py` |
| Next.js 14 App Router shell + Tailwind setup | Lâm | 20/04 → 22/04 | DONE | `frontend/app/layout.tsx` |
| Login page (email/password) + AuthProvider | Lâm | 22/04 → 24/04 | DONE | localStorage JWT |
| `frontend/components/Sidebar.tsx` v1 | Lâm | 25/04 → 26/04 | DONE | New Research + project list |

### Sprint 2 — 27/04 → 03/05/2026 (Discovery + Admin + Deep Search foundation)

| Task | Người phụ trách | Thời gian | Trạng thái | Ghi chú |
|---|---|---|---|---|
| Google Sign-In (GIS) backend + migration | Hùng | 27/04 → 30/04 | DONE | `POST /auth/google`, `auth_provider`, `google_sub` columns |
| Google Sign-In frontend (GIS button + types) | Hùng | 29/04 → 30/04 | DONE | `frontend/types/google-gsi.d.ts` |
| `ai_usage_events` schema + admin token usage dashboard | Hùng | 27/04 → 29/04 | DONE | `/admin/usage` + `ADMIN_EMAILS` bypass |
| Reader node + embedding ranking | Khánh | 27/04 → 29/04 | DONE | OpenRouter `text-embedding-3-small` |
| Structured paper summaries (problem/method/result) | Khánh | 29/04 → 01/05 | DONE | `Summary.has_error` cho LLM failure |
| Deep Search mode v1: plan, Tavily, persisted runs, SSE | Khánh | 01/05 → 03/05 | DONE | `services/deep_search.py`, `services/tavily.py` |
| Deep Search context panel + source chips frontend | Lâm | 01/05 → 03/05 | DONE | `frontend/components/ChatProvider.tsx` |
| Admin usage dashboard frontend (top projects, log table) | Lâm | 27/04 → 29/04 | DONE | Sticky header, custom scrollbar |
| Login page polish (Google button rect, hover lift) | Lâm | 30/04 → 30/04 | DONE | Width match form |

### Sprint 3 — 04/05 → 10/05/2026 (Writer foundation + chat polish + billing)

| Task | Người phụ trách | Thời gian | Trạng thái | Ghi chú |
|---|---|---|---|---|
| SePay/VietQR top-up: orders, webhook, FX snapshot | Hùng | 04/05 → 06/05 | DONE | `payment_orders` + `/webhooks/sepay` idempotent |
| Credit ledger + `require_credits` enforcement | Hùng | 06/05 → 07/05 | DONE | HTTP 402 with `required` + `balance` |
| SePay webhook bug: integer `id` rejected by pydantic v2 | Hùng | 08/05 | DONE | `coerce_numbers_to_str=True` (xem [Bug #2](#bug-2--sepay-webhook-422-do-pydantic-strict-string)) |
| Citation graph endpoint + import-citation | Khánh | 05/05 → 06/05 | DONE | `papers/{id}/citation-graph` |
| Sentence-level Deep Search citation buttons | Khánh | 05/05 | DONE | Named Markdown links + source previews |
| Deep Search heartbeat `stage_update` events (planning, evidence) | Khánh | 03/05 | DONE | Anti-frozen UI, 4s interval |
| Project chat first-token timeout fix (60s) | Khánh | 10/05 | DONE | `PROJECT_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` |
| Xiaomi MiMo model-aware routing (xem [ADR-8](#adr-8-model-aware-llm-routing-cho-xiaomi-mimo--10052026)) | Khánh | 10/05 | DONE | `mimo-*` / `xiaomi/*` → Xiaomi base URL |
| Writer agent v1 (outputs với citation formatting) | Lâm | 04/05 → 07/05 | DONE | IEEE/APA/Chicago via `services/citations.py` |
| Reference PDF upload + PyMuPDF chunking | Lâm | 04/05 → 06/05 | DONE | `services/document_extraction.py` |
| Writer document MVP (sections, outline approval) | Lâm | 07/05 → 09/05 | DONE | `writer_documents`, `writer_sections` |
| Writer Editor Overlay (Monaco portal, span edit/insert) | Lâm | 09/05 → 10/05 | DONE | `WriterEditorOverlay.tsx`, `WriterSectionVersion` history |
| KaTeX math rendering in chat Markdown | Lâm | 10/05 | DONE | `frontend/app/layout.tsx` |
| Writer page back-to-chat header link | Lâm | 10/05 | DONE | Preserves active project |

### Sprint 4 — 11/05 → 17/05/2026 (Writer chat + polish + docs)

| Task | Người phụ trách | Thời gian | Trạng thái | Ghi chú |
|---|---|---|---|---|
| `database.md` + Mermaid ERD + README rewrite | Hùng | 17/05 | DONE | Tài liệu schema + project overview |
| Backend diagram refactor (Mermaid classDefs, split routes) | Hùng | 06/05 | DONE | `docs/backend-diagram.md` |
| Update CI workflow for dedicated test database | Hùng | 05/05 | DONE | `TEST_DATABASE_URL` |
| Deep Research Max adaptive loop mode | Khánh | 09/05 → 10/05 | DONE | 3rd chat mode, 5× credit, `ResearchState` accumulator |
| Deep Search arXiv timeout / network error fallbacks | Khánh | 15/05 | DONE | `ArxivUnavailable`, non-canceling `asyncio.wait` |
| Progressive related-paper SSE for first standard chat | Khánh | 12/05 | DONE | `papers` event before `summary` events |
| Sidebar restructure: Writer near top, account popover | Lâm | 14/05 | DONE | Beta badge preserved |
| Writer document chat panel (Xiaomi MiMo, in-mem + Redis) | Lâm | 15/05 | DONE | `feature/writer-document-chat` branch |
| Writer attached source names (no UUIDs) | Lâm | 12/05 | DONE | `source_papers` ordered metadata |
| Writer workspace Batch A polish (autosave, metrics, a11y) | Lâm | 16/05 | DONE | Memoized chat panel, skip-to-editor |
| Terms page scrolling fix | Lâm | 16/05 | DONE | `h-screen overflow-y-auto` container |

---

## Brainstorming

### Brainstorm: Cách present Deep Search "thinking" cho user — 02/05/2026

**Câu hỏi:** Deep Search có thể chạy 20-40 giây. Làm sao để user không nghĩ app bị treo?

**Các ý tưởng:**
- **Ý tưởng 1 (Hùng):** Spinner đơn giản + ETA estimate. Nhanh implement nhưng nhàm chán.
- **Ý tưởng 2 (Khánh):** SSE stream phases (`Planning` → `Searching academic` → `Searching web` → `Synthesizing`) với current phase highlight. Cho thấy progress nhưng user không thấy bằng chứng cụ thể.
- **Ý tưởng 3 (Lâm):** Perplexity-style "thinking panel" expandable: stream cả planned research steps, source chips (khi tìm thấy URL), và snippet quotes trong khi vẫn chờ final answer. UX wow nhất nhưng phức tạp.

**Kết luận:** Chọn ý tưởng 3, nhưng làm theo phases:
- Phase 1 (Khánh): SSE event types `stage_start`, `stage_update`, `source_found`, `stage_complete`, `finalizing`.
- Phase 2 (Lâm): expandable `Show thinking` panel với live elapsed timer + pulsing active phase + progress shimmer.
- Phase 3 (Khánh): heartbeat `stage_update` mỗi 4s khi slow await để UI không "đông cứng".

Triển khai trải dài Sprint 2 → Sprint 4.

---

### Brainstorm: Phân chia ownership giữa Project chat và Writer — 09/05/2026

**Câu hỏi:** Writer ban đầu thuộc về project. Có nên giữ nguyên không?

**Các ý tưởng:**
- **Ý tưởng 1 (Khánh):** Giữ nguyên — Writer luôn cần project context để fetch papers. Đơn giản hóa data model.
- **Ý tưởng 2 (Lâm):** User-owned hoàn toàn — Writer là workspace riêng, project chỉ là một source provider tùy chọn. Phù hợp use case "Tôi đang viết related work, muốn import bài từ 3 project khác nhau".
- **Ý tưởng 3 (Hùng):** Hybrid — `writer_documents.user_id` bắt buộc, `project_id` optional với `ON DELETE SET NULL`. Có cả 2 luồng.

**Kết luận:** Chọn ý tưởng 3 (xem [ADR-7](#adr-7-writer-documents-user-owned-thay-vì-project-owned--09052026)). Frontend route `/writer` tách hoàn toàn khỏi `/chat`. Sidebar có nút Writer riêng.

---

### Brainstorm: Hỗ trợ thanh toán cho user Việt Nam — 25/04/2026

**Câu hỏi:** Người dùng chính là sinh viên + nhà nghiên cứu VN. Đa số không có thẻ tín dụng quốc tế. Lựa chọn gì?

**Các ý tưởng:**
- **Ý tưởng 1 (Hùng):** Stripe cho thị trường quốc tế, ai có thẻ thì dùng. → Loại: không hỗ trợ TK VN.
- **Ý tưởng 2 (Khánh):** MoMo/ZaloPay API. → Loại: thủ tục merchant dài, phải có pháp nhân.
- **Ý tưởng 3 (Hùng):** SePay + VietQR. Người dùng quét QR và chuyển khoản, webhook xác nhận. Settle T+0.
- **Ý tưởng 4 (Lâm):** Bonus free credit khi đăng ký để giảm friction.

**Kết luận:** Chọn ý tưởng 3 (xem [ADR-3](#adr-3-sepayvietqr-cho-credit-top-up-thay-vì-stripe--25042026)) + ý tưởng 4 (signup grant 100 credits). Admin allowlist (`ADMIN_EMAILS`) bypass credit gating cho team nội bộ.

---

### Brainstorm: Tính năng demo cho buổi báo cáo — 12/05/2026

**Câu hỏi:** Demo 10 phút nên show gì để cover được hết flow chính?

**Các ý tưởng:**
- **Ý tưởng 1 (Hùng):** Live signup → top-up → search → chat. Cover billing + flow chính.
- **Ý tưởng 2 (Khánh):** Pre-seeded project + Deep Search live demo với câu hỏi domain phức tạp. Show được sức mạnh Tavily + academic search.
- **Ý tưởng 3 (Lâm):** Writer workspace live edit + agent revise paragraph + export LaTeX. Show end-to-end output.

| Ý tưởng | Pros | Cons |
|---|---|---|
| Signup → top-up → chat | Cover billing, không bị fail | Phần Deep Search/Writer mất thời gian |
| Deep Search live | Wow factor cao nhất | Nếu Tavily chậm → demo timeout |
| Writer end-to-end | Output cụ thể, ấn tượng | Cần script kỹ để tránh edge case |

**Kết luận:**
- Phút 1-2: Signup + top-up (Hùng).
- Phút 3-5: Pre-seeded project + Deep Search trên topic đã verify trước (Khánh).
- Phút 6-9: Writer workspace + agent edit + export (Lâm).
- Phút 10: Q&A.

---

## Bug & sự cố quan trọng

### Bug #1 — Deep Search infinite "Synthesizing" + network error — 15/05/2026

**Người phụ trách:** Khánh

**Triệu chứng:** Stream phase tới `Synthesizing the answer` rồi báo `network error`, run lưu `failed`.

**Root cause:** Streaming writer provider fail sau khi sources đã condense → exception bubble through không có fallback.

**Fix:** Thêm live report-writer fallback. Nếu provider streaming fail → log warning, append persisted fallback warning, stream local evidence-grounded report từ condensed source notes, verify, persist run là `succeeded`, emit `done` thay vì `error`. Test coverage trong `tests/test_deep_search.py`.

**Học được:** Mọi external streaming call cần có graceful fallback path. SSE `done` event là source of truth cho frontend — tuyệt đối không cho phép `error` bubble qua phase cuối.

---

### Bug #2 — SePay webhook 422 do pydantic strict string — 08/05/2026

**Người phụ trách:** Hùng

**Triệu chứng:** SePay dashboard hiển thị transaction thành công nhưng credit balance không update. Webhook log: HTTP 422 cho mọi delivery thật.

**Root cause:** SePay gửi `id` là JSON number, `SepayWebhookPayload.transaction_id: str` reject dưới strict-string default của pydantic v2 → request fail trước khi tới settlement.

**Fix:** Thêm `coerce_numbers_to_str=True` vào `model_config` của webhook schema. Regression test post nguyên payload thật (integer `id`, `subAccount`, BIDV gateway).

**Học được:** Schema validation ở boundary phải dung sai với JSON loosely-typed từ third party. Test với payload thật thay vì payload đã được normalize.

---

### Bug #3 — Chat streaming force scroll bottom — 15/05/2026

**Người phụ trách:** Khánh (backend SSE) + Lâm (frontend behavior)

**Triệu chứng:** Khi assistant đang stream token, user không scroll lên đọc lịch sử được — viewport bị force về bottom mỗi token.

**Root cause:** Auto-scroll chạy mỗi lần `messages` thay đổi, không phân biệt user đang đọc hay không.

**Fix:** Thêm bottom-stickiness guard + wheel/touch intent tracking. Auto-scroll chỉ chạy khi viewport đã near-bottom; gesture upward → disable follow ngay lập tức; gửi message mới hoặc scroll xuống → re-enable.

**Học được:** Stream UX không phải chỉ "render token cho nhanh" — phải tôn trọng user intent.

---

### Bug #4 — Paper Q&A output token truncation — 10/05/2026

**Người phụ trách:** Lâm

**Triệu chứng:** Bảng dài trong câu trả lời bị cắt giữa dòng.

**Root cause:** `DEFAULT_MAX_ANSWER_TOKENS = 800` quá thấp cho structured tables.

**Fix:** Tăng `DEFAULT_MAX_ANSWER_TOKENS` từ 800 → 2048 trong `backend/services/paper_conversations.py`. Project conversations import cùng constant nên cũng được benefit.

**Học được:** Token cap mặc định cần dimension theo output expected (table, list, paragraph). Cân nhắc adaptive cap theo prompt intent trong tương lai.

---

### Bug #5 — Writer UI "No project selected" với draft skeleton — 10/05/2026

**Người phụ trách:** Lâm

**Triệu chứng:** Bấm Writer → hiển thị đồng thời "No project selected" và loading skeleton.

**Root cause:** Writer page clear loading state sai chỗ + không restore route `project` query parameter trước khi fallback về localStorage.

**Fix:** Clear document loading state khi không có project active; restore query param trước; tránh clear saved active-project state trước khi restore. Regression test trong `tests/test_frontend_writer_static.py`.

**Học được:** State machine cho loading/empty/error phải tách biệt từng case. Source of truth ưu tiên: URL → localStorage → empty.

---

### Bug #6 — Code popover bị clipped bởi sidebar — 06/05/2026

**Người phụ trách:** Lâm

**Triệu chứng:** Date range popover trong admin usage dashboard bị che một nửa khi sidebar mở.

**Root cause:** `right-0` absolute positioning trong `overflow-y-auto` container làm popover overflow trái và bị clip.

**Fix:** Đổi `right-0` → `left-0` để giữ popover trong scrollable container.

**Học được:** Khi dùng absolute positioning trong overflow container, luôn check overflow direction trước. Browser agent reproduce bug rất hiệu quả ở case này.
