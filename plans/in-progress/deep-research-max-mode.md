# Plan: Deep Research Max — Adaptive Agent Mode

## Context

The current Deep Search pipeline (`backend/services/deep_search.py`) is **static**: it plans 3–5 research questions upfront, runs one batch of academic + web searches against those questions verbatim, then summarizes and writes a report. The LLM never sees what it found before deciding what to search next, which limits depth, prevents the agent from filling identified gaps, and forces the user's research questions to double as search queries (which makes API calls fail when the question is a long natural-language sentence).

Rather than refactor the existing static path (which works fine for fast, shallow research), this plan adds a **new mode "Deep Research Max"** alongside Standard and Deep Search. Max runs an adaptive agent loop: `search → summarize → decide what's missing → search again`, until the agent signals completion or hits the iteration cap. Standard Deep Search remains untouched.

## Decisions (locked in)

| Decision | Value |
|---|---|
| Code structure | Add `mode: Literal["standard", "max"]` parameter to `DeepSearchService.stream_run`; branches internally; shares helpers |
| UI mode selector | Third button next to Deep Search in chat composer (`Standard | Deep Search | Deep Research Max`) |
| Credit cost | 5× standard Deep Search (matches the 5× LLM call count: planner + decider ×4 + summarizer ×4 + writer + verifier) |
| Max iterations | 4 |
| Reasoning visibility | `decision.reasoning` shown in thinking panel under new `"deciding"` phase |
| Search tools per iteration | Academic + web always run in parallel |
| Backward compat | `mode="standard"` (current behavior) is the default for existing calls |

## Design Overview

```
User picks "Deep Research Max" in composer
  ↓
POST /projects/{id}/deep-search/stream  body: { question, mode: "max" }
  ↓
Planner (1 LLM call)
  ├─ research_questions: [str]   (3–5, shown in plan card)
  └─ seed_queries: [str]         (1–2 short keyword strings)
  ↓
Project evidence (once, unchanged)
  ↓
ADAPTIVE LOOP (max 4 iterations):
  1. Search academic + web in parallel for current queries
  2. Summarize NEW sources only (incremental)
  3. Decider LLM: { reasoning, gaps, next_queries, done }
  4. If done OR iteration cap hit OR 2 consecutive empty rounds → break
  ↓
Stream report (citing all gathered sources)
  ↓
Verify citations
```

When `mode="standard"` everything below the planner runs the existing static code path. The two paths share `_plan_research`, `_collect_project_sources`, `_summarize_sources`, `_stream_report`, `_verify_report`, `_persist_success`.

## Files to Modify

### Backend

| File | Change |
|---|---|
| `backend/services/deep_search.py` | Add `mode` param to `stream_run`; new methods `_decide_next_step`, `_run_adaptive_loop`, `ResearchState` dataclass; refactor planner to return `(research_questions, seed_queries)` shared by both modes |
| `backend/db/models.py` | Add `mode` string column to `DeepSearchRun` (default `"standard"`) |
| `backend/db/migrations/versions/<new>_deep_search_mode.py` | New Alembic migration adding the `mode` column with default `"standard"` |
| `backend/api/schemas/projects.py` (or wherever DeepSearch DTOs live) | Add `mode: Literal["standard", "max"]` field to the deep-search stream request body; add to `DeepSearchRunRead`/`DeepSearchRunSummaryRead` for visibility in admin/usage |
| `backend/api/routers/projects.py` | Pass `mode` from request to `stream_run`; persist `mode` on the run row |
| `backend/api/routers/pipeline.py` | `/deep-search/plan` endpoint optionally returns `seed_queries` (used by both modes; UI may ignore for now) |
| `backend/api/dependencies.py` | New credit cost for max mode (5× standard) — extend `require_credits` or add a per-mode cost map |
| `backend/config.py` | Confirm `deep_search_max_iterations` default = 4. Add `deep_search_max_mode_credit_cost` if costs are configurable |

