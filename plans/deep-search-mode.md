# Deep Search Mode Implementation Plan

## Summary

Add a `Deep Search` mode to the existing chat workspace. In v1 it is available to all authenticated users, uses Tavily for web search when configured, reuses existing academic sources and PDF grounding, persists each run, streams progress and results through SSE, and keeps the feature boundary clean for future paid gating.

Use cheap non-production model defaults:

- Planner, research, summarizer, verifier: `google/gemini-2.5-flash-lite`
- Writer: `deepseek/deepseek-chat-v3.1`
- Embeddings: keep current `openai/text-embedding-3-small`

## Key Changes

- Add config and env support:
  - `TAVILY_API_KEY`
  - `TAVILY_BASE_URL=https://api.tavily.com`
  - `DEEP_SEARCH_PLANNER_MODEL`
  - `DEEP_SEARCH_RESEARCH_MODEL`
  - `DEEP_SEARCH_SUMMARIZER_MODEL`
  - `DEEP_SEARCH_WRITER_MODEL`
  - `DEEP_SEARCH_VERIFIER_MODEL`
  - `DEEP_SEARCH_MAX_WEB_SEARCHES=5`
  - `DEEP_SEARCH_MAX_ITERATIONS=2`
  - `DEEP_SEARCH_MAX_RESULTS_PER_QUERY=5`
- Add persistence:
  - `deep_search_runs`: project id, user prompt, status, selected paper ids, plan JSON, report body, source summary JSON, warnings JSON, QA flags JSON, created, updated, and completed timestamps.
  - `deep_search_sources`: run id, source type (`paper`, `paper_chunk`, `citation_graph`, `web`), title, URL, paper id, snippet, and metadata JSON.
- Add API:
  - `POST /projects/{project_id}/deep-search/stream`
    - request: `{ "question": string, "paper_ids": string[] }`
    - SSE events: `run`, `status`, `source`, `token`, `done`, `error`
    - creates and persists a run before research starts.
  - `GET /projects/{project_id}/deep-search-runs`
    - lists run summaries ordered newest first.
  - `GET /projects/{project_id}/deep-search-runs/{run_id}`
    - returns one run with sources, report, warnings, and QA flags.
- Keep v1 access simple:
  - no `users.plan`, entitlement table, or paid gate yet.
  - code should route through a single helper such as `ensure_deep_search_allowed(current_user)` that currently permits everyone, so future paid gating is localized.

## Backend Design

- Add a `TavilySearchService` using existing `httpx`.
  - Default request uses `search_depth="basic"`, `include_answer=false`, `include_raw_content=false`, `max_results=5`.
  - If `TAVILY_API_KEY` is missing, return no web sources plus a warning; do not fail the whole run.
- Add `DeepSearchService` as the orchestration boundary.
  - Planner generates 3 to 5 research questions.
  - Academic worker reuses Semantic Scholar and arXiv search paths where practical.
  - Project evidence worker retrieves selected paper summaries and relevant chunks.
  - Web worker calls Tavily within configured limits.
  - Compressor turns raw source snippets into compact evidence notes.
  - Writer streams the final report.
  - Verifier emits QA flags for uncited claims, weak evidence, and web-only claims.
- Track OpenRouter usage with existing `start_usage_collection` and `flush_usage_events`.
  - Use feature names like `deep_search_planning`, `deep_search_web_summarization`, `deep_search_report_writer`, `deep_search_verifier`.
  - For Tavily, record source counts and credit usage in run metadata; do not force it into OpenRouter token totals unless a generic external-usage model is later added.
- Keep failure behavior explicit:
  - Tavily failure: continue with academic and PDF evidence plus a warning.
  - LLM failure before report: mark run `failed`, stream `error`, rollback only incomplete transient DB work.
  - Partial source failures: store warnings and continue.

## Frontend Design

- Add a compact `Standard / Deep Search` mode toggle in the existing chat composer.
- In `Deep Search` mode:
  - submit to `/projects/{id}/deep-search/stream`.
  - render progress messages from `status` events.
  - stream the final report into the chat as an assistant message.
  - show source chips or a small source list from `source` and `done` payloads.
- If no project exists, keep current behavior: create a project from the prompt first, then start the Deep Search run.
- Keep selected-paper behavior:
  - pass current `selectedPaperIds`.
  - allow zero selected papers; the agent then uses project topic, academic search, and Tavily.

## Tests

- Backend unit and API tests:
  - creating a deep search run streams `run`, `status`, `done` and persists the run.
  - run ownership is enforced with `404 Project not found` and `404 run not found`.
  - missing Tavily key continues with warning.
  - Tavily upstream failure continues with warning.
  - LLM or service failure marks run `failed` and streams `error`.
  - OpenRouter usage events are persisted with `deep_search_*` feature names.
- Service tests:
  - Tavily request payload uses cheap defaults.
  - source deduplication prevents repeated URLs and papers.
  - verifier flags report claims without citations.
- Frontend checks:
  - mode toggle changes request path.
  - Deep Search stream appends progress and final report.
  - selected paper ids are included.
- Quality gates:
  - `uv run ruff check .`
  - `uv run mypy backend/`
  - `uv run pytest tests/ -x`
  - `cd frontend && npm run lint` if the frontend lint script exists.

## Docs And Repo Hygiene

- Update `.env.example`, `README.md`, `docs/feature-map.md`, `frontend/README.md`, and add `docs/features/deep_search.md`.
- Update `JOURNAL.md` with timestamp, request summary, changed files, and status.
- Do not commit `.ai-log/*.jsonl`.
- If creating a PR later, run `bash scripts/setup_hooks.sh` first and use the required PR description format.

## Assumptions

- v1 is not production billing-gated; all authenticated users can access Deep Search.
- Tavily is web search only; Semantic Scholar and arXiv remain the academic search path.
- Runs are persisted and streamed in the same request for v1; no separate worker queue yet.
- Use cheap model defaults now, with env overrides so production can later switch to stronger models.
