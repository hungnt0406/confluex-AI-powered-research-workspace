# Section Outline Approval Before Drafting

## Summary

Add a required section-outline approval step before generating a writer section draft. The first implementation targets `paper_type=research` as an empirical IMRaD paper type. A section can only be drafted after the user reviews and approves an outline for that section. The approved outline becomes the structural contract for the draft, especially for `Methods`, which must produce LaTeX `\subsection{...}` blocks.

Assumption: `research` means empirical IMRaD, not survey or review methodology.

## Key Changes

- Add section-level outline APIs:
  - `POST /writer/documents/{document_id}/sections/{section_id}/outline/propose`
  - `PUT /writer/documents/{document_id}/sections/{section_id}/outline`
- Reuse existing `writer_sections.outline_text`; no migration is required.
- Keep the existing document-level outline endpoint, but make its generated outlines paper-type-aware for `research`.
- Block `draft_section()` when `outline_text` is empty and return HTTP 422 with `Approve a section outline before drafting.`
- Add a paper-type outline registry for research sections.
- Make research Methods include these subsections:
  - `\subsection{Study Design and Experimental Setup}`
  - `\subsection{Datasets, Materials, or Participants}`
  - `\subsection{Proposed Method}`
  - `\subsection{Baselines and Comparators}`
  - `\subsection{Evaluation Metrics}`
  - `\subsection{Implementation Details}`
  - `\subsection{Reproducibility and Limitations}`

## Drafting Behavior

- Update `WriterSectionAgent` so the approved outline is mandatory structure, not optional context.
- Preserve approved LaTeX subsection headings from the outline in generated drafts.
- For `paper_type=research` and `section_type=methods`, generate multi-subsection methodological content instead of a flat paragraph.
- Keep existing citation behavior and unsupported-claim `\todo{citation needed: ...}` tagging.

## Frontend Flow

- In `WriterQuestionsPanel`, gate `Draft section` behind an approved outline.
- If a section lacks `outline_text`, show `Generate section outline`.
- Show an editable outline preview after proposal.
- Persist the outline with `Approve outline`.
- Only enable `Draft section` after approval.
- Add frontend API helpers for proposing and approving section outlines.

## Tests

- Backend service tests for research Methods outlines, approval persistence, and draft blocking.
- Router tests for section-outline propose/approve endpoints and draft 422 before approval.
- Agent tests that research Methods drafts preserve subsection headings.
- Frontend static tests for the outline-gated UI and API helpers.

## Verification

- `uv run pytest tests/test_writer_section_agent.py tests/test_writer_documents.py tests/test_frontend_writer_static.py`
- `cd frontend && ./node_modules/.bin/tsc --noEmit`
