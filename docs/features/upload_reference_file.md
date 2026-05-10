# Upload Reference File

This feature lets an authenticated user upload a PDF reference paper into a project. The backend stores the original PDF, extracts paper metadata/text, creates a linked `Paper` record when parsing succeeds, and uses that uploaded paper as seed context when generating search queries for the research pipeline.

## HTTP Endpoints

| Action | Method | Path | Route function |
| --- | --- | --- | --- |
| Upload a reference PDF | `POST` | `/projects/{project_id}/reference-files` | `upload_project_reference_file` in `backend/api/routers/projects.py` |
| List uploaded reference files | `GET` | `/projects/{project_id}/reference-files` | `list_project_reference_files` in `backend/api/routers/projects.py` |
| Delete an uploaded reference file | `DELETE` | `/projects/{project_id}/reference-files/{reference_file_id}` | `delete_project_reference_file` in `backend/api/routers/projects.py` |
| Run the project pipeline | `POST` | `/projects/{project_id}/run` | `queue_project_pipeline` in `backend/api/routers/projects.py` |
| Inspect project papers | `GET` | `/projects/{project_id}/papers` | `list_project_papers` in `backend/api/routers/projects.py` |

All endpoints require:

```text
Authorization: Bearer <access_token>
```

The upload endpoint expects multipart form data:

```text
file=<local PDF file>
```

## Upload Flow

The upload flow starts when the client calls:

```text
POST /projects/{project_id}/reference-files
```

The request is handled by `upload_project_reference_file` in `backend/api/routers/projects.py`.

1. FastAPI resolves dependencies declared on the route:
   - `session: DbSession` comes from `get_db_session` in `backend/db/session.py`.
   - `current_user: CurrentUser` comes from `get_current_user` in `backend/api/dependencies.py`.
   - `reference_file_service: ReferenceFileServiceDependency` comes from `get_reference_file_service` in `backend/api/dependencies.py`.

2. `get_current_user` validates the bearer token:
   - It reads the token through FastAPI's `HTTPBearer`.
   - It calls `decode_access_token` in `backend/security.py`.
   - It loads the matching `User` from the database.
   - It returns `401 Unauthorized` if the token is missing, invalid, or points to a deleted user.

3. `upload_project_reference_file` calls `get_owned_project_or_404` in `backend/api/routers/projects.py`:
   - It queries `Project` by `project.id == project_id` and `project.user_id == current_user.id`.
   - It returns `404 Not Found` if the project does not exist or does not belong to the user.

4. `upload_project_reference_file` reads the uploaded file:
   - It reads the multipart file bytes from FastAPI's `UploadFile`.
   - There is no application-level upload byte cap.

5. `upload_project_reference_file` calls `ReferenceFileService.create_reference_file` in `backend/services/reference_files.py`.

## Validation And Storage

`ReferenceFileService.create_reference_file` performs the core upload work.

### 1. Sanitize The Filename

The service normalizes the uploaded filename with:

```python
safe_filename = Path(filename or "reference.pdf").name
```

This keeps only the final path component and prevents client-provided directory paths from becoming storage paths.

### 2. Validate The Uploaded PDF

`create_reference_file` calls `validate_pdf_upload` in `backend/services/reference_files.py`.

`validate_pdf_upload` checks:

- The filename ends with `.pdf`.
- The content type is one of:
  - `application/pdf`
  - `application/x-pdf`
  - `application/octet-stream`
- The uploaded bytes are not empty.
- The file starts with the PDF magic header `%PDF` after leading whitespace is stripped.

Validation failures raise `ReferenceFileValidationError`. The route catches that exception and returns:

```text
400 Bad Request
```

### 3. Detect Duplicate Uploads

`create_reference_file` calls `compute_sha256` in `backend/services/reference_files.py`.

It then queries `ReferenceFile` for the same `project_id` and `sha256`.

If a matching row already exists, the service raises `ReferenceFileDuplicateError`. The route catches that exception and returns:

```text
409 Conflict
```

The database also enforces this with the unique constraint:

```text
uq_reference_files_project_sha256
```

on the `reference_files` table.

### 4. Write The PDF To Disk

If validation passes and the file is not a duplicate, `create_reference_file` generates a new reference ID with `generate_identifier` from `backend/db/models.py`.

It stores the file at:

```text
{REFERENCE_UPLOAD_DIR}/{project_id}/{reference_file_id}.pdf
```

The default upload root is configured in `backend/config.py`:

