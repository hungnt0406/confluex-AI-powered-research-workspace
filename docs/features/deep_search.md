# Deep Search Mode

Deep Search is a project-scoped research mode for the chat workspace. It creates a persisted run, gathers selected-paper evidence, searches academic providers, optionally searches the web through Tavily, streams progress and the final report through SSE, and stores sources, warnings, and QA flags for later review.

## Endpoints

| Action | Method | Path |
|---|---|---|
| Stream a new Deep Search run | `POST` | `/projects/{project_id}/deep-search/stream` |
| List prior runs | `GET` | `/projects/{project_id}/deep-search-runs` |
| Get one run | `GET` | `/projects/{project_id}/deep-search-runs/{run_id}` |

The stream request body is:

```json
{
  "question": "What evidence supports deep search workflows?",
  "paper_ids": ["paper-id-1", "paper-id-2"]
}
```

`paper_ids` may be empty. When papers are selected, the service includes their summaries and available persisted PDF chunks.

## Stream Events

The stream emits:

- `run`: the persisted run summary created before research starts.
- `status`: the current phase, such as `planning`, `project_evidence`, `academic_search`, `web_search`, `summarizing_sources`, `writing`, or `verifying`.
- `source`: a compact source note with source id, type, title, URL, paper id, and note.
- `token`: report text delta.
- `done`: the persisted run with report, sources, warnings, and QA flags.
- `error`: failure detail and run id when the run was already created.

## Implementation

- Access hook: `ensure_deep_search_allowed(current_user)` currently allows all authenticated users and centralizes future paid gating.
- Orchestrator: `backend/services/deep_search.py`.
- Tavily client: `backend/services/tavily.py`.
- API routing: `backend/api/routers/projects.py`.
- Persistence: `deep_search_runs` and `deep_search_sources`.
- Frontend mode switch: `frontend/components/ChatWorkspace.tsx`.
- Frontend stream orchestration: `frontend/components/ChatProvider.tsx`.

## Configuration

- `TAVILY_API_KEY`
- `TAVILY_BASE_URL`
- `DEEP_SEARCH_PLANNER_MODEL`
- `DEEP_SEARCH_RESEARCH_MODEL`
- `DEEP_SEARCH_SUMMARIZER_MODEL`
- `DEEP_SEARCH_WRITER_MODEL`
- `DEEP_SEARCH_VERIFIER_MODEL`
- `DEEP_SEARCH_MAX_WEB_SEARCHES`
- `DEEP_SEARCH_MAX_ITERATIONS`
- `DEEP_SEARCH_MAX_RESULTS_PER_QUERY`

If Tavily is not configured, the run continues with a warning. OpenRouter usage from planning, source compression, report writing, and verification is persisted with `deep_search_*` feature names when live LLM calls are used.

## Tests

- `tests/test_deep_search.py`
- `tests/test_frontend_deep_search_static.py`