### Frontend

| File | Change |
|---|---|
| `frontend/components/ChatProvider.tsx` | Add `"deep_research_max"` to `ChatMode` type; thread it through composer state and the deep-search request body; add `"deciding"` to `DEEP_SEARCH_THINKING_PHASES` and `deepSearchThinkingDefinition` (lines 429–479) |
| `frontend/components/ChatWorkspace.tsx` (or composer component) | Add third button to mode selector. UI: `Standard | Deep Search | Deep Research Max`. The Max button gets a subtle accent (e.g., gradient or small "5x credits" tooltip) so users know it costs more |
| `frontend/lib/api.ts` | Update deep-search streaming client to accept and send `mode` |

### Tests

| File | Change |
|---|---|
| `tests/test_deep_search.py` | Reuse `local_deep_search_service` fixture pattern; add tests for `mode="max"` covering iteration loop, dedup, bail conditions, decider failure |
| Frontend (if e2e): existing chat flow tests get a `mode="max"` variant where applicable |

## Detailed Backend Changes (`backend/services/deep_search.py`)

### 1. Shared planner — `_plan_research` (replaces current `_plan_questions`)

Used by both modes. Returns both research questions (for UI) and seed queries (for searching):

```python
schema = {
  "type": "object",
  "properties": {
    "research_questions": {"type": "array", "minItems": 3, "maxItems": 5,
                           "items": {"type": "string"}},
    "seed_queries": {"type": "array", "minItems": 1, "maxItems": 2,
                     "items": {"type": "string", "maxLength": 80}}
  },
  "required": ["research_questions", "seed_queries"],
  "additionalProperties": False
}
```

System prompt asks for short keyword `seed_queries` (NOT full sentences) suitable for academic search APIs. Local fallback `_build_local_plan_research` derives seed queries via `backend/agents/searcher.py:_extract_key_terms` (already implemented — REUSE).

### 2. New `ResearchState` dataclass (Max mode only)

```python
@dataclass
class ResearchState:
    original_question: str
    research_questions: list[str]
    gathered_summaries: list[dict]
    queries_run: set[str]
    iteration: int
    consecutive_empty_iterations: int
```

### 3. New `_decide_next_step` method (Max mode only)

```python
async def _decide_next_step(self, state: ResearchState) -> DecisionPayload:
    # Returns {reasoning, gaps, next_queries (max 3, ≤80 chars each), done}
    # Falls back to done=True on StructuredOutputError
```

Schema mirrors the spec above. System prompt:
> You are a deep research agent. Given the original research questions, sources gathered so far, and queries already run, decide the next 1–3 short keyword search queries (or signal `done=true` if the questions are well-covered). Avoid duplicating past queries. Prefer specific over generic. Keep each query under 8 words.

### 4. `stream_run` — branch on `mode`

```python
async def stream_run(
    self,
    *,
    session: AsyncSession,
    project: Project,
    question: str,
    selected_papers: list[Paper],
    mode: Literal["standard", "max"] = "standard",
) -> AsyncIterator[DeepSearchStreamEvent]:
    # ... create run with mode=mode persisted ...
    # planning + project_evidence (shared, unchanged)
    if mode == "max":
        async for event in self._run_adaptive_loop(state, ...):
            yield event
    else:
        async for event in self._run_static(...):  # existing code factored out
            yield event
    # summarizing/writing/verifying (shared)
```

### 5. `_run_adaptive_loop` — the new core