```text
REFERENCE_UPLOAD_DIR=data/reference_uploads
REFERENCE_MAX_EXTRACTED_CHARS=120000
```

So the default final path looks like:

```text
data/reference_uploads/<project_id>/<reference_file_id>.pdf
```

The database keeps both:

- `original_filename`: the user-visible filename from the upload.
- `storage_path`: the server-side path where the PDF was stored.

## PDF Extraction

After writing the file, `create_reference_file` calls `PaperDocumentExtractionService.extract_uploaded_pdf` through the `ReferenceExtractionClient` interface in `backend/services/reference_files.py`.

The uploaded bytes are sent through the same document extraction service used by grounded paper conversations:

- The service first tries local PDF text extraction with PyMuPDF. This is the preferred path for normal text-based uploads because it avoids provider parser corruption when the PDF already contains extractable text.
- If local extraction fails or produces no text and `OPENROUTER_API_KEY` is configured, the service sends the PDF as a base64 `data:application/pdf` URL to OpenRouter's file parser using `OPENROUTER_DOCUMENT_MODEL` and `OPENROUTER_PDF_ENGINE`.

The extracted text is then normalized and truncated to `REFERENCE_MAX_EXTRACTED_CHARS` for storage.

The upload service invokes these helper functions in `backend/services/reference_files.py`:

| Helper | Purpose |
| --- | --- |
| `normalize_pdf_text` | Normalizes line endings, whitespace, and excessive blank lines. |
| `first_plausible_title_line` | Uses the first plausible extracted text line as a fallback title. |
| `extract_year` | Finds a plausible publication year from extracted text. |
| `extract_abstract` | Extracts the abstract section or falls back to an opening excerpt. |

The metadata builder returns a `ParsedReferenceMetadata` object with:

- `title`
- `authors`
- `year`
- `abstract`
- `text`
- `error_message`

Its `parse_status` property returns:

- `parsed` when there is no parse error.
- `parse_error` when `error_message` is set.

If the PDF has no extractable text, the upload still succeeds, but the metadata records:

```text
parse_status=parse_error
error_message=PDF extraction failed: <extraction error>
```

## Database Records

After parsing, `create_reference_file` creates a `ReferenceFile` row from `backend/db/models.py`.

Important columns:

| Column | Meaning |
| --- | --- |
| `id` | Generated reference file ID. |
| `project_id` | Owning project. |
| `original_filename` | Filename sent by the user. |
| `content_type` | Upload content type. |
| `byte_size` | Uploaded byte size. |
| `sha256` | Content hash used for duplicate detection. |
| `storage_path` | Server path to the stored PDF. |
| `parse_status` | `parsed` or `parse_error`. |
| `extracted_title` | Parsed title or fallback title. |
| `extracted_authors` | Author list inferred from simple first-page/header author lines when present. |
| `extracted_year` | Year inferred from extracted text. |
| `extracted_abstract` | Parsed abstract or opening excerpt. |
| `extracted_text` | Normalized extracted text. |
| `error_message` | Parse error details, if any. |

If `parse_status == "parsed"`, `create_reference_file` also creates a linked `Paper` row.

The linked paper is created with:

```text
source=user_upload
reference_file_id=<reference_file.id>
source_paper_id=<reference_file.id>
pdf_url=<storage_path>
status=candidate
relevance_score=null
```

This linked paper is what the research pipeline later uses as search context.

It is also eligible for grounded chat. Because `pdf_url` points to the stored local PDF path, `PaperDocumentExtractionService` treats it as a local upload source, reads it from the configured upload directory, persists `paper_documents` and `paper_chunks`, and retrieves chunks for later questions.

If parsing fails, the `ReferenceFile` row is still saved, but no linked `Paper` row is created. That means the file appears in the reference-file list, but it is not used for query expansion.

Finally, `create_reference_file` commits the transaction and returns the `ReferenceFile`.

## Upload Response

After `create_reference_file` returns, `upload_project_reference_file` reloads the reference through `get_project_reference_file_or_404`.

It then sets:

```text
Location: /projects/{project.id}/reference-files/{reference_file.id}
```

and returns a `ReferenceFileRead` response from `backend/api/schemas/projects.py`.

Response fields include:

```text
id
project_id
original_filename
content_type
byte_size
sha256
parse_status
extracted_title
extracted_authors
extracted_year
extracted_abstract
linked_paper_id
error_message
created_at
updated_at
```

`linked_paper_id` is present only when parsing succeeded and a linked `Paper` row exists.

## Query Context Flow

