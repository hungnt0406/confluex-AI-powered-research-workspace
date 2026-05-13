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
- `POST /projects/{id}/papers/import-citation` for adding missing citation-graph papers to a project with project-scoped dedupe
- Grounded paper conversations with persisted first-turn and follow-up Q&A
- Project-scoped multi-paper grounded conversations for the main chat workspace
- Project-scoped Deep Search mode with plan approval, visible thinking/progress, persisted runs, Tavily web search fallback, academic/project evidence, report streaming, source capture, and QA flags
- User-invoked writer generation over selected papers with deterministic citation formatting, persisted outputs, and QA flags
- User-owned writer documents that can start without a project, attach their own sources, upload PDFs, approve section outlines, and optionally import project papers as document sources
- Sepay/VietQR credit top-ups with payment orders, webhook confirmation, user credit ledger, signup credit grants, and quota enforcement on expensive research operations
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
`CORS_ALLOWED_ORIGINS` is comma-separated and defaults to local frontend origins; set it to the Vercel production URL for the deployed backend.
For credit top-ups, set `SEPAY_WEBHOOK_API_KEY`, `SEPAY_ACCOUNT_NUMBER`, `SEPAY_ACCOUNT_BANK_BIN`, and optionally `USD_TO_VND_RATE`; missing Sepay credentials still allow deterministic local/test QR payload generation.

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
- `GET /payments/packs`
- `POST /payments/orders`
- `GET /payments/orders/{order_id}`
- `GET /payments/balance`
- `POST /webhooks/sepay`
- `POST /projects`
- `GET /projects`
- `GET /projects/{id}`
- `GET /projects/{id}/token-usage`
- `PATCH /projects/{id}`
- `DELETE /projects/{id}`
- `POST /projects/{id}/run`
- `POST /projects/{id}/run/stream`
- `GET /projects/{id}/papers`
- `GET /projects/{id}/papers/{paper_id}/citation-graph`
- `POST /projects/{id}/papers/import-citation`
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
- `POST /writer/documents`
- `GET /writer/documents`
- `POST /projects/{id}/writer/documents`
- `GET /projects/{id}/writer/documents`
- `GET /writer/documents/{document_id}`
- `PATCH /writer/documents/{document_id}`
- `DELETE /writer/documents/{document_id}`
- `POST /writer/documents/{document_id}/sources/upload`
- `POST /writer/documents/{document_id}/sources/import-project`
- `POST /writer/documents/{document_id}/sources/attach`
- `POST /writer/documents/{document_id}/sources/attach-paper`
- `POST /projects/{id}/deep-search/stream`
- `GET /projects/{id}/deep-search-runs`
- `GET /projects/{id}/deep-search-runs/{run_id}`
- `GET /pipeline/health`

