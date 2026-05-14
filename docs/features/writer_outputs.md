# Writer Outputs

This document describes the user-invoked writer generation flow, citation/reference formatting, and QA validation.

Note: this page covers the one-shot project writer output endpoint. The section-based writer workspace is separate: writer documents are user-owned, can be created without a project through `/writer/documents`, and use `writer_document_sources` for attached sources. Projects are optional source providers for that workspace. Workspace section drafts require an approved section outline before drafting, and research/survey Methods and Results outlines are structured as LaTeX subsections. The workspace also has a targeted editor-agent path for revising the current draft only: preview edits with `POST /writer/documents/{document_id}/sections/{section_id}/edit`, then apply accepted patches with `POST /writer/documents/{document_id}/sections/{section_id}/edit/apply`; apply calls reuse section version snapshots.

## HTTP Endpoints

| Action | Method | Path |
|---|---|---|
| Generate a writer artifact | `POST` | `/projects/{project_id}/writer/generate` |
| Get a persisted writer artifact | `GET` | `/projects/{project_id}/writer/outputs/{output_id}` |

Router ownership: `backend/api/routers/projects.py`

## Main Code Locations

- Route handlers: `backend/api/routers/projects.py`
- Schemas: `backend/api/schemas/projects.py`
- Writer service: `backend/services/writer_outputs.py`
- Writer agent: `backend/agents/writer.py`
- QA agent: `backend/agents/qa.py`
- Citation formatter: `backend/services/citations.py`
- Persistence model: `backend/db/models.py`

## Request Surface

The request accepts:

- `paper_ids`
- `instruction`
- `output_target`
- `citation_mode`
- `reference_style`
- `include_references`
- `max_words`

Validation is defined in `WriterGenerateRequest` in `backend/api/schemas/projects.py`.

## Generation Flow

1. The route verifies project ownership and loads the selected papers.
2. `WriterOutputService` resolves default output settings from the request and project context.
3. The service builds paper contexts from paper metadata, structured summaries, and the most relevant grounded chunks when available.
4. `GroundedWriterAgent` generates the body constrained to the selected papers.
5. `CitationFormatter` renders references and citation artifacts for the requested output mode.
6. `WriterQAAgent` validates the output and returns machine-readable QA flags.
7. The final artifact is persisted to `writer_outputs` and can be reloaded later without regeneration.

## Stored Artifact

Each persisted `writer_outputs` row stores:

- selected paper IDs
- a paper metadata snapshot
- original instruction and output settings
- generated body
- references
- BibTeX entries
- optional `thebibliography` text
- citation usage
- warnings
- QA flags

## Output Modes

Supported output targets:

- `latex`
- `docs`
- `markdown`
- `plain_text`

Supported citation modes:

- `numbered`
- `author_year`
- `latex_cite`
- `bibtex_only`
- `thebibliography`

Supported reference styles:

- `ieee`
- `apa`
- `chicago`
- `bibtex`

## Related Tests

- `tests/test_writer_outputs.py`
- `tests/test_writer_editor.py` for section-editor preview/apply behavior
- `tests/test_frontend_writer_static.py` for writer editor UI wiring

These tests cover:

- docs output with inferred defaults
- LaTeX output with `thebibliography`
- ownership enforcement on read
- missing selected-paper handling

## Related Docs

- `README.md`
- `docs/TEST_POSTMAN.md`
- `docs/user-journey.md`
- `plans/phase-3-writer-qa.md`
