# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. It combines project-specific guidance with the Everything Claude Code (ECC) agent instructions defined in `.codex/AGENTS.md`.

## Project

Automated Literature Review: async FastAPI backend + Next.js 14 frontend shell. Runs a LangGraph pipeline (Searcher → Reader → Writer → QA) over Semantic Scholar / arXiv to produce ranked papers, structured summaries, grounded paper conversations, and grounded writer drafts with citation export.

## Common commands

Dependencies / setup:
```bash
bash scripts/setup_hooks.sh          # install git pre-push AI log hook (one-time)
cp .env.example .env                 # set DATABASE_URL, JWT_SECRET_KEY, OPENROUTER_API_KEY
uv sync --extra dev
```

Backend:
```bash
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload
```

Frontend:
```bash
cd frontend && npm install && npm run dev
```

Quality gates (must pass in CI):
```bash
uv run ruff check .
uv run mypy backend/
uv run pytest tests/ -x
```

Run a single test:
```bash
uv run pytest tests/test_pipeline.py::test_name -x
```

Opt-in suites (skipped by default):
```bash
RUN_LIVE_API_TESTS=1 uv run pytest tests/test_services.py -m integration
RUN_EVAL_TESTS=1     uv run pytest tests/test_search_quality.py -m eval
```

## Architecture

Layered async FastAPI app. Keep external I/O (HTTP, LLM, embeddings, PDF extraction) inside `backend/services/`; keep pipeline orchestration inside `backend/agents/`; keep HTTP concerns (routers, schemas, deps) inside `backend/api/`.

- `backend/main.py`, `backend/config.py`, `backend/security.py` — app factory, pydantic-settings config, JWT.
- `backend/api/routers/` + `backend/api/schemas/` — `/auth`, `/projects`, `/pipeline`. `POST /projects/{id}/run` drives the Searcher+Reader flow; `POST /projects/{id}/writer/generate` invokes the writer agent; paper conversations live under `/projects/{id}/papers/{paper_id}/conversations`.
- `backend/agents/` — LangGraph pipeline. `state.py` defines shared state; `graph.py` wires `searcher.py → reader.py → writer.py → qa.py` with a warning branch when ranking yields too few papers. `pipeline.py` is the entry point used by the API.
- `backend/services/` — `semantic_scholar.py`, `arxiv.py` (search + dedup), `embeddings.py` (OpenRouter `openai/text-embedding-3-small`, cosine rank), `llm.py` (OpenRouter chat for query expansion + structured summaries), `document_extraction.py` (PyMuPDF chunking for grounding), `paper_conversations.py`, `writer_outputs.py`, `citations.py` (APA/IEEE/Chicago formatting), `reference_files.py`, `research_utils.py`.
- `backend/db/` — SQLAlchemy 2.0 async models, session factory, Alembic migrations (project search settings, paper status, summary error tracking, persisted conversations and writer outputs). Add new schema changes as Alembic revisions.
- `tests/` — pytest-asyncio (`asyncio_mode = auto`). Fixtures cover auth, projects, pipeline, graph flow, searcher/reader, services. Live API and eval tests are gated by env markers above.

Frontend pages (`frontend/app/`):
- `chat/page.tsx` — main research workspace (requires auth); sidebar (`components/Sidebar.tsx`) has New Research, project list, Plans link, admin link, logout.
- `login/page.tsx` — email + Google OAuth login.
- `admin/usage/` — token usage dashboard (admin-only).
- `pricing/page.tsx` — standalone public pricing page (no auth); billing toggle, 4-tier plan cards, comparison table, add-ons, FAQ, CTA. Linked from the sidebar "Plans" button.

Offline fallback is a hard requirement: when `OPENROUTER_API_KEY` / external keys are missing (local, dev, CI, tests), services must return deterministic offline results so the pipeline and tests still pass. Preserve this when editing `llm.py`, `embeddings.py`, or the agent nodes.

## Core Principles (from ECC)

1. **Agent-First** — Delegate domain tasks to specialized agents instead of doing everything in the main context.
2. **Test-Driven** — Write tests before implementation; aim for 80%+ coverage on changed code.
3. **Security-First** — Never compromise on security; validate all inputs at system boundaries.
4. **Immutability** — Always create new objects/state; never mutate shared state in place.
5. **Plan Before Execute** — Plan complex features (planner/architect agent) before writing code.

## Agent Orchestration

Use specialized agents proactively without waiting for the user to ask. Launch independent agents in parallel (single message, multiple Agent tool calls).

| Trigger | Agent |
|---------|-------|
| Complex feature request, refactor | `planner` |
| Architectural decision, scalability | `architect` |
| New feature or bug fix | `tdd-guide` |
| After writing/modifying code | `code-reviewer` |
| Sensitive code, before commit | `security-reviewer` |
| Build/type errors | `build-error-resolver` |
| Critical user flows | `e2e-runner`, `frontend-qa-tester` |
| Python code review | `python-reviewer` |
| TypeScript/Next.js review | `typescript-reviewer` |
| PostgreSQL/Supabase schema or queries | `database-reviewer` |
| Doc/codemap updates | `doc-updater` |
| Dead code cleanup | `refactor-cleaner` |
| Autonomous loop monitoring | `loop-operator` |
| Harness reliability/cost | `harness-optimizer` |

