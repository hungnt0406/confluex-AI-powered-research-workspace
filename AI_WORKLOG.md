# AI Worklog - 2026-05-05

## Implementation Details: Citation Graph Import & CI Hardening

### Background
The project needed a way to import papers directly from the citation graph into the project library. This involves verifying ownership, preventing duplicates, and ensuring CI can run these tests against a proper Postgres instance.

### Changes
#### 1. Backend: Project Router
- Added `POST /projects/{id}/papers/import-citation`.
- Logic:
  - Check if paper exists by `source_paper_id` OR `doi` OR normalized `title`.
  - If exists, return existing paper with `created=False`.
  - If not, create new paper with `status="candidate"`.

#### 2. CI Workflow Hardening
- Updated `.github/workflows/ci.yml` to use `literature_review_test` database.
- Added `TEST_DATABASE_URL` to environment to ensure pytest uses the correct Postgres instance in CI.
- This prevents tests from trying to use a default or non-existent database during automated runs.

#### 3. Testing
- Added `test_import_project_citation_graph_paper_creates_and_deduplicates` in `tests/test_projects.py`.
- Added static regression tests in `tests/test_frontend_deep_search_static.py` for frontend integration points.

### Verification Results
- Backend tests pass.
- CI configuration verified against existing environment variables.
