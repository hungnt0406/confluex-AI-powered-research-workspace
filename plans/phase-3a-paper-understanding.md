# Phase 3A — Paper Understanding Conversations

**Timeline:** Week 3 (additive track)  
**Goal:** Let a user pick a suggested paper and ask the system to understand that paper through grounded backend conversations with persisted memory.

> This plan is additive to `phase-3-writer-qa.md`. It does not replace the Writer + QA track.

---

## Summary

- Keep Phase 3A as the metadata foundation: persist `source_paper_id`, `source_url`, and `pdf_url` on `papers` so one selected paper can be revisited without re-running search.
- Replace the old Phase 3B "provider detail fetchers only" step with OpenRouter PDF grounding: send the paper PDF to OpenRouter `/api/v1/chat/completions` using `google/gemini-2.5-flash-lite`, normalize the parsed PDF content, and persist reusable chunks for retrieval-based Q&A.
- Do not add OCR in v1. Prefer OpenRouter `native` PDF handling for Gemini; if that is unavailable, retry with `cloudflare-ai` text parsing. If no usable PDF content is available, fall back to title + abstract + summary and explicitly limit the answer.

---

## Key Changes

### Phase 3A — Paper Metadata Foundation

- Persist `source_paper_id`, `source_url`, and `pdf_url` on `papers`.
- Keep `PaperRecord` strict so all search providers return those keys, with `None` when missing.
- Preserve existing `GET /projects/{id}/papers` behavior unless additive nullable fields are intentionally exposed later.

### Phase 3B — OpenRouter PDF Extraction and Chunk Storage

- Extend the existing OpenRouter-based LLM layer instead of adding a direct Gemini SDK.
- Add config for:
  - `OPENROUTER_DOCUMENT_MODEL`, default `google/gemini-2.5-flash-lite`
  - `OPENROUTER_PDF_ENGINE`, default `native`
  - `PDF_DOWNLOAD_TIMEOUT_SECONDS`
  - `PAPER_CHUNK_SIZE_CHARS`
  - `PAPER_RETRIEVAL_TOP_K`
- Add an OpenRouter document service, e.g. `backend/services/document_extraction.py`, that:
  - submits a public `pdf_url` as a `file` content part to `/api/v1/chat/completions`
  - uses model `google/gemini-2.5-flash-lite`
  - sets `plugins: [{ id: "file-parser", pdf: { engine: "native" } }]`
  - retries once with `engine: "cloudflare-ai"` if native PDF handling is rejected or unavailable
  - captures OpenRouter file annotations or parsed text content and normalizes them into page-aware text blocks
- Add `paper_documents` and `paper_chunks` persistence:
  - `paper_documents`: `paper_id`, `status` (`pending`, `ready`, `failed`), `source_pdf_url`, `openrouter_file_hash`, `page_count`, `error_message`, `extracted_at`
  - `paper_chunks`: `paper_id`, `chunk_index`, `page_start`, `page_end`, optional `section_title`, `content`, `embedding_json`
- Chunking flow:
  - normalize parsed PDF text into ordered text blocks
  - merge blocks into fixed-size chunks
  - embed chunks with the existing embedding service
  - persist chunks and embeddings for retrieval
- Do not download/store raw PDFs in the database.

### Phase 3C — Conversation Persistence

- Add `paper_conversations` and `paper_messages` tables scoped to a single paper.
- Store server-side history only; do not require the client to send prior turns.
- Enforce ownership through project + paper lookup.

### Phase 3D — First Ask Endpoint

- Add `POST /projects/{project_id}/papers/{paper_id}/conversations`
- Request body: `{ "question": string }`
- Behavior:
  - verify ownership
  - create conversation
  - ensure grounding is available
  - if chunks are missing and `pdf_url` exists, run extraction once
  - retrieve top-k chunks by cosine similarity against the question embedding
  - answer using retrieved chunks plus paper metadata
  - persist the first user/assistant turn
  - return `201 Created` with `Location`
- If extraction cannot produce chunks, answer from title + abstract + summary and include a limitation note.

### Phase 3E — Follow-Up Q&A

- Add `POST /projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}/messages`
- Load the newest 10 messages plus top-k retrieved chunks for the new question.
- Keep answers grounded in retrieved paper chunks first, metadata fallback second.

### Phase 3F — Read APIs and Cleanup

- Add `GET /projects/{project_id}/papers/{paper_id}/conversations`
- Add `GET /projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}`
- Add schemas for conversation summary, conversation detail, and message records.
- Update the plan text so Phase 3B explicitly means OpenRouter PDF grounding, not metadata-only enrichment.

---

## Public API and Interface Changes

- New config:
  - `OPENROUTER_DOCUMENT_MODEL=google/gemini-2.5-flash-lite`
  - `OPENROUTER_PDF_ENGINE=native`
  - `PDF_DOWNLOAD_TIMEOUT_SECONDS`
  - `PAPER_CHUNK_SIZE_CHARS`
  - `PAPER_RETRIEVAL_TOP_K`
- New internal types/tables:
  - `PaperDocument`
  - `PaperChunk`
  - `PaperConversation`
  - `PaperMessage`
- New endpoints:
  - `POST /projects/{project_id}/papers/{paper_id}/conversations`
  - `POST /projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}/messages`
  - `GET /projects/{project_id}/papers/{paper_id}/conversations`
  - `GET /projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}`
- Existing project and paper list endpoints remain additive and backward-compatible.

---

## Test Plan

- Metadata ingestion:
  - provider normalization persists `source_paper_id`, `source_url`, and `pdf_url`
  - legacy fixtures without those keys still persist safely as `None`
- OpenRouter PDF extraction:
  - public `pdf_url` with `native` engine produces normalized text blocks, document row, chunk rows, and embeddings
  - `native` engine failure retries with `cloudflare-ai`
  - missing `pdf_url` skips extraction and falls back to metadata-only answering
  - extraction failure marks document `failed` and preserves fallback answering
- Retrieval grounding:
  - first ask retrieves the most relevant stored chunks for the question
  - follow-up ask combines recent history with new retrieved chunks
  - no-chunk path answers from abstract/summary with a clear limitation note
- API and auth:
  - create conversation
  - continue conversation
  - list conversations
  - fetch one conversation
  - reject cross-user, cross-project, and mismatched `paper_id` / `conversation_id`
- Regression:
  - `mypy backend/`, `ruff check backend tests`, `pytest tests/ -x`, and `alembic upgrade head` remain passing
  - existing phase-2 searcher/reader/projects coverage stays green

---

## Assumptions

- OpenRouter supports PDF inputs through `/api/v1/chat/completions`, and Gemini is accessed through OpenRouter rather than a direct Google SDK.
- v1 only supports publicly accessible `pdf_url` values from searched papers. Local/private PDF upload is a separate future feature.
- OCR is out of scope for v1. If `native` PDF handling is unavailable, the only fallback parser is `cloudflare-ai`; scanned/image-only PDFs degrade to metadata-only answers.
- Retrieval uses the existing embedding service and cosine similarity utilities; no vector database is introduced in this phase.
- Persisted chunks are the long-term grounding source for Q&A; OpenRouter annotations are used only to derive those chunks and optionally to store the parsed file hash for traceability/cost avoidance.
