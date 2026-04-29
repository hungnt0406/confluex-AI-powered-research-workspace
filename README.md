# Automated Literature Review

[![CI](https://github.com/a20-ai-thuc-chien/A20-App-143/actions/workflows/ci.yml/badge.svg)](https://github.com/a20-ai-thuc-chien/A20-App-143/actions/workflows/ci.yml)

The repository now contains an async FastAPI backend, PostgreSQL/Alembic schema, multi-source paper search, relevance ranking, structured paper summaries, persisted PDF grounding chunks, persisted multi-turn paper conversations, persisted grounded writer outputs with QA validation, pytest coverage, and a minimal Next.js 14 frontend shell.

## Current scope

- Async FastAPI backend with `/auth`, `/projects`, and `/pipeline`
- JWT register/login flow and project CRUD
- SQLAlchemy 2.0 models plus Alembic migrations for project search settings, paper status, and summary error tracking
- Semantic Scholar and arXiv search across expanded queries with deduplication and filtering
- Relevance ranking via embeddings and structured summaries for top papers
- Discovery pipeline with `searcher -> reader` plus a warning branch when ranking returns too few papers
- Paginated `GET /projects/{id}/papers` endpoint for inspecting ranked/summarized papers
- On-demand `GET /projects/{id}/papers/{paper_id}/citation-graph` for exact-paper cited-by and reference lists via Semantic Scholar
- Grounded paper conversations with persisted first-turn and follow-up Q&A
- Project-scoped multi-paper grounded conversations for the main chat workspace
- User-invoked writer generation over selected papers with deterministic citation formatting, persisted outputs, and QA flags
- Project-scoped OpenRouter token usage telemetry with aggregate API
- Admin-only OpenRouter token usage monitoring across all users/projects
- Pytest fixtures for auth, projects, pipeline, services, graph flow, and searcher/reader behavior
- GitHub Actions CI for migrations, linting, type-checking, and tests

## Documentation map

- `README.md` is the current-state overview and setup entry point.
- `docs/feature-map.md` is the canonical feature-to-code/test/doc/config traceability map.
- `docs/backend-diagram.md` explains backend wiring, route ownership, and data flow.
- `docs/TEST_POSTMAN.md` covers manual API verification in Postman.
- `docs/features/upload_reference_file.md`, `docs/features/paper_citation_graph.md`, `docs/features/paper_conversations.md`, and `docs/features/writer_outputs.md` are feature deep dives.
- `docs/user-journey.md` describes the shipped and planned UX journey.
- `plans/` contains historical phase plans and roadmap material, not the canonical current-state docs.

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
- `GET /admin/access`
- `GET /admin/token-usage`
- `POST /projects`
- `GET /projects`
- `GET /projects/{id}`
- `GET /projects/{id}/token-usage`
- `PATCH /projects/{id}`
- `DELETE /projects/{id}`
- `POST /projects/{id}/run`
- `GET /projects/{id}/papers`
- `GET /projects/{id}/papers/{paper_id}/citation-graph`
- `POST /projects/{id}/papers/{paper_id}/conversations`
- `GET /projects/{id}/papers/{paper_id}/conversations`
- `GET /projects/{id}/papers/{paper_id}/conversations/{conversation_id}`
- `POST /projects/{id}/papers/{paper_id}/conversations/{conversation_id}/messages`
- `POST /projects/{id}/conversations`
- `POST /projects/{id}/conversations/stream`
- `GET /projects/{id}/conversations`
- `GET /projects/{id}/conversations/{conversation_id}`
- `POST /projects/{id}/conversations/{conversation_id}/messages`
- `POST /projects/{id}/conversations/{conversation_id}/messages/stream`
- `POST /projects/{id}/writer/generate`
- `GET /projects/{id}/writer/outputs/{output_id}`
- `GET /pipeline/health`

`POST /projects/{id}/run` now executes the phase-2 Searcher + Reader flow and returns query/count metadata for the completed run.
`PATCH /projects/{id}` renames an owned project without changing any of its persisted papers, conversations, or writer outputs.
`DELETE /projects/{id}` removes an owned project and cascades its persisted papers, conversations, writer outputs, and uploaded reference files; any stored PDF uploads are also unlinked from local disk on a best-effort basis.
`GET /admin/access` reports whether the authenticated user's email is included in the `ADMIN_EMAILS` allowlist.
`GET /admin/token-usage` returns admin-only global token usage totals, daily/feature/model breakdowns, user/project drilldowns, and all matching user log rows for the selected range with optional `date_from`, `date_to`, `user_id`, and `project_id` filters. Project chat usage rows include the persisted user prompt that produced the chat answer.
`GET /projects/{id}/token-usage` returns provider-reported token totals plus breakdowns by feature, model, and day for the authenticated user's project.
`GET /projects/{id}/papers/{paper_id}/citation-graph` resolves the exact paper in Semantic Scholar using its stored provider metadata, then returns both the papers that cite it and the papers it references.
`POST /projects/{id}/papers/{paper_id}/conversations` starts the first grounded paper-Q&A conversation, extracting PDF chunks on demand and falling back to metadata when chunk grounding is unavailable.
`POST /projects/{id}/papers/{paper_id}/conversations/{conversation_id}/messages` appends a grounded follow-up turn using the latest persisted conversation history plus newly retrieved paper chunks.
`GET /projects/{id}/papers/{paper_id}/conversations` and `GET /projects/{id}/papers/{paper_id}/conversations/{conversation_id}` expose summary/detail reads for the persisted paper-conversation state.
`POST /projects/{id}/conversations` starts a project-scoped chat over 0 to 5 selected papers, answering generally when no papers are selected and retrieving evidence across the selected set once papers are selected.
`POST /projects/{id}/conversations/stream` provides the same first-turn behavior over backend-proxied `text/event-stream`, emitting status, conversation, token, done, and error events for the main chat UI.
`POST /projects/{id}/conversations/{conversation_id}/messages` appends a follow-up turn for the current selected paper set; when the selected set changes, including being cleared, the conversation stores a system message describing the new selection before the user turn.
`POST /projects/{id}/conversations/{conversation_id}/messages/stream` provides the same follow-up behavior over `text/event-stream` while preserving usage telemetry and persisted message semantics.
`GET /projects/{id}/conversations` and `GET /projects/{id}/conversations/{conversation_id}` expose summary/detail reads for the persisted project-scoped multi-paper chat state.
`POST /projects/{id}/writer/generate` takes selected paper ids plus a free-form instruction, then returns a grounded writer artifact with format-aware citations, warnings, and QA flags.
`GET /projects/{id}/writer/outputs/{output_id}` rehydrates a persisted writer artifact without regenerating it.

## Quality gates

```bash
uv run ruff check .
uv run mypy backend/
uv run pytest tests/ -x
```

Tests use temporary SQLite databases by default for quick local runs. To run the same pytest suite against a dedicated PostgreSQL database, set `TEST_DATABASE_URL`; the test fixture refuses to reset Postgres databases whose name does not include `test` or `pytest`.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/literature_review_test \
  uv run pytest tests/ -x
```

## Notes

- Query expansion and structured summaries use OpenRouter chat completions when `OPENROUTER_API_KEY` is configured.
- Embeddings use OpenRouter's embeddings endpoint with `openai/text-embedding-3-small` by default.
- Live OpenRouter responses with provider usage metadata are persisted as compact project-scoped `ai_usage_events`; raw prompts, responses, abstracts, and PDF text are not stored in usage telemetry. The admin user log reads chat prompts from already-persisted project messages for display.
- `ADMIN_EMAILS` is a comma-separated allowlist for the admin usage monitor.
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

- Update `JOURNAL.md` before each PR with weekly learnings and shipped work.
- Update `WORKLOG.md` when the team makes meaningful technical decisions.
- AI tool prompts are logged automatically. See `AGENTS.md` for repository rules.
