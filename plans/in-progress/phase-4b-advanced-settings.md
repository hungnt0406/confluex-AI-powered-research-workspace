# Phase 4B — Advanced Research Settings

**Goal**: Allow users to customize their search and citation preferences before starting a research run.

## Frontend Changes

### [NEW] [NewProjectModal.tsx](file:///home/tungnguyen/Programming/A20-App-143/frontend/components/NewProjectModal.tsx)
- A modal to capture:
  - Year Range Start (default: 2018)
  - Max Candidate Papers (default: 30)
  - Citation Style (IEEE, APA, Chicago)
  - Output Format (Markdown, LaTeX)

### [MODIFY] [ChatWorkspace.tsx](file:///home/tungnguyen/Programming/A20-App-143/frontend/components/ChatWorkspace.tsx)
- Trigger the `NewProjectModal` when "New Research" is clicked or a new topic is entered from a blank state.

### [MODIFY] [ChatProvider.tsx](file:///home/tungnguyen/Programming/A20-App-143/frontend/components/ChatProvider.tsx)
- Update `submitMessage` to pass the new settings to the `POST /projects` and `POST /projects/{id}/run` endpoints.
- Ensure the state is updated and persisted throughout the project lifecycle.

## Verification
- `npm test`: Verify that the `NewProjectModal` correctly passes state to the provider.
- Manual check: Start a new research project with specific year filters and verify that only relevant papers are returned.