`POST /projects/{id}/run` now executes the phase-2 Searcher + Reader flow and returns query/count metadata for the completed run.
`POST /projects/{id}/run/stream` runs the same discovery pipeline over `text/event-stream`, emitting `status`, `papers`, `summary`, `done`, and `error` events so ranked related papers can appear before all summaries finish. The `papers` event is emitted after ranking commits, and each `summary` event reflects one newly persisted paper summary or summary error.
`PATCH /projects/{id}` renames an owned project without changing any of its persisted papers, conversations, or writer outputs.
`DELETE /projects/{id}` removes an owned project and cascades its persisted papers, conversations, writer outputs, and uploaded reference files; any stored PDF uploads are also unlinked from local disk on a best-effort basis.
`GET /admin/access` reports whether the authenticated user's email is included in the `ADMIN_EMAILS` allowlist. The same allowlist bypasses credit debits for paid research endpoints.
`GET /admin/token-usage` returns admin-only global token usage totals, daily/feature/model breakdowns, user/project drilldowns, and all matching user log rows for the selected range with optional `date_from`, `date_to`, `user_id`, and `project_id` filters. Project chat usage rows include the persisted user prompt that produced the chat answer.
`GET /payments/packs` returns the static credit pack catalog with USD cents, credit amounts, and current VND conversions. `POST /payments/orders` creates a pending Sepay/VietQR order for one pack and snapshots the VND amount, FX rate, reference code, receiving account, and QR URL. `GET /payments/orders/{order_id}` polls one owned order, while `GET /payments/balance` returns the authenticated user's balance, admin unlimited-credit flag, and recent ledger rows. `POST /webhooks/sepay` verifies `Authorization: Apikey <SEPAY_WEBHOOK_API_KEY>`, matches `ORD...` reference codes from incoming transfers, and credits paid orders idempotently.
`GET /projects/{id}/token-usage` returns provider-reported token totals plus breakdowns by feature, model, and day for the authenticated user's project.
`GET /projects/{id}/papers/{paper_id}/citation-graph` resolves the exact paper in Semantic Scholar using its stored provider metadata, then returns both the papers that cite it and the papers it references; each related paper includes its own `citation_count` so the frontend can render a Connected-Papers-style citation neighborhood graph in the right-hand context panel. The frontend caches graph payloads while the workspace is open, shows in-app node previews, marks nodes already in the project, offers an accessible list view, and can import missing related papers through `POST /projects/{id}/papers/import-citation`.
`POST /projects/{id}/papers/{paper_id}/conversations` starts the first grounded paper-Q&A conversation, extracting PDF chunks on demand and falling back to metadata when chunk grounding is unavailable.
`POST /projects/{id}/papers/{paper_id}/conversations/{conversation_id}/messages` appends a grounded follow-up turn using the latest persisted conversation history plus newly retrieved paper chunks.
`GET /projects/{id}/papers/{paper_id}/conversations` and `GET /projects/{id}/papers/{paper_id}/conversations/{conversation_id}` expose summary/detail reads for the persisted paper-conversation state.
`POST /projects/{id}/conversations` starts a project-scoped chat over 0 to 5 selected papers, answering generally when no papers are selected and retrieving evidence across the selected set once papers are selected.
`POST /projects/{id}/conversations/stream` provides the same first-turn behavior over backend-proxied `text/event-stream`, emitting status, conversation, token, done, and error events for the main chat UI.
`POST /projects/{id}/conversations/{conversation_id}/messages` appends a follow-up turn for the current selected paper set; when the selected set changes, including being cleared, the conversation stores a system message describing the new selection before the user turn.
`POST /projects/{id}/conversations/{conversation_id}/messages/stream` provides the same follow-up behavior over `text/event-stream` while preserving usage telemetry and persisted message semantics.
`GET /projects/{id}/conversations` and `GET /projects/{id}/conversations/{conversation_id}` expose summary/detail reads for the persisted project-scoped multi-paper chat state.
`POST /projects/{id}/deep-search/stream` creates a persisted Deep Search run, streams `run`, `status`, `source`, `token`, `done`, and `error` SSE events, uses selected project papers when provided, searches Semantic Scholar/arXiv, and uses Tavily web search when `TAVILY_API_KEY` is configured. The frontend shows a plan approval card before calling this endpoint and renders stream phases as an expandable thinking panel.
`GET /projects/{id}/deep-search-runs` and `GET /projects/{id}/deep-search-runs/{run_id}` expose persisted Deep Search run summaries, sources, reports, warnings, and QA flags.
`POST /projects/{id}/writer/generate` takes selected paper ids plus a free-form instruction, then returns a grounded writer artifact with format-aware citations, warnings, and QA flags.
`GET /projects/{id}/writer/outputs/{output_id}` rehydrates a persisted writer artifact without regenerating it.
Writer document routes under `/writer/documents` are user-owned and do not require an active project. Project-scoped writer document routes remain for compatibility and optional project association. Document sources live in `writer_document_sources`; source PDFs and search/manual attachments can create user-owned papers without a project, while `/sources/import-project` copies selected papers from an owned project into the writer document source set. Section drafts require an approved section outline first. Research-paper Methods and Results outlines use explicit LaTeX subsections for empirical protocol, baselines, metrics, findings, comparisons, errors, runtime, and robustness; survey-paper Methods and Results outlines use review-protocol and comparative-synthesis subsections for scope, literature selection, taxonomy, benchmark coverage, evaluation dimensions, cross-method findings, domain evidence, trade-offs, and gaps.

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

