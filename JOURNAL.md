# Weekly Journal

Ghi lại hành trình xây dựng sản phẩm mỗi tuần — những gì đã làm, học được gì, AI giúp như thế nào.

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

---

### Tuần 1 — 05/04/2026

**Thành viên:** tungnguyenlam (Lead)

#### Đã làm
- **Thiết kế Kiến trúc RAG-First**: Xây dựng kế hoạch chi tiết (`PLAN.md` và `implementation_plan.md`) tập trung vào việc giảm thiểu chi phí API bằng cách chỉ dùng LLM ở bước tổng hợp cuối cùng.
- **Tái cấu trúc Project**: Chuyển đổi từ code mẫu sang cấu trúc module chuyên nghiệp (`src/pipeline`, `src/sources`, `src/indexing`, `src/db`, `src/auth`).
- **Thiết lập Database**: Cài đặt PostgreSQL v17, cấu tạo Schema với 5 bảng chính và khởi tạo thành công qua SQLAlchemy.
- **Phát triển UI Shell**: Hoàn thiện khung ứng dụng Streamlit với hệ thống Multi-page, giao diện Dark mode cao cấp và tích hợp Authentication (admin/admin123).
- **Scaffolding Pipeline**: Định nghĩa `PipelineState` và các wrapper cho Embedding (all-MiniLM-L6-v2) và Vector Store (ChromaDB).

#### Khó nhất tuần này
- Cấu hình PostgreSQL trên macOS gặp lỗi `Connection refused` do dịch vụ Brew không tự chạy — xử lý bằng cách khởi tạo và chạy thủ công qua `pg_ctl`.
- Đảm bảo tính nhất quán của dữ liệu khi truyền qua các node trong LangGraph (đã giải quyết bằng Pydantic `PipelineState`).

#### AI tool đã dùng
| Tool | Dùng để làm gì | Kết quả |
|---|---|---|
| Gemini (Antigravity) | Lập kế hoạch, sinh code kiến trúc, cấu hình DB và UI | Hoàn thành toàn bộ Phase 1 trong nửa ngày |

#### Học được
- Cách tối ưu chi phí RAG bằng cách tách biệt bước lọc (Embedding-based) và bước tổng hợp (LLM-based).
- Quản lý session và auth trong Streamlit kết hợp với PostgreSQL.
- Tầm quan trọng của việc thiết kế `PipelineState` chặt chẽ ngay từ đầu để tránh bug khi mở rộng pipeline.

#### Nếu làm lại, sẽ làm khác
- Sẽ kiểm tra version PostgreSQL của Homebrew kỹ hơn trước khi install để tránh xung đột version cũ.

#### Kế hoạch tuần tới (Phase 2)
- Triển khai 3 API Client: Semantic Scholar, arXiv và PubMed.
- Xây dựng logic xử lý rate limit và retry thông minh cho các nguồn dữ liệu học thuật.
- Bắt đầu thực hiện Stage 1 & 2 của pipeline (Search & Filter).
