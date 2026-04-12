# Build Plan — Literature Review Multi-Agent

6-week plan to build and ship the AI20K-026 project.

## Phases

| Phase | File | Week | Goal |
|---|---|---|---|
| 1 | [phase-1-foundation.md](./phase-1-foundation.md) | Week 1 | Repo, DB, API clients, LangGraph skeleton |
| 2 | [phase-2-searcher-reader.md](./phase-2-searcher-reader.md) | Week 2 | Searcher + Reader agents working |
| 3 | [phase-3-writer-qa.md](./phase-3-writer-qa.md) | Week 3 | Writer + QA agents, Word export |
| 4 | [phase-4-ui-deployment.md](./phase-4-ui-deployment.md) | Week 4–5 | Full UI, SSE streaming, deployed URL |
| 5 | [phase-5-polish-demo.md](./phase-5-polish-demo.md) | Week 6 | User testing, demo prep, ship |

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
