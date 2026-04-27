# Phase 1 — Foundation & Scaffolding

**Timeline:** Week 1  
**Goal:** A working skeleton you can run end-to-end with dummy data — no real AI yet.

> Do NOT touch the LLM yet. Hardcode responses. The goal is a plumbing test, not an AI test.

---

## Tasks

### 1. Repo & environment
- Init Python monorepo with `pyproject.toml` (use `uv` or `poetry`)
- `.env.example` with all required keys: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `SEMANTIC_SCHOLAR_API_KEY`
- Pre-commit hooks: `ruff` (lint), `mypy` (types), `black` (format)
- Folder structure:
  ```
  /backend
    /agents       ← one file per agent
    /api          ← FastAPI routers
    /db           ← models + migrations
    /services     ← external API clients
  /frontend       ← Next.js app
  /tests
  ```

### 2. Database schema
- PostgreSQL via SQLAlchemy + Alembic migrations
- Tables to create:

| Table | Key columns |
|---|---|
| `users` | id, email, hashed_password, created_at |
| `projects` | id, user_id, title, topic_description, citation_format, created_at |
| `papers` | id, project_id, title, authors, year, abstract, doi, source, relevance_score |
| `summaries` | id, paper_id, problem, method, result, relevance_to_topic |
| `drafts` | id, project_id, outline_json, content, word_count, qa_flags_json, created_at |

- Run `alembic upgrade head` to verify migrations work cleanly.

### 3. External API clients
- **Semantic Scholar** (`/services/semantic_scholar.py`):
  - `search_papers(query, year_start, limit)` → list of paper dicts
  - Handle rate limits (3 req/s on free tier) with `asyncio.Semaphore`
  - Test: assert a known paper title appears in results for a known query
- **arXiv** (`/services/arxiv.py`):
  - `search_papers(query, year_start, limit)` → same schema
  - Parse XML response (use `feedparser`)
  - Test: assert results are returned and have required fields

### 4. LangGraph state graph skeleton
- Define `AgentState` dataclass:
  ```python
  @dataclass
  class AgentState:
      project_id: str
      topic: str
      queries: list[str] = field(default_factory=list)
      raw_papers: list[dict] = field(default_factory=list)
      ranked_papers: list[dict] = field(default_factory=list)
      summaries: list[dict] = field(default_factory=list)
      draft: str = ""
      qa_flags: list[str] = field(default_factory=list)
      errors: list[str] = field(default_factory=list)
  ```
- Wire 4 empty nodes with `print()` logging only:
  ```
  searcher_node → reader_node → writer_node → qa_node
  ```
- Confirm graph compiles and runs without error on dummy state.

### 5. Auth & API scaffold
- FastAPI app with routers: `/auth`, `/projects`, `/pipeline`
- JWT login + register (`/auth/login`, `/auth/register`)
- Project CRUD: `POST /projects`, `GET /projects`, `GET /projects/{id}`
- Placeholder `POST /projects/{id}/run` that returns `{"status": "queued"}`
- Pytest fixtures: test DB, test client, sample user + project

### 6. CI pipeline
- GitHub Actions workflow on every push:
  - `ruff check .`
  - `mypy backend/`
  - `pytest tests/ -x`
- Badge in README showing CI status

---

## End-of-phase checkpoint

- [ ] Repo pushed, CI green
- [ ] `alembic upgrade head` runs without error
- [ ] Semantic Scholar and arXiv clients return real paper data
- [ ] LangGraph graph runs dummy nodes start-to-finish with logging
- [ ] `POST /auth/login` returns a JWT
- [ ] All pytest fixtures pass

---

## Key decisions to make this week

- **Async or sync FastAPI?** → Use `async def` everywhere. The pipeline will need `asyncio.gather()` in Phase 2.
- **ORM choice?** → SQLAlchemy 2.0 with async engine (`asyncpg` driver).
- **Frontend framework?** → Next.js 14 (App Router). Init now, leave mostly empty until Phase 4.
