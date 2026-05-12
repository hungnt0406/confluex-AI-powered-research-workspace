

  # Progressive Related Papers Pipeline

  ## Summary

  Add a streaming pipeline path so the first standard chat message can show related papers as soon as
  search/ranking finishes, while paper summaries continue progressively. Keep the existing first-message
  chat behavior: after the pipeline stream fully completes, start the same standard project chat turn
  with no selected papers.

  ## Key Changes

  - Keep POST /projects/{id}/run unchanged for compatibility.
  - Add POST /projects/{id}/run/stream as SSE:
      - status: current phase, e.g. searching, ranking, summarizing, completed.
      - papers: emitted after ranking, with queries, counts, and ranked ProjectPaperRead[].
      - summary: emitted after each paper summary attempt, with updated ProjectPaperRead.
      - done: final RunPipelineResponse.
      - error: fatal pipeline error.
  - Split pipeline internals so ranking can commit before summaries:
      - Search persists candidates as today.
      - Ranking sets relevance/status to ranked, commits, and emits papers.
      - Summary generation updates each paper to summarized or summary_error and emits updates.
  - No schema migration: reuse existing Paper.status and nullable summary.

  ## Frontend Behavior

  - On first standard message with no active project:
      - Create the project.
      - Start /run/stream.
      - On papers, immediately populate the Related Papers panel and show a summarizing status.
      - On each summary, replace that paper in local state so cards update progressively.
      - On done, reconcile once with GET /projects/{id}/papers, set runSummary, then call the existing
        streamProjectChatTurn with paperIds: [].
  - Update paper cards:
      - ranked with no summary: show “Summary pending” or equivalent compact status.
      - summarized: show existing summary toggle.
      - summary_error: show existing error summary state.
  - Keep composer busy until the preserved first-message chat turn completes, but make related papers
    visible during the wait.

  ## Tests

  - Backend:
      - Streaming endpoint emits papers before any summary event.
      - Summary events update individual paper status and payload.
      - Existing blocking /run tests continue to pass.
      - Credit debit/commit behavior matches current /run; fatal stream errors refund.
  - Frontend/static:
      - First-message flow uses streamProjectPipeline.
      - papers event updates papers before final done.
      - summary event patches a single paper.
      - Existing standard chat starts only after pipeline done, preserving previous behavior.
  - Docs:
      - Update README.md, frontend/README.md, and docs/feature-map.md for the new streaming pipeline
        endpoint and progressive paper states.

  ## Assumptions

  - V1 uses request-scoped SSE, not a persisted background job. If the browser disconnects, the user can
    rerun or use the existing blocking /run.
  - Ranked papers are useful before summaries because title, abstract, metadata, and relevance score are
    already available.
  - We do not auto-select top papers or change standard chat grounding semantics in this change.