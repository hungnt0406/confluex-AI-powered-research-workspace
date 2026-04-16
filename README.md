# Automated Literature Review

[![CI](https://github.com/a20-ai-thuc-chien/A20-App-143/actions/workflows/ci.yml/badge.svg)](https://github.com/a20-ai-thuc-chien/A20-App-143/actions/workflows/ci.yml)

The repository now contains an async FastAPI backend, PostgreSQL/Alembic schema, multi-source paper search, relevance ranking, structured paper summaries, persisted PDF grounding chunks, persisted multi-turn paper conversations, pytest coverage, and a minimal Next.js 14 frontend shell.

## Phase 2 scope

- Async FastAPI backend with `/auth`, `/projects`, and `/pipeline`
- JWT register/login flow and project CRUD
- SQLAlchemy 2.0 models plus Alembic migrations for project search settings, paper status, and summary error tracking
- Semantic Scholar and arXiv search across expanded queries with deduplication and filtering
- Relevance ranking via embeddings and structured summaries for top papers
- LangGraph pipeline with `searcher -> reader -> writer -> qa` plus a warning branch when ranking returns too few papers
- Paginated `GET /projects/{id}/papers` endpoint for inspecting ranked/summarized papers
- Pytest fixtures for auth, projects, pipeline, services, graph flow, and searcher/reader behavior
- GitHub Actions CI for migrations, linting, type-checking, and tests

## Repository layout

```text
backend/
  agents/      LangGraph state and dummy pipeline nodes
  api/         FastAPI routers, dependencies, and schemas
  db/          SQLAlchemy models, sessions, and Alembic files
  services/    External API clients for paper search
frontend/      Next.js 14 App Router shell
plans/         Delivery plans for each phase
scripts/       AI logging and repository utility scripts
tests/         Async pytest suite and fixtures
```

## Local setup

### 1. Install repository hooks

```bash
bash scripts/setup_hooks.sh
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Fill in the values you need locally, especially `DATABASE_URL`, `JWT_SECRET_KEY`, and `OPENROUTER_API_KEY`.

### 3. Install Python dependencies

```bash
uv sync --extra dev
```

If you prefer `pip`, the compatibility entrypoint remains available:

```bash
pip install -r requirements.txt
```

### 4. Run the backend

```bash
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload
```

### 5. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

## API surface

- `POST /auth/register`
- `POST /auth/login`
- `POST /projects`
- `GET /projects`
- `GET /projects/{id}`
- `POST /projects/{id}/run`
- `GET /projects/{id}/papers`
- `POST /projects/{id}/papers/{paper_id}/conversations`
- `GET /projects/{id}/papers/{paper_id}/conversations`
- `GET /projects/{id}/papers/{paper_id}/conversations/{conversation_id}`
- `POST /projects/{id}/papers/{paper_id}/conversations/{conversation_id}/messages`
- `GET /pipeline/health`

`POST /projects/{id}/run` now executes the phase-2 Searcher + Reader flow and returns query/count metadata for the completed run.
`POST /projects/{id}/papers/{paper_id}/conversations` starts the first grounded paper-Q&A conversation, extracting PDF chunks on demand and falling back to metadata when chunk grounding is unavailable.
`POST /projects/{id}/papers/{paper_id}/conversations/{conversation_id}/messages` appends a grounded follow-up turn using the latest persisted conversation history plus newly retrieved paper chunks.
`GET /projects/{id}/papers/{paper_id}/conversations` and `GET /projects/{id}/papers/{paper_id}/conversations/{conversation_id}` expose summary/detail reads for the persisted paper-conversation state.

## Quality gates

```bash
uv run ruff check .
uv run mypy backend/
uv run pytest tests/ -x
```

## Notes

- Query expansion and structured summaries use OpenRouter chat completions when `OPENROUTER_API_KEY` is configured.
- Embeddings use OpenRouter's embeddings endpoint with `openai/text-embedding-3-small` by default.
- When those API keys are missing in local/dev/test environments, the pipeline falls back to deterministic offline behavior so the app and tests still run.
- Live API smoke tests for Semantic Scholar and arXiv are opt-in:

```bash
RUN_LIVE_API_TESTS=1 uv run pytest tests/test_services.py -m integration
```

- The search-quality evaluation harness is also opt-in:

```bash
RUN_EVAL_TESTS=1 uv run pytest tests/test_search_quality.py -m eval
```

## Project hygiene

- Update [JOURNAL.md](/Users/hungcucu/Documents/VinAI/A20-App-143/JOURNAL.md) before each PR with weekly learnings and shipped work.
- Update [WORKLOG.md](/Users/hungcucu/Documents/VinAI/A20-App-143/WORKLOG.md) when the team makes meaningful technical decisions.
- AI tool prompts are logged automatically. See [AGENTS.md](/Users/hungcucu/Documents/VinAI/A20-App-143/AGENTS.md) for repository rules.