Uploaded reference papers are used as context when the client runs:

```text
POST /projects/{project_id}/run
```

The request is handled by `queue_project_pipeline` in `backend/api/routers/projects.py`.

The function call chain is:

```text
queue_project_pipeline
  -> get_owned_project_or_404
  -> LiteraturePipelineService.run_project
  -> ProjectPipelineRunner.run
  -> ProjectPipelineRunner.build_graph
  -> ProjectPipelineRunner.searcher_node
  -> SearcherAgent.run
  -> SearcherAgent._prepare_existing_project_papers
  -> SearcherAgent._build_reference_context
  -> SearcherAgent.collect_candidates
  -> SearcherAgent.expand_queries
```

### 1. Pipeline Service

`queue_project_pipeline` calls `pipeline_service.run_project`.

`pipeline_service` is a `LiteraturePipelineService` from `backend/agents/pipeline.py`.

`LiteraturePipelineService.run_project` creates a `ProjectPipelineRunner` from `backend/agents/graph.py` and calls its `run` method.

### 2. LangGraph Runner

`ProjectPipelineRunner.run` creates an `AgentState` with:

```text
project_id
topic
year_start
candidate_limit
summary_limit
```

It builds the graph in `ProjectPipelineRunner.build_graph`.

The graph starts at `searcher_node`, then continues to `reader_node`.

The reference-file query-context behavior happens in `searcher_node`, which calls:

```python
SearcherAgent.run(state, session, project)
```

### 3. Preserve Uploaded Papers

`SearcherAgent.run` first calls `_prepare_existing_project_papers`.

`_prepare_existing_project_papers` does two important things:

1. Deletes old summaries for all project papers.
2. Deletes stale external papers, but preserves uploaded papers:

```python
delete(Paper).where(
    Paper.project_id == project_id,
    Paper.source != REFERENCE_SOURCE,
)
```

`REFERENCE_SOURCE` is defined in `backend/services/reference_files.py`:

```python
REFERENCE_SOURCE = "user_upload"
```

Then it loads all preserved uploaded papers:

```python
select(Paper).where(
    Paper.project_id == project_id,
    Paper.source == REFERENCE_SOURCE,
)
```

For each uploaded paper, it resets:

```text
status=candidate
relevance_score=null
```

This makes uploaded papers participate cleanly in the next ranking run.

### 4. Build Compact Reference Context

`SearcherAgent.run` passes those uploaded papers into `_build_reference_context`.

`_build_reference_context` converts each uploaded `Paper` into a `ReferencePaperContext`:

```python
ReferencePaperContext(
    title=paper.title,
    year=paper.year,
    abstract=paper.abstract,
    doi=paper.doi,
)
```

This intentionally uses a compact subset of the paper data. It does not send the full uploaded PDF or the full extracted text into query generation.

### 5. Generate Better Queries With LLM Context

`SearcherAgent.run` calls `collect_candidates` with:

```python
reference_context=reference_context
existing_papers=reference_papers
```

`collect_candidates` calls `expand_queries`.

If the configured LLM service is available, `expand_queries` calls `_build_query_expansion_prompt`.

`_build_query_expansion_prompt` starts with:

```text
Generate 5 to 8 academic search queries for this literature review topic.
Topic: <project topic>
```

When uploaded reference context exists, it appends up to 5 uploaded reference papers. Each reference is formatted as:

```text
<index>. <title> (<year>). Abstract/snippet: <first 700 chars of abstract>
```

It also instructs the model:

```text
The user has already uploaded these seed reference papers. Use them to generate queries for related work, missing background, and adjacent papers. Do not simply repeat only the uploaded titles.
```

The final prompt is sent through:

```python
ClaudeStructuredOutputService.generate_json(...)
```

from `backend/services/llm.py`.

The expected output is validated against `SEARCH_QUERY_SCHEMA` in `backend/agents/searcher.py`. The result is coerced into `SearchQuery` objects by `_coerce_query_payload`.

### 6. Fallback Query Generation

If the LLM is not configured, `expand_queries` calls `_build_fallback_queries`.

If the LLM call fails or returns invalid JSON, `expand_queries` also falls back to `_build_fallback_queries`.

Fallback generation still uses the uploaded references:

```text
_build_fallback_queries
  -> _build_reference_fallback_queries
```

`_build_reference_fallback_queries` tokenizes the uploaded paper titles and abstracts, removes stopwords, takes the most common terms, pairs them, and appends those term pairs to the normalized project topic.