```python
state = ResearchState(...)
current_queries = seed_queries
for iteration in range(self.max_iterations):  # default 4
    state.iteration = iteration + 1
    fresh = [q for q in current_queries if _normalize(q) not in state.queries_run]
    if not fresh:
        break
    state.queries_run.update(_normalize(q) for q in fresh)

    # emit activity: stage_start/update under academic_search + web_search with iteration N
    new_candidates = await asyncio.gather(
        self._collect_academic_sources(project, fresh),
        self._collect_web_sources(fresh),
    )
    flat_new = flatten(new_candidates)
    if not flat_new:
        state.consecutive_empty_iterations += 1
        if state.consecutive_empty_iterations >= 2:
            break
    else:
        state.consecutive_empty_iterations = 0

    new_summaries = await self._summarize_sources(...flat_new...)
    state.gathered_summaries.extend(new_summaries)

    yield DeepSearchStreamEvent("status", {"phase": "deciding"})
    yield activity(stage_start, phase="deciding", detail=f"Iteration {state.iteration} of {max}: planning next searches")
    decision = await self._decide_next_step(state)
    yield activity(stage_update, phase="deciding", detail=decision.reasoning)
    if decision.done:
        yield activity(stage_complete, phase="deciding", detail="Decided we have enough evidence.")
        break
    current_queries = decision.next_queries
```

### 6. Activity events — new `"deciding"` phase

Add `"deciding"` between `web_search` and `summarizing_sources` in the phase order. Frontend adds matching entry to `deepSearchThinkingDefinition`. Existing reducer logic (`applyDeepSearchThinkingActivityToState`, ChatProvider lines 576–621) handles arbitrary phases generically — no reducer changes needed.

`academic_search` and `web_search` get re-entered each iteration. Each re-entry emits `stage_update` (NOT `stage_start` again) with detail like `"Iteration N: searching arXiv for {query}"`. Final `stage_complete` for these phases fires only after the loop exits.

### 7. Persistence

`DeepSearchRun.mode` column gets set on the run row at creation. `DeepSearchRunRead` schema exposes it so admin views can filter / show a "Max" badge. `plan_json` stores both `research_questions` and `seed_queries`. For Max runs, append `iteration_history: list[{iteration, queries, reasoning, gaps}]` to `plan_json` for debugging.

### 8. Backward compatibility

- `mode="standard"` is the default — existing API callers and tests continue working unchanged.
- Offline (`use_live_llm=False`) Max runs degrade to a single iteration with seed queries; no decider call.
- Decider failure → treat as `done=True`, log warning, write report from accumulated evidence.

## Frontend Changes

### Mode selector (`ChatWorkspace.tsx` composer)

Three buttons in the composer toolbar:
```
[ Standard ]  [ Deep Search ]  [ Deep Research Max ✨ ]
                                   ↑ subtle gradient/badge to signal premium
```
Tooltip on hover for Max: `"Adaptive multi-round research. ~5× credits."`

### `ChatProvider.tsx`

```ts
export type ChatMode = "standard" | "deep_search" | "deep_research_max";

// In submitMessage():
if (chatMode === "deep_research_max") {
  // same plan card flow as deep_search, but pass mode: "max" in startDeepSearchPlan
  // call /pipeline/deep-search/plan to get research_questions and seed_queries
  // start streaming with body: { question, mode: "max" }
}

// DEEP_SEARCH_THINKING_PHASES gets "deciding" added between web_search and summarizing_sources
// deepSearchThinkingDefinition gets a "deciding" case:
case "deciding":
  return { title: "Reasoning about gaps", detail: "Deciding what to search next…" };
```

### `lib/api.ts`

Streaming function gets a `mode` parameter, passed in request body.

### Plan card (already done in prior change)

No structural change. Optionally add a small "Max" badge in the plan card title when triggered from Max mode, so the user sees what's about to run.

## Credits

`backend/api/dependencies.py:require_credits` currently assumes a flat cost per gated feature. Update to accept a `mode` parameter or per-mode cost lookup:

```python
DEEP_SEARCH_COST_BY_MODE = {"standard": 1, "max": 5}  # tuned to existing standard cost
```

Admin allowlist (`ADMIN_EMAILS`) bypass remains unchanged. Refund-on-failure behavior in `credits.py` remains unchanged.