- The intended split deployment is Vercel for `frontend/`, Render Web Service for the FastAPI backend, Render Postgres for `DATABASE_URL`, and a Render persistent disk mounted at `/var/data` with `REFERENCE_UPLOAD_DIR=/var/data/reference_uploads`. See `plans/vercel-render-deployment-plan.md` for the provider-dashboard steps and smoke tests.
- Query expansion and structured summaries use OpenRouter chat completions when `OPENROUTER_API_KEY` is configured.
- Reference PDF uploads prefer local PyMuPDF text extraction and only fall back to the live PDF parser when local extraction cannot produce usable text.
- Project chat streaming waits up to `PROJECT_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` seconds for the first live answer token before falling back to the deterministic local answer; the default is 60 seconds.
- Deep Search uses `DEEP_SEARCH_*` model settings for planning, evidence compression, report writing, and verification. The stream also emits user-facing `activity` events so the thinking panel can show planned research paths, source counts, and source references while the run is in progress. Final reports ask the writer to attach URL-backed Markdown citations to factual sentences, and the chat UI renders those links as compact source buttons with hover previews. If `TAVILY_API_KEY` is missing, web search is skipped with a persisted warning while academic/project evidence still runs.
- Writer workspace source suggestions and auto-draft source fetching locally filter, dedupe, and rank candidates before drafting. Manual suggestions fetch 7 arXiv candidates plus 12 Tavily web candidates, auto-draft fetches 12 Tavily candidates for the active section and falls back to 7 arXiv candidates when no Tavily source can be used; both keep at most 7 sources. Writer documents are owned by the user, not by project chat state; projects are optional source providers. Section drafting is gated on an approved section outline, and research/survey Methods and Results drafts preserve approved LaTeX subsection structure. When `XIAOMI_MIMO_API_KEY` is set, source ranking uses Xiaomi MiMo through `WRITER_SOURCE_RANKER_MODEL` and `XIAOMI_MIMO_BASE_URL`; missing credentials or provider failures fall back to deterministic local ranking without OpenRouter.
- Writer generation uses `WRITER_GENERATION_TIMEOUT_SECONDS` for live draft requests; the default is 60 seconds because section drafts can include several source abstracts and take longer than smaller structured-output calls.
- Credit costs default to 20 credits for discovery pipeline runs, 80 for Deep Search, 40 for writer output, 2 for paper-chat follow-ups, and 5 for reference PDF uploads. Insufficient balances return HTTP 402 with `required` and `balance` fields.
- Embeddings use OpenRouter's embeddings endpoint with `openai/text-embedding-3-small` by default.
- Live OpenRouter responses with provider usage metadata are persisted as compact project-scoped `ai_usage_events`; raw prompts, responses, abstracts, and PDF text are not stored in usage telemetry. The admin user log reads chat prompts from already-persisted project messages for display.
- `ADMIN_EMAILS` is a comma-separated allowlist for the admin usage monitor and credit enforcement bypass. Allowlisted admins can run gated paid features with zero balance, and those requests do not create credit ledger debits.
- When those API keys are missing in local/dev/test environments, the pipeline falls back to deterministic offline behavior so the app and tests still run.
- Live API smoke tests for Semantic Scholar and arXiv are opt-in:

```bash
RUN_LIVE_API_TESTS=1 uv run pytest tests/test_services.py -m integration
```

- The search-quality evaluation harness is also opt-in:

```bash
RUN_EVAL_TESTS=1 uv run pytest tests/test_search_quality.py -m eval
```

- Deterministic agent and chat evaluation helpers (Reader summary coverage, Deep Search citation hygiene, paper-chat format and grounding proxies, Writer QA rollups) live in `backend/eval/metrics.py` with CI-safe coverage in `tests/test_eval_metrics.py`. To print sample metric outputs locally (no DB/API): `uv run python scripts/run_eval_metric_samples.py`.

## Project hygiene

- Update `JOURNAL.md` before each PR with weekly learnings and shipped work.
- Update `WORKLOG.md` when the team makes meaningful technical decisions.
- AI tool prompts are logged automatically. See `AGENTS.md` for repository rules.
