# Paper Citation Graph Endpoint

## Summary
- Add a backend-only read endpoint `GET /projects/{project_id}/papers/{paper_id}/citation-graph?limit=20` that returns both lists for the selected project paper: `cited_by` and `references`.
- Keep v1 on-demand and stateless: no DB schema change, no caching layer, no frontend work, and no change to `GET /projects/{id}/papers`.
- Use Semantic Scholar as the source of truth for both lists, including arXiv-origin papers.

## Implementation Changes
- Add new response models in `backend/api/schemas/projects.py`:
  - `CitationGraphPaperRead` with `title`, `authors`, `year`, `abstract`, `doi`, `source`, `source_paper_id`, `source_url`, `pdf_url`.
  - `PaperCitationGraphRead` with `paper_id`, `resolved_by`, `resolved_source_paper_id`, `citation_count`, `reference_count`, `cited_by`, `references`.
- Add `GET /projects/{project_id}/papers/{paper_id}/citation-graph` in `backend/api/routers/projects.py`. Query param `limit` defaults to `20`, min `1`, max `100`. Reuse the existing ownership and paper lookup helpers. Return:
  - `404` if the project or local paper is missing.
  - `400` if the paper cannot be resolved exactly to Semantic Scholar.
  - `404` if Semantic Scholar cannot find the exact paper.
  - `502` if Semantic Scholar fails or times out.
- Add a project-facing citation service in `backend/services/paper_citations.py` plus dependency wiring in `backend/api/dependencies.py`. Resolution order is fixed:
  - Semantic Scholar paper: use `paper.source_paper_id`.
  - arXiv paper: resolve through Semantic Scholar using the exact arXiv metadata already stored on the paper row; do not use title search.
  - Uploaded or legacy paper: resolve only if a DOI exists; otherwise fail fast with `400`.
- Extend `backend/services/semantic_scholar.py` with low-level helpers for canonical paper lookup, cited-by fetch, reference fetch, and normalization of returned related papers into the shared metadata shape already used elsewhere. Reuse existing timeout and API-key settings and keep request throttling conservative.
- Do not persist returned citation/reference items as project `Paper` rows in v1. The endpoint is a read-through view over Semantic Scholar data.
- Update docs: README API surface, `docs/feature-map.md`, `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md`, and add a feature deep dive for the citation-graph endpoint. When implementation edits repo files, append a timestamped `JOURNAL.md` entry referencing the work.

## Test Plan
- Add provider/client tests for Semantic Scholar citation/reference normalization and upstream error mapping.
- Add route/service tests for:
  - Semantic Scholar paper success path.
  - arXiv paper success path resolved via Semantic Scholar.
  - uploaded/local-only paper without DOI returning `400`.
  - missing project paper returning `404`.
  - upstream exact-match miss returning `404`.
  - upstream failure returning `502`.
  - `limit` validation and truncation behavior.
- Run `python -m pytest tests/test_projects.py tests/test_services.py tests/test_paper_citations.py -q`.

## Assumptions
- V1 is backend API only.
- `limit` applies independently to both `cited_by` and `references`; counts report the full upstream totals even when lists are truncated.
- Exact-match safety is more important than coverage: no title-based fallback, no fuzzy paper resolution, and no silent best-effort substitution.