Those reference-derived fallback queries get:

```text
focus=uploaded-reference
```

Example shape:

```text
<project topic> <reference term 1> <reference term 2>
```

### 7. Search And Deduplicate Against Uploads

After query expansion, `collect_candidates` searches each query through the configured search clients:

- `SemanticScholarSearchClient`
- `ArxivSearchClient`

Then it calls `_filter_and_deduplicate`.

`_filter_and_deduplicate` receives:

```python
existing_papers=reference_papers
```

It builds `seen_dois` and `seen_titles` from uploaded papers and filters out external search results that duplicate the uploaded references by DOI or normalized title.

This prevents the same paper from appearing twice: once as a user upload and once as an external search result.

### 8. Returned Raw Papers

`SearcherAgent.run` returns raw papers in this order:

```python
[*reference_papers, *paper_models]
```

That means uploaded reference papers are included in the graph state before newly discovered external candidates.

Later, `ReaderAgent.run` in `backend/agents/reader.py` ranks all project papers, including uploaded `user_upload` papers, by embedding similarity to the project topic. If an uploaded reference ranks within `project.summary_limit`, it can be summarized like any other candidate.

## Listing Reference Files

The client can list uploaded reference files with:

```text
GET /projects/{project_id}/reference-files
```

The route function is `list_project_reference_files` in `backend/api/routers/projects.py`.

Flow:

```text
list_project_reference_files
  -> get_owned_project_or_404
  -> select(ReferenceFile).options(selectinload(ReferenceFile.paper))
  -> ReferenceFileRead.from_reference
```

The response is ordered by:

```text
ReferenceFile.created_at DESC
```

Each item includes `linked_paper_id` when a linked uploaded-paper row exists.

## Deleting Reference Files

The client can delete an uploaded reference file with:

```text
DELETE /projects/{project_id}/reference-files/{reference_file_id}
```

The route function is `delete_project_reference_file` in `backend/api/routers/projects.py`.

Flow:

```text
delete_project_reference_file
  -> get_owned_project_or_404
  -> get_project_reference_file_or_404
  -> session.delete(reference_file.paper), if present
  -> session.delete(reference_file)
  -> session.commit
  -> anyio.to_thread.run_sync(unlink_stored_file, storage_path)
```

`unlink_stored_file` deletes the stored PDF from disk with:

```python
storage_path.unlink(missing_ok=True)
```

If disk deletion raises `OSError`, the route ignores the error after the database records have been deleted.

The endpoint returns:

```text
204 No Content
```

## Data Model Relationships

The relevant models are defined in `backend/db/models.py`.

`Project` has many `ReferenceFile` rows:

```python
Project.reference_files
```

`ReferenceFile` belongs to one `Project`:

```python
ReferenceFile.project
```

`ReferenceFile` may have one linked `Paper`:

```python
ReferenceFile.paper
```

`Paper` may point back to one `ReferenceFile`:

```python
Paper.reference_file
```

The `Paper.reference_file_id` foreign key uses:

```text
ondelete=CASCADE
unique=True
nullable=True
```

So one uploaded reference file can create at most one linked paper.

## Status And Error Summary

| Scenario | Result |
| --- | --- |
| Missing or invalid auth token | `401 Unauthorized` |
| Project does not belong to user | `404 Not Found` |
| Non-PDF filename/content type | `400 Bad Request` |
| Empty upload | `400 Bad Request` |
| Oversized upload | `400 Bad Request` |
| Bytes do not look like a PDF | `400 Bad Request` |
| Same PDF uploaded twice to same project | `409 Conflict` |
| PDF has extractable text | `ReferenceFile` row plus linked `Paper` row |
| PDF has no extractable text | `ReferenceFile` row only, with `parse_status=parse_error` |
| Delete succeeds | Database rows removed and stored PDF unlinked |

## Tests

The main tests for this feature are in `tests/test_reference_files.py`.

Important test coverage includes:

- `test_upload_list_and_delete_reference_file`
- `test_upload_reference_file_rejects_duplicate`
- `test_upload_reference_file_rejects_non_pdf`
- `test_upload_reference_file_rejects_oversized_pdf`
- `test_reference_file_upload_requires_authentication`
- `test_reference_file_upload_requires_project_ownership`

The pipeline behavior is covered in `tests/test_searcher_reader.py`.

Important tests include:

- `test_searcher_query_expansion_receives_uploaded_reference_context`
- `test_searcher_preserves_uploaded_reference_papers_and_deduplicates_against_them`