## Tests (`tests/test_deep_search.py`)

Reuse existing `local_deep_search_service` fixture. Mock `OpenRouterStructuredOutputService.generate_json` to script planner + decider responses.

| Test | Scenario | Expected |
|---|---|---|
| `test_max_mode_single_iteration` | Decider returns `done=true` after iteration 1 | Run completes; one round of searches; one summarization batch |
| `test_max_mode_multi_iteration` | Decider returns `next_queries` twice, then `done=true` | 3 search rounds; sources from all rounds in final report |
| `test_max_mode_iteration_cap` | Decider always returns `done=false` | Loop stops at `max_iterations=4` |
| `test_max_mode_no_progress_bail` | Searches return empty 2 iterations in a row | Loop bails after 2 consecutive empty iterations |
| `test_max_mode_query_dedup` | Decider returns a query already in `queries_run` | Duplicate skipped; no extra API call |
| `test_max_mode_decider_failure` | Decider raises `StructuredOutputError` | Run completes with iteration 1's sources only; warning logged |
| `test_max_mode_offline` | `use_live_llm=False`, `mode="max"` | Degrades to single iteration with seed queries |
| `test_max_mode_activity_events` | Mode="max" run | `"deciding"` phase events appear; conform to `REQUIRED_DEEP_SEARCH_ACTIVITY_KEYS` |
| `test_standard_mode_unchanged` | Existing tests still pass with default `mode="standard"` | Behavior identical to today |
| `test_run_persists_mode` | Insert run with `mode="max"` | `DeepSearchRun.mode` reads back as `"max"` |
| `test_credits_max_charges_5x` | Max mode debit | Ledger shows 5× standard cost |

## Verification

```bash
# Backend
uv run alembic upgrade head    # apply new mode column migration
uv run ruff check backend/
uv run mypy backend/
uv run pytest tests/test_deep_search.py -x -v

# Frontend
cd frontend && npm run build

# Manual end-to-end (with OPENROUTER/MIMO key configured):
uv run uvicorn backend.main:app --reload
# In browser:
#  1. Trigger Standard Deep Search with a non-trivial question — verify behavior unchanged
#  2. Trigger Deep Research Max with the same question — verify:
#     - Plan card shows research questions (already working)
#     - Thinking panel shows multiple iterations under academic_search/web_search
#     - "Reasoning about gaps" step appears between iterations with the agent's reasoning
#     - Final report cites sources from across iterations
#     - Total iterations ≤ 4
#     - Credit balance debited 5× the standard cost
#     - DeepSearchRun row has mode="max"
```

## Existing Code to Reuse

- `backend/agents/searcher.py:_extract_key_terms` — derive seed queries from question when LLM is offline
- `backend/services/deep_search.py:_thinking_activity` (line 1584) — emit new `"deciding"` events
- `backend/services/deep_search.py:deduplicate_source_candidates` (line 99) — applies after the loop to dedupe across iterations
- `OpenRouterStructuredOutputService.generate_json` — used as-is for new decider call (handles MiMo's `json_object` mode)
- `_build_writer_prompt` — already accepts `research_questions`; no change needed for Max mode
- `_persist_success` — extend to also persist `mode` and `iteration_history`

## Effort Estimate

- Phase 1 — Shared planner refactor + `ResearchState` + decider: ~150 lines, half a day
- Phase 2 — `_run_adaptive_loop` + `mode` branching + DB migration: ~150 lines, half a day
- Phase 3 — Frontend mode selector + `"deep_research_max"` plumbing: ~80 lines, 2 hours
- Phase 4 — Credits per-mode cost: ~30 lines, 30 minutes
- Phase 5 — Tests (10–11 cases) + manual QA: ~250 lines, 3 hours

**Total: ~1.5 days of focused work.** Largest risk: prompt quality for `_decide_next_step` — needs iteration to ensure it produces *specific* follow-up queries rather than generic filler.
