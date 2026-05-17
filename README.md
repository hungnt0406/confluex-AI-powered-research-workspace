# Automated Literature Review

> An AI-powered research assistant that automates the end-to-end literature review workflow — from paper discovery to grounded writing — so researchers spend their time thinking, not chasing PDFs.

**Live demo:** _Coming soon — link will be added here._

## Table of contents

- [Description](#description)
- [Problem & purpose](#problem--purpose)
- [Main features](#main-features)
- [Tech stack](#tech-stack)
- [Installation & setup](#installation--setup)
- [API surface](#api-surface)
- [Quality gates](#quality-gates)
- [Documentation map](#documentation-map)
- [Notes & operational details](#notes--operational-details)

## Description

Automated Literature Review is a full-stack research workspace built around a multi-agent LangGraph pipeline (**Searcher → Reader → Writer → QA**). It searches Semantic Scholar and arXiv, ranks results by topic relevance, summarizes selected papers, supports grounded chat over a single paper or a set of papers, runs Deep Search reports backed by web + academic sources, and produces citation-formatted drafts the user can refine inside a Monaco-based writer editor.

The system is split into an async FastAPI backend and a Next.js 14 frontend, with PostgreSQL for persistence, OpenRouter for LLM/embeddings, Tavily for web search, and SePay/VietQR for credit top-ups.

## Problem & purpose

Researchers, graduate students, and engineering teams who write surveys or related-work sections face the same friction every time:

- **Discovery is noisy.** Keyword search on Google Scholar, Semantic Scholar, and arXiv returns hundreds of candidates that have to be triaged by hand.
- **Reading is slow.** Skimming PDFs to extract problem/method/result for dozens of papers takes hours per topic.
- **Synthesis is error-prone.** Hand-assembled related-work sections drift from sources, miscite, or omit the strongest evidence.
- **Tooling is fragmented.** Search, note-taking, PDF chat, and writing usually live in four different apps with no shared state.

This project collapses those steps into a single workspace:

1. The Searcher agent expands queries, hits multiple databases, deduplicates, and ranks by embedding-based relevance.
2. The Reader agent produces structured per-paper summaries (problem / method / result / relevance).
3. Grounded chat and Deep Search let users interrogate the corpus with citations.
4. The Writer agent + editor produces a draft in IEEE / APA / Chicago / IMRAD format with reference lists ready for export.

The goal is to take a literature-review effort from days to hours while keeping every claim traceable to a source.

## Main features

### Discovery & ingestion
- Multi-source paper search across Semantic Scholar and arXiv with query expansion, dedupe, and year/relevance filtering.
- Embedding-based relevance ranking and structured summaries (problem / method / result / topic relevance) for top papers.
- Citation-graph exploration: pull cited-by / references for any paper and import missing neighbors into the project.
- User-uploaded reference PDFs with local PyMuPDF extraction and chunked storage for grounding.

### Grounded conversations
- **Paper chat** — multi-turn grounded Q&A scoped to a single paper, with persisted PDF chunks and conversation history.
- **Project chat** — multi-paper conversations across 0–5 selected papers, streamed over SSE.
- **Deep Search** — plan-approval flow that combines academic search, Tavily web search, and the project library into a streamed report with visible thinking, source capture, warnings, and QA flags.

### Writer & editor
- One-shot writer generation over selected papers with deterministic citation formatting (IEEE / APA / Chicago).
- User-owned writer documents that survive without a project, can import project papers or upload their own PDFs, and approve outlines before drafting.
- Monaco-based section editor with targeted edit/insert operations, low-confidence span highlighting, versioned history, and stale-preview guards.
- BibTeX + `\thebibliography` export.

### Billing & admin
- SePay/VietQR credit top-ups with payment orders, webhook settlement, signup credit grants, and quota enforcement on paid endpoints.
- Append-only credit ledger with feature-tagged debits and refunds.
- Admin allowlist (`ADMIN_EMAILS`) that bypasses credit gating and unlocks a global token-usage dashboard with daily / feature / model / per-user breakdowns.

### Reliability
- Deterministic offline fallbacks for LLM and embedding calls so local/dev/CI runs succeed without API keys.
- Server-sent events for discovery, project chat, Deep Search, and writer streaming.
- Pytest + Alembic + Ruff + mypy gates in CI on every PR.

## Tech stack

### Backend
- **Python 3.11+**, **FastAPI** (async), **uvicorn**
- **LangGraph** for the Searcher → Reader → Writer → QA pipeline
- **SQLAlchemy 2.0** (async) + **Alembic** migrations
- **PostgreSQL** (asyncpg) in production; SQLite for fast local tests
- **PyMuPDF** for local PDF extraction
- **pydantic-settings** for typed config, **python-jose** for JWT

### Frontend
- **Next.js 14** App Router, **React 18**, **TypeScript**
- **Tailwind CSS** for styling
- **Monaco Editor** for the writer surface
- **d3-force-3d** for the citation neighborhood graph
- Server-sent events for streaming chat, discovery, and Deep Search

### AI & external services
- **OpenRouter** — chat completions (`openai/gpt-*`, configurable per stage) and embeddings (`openai/text-embedding-3-small`)
- **Semantic Scholar** + **arXiv** APIs for paper discovery
- **Tavily** for Deep Search web evidence
- **SePay / VietQR** for credit top-ups (optional Xiaomi MiMo for writer source ranking)

### Tooling & ops
- **uv** for Python dependency management (pip shim available via `requirements.txt`)
- **Ruff**, **mypy** (`strict`), **pytest** + **pytest-asyncio**
- **GitHub Actions** for CI (migrations, lint, type-check, tests)
- Intended deployment: **Vercel** (frontend), **Render** Web Service (backend), **Render Postgres**, Render persistent disk for reference uploads

## Installation & setup

### Prerequisites
- Python **3.11+**
- Node.js **18+** and npm
- PostgreSQL **14+** (or use SQLite locally — the default fallback)
- [`uv`](https://docs.astral.sh/uv/) installed (`pip install uv` if needed)

### 1. Clone and install repository hooks

```bash
git clone https://github.com/a20-ai-thuc-chien/A20-App-143.git
cd A20-App-143
bash scripts/setup_hooks.sh
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Fill in at minimum:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres or SQLite connection string |
| `JWT_SECRET_KEY` | Secret for issuing JWT auth tokens |
| `OPENROUTER_API_KEY` | LLM + embeddings (optional — offline fallback exists) |
| `TAVILY_API_KEY` | Deep Search web evidence (optional) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated; defaults to local frontend origins |
| `ADMIN_EMAILS` | Comma-separated allowlist for admin features and credit bypass |
| `SEPAY_WEBHOOK_API_KEY`, `SEPAY_ACCOUNT_NUMBER`, `SEPAY_ACCOUNT_BANK_BIN` | SePay/VietQR top-ups (optional) |
| `USD_TO_VND_RATE` | Override the FX snapshot used at order creation |

Missing optional keys are fine — services degrade gracefully to deterministic offline behavior.

### 3. Install Python dependencies

```bash
uv sync --extra dev
```

`pip` is also supported:

```bash
pip install -r requirements.txt
```

### 4. Run database migrations and start the backend

```bash
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload
```

Backend listens on `http://localhost:8000`.

### 5. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`. Open it, register an account (signup grants 100 credits), and start a project.

### 6. (Optional) Seed admin access

Add your email to `ADMIN_EMAILS` in `.env` to unlock the admin token-usage dashboard at `/admin/usage` and bypass credit gating.

## API surface

Selected endpoints — see `docs/feature-map.md` and `docs/TEST_POSTMAN.md` for the full traceability matrix.

**Auth & billing**
- `POST /auth/register`, `POST /auth/login`
- `GET /admin/access`, `GET /admin/token-usage`
- `GET /payments/packs`, `POST /payments/orders`, `GET /payments/balance`, `POST /webhooks/sepay`

**Projects & discovery**
- `POST /projects`, `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}`, `DELETE /projects/{id}`
- `POST /projects/{id}/run`, `POST /projects/{id}/run/stream`
- `GET /projects/{id}/papers`, `GET /projects/{id}/papers/{paper_id}/citation-graph`
- `POST /projects/{id}/papers/import-citation`

**Conversations**
- `POST /projects/{id}/papers/{paper_id}/conversations` (+ messages, GET endpoints)
- `POST /projects/{id}/conversations`, `POST /projects/{id}/conversations/stream`
- `POST /projects/{id}/conversations/{conversation_id}/messages[/stream]`

**Deep Search**
- `POST /projects/{id}/deep-search/stream`
- `GET /projects/{id}/deep-search-runs[/{run_id}]`

**Writer**
- `POST /projects/{id}/writer/generate`, `GET /projects/{id}/writer/outputs/{output_id}`
- `POST /writer/documents`, `GET /writer/documents`, `GET|PATCH|DELETE /writer/documents/{id}`
- `POST /writer/documents/{id}/sources/{upload|import-project|attach|attach-paper}`
- `POST /writer/documents/{id}/sections/{section_id}/edit[/apply]`

## Quality gates

```bash
uv run ruff check .
uv run mypy backend/
uv run pytest tests/ -x
```

Tests use temporary SQLite databases by default. Point at a dedicated Postgres database via `TEST_DATABASE_URL` (must include `test` or `pytest` in the database name — the fixture refuses to reset unrelated databases):

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/literature_review_test \
  uv run pytest tests/ -x
```

Opt-in suites:

```bash
RUN_LIVE_API_TESTS=1 uv run pytest tests/test_services.py -m integration
RUN_EVAL_TESTS=1     uv run pytest tests/test_search_quality.py -m eval
```

## Documentation map

- `README.md` — current-state overview and setup entry point (this file).
- `docs/database.md` — full database schema with Mermaid ERD.
- `docs/backend-diagram.md` — backend wiring, route ownership, data flow.
- `docs/feature-map.md` — feature-to-code/test/doc/config traceability.
- `docs/user-journey.md` — shipped and planned UX journey.
- `docs/TEST_POSTMAN.md` — manual API verification recipes.
- `docs/features/` — per-feature deep dives (reference upload, citation graph, paper conversations, writer outputs, etc.).
- `plans/` — historical phase plans and roadmap material (not canonical current state).

## Notes & operational details

- **Deployment target.** Vercel for `frontend/`, Render Web Service for FastAPI, Render Postgres for `DATABASE_URL`, Render persistent disk at `/var/data` with `REFERENCE_UPLOAD_DIR=/var/data/reference_uploads`. See `plans/vercel-render-deployment-plan.md`.
- **Offline fallbacks.** When `OPENROUTER_API_KEY` / external keys are missing, `llm.py`, `embeddings.py`, and Tavily integration return deterministic results so the app and tests still run.
- **Credit costs (defaults).** Discovery run 20, Deep Search 80, writer generation 40, paper-chat follow-up 2, reference PDF upload 5. Writer editor previews: 1 (fix), 2 (paragraph), 3 (incorporate); web search raises generation/incorporation to 4/5. Insufficient balance returns HTTP 402 with `required` and `balance` fields.
- **Token telemetry.** Provider-reported usage is persisted as compact `ai_usage_events`; raw prompts and PDF text are never stored in telemetry.
- **Project chat streaming** waits up to `PROJECT_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` (default 60s) for the first live token before falling back to the deterministic local answer.
- **Deep Search** uses `DEEP_SEARCH_*` model settings for planning, evidence compression, report writing, and verification. Missing `TAVILY_API_KEY` skips web search with a persisted warning while academic/project evidence still runs.
- **Writer source ranking.** When `XIAOMI_MIMO_API_KEY` is set, ranking uses Xiaomi MiMo via `WRITER_SOURCE_RANKER_MODEL` and `XIAOMI_MIMO_BASE_URL`; otherwise it falls back to deterministic local ranking.
- **Project hygiene.** Update `JOURNAL.md` before each PR with weekly learnings and shipped work; update `WORKLOG.md` for meaningful technical decisions. AI tool prompts are logged automatically — see `AGENTS.md`.