Full agent list lives in `.codex/AGENTS.md`. Available skills are auto-loaded from `.agents/skills/` (see `.codex/AGENTS.md` for the catalog: `tdd-workflow`, `security-review`, `backend-patterns`, `frontend-patterns`, `e2e-testing`, `verification-loop`, `claude-api`, etc.).

## Security Guidelines

Before any commit:
- No hardcoded secrets (API keys, passwords, tokens) — use env vars / `.env` (already gitignored).
- All user inputs validated at system boundaries (API routers, form handlers).
- Parameterized queries only — no string-concatenated SQL.
- Sanitize HTML to prevent XSS; CSRF protection on state-changing endpoints.
- Auth/authorization verified on every protected route (`backend/api/deps.py`).
- Error messages must not leak stack traces, secrets, or internal paths.

If a security issue is found: **STOP** → invoke `security-reviewer` → fix CRITICAL issues → rotate exposed secrets → sweep the codebase for similar patterns.

## Coding Style

- **Immutability** — Return new objects with changes applied; do not mutate shared state in place.
- **File organization** — Many small files over a few large ones. Target 200–400 lines, hard cap ~800. Organize by feature/domain (already the case in `backend/services/`, `backend/agents/`, `backend/api/`).
- **Function size** — Keep functions <50 lines; avoid nesting beyond 4 levels.
- **Error handling** — Handle errors at every level; user-friendly messages in API/UI; detailed structured logs server-side; never silently swallow errors.
- **Input validation** — Schema-based validation (pydantic) at boundaries; fail fast with clear messages.
- **Comments** — Default to none. Only add when the *why* is non-obvious (constraints, invariants, workarounds). Names should explain *what*.

## Testing Requirements

Minimum coverage on changed code: **80%**.

Required test types:
1. **Unit** — pure functions, utilities, components.
2. **Integration** — API endpoints, DB operations (use the existing async fixtures).
3. **E2E** — critical user flows (Playwright via `e2e-runner` / `frontend-qa-tester`).

TDD loop (mandatory for new features and bug fixes):
1. **RED** — write the failing test first.
2. **GREEN** — minimal implementation to pass.
3. **REFACTOR** — clean up; verify coverage remains ≥80%.

Troubleshooting failures: check test isolation → verify mocks/fixtures → fix the implementation (do not bend tests to pass unless the test itself is wrong).

Preserve offline fallbacks in tests: when `OPENROUTER_API_KEY` is unset, `llm.py` / `embeddings.py` must still return deterministic results so the suite is hermetic.

## Development Workflow

1. **Plan** — `planner` agent for non-trivial work; identify dependencies, risks, phases.
2. **TDD** — `tdd-guide` agent; write tests first, implement, refactor.
3. **Review** — `code-reviewer` agent immediately after writing code; address CRITICAL/HIGH findings before commit.
4. **Capture knowledge in the right place**
   - Personal debugging notes / preferences / temporary context → auto memory.
   - Team/project knowledge (architecture, API changes, runbooks) → existing project docs (`JOURNAL.md`, `AI_WORKLOG.md`, `WORKLOG.md`).
   - Don't duplicate information that already lives in code comments or commit messages.
5. **Commit** — Conventional commits format; comprehensive PR summaries.

## Repo conventions (from AGENTS.md)

- AI prompt logging is automatic via hooks in `.claude/`, `.cursor/`, `.codex/`, `.gemini/`, `.github/hooks/` writing to `.ai-log/session.jsonl` (gitignored). Do not ask users to log prompts manually; do not commit `.ai-log/*.jsonl`.
- Update `JOURNAL.md` whenever repository changes are made (timestamped entry: request, files changed, status). Use `AI_WORKLOG.md` as the detail reference. Update `WORKLOG.md` for meaningful technical decisions.
- PR description must follow:
  ```
  ## Summary
  <description>

  ## Changes
  - <list of changed files>
  ```
- Before opening a PR, ensure `bash scripts/setup_hooks.sh` has been run.

## Git Workflow

- **Commit format** — `<type>: <description>` (types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`).
- **PR workflow** — Analyze full commit history → draft summary covering all commits (not just the latest) → include test plan → push with `-u` flag.
- Never `--no-verify`, never force-push to `main`/`master`, never amend already-pushed commits without explicit user approval.

## Tooling config

- Python ≥ 3.11, ruff (line 100, selects `E,F,I,B,UP,ASYNC`), mypy `strict = true` (excludes `frontend/` and `backend/db/migrations/`), black line-length 100.
- Package managed by `uv` via `pyproject.toml`; `requirements.txt` is a pip compatibility shim only.

## Performance & Context

- Avoid the last ~20% of context window for large multi-file refactors; offload research/searches to subagents.
- Use `Explore` / `general-purpose` subagents for broad codebase searches that span >3 queries; use `grep`/`find` directly for narrow lookups.
- Build failures → `build-error-resolver` (or `pytorch-build-resolver` for PyTorch/CUDA issues).

## Reference

- Full agent + skill catalog and ECC-wide policy: `.codex/AGENTS.md`.
- Codex CLI specifics (multi-agent flag, MCP baseline, sync script): `.codex/AGENTS.md` § "ECC for Codex CLI".
