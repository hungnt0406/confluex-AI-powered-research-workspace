# Build Plan — Literature Review Multi-Agent

6-week plan to build and ship the AI20K-026 project.

## Phases

### Completed
- [Phase 1: Foundation](./completed/phase-1-foundation.md)
- [Phase 2: Searcher + Reader](./completed/phase-2-searcher-reader.md)
- [Phase 3: Writer + QA](./completed/phase-3-writer-qa.md)
- [Phase 3A: Paper Understanding](./completed/phase-3a-paper-understanding.md)

### In-Progress (Missing Basic Features)
- [Phase 4A: Export Infrastructure](./in-progress/phase-4a-export-infrastructure.md)
- [Phase 4B: Advanced Research Settings](./in-progress/phase-4b-advanced-settings.md)
- [Phase 4C: UI Refinements & Hardening](./in-progress/phase-4c-ui-refinements.md)

## Cost estimate (per full pipeline run)

| Phase | Operations | Est. cost |
|---|---|---|
| Phase 2 | Query expansion + embeddings + summaries | ~$0.08 |
| Phase 3 | Theme clustering + drafting + QA | ~$0.18 |
| **Total** | | **~$0.26 per run** |

## Tech stack

| Layer | Technology |
|---|---|
| Agent framework | LangGraph |
| LLM | Claude Sonnet (Anthropic API) |
| Paper search | Semantic Scholar API + arXiv API |
| Embeddings | OpenAI text-embedding-3-small |
| Backend | FastAPI (async) + PostgreSQL + Alembic |
| Frontend | Next.js 14 (App Router) |
| Export | python-docx |
| Deployment | Railway (backend) + Vercel (frontend) |
| Streaming | Server-Sent Events (SSE) |
