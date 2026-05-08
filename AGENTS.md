# Agent Guidelines

This file is the first stop for AI coding agents working in this repository. It combines repository rules with the product context needed to make safe, project-aware changes.

## Project Context

This repository is an **Automated Literature Review** application for researchers. The product helps a user move from a fuzzy research topic to:

- a persisted project workspace,
- ranked and summarized academic papers,
- uploaded reference PDFs that seed and ground the project,
- grounded paper/project conversations,
- Deep Search research reports with visible progress and source capture,
- grounded writer outputs with citation/reference formatting and QA validation,
- token usage visibility for users and admins.

The backend is an async FastAPI app with SQLAlchemy 2.0, Alembic migrations, PostgreSQL-compatible models, external academic/web search clients, OpenRouter-backed LLM services, and pytest coverage. The frontend is a Next.js App Router chat workspace with login, sidebar projects, related-paper context, selected-paper Q&A, reference PDF upload, Deep Search plan approval, thinking/progress display, source previews, and admin usage pages.

Canonical project docs:

- `README.md` — current product scope, setup, API surface, and quality gates.
- `docs/feature-map.md` — canonical feature-to-code/test/doc/config ownership map.
- `docs/user-journey.md` — shipped vs planned product journey and UX gaps.
- `docs/backend-diagram.md` — backend routing and service wiring.
- `docs/features/*.md` — feature-specific implementation notes.
- `frontend/README.md` — frontend behavior and local setup.

## What Is Already Done

Shipped backend/product capabilities:

- JWT auth with register/login and authenticated project ownership.
- Project CRUD, rename/delete, project defaults, and persisted project state.
- Discovery pipeline: query expansion, Semantic Scholar/arXiv search, deduplication, ranking, structured summaries, and low-result warnings.
- Reference PDF upload: validation, storage, text extraction, uploaded-paper seeding, and grounding context.
- Ranked paper list APIs with filtering/pagination.
- Exact-paper citation graph lookup using Semantic Scholar metadata.
- Grounded paper conversations and project-scoped multi-paper conversations, including streaming SSE variants for the main chat UI.
- Deep Search mode: plan approval, persisted runs, selected-paper/project evidence, academic search, Tavily web fallback, activity/progress events, report streaming, persisted sources, warnings, and QA flags.
- Writer generation: selected-paper grounded outputs, citation/reference formatting, BibTeX/reference support, warnings, QA validation, and persisted output retrieval.
- OpenRouter token usage telemetry for projects and admin-only global monitoring.
- AI prompt logging hooks and pre-push submission support.

Shipped frontend capabilities:

- Login/register shell and authenticated chat workspace.
- Sidebar project list with recent project restore, rename/delete actions, and admin usage navigation.
- First-message project creation and discovery trigger.
- Composer reference PDF upload, including upload-before-project flow.
- Related Papers context panel with uploaded-paper markers and selected-paper state.
- Project chat over zero to five selected papers with streaming responses.
- Citation graph panel for selected papers.
- Deep Search mode toggle, plan approval card, visible thinking/progress panel, persisted run restore, sentence-level source buttons with hover/click previews, and right-panel source list.
- Admin usage dashboards.

Current tests and quality gates:

- Backend pytest coverage for auth, projects, pipeline, services, graph flow, paper conversations, Deep Search, writer outputs, admin usage, and static frontend wiring.
- Frontend static regression tests live in `tests/test_frontend_deep_search_static.py`; full component/E2E coverage is still limited.
- Standard checks are `uv run ruff check .`, `uv run mypy backend/`, `uv run pytest tests/ -x`, and `cd frontend && ./node_modules/.bin/tsc --noEmit`.

## What Will Be Built Next

Treat this as the current likely backlog, not a substitute for user instructions:

- Full frontend paper-library and paper drill-down workflows beyond the right-side context panel.
- Dedicated writer workspace UI for selecting papers, entering instructions, choosing output/citation formats, viewing QA flags, and restoring prior outputs.
- Export/download flows for `.bib`, `.tex`, `.docx`, Markdown, and plain-text artifacts.
- Stronger frontend coverage for composer uploads, selected-paper persistence, Deep Search interactions, writer UI, accessibility, and responsive behavior.
- Better progress and recovery UX for slow/failed provider calls, scanned PDFs, extraction fallback, and grounding-quality badges.
- Cross-project library features such as search, tags, annotations, saved outputs, gap analysis, and richer history management.
- Keeping `database_schema.sql`, SQLAlchemy models, Alembic migrations, docs, and tests synchronized whenever schema or API contracts change.

