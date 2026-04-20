# Phase 4C — UI Refinements & Hardening

**Goal**: Improve the day-to-day usability of the research library and pipeline.

## Frontend Changes

### [MODIFY] [ContextPanel.tsx](file:///home/tungnguyen/Programming/A20-App-143/frontend/components/ContextPanel.tsx)
- **Paper Filtering**: Add a search bar and a "Min Relevance" slider to the paper list.
- **Starring**: Add a star icon to papers to mark them as "favorites" (persisted in DB).
- **Exclusion**: Allow users to uncheck papers to exclude them from future writer summaries.

### [MODIFY] [ChatWorkspace.tsx](file:///home/tungnguyen/Programming/A20-App-143/frontend/components/ChatWorkspace.tsx)
- Update the typing indicator/status bubble to reflect SSE progress messages ("Summarizing paper 5/20...").

## Backend Changes

### [MODIFY] [pipeline.py](file:///home/tungnguyen/Programming/A20-App-143/backend/agents/pipeline.py) & [projects.py](file:///home/tungnguyen/Programming/A20-App-143/backend/api/routers/projects.py)
- Implement SSE (Server-Sent Events) endpoint `GET /projects/{id}/stream` for real-time progress updates.
- Ensure the LangGraph nodes emit events that the streaming endpoint can capture.

## Verification
- Manual check: Filter papers in the library and verify the view updates instantly.
- Manual check: Run a long pipeline and verify the "Summarizing..." status updates in real-time.
