# Phase 4A — Export Infrastructure

**Goal**: Add the ability to download generated research artifacts in standard academic formats.

## Backend Changes

### [NEW] [export.py](file:///home/tungnguyen/Programming/A20-App-143/backend/api/routers/export.py)
- Create a new router for file exports.
- Endpoint: `GET /projects/{id}/writer/outputs/{output_id}/export?format={bibtex|word|latex}`.
- Logic: Rehydrate the `WriterOutput` and use formatters to generate file responses.

### [MODIFY] [writer_outputs.py](file:///home/tungnguyen/Programming/A20-App-143/backend/services/writer_outputs.py)
- Add methods to generate binary/text stream for Word (using `python-docx`) and LaTeX (using `pylatex`).

## Frontend Changes

### [MODIFY] [ContextPanel.tsx](file:///home/tungnguyen/Programming/A20-App-143/frontend/components/ContextPanel.tsx)
- Add an "Export" section with buttons for BibTeX, Word, and LaTeX when a writer output is active.
- Display a loading state during generation and trigger a browser download upon completion.

## Verification
- `pytest tests/test_export.py`: Verify that export endpoints return valid files with correct headers.
- Manual check: Download a BibTeX file and verify it imports into Zotero/Mendeley.
