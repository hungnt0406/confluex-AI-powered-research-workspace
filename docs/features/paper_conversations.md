# Paper Conversations

This document describes the grounded paper Q&A feature for project papers.

## HTTP Endpoints

| Action | Method | Path |
|---|---|---|
| Create first-turn paper conversation | `POST` | `/projects/{project_id}/papers/{paper_id}/conversations` |
| Add follow-up message | `POST` | `/projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}/messages` |
| List conversations for a paper | `GET` | `/projects/{project_id}/papers/{paper_id}/conversations` |
| Get one conversation | `GET` | `/projects/{project_id}/papers/{paper_id}/conversations/{conversation_id}` |

Router ownership: `backend/api/routers/projects.py`

## Main Code Locations

- Route handlers: `backend/api/routers/projects.py`
- Schemas: `backend/api/schemas/projects.py`
- Conversation service: `backend/services/paper_conversations.py`
- PDF extraction and chunk persistence: `backend/services/document_extraction.py`
- Persistence models: `backend/db/models.py`

## Conversation Flow

1. The route verifies project ownership and loads the target paper.
2. `PaperConversationService` normalizes the question and creates or loads the conversation context.
3. The service loads persisted `paper_chunks` for the paper.
4. If chunks do not exist and the paper has a `pdf_url`, `PaperDocumentExtractionService` extracts the PDF, persists `paper_documents` and `paper_chunks`, and stores embeddings for retrieval.
5. The service embeds the user question, ranks the most relevant chunks by cosine similarity, and uses the top-k chunks for answer generation.
6. If chunk grounding is unavailable, the service falls back to paper metadata and summary fields.
7. The user and assistant messages are persisted in `paper_messages`, and the conversation is returned.

## Persistence Model

- `paper_conversations` stores conversation headers and timestamps.
- `paper_messages` stores the ordered user and assistant turns.
- `paper_documents` stores extraction status for a paper PDF.
- `paper_chunks` stores chunk text, section/page metadata, and embeddings used for retrieval.

## Grounding Behavior

- Preferred path: answer from retrieved PDF chunks.
- Fallback path: answer from abstract and summary metadata if extraction fails or no chunks exist.
- Follow-up turns use recent persisted conversation history plus newly retrieved chunks for the new question.

## Related Tests

- `tests/test_paper_conversations.py`
- `tests/test_document_extraction.py`

These tests cover:

- first-turn grounded answers from existing chunks
- on-demand extraction when chunks are missing
- metadata fallback when extraction fails
- follow-up persistence and history reuse
- ownership and route mismatch checks

## Related Docs

- `README.md`
- `docs/backend-diagram.md`
- `docs/TEST_POSTMAN.md`
- `docs/user-journey.md`
- `plans/phase-3a-paper-understanding.md`
