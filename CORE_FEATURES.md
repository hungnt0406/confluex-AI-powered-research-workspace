# CORE FEATURES — BẮT BUỘC

| TÍNH NĂNG | KỸ THUẬT | PRIORITY |
| :--- | :--- | :--- |
| **Topic input & query engine** — nhận mô tả đề tài -> generate search queries đa chiều, không chỉ keywords | Prompt engineering + query expansion | P0 |
| **Paper search & ranking** — kết nối Semantic Scholar API + arXiv, rank theo semantic relevance (không phải citation count đơn thuần) | Semantic Scholar API, OpenAI Embeddings, cosine similarity | P0 |
| **Paper summarizer** — tóm tắt mỗi paper theo template: Problem / Method / Result / Relevance to your topic | LLM + structured output | P0 |
| **Literature review draft generator** — tổng hợp thành văn bản có narrative flow: intro -> themes -> gaps -> conclusion | LangGraph multi-agent (Searcher -> Reader -> Writer -> QA) | P0 |
| **Citation export** — export danh sách tài liệu tham khảo đúng format APA, IEEE, Chicago | Template formatting | P0 |
| **Draft export Word/LaTeX** — export draft với citations inline, đúng format journal mục tiêu | python-docx, pylatex | P0 |
| **Paper library (saved list)** — lưu papers, tag, annotate, tổ chức theo project | PostgreSQL | P0 |

# NICE-TO-HAVE — NÊN CÓ NẾU KỊP

| TÍNH NĂNG | KỸ THUẬT | PRIORITY |
| :--- | :--- | :--- |
| **Upload PDF của user** — user upload papers đã có -> hệ thống gợi ý papers còn thiếu dựa trên gap analysis | PyMuPDF + embeddings | P1 |
| **Timeline view** — visualize sự phát triển của một concept theo năm (2015 -> nay) | D3.js timeline | P1 |
| **Citation checker** — scan draft -> cảnh báo claim nào thiếu citation | LLM structured analysis | P2 |
| **Disagreement map** — tìm papers có kết quả mâu thuẫn nhau về cùng topic | LLM claim extraction + comparison | P2 |
| **Multi-project workspace** — quản lý nhiều đề tài nghiên cứu song song | PostgreSQL multi-tenant | Nice |
| **Share & collaborate** — chia sẻ project với advisor, comment trực tiếp trên draft | Real-time collab hoặc async | Nice |