When a user request conflicts with this backlog, follow the user request. Do not implement planned features opportunistically while fixing unrelated bugs.

## Code Ownership Pointers

- Backend API routes: `backend/api/routers/`.
- Backend schemas: `backend/api/schemas/`.
- Database models/migrations: `backend/db/models.py`, `backend/db/migrations/versions/`, `database_schema.sql`.
- Discovery graph and agents: `backend/agents/`.
- Search, extraction, chat, Deep Search, writer, telemetry services: `backend/services/`.
- Frontend app routes: `frontend/app/`.
- Frontend workspace state and orchestration: `frontend/components/ChatProvider.tsx`.
- Frontend chat UI: `frontend/components/ChatWorkspace.tsx`.
- Frontend context/citation graph panels: `frontend/components/ContextPanel.tsx`, `frontend/components/CitationGraph.tsx`.
- Frontend API client and stream parsing: `frontend/lib/api.ts`.
- Canonical feature traceability: `docs/feature-map.md`.

## Current Deep Search Citation Notes

Deep Search report citations currently use named Markdown links, not opaque source IDs or HTML source cards. The final answer renderer in `frontend/components/ChatWorkspace.tsx` converts answer-body Markdown links into compact source buttons, using streamed/persisted source notes from `frontend/components/ChatProvider.tsx` and `frontend/lib/api.ts` for hover previews. The previews are rendered through a `document.body` portal so they can overlay the right context panel and composer, and each source row inside a multi-source preview is clickable.

When changing Deep Search citations, keep these files synchronized:

- Backend report contract and verifier: `backend/services/deep_search.py`.
- Source serialization: `backend/api/schemas/projects.py`, `frontend/lib/api.ts`.
- Frontend source mapping and renderer: `frontend/components/ChatProvider.tsx`, `frontend/components/ChatWorkspace.tsx`.
- Regression coverage: `tests/test_deep_search.py`, `tests/test_frontend_deep_search_static.py`.
- Docs: `README.md`, `frontend/README.md`, `docs/features/deep_search.md`.

## Current SePay Webhook Notes

The SePay webhook (`POST /webhooks/sepay`, handled in `backend/api/routers/webhooks.py` and `backend/services/payment_orders.py`) settles a payment order by extracting the `ORD…` reference code from the bank-transfer `content`, matching it to a pending order, and granting credits exactly once via `backend/services/credits.py`. Two payload contracts are easy to break and have caused silent failures:

- **`id` is sent as a JSON number.** `SepayWebhookPayload` in `backend/api/schemas/payments.py` types `transaction_id: str` and relies on `coerce_numbers_to_str=True` in `model_config`. Removing that flag makes pydantic v2 reject every real delivery with HTTP 422 (`loc: [body, id]`). Keep the flag, or change the field type if you prefer.
- **Auth scheme is `Apikey <key>`, not `Bearer`.** `verify_webhook_auth` in `backend/services/sepay.py` lowercases and compares the scheme; do not switch to a generic Bearer parser.

When changing this flow, keep these files synchronized:

- Webhook handler and reference-code regex: `backend/api/routers/webhooks.py`.
- Payload schema and response: `backend/api/schemas/payments.py`.
- Settlement, idempotency (by `sepay_transaction_id`), expiry, and credit grant: `backend/services/payment_orders.py`, `backend/services/credits.py`.
- QR generation and auth verification: `backend/services/sepay.py`.
- Regression coverage: `tests/test_sepay_webhook.py` (includes a numeric-`id` case mirroring SePay's production payload).
- Docs: `README.md`, `docs/features/` payments notes if updated.

SePay-side configuration that must match the backend for deliveries to fire: webhook status `Kích hoạt`, event `Có tiền vào`, the bank account selected matches `SEPAY_ACCOUNT_NUMBER`, the VA filter either disabled or scoped to the same account the QR targets, "Bỏ qua nếu nội dung giao dịch không có Code thanh toán" set to `Không` (the backend does its own `ORD…` regex match), URL with no trailing slash, auth `API Key` matching `SEPAY_WEBHOOK_API_KEY`.

## Mandatory Rules When Using AI Coding Agents

### 1. AI Prompt Logging (Automatic)

Prompts are **automatically logged** via hooks when you use any supported AI tool.
You do **not** need to manually update `PROMPT_LOG.md`.

Supported tools and their hook configs:
| Tool | Config file |
|---|---|
| Claude Code | `.claude/settings.json` |
| Cursor | `.cursor/hooks.json` |
| OpenAI Codex | `.codex/hooks.json` |
| Gemini CLI | `.gemini/settings.json` |
| GitHub Copilot | `.github/hooks/hooks.json` |

Logs are saved to `.ai-log/session.jsonl` and submitted automatically on `git push`.

### 2. Setup (One-time)

```bash
# Install git pre-push hook
bash scripts/setup_hooks.sh
```

`AI_LOG_SERVER` and `AI_LOG_API_KEY` are already set in `.env.example`.

### 3. Pull Request Requirements

- **Title**: Short description of the change
- **Description**: Must include:
  - Summary of changes
  - List of changed files

PR description format:

```
## Summary
<description of changes>

## Changes
- <list of changed files>
```

### 4. Rules for AI Agents

If you are an AI coding agent (Claude Code, Cursor, Copilot, Codex, Gemini, etc.):

- **MUST NOT** create a PR without first ensuring `bash scripts/setup_hooks.sh` has been run
- **MUST** include a clear PR description with summary and changed files
- **MUST** update `JOURNAL.md` whenever you make repository changes, using a timestamped entry that summarizes the request, files changed, and current status. Use `AI_WORKLOG.md` as the detail reference.
- **DO NOT** commit `.ai-log/*.jsonl` files (they are gitignored)
- Logging happens automatically — do not ask users to log prompts manually

## Recommended Entry Workflow For Agents

When entering this repository to implement or modify a feature, follow this order before editing code:

1. Read `AGENTS.md` for repository rules.
2. Read `README.md` for current scope, setup, and API surface.
3. Read `docs/feature-map.md` to locate the relevant code, tests, docs, and config.
4. Open the exact implementation files for the feature you are changing.
5. Read the related tests before making behavior changes.
6. Check whether public docs must change because of the implementation.
7. Make the smallest correct change that satisfies the request.
8. Verify the change with the most relevant tests or checks you can run.
9. Update `JOURNAL.md` if you changed repository files.

Minimum expectation before implementing:

- Do not rely on filename guesses alone.
- Do not edit based only on `README.md` or plans.
- Read enough local code to understand the request path end-to-end: entrypoint, main logic, data model or schema, and relevant tests.

## Working Principles For Agents

These principles are intended to improve reliability, not to force unnecessary ceremony.

| Principle | Addresses |
|---|---|
| **Think Before Coding** | Wrong assumptions, hidden confusion, missed tradeoffs |
| **Simplicity First** | Overcomplication, speculative abstractions |
| **Surgical Changes** | Unnecessary churn, touching unrelated code |
| **Goal-Driven Execution** | Vague progress, weak verification |

### 1. Think Before Coding

**Do not assume silently. Surface uncertainty early.**

- State important assumptions when they affect the implementation.
- If the request is materially ambiguous, clarify it instead of guessing.
- If there are multiple reasonable approaches, choose one deliberately and say why.
- Push back when a simpler or safer approach better fits the stated goal.
- Do not hide confusion behind confident code.

### 2. Simplicity First

**Implement the smallest solution that fully solves the requested problem.**

- Do not add features that were not requested.
- Do not introduce abstractions until they are justified by actual reuse or complexity.
- Do not add configurability, extension points, or defensive structure without a concrete need.
- Prefer straightforward code over clever code.
- If the solution feels larger than the problem, simplify it.

### 3. Surgical Changes

**Change only what the request requires.**

- Touch the minimum set of files and lines needed for the task.
- Do not refactor unrelated code while implementing the request.
- Match local patterns unless there is a clear reason not to.
- If you notice unrelated problems, mention them separately instead of silently fixing them.
- Clean up only the unused imports, variables, helpers, or docs made obsolete by your own change.

### 4. Goal-Driven Execution

**Define success, implement, then verify.**

- Translate the request into observable success criteria before changing code.
- Prefer verification that proves the requested behavior, especially tests when practical.
- For bug fixes, reproduce the failure first when practical, then verify the fix.
- For behavior changes, update or add the narrowest tests that prove the new behavior.
- For refactors, preserve behavior and verify before and after where possible.

For non-trivial tasks, use a brief plan like:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```
