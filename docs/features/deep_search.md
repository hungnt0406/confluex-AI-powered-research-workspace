# Deep Search Mode

Deep Search is a project-scoped research mode for the chat workspace. The frontend first shows a research plan and waits for the user to start it. After approval, it creates a persisted run, gathers selected-paper evidence, searches academic providers, optionally searches the web through Tavily, streams visible thinking/progress and the final report through SSE, and stores sources, warnings, and QA flags for later review.

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

## Frontend Context Panel

Deep Search keeps the right context panel split into two sections:

- `Related Papers` appears first and is populated from the existing Searcher -> Reader project pipeline.
- `Deep Search Sources` appears below it and is populated from the Deep Search run's streamed and persisted source events.

When a Deep Search prompt starts without discovered project papers, the frontend runs `POST /projects/{project_id}/run`, refreshes `GET /projects/{project_id}/papers`, and then starts the Deep Search stream. Existing discovered paper lists are preserved for follow-up Deep Search prompts so selected non-uploaded papers are not deleted by a redundant discovery rerun.

## Frontend Approval and Thinking UI

When the composer is in Deep Search mode, submitting text appends the user message and a pending `Deep Search Plan` card instead of immediately calling the streaming endpoint. The plan card summarizes the research, analysis, and report-writing steps and exposes `Edit plan` and `Start research` actions.

`Start research` runs the existing project creation/discovery preflight when needed, then calls `POST /projects/{project_id}/deep-search/stream`. The `Show thinking` panel immediately displays the full research path: planning, project evidence, academic search, web search, source summarization, writing, and verification. Stream `status` events move the active marker through that path while future phases remain visible but muted. Stream `activity` events replace generic phase copy with user-facing research-log notes derived from planned questions, discovered evidence, source counts, and source titles. Activity payloads include both `type` and `event_type`, both `message` and `detail`, and a `sources` array for runtime source chips; the only activity values are `stage_start`, `stage_update`, `source_found`, `stage_complete`, and `finalizing`. Academic and web provider loops emit `stage_update` before each provider query and `source_found` when usable runtime sources are returned, so the panel can change while the backend is still working. This is visible process telemetry, not hidden model chain-of-thought. While waiting for the next server event, the thinking panel keeps a live elapsed timer and animated progress bar so long backend phases do not look frozen. Stream `source` events are attached both to the thinking panel and to the right-side `Deep Search Sources` panel. The final answer bubble is created only after the first report token or final `done` event, avoiding an empty assistant row during retrieval.

Deep Search SSE frames are sent with padding comments to reduce buffering of small `status` events in local browsers or proxies. The padding is ignored by the SSE parser and does not change the client event contract.

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
