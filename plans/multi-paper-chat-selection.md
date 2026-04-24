# Multi-Paper Chat Selection

## Summary

- Convert the main workspace chat from fixed top-paper grounding into a project-scoped selected-paper chat flow.
- After discovery, default the selection to the top-ranked paper, but let users multi-select up to 5 papers from the right panel.
- Keep the visible transcript when selection changes; only future turns use the updated selected set.
- Mention the current selection in two places: a short status note in the chat transcript and a persistent selected-papers strip above the composer.
- Persist selected paper IDs in browser localStorage per user/project.
- Keep the existing single-paper `/papers/{paper_id}/conversations` flow unchanged.

## API And Data Changes

- Add project-scoped conversation resources under `/projects/{project_id}/conversations`:
  - `POST /projects/{project_id}/conversations` with `paper_ids` and `question`
  - `POST /projects/{project_id}/conversations/{conversation_id}/messages` with `paper_ids` and `question`
  - `GET /projects/{project_id}/conversations`
  - `GET /projects/{project_id}/conversations/{conversation_id}`
- Add `project_conversations` and `project_messages` persistence with `project_id`, timestamps, `selected_paper_ids_json`, and message roles `user`, `assistant`, `system`.
- Return `selected_paper_ids` in conversation read and summary schemas so the frontend can restore the active set when browser-local state is missing.
- Leave existing paper-specific conversation endpoints and models untouched for later dedicated per-paper UI.

## Implementation Changes

- Backend:
  - Add a new `ProjectConversationService` instead of retrofitting `PaperConversationService`.
  - Validate selected papers with the same project-owned loading pattern already used by writer generation.
  - Compute one question embedding, retrieve chunks across all selected papers, rank globally, and cap evidence to 5 total snippets with at most 2 snippets per paper.
  - Reuse existing PDF extraction, chunk persistence, and metadata fallback behavior per paper.
  - On follow-up, use the incoming `paper_ids` for the new turn. If the set changed, update `selected_paper_ids_json` and persist a `system` message before the user turn describing the new selected set.
- Frontend:
  - Replace single `groundingPaper` state with `selectedPaperIds` plus project-scoped conversation state in `ChatProvider`.
  - On first pipeline completion, auto-select only the top-ranked paper and create the initial project conversation with the current overview prompt.
  - In the right panel, turn paper cards into explicit multi-select toggles while keeping summary expand/collapse.
  - In the chat area, add a selected-papers strip above the composer showing up to 3 title chips plus `+N more`.
  - Append a local status bubble whenever selection changes so users can see which papers future questions will use.
  - On project reopen, restore the saved selected set from localStorage filtered against current paper IDs; if none remain valid, fall back to the latest backend conversation’s `selected_paper_ids`, then to the top-ranked paper.
- Documentation:
  - Update `README.md`, `frontend/README.md`, `docs/feature-map.md`, and `docs/user-journey.md` for the new project-scoped selected-paper chat flow and endpoints.

## Test Plan

- Backend pytest:
  - create project conversations with one paper and with multiple selected papers
  - follow-up turn with changed `paper_ids` persists the `system` selection-change message and updates `selected_paper_ids_json`
  - reject empty, duplicate, unknown, and over-limit `paper_ids`
  - retrieve evidence across multiple papers and preserve metadata fallback when PDFs or chunks are missing
  - enforce ownership on project conversation list/detail routes
  - keep existing single-paper conversation tests green
- Frontend:
  - add minimal `Vitest` + React Testing Library coverage for multi-select toggling, composer chip rendering, localStorage restore, and submit payloads carrying current `paper_ids`
- Manual acceptance:
  - select 2-5 papers, ask a question, and verify the answer is no longer fixed to the original top paper
  - reopen the same project in the same browser and verify the selected set is restored and shown in the composer and transcript

## Assumptions And Defaults

- One chat answer uses at most 5 selected papers.
- Selection changes do not clear the visible thread; they apply to later turns only.
- Browser-local persistence is sufficient; there is no cross-device sync in this feature.
- The existing per-paper conversation API remains available and is not migrated to the new workspace chat flow.
