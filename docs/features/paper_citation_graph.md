# Paper Citation Graph

This feature exposes one read endpoint that returns both:

- the papers that cite a project paper
- the papers that the project paper references

It is an on-demand read-through over Semantic Scholar. The backend does not persist citation graph payloads in v1.

## API

| Purpose | Method | Path |
|---|---|---|
| Read cited-by and references for one project paper | `GET` | `/projects/{project_id}/papers/{paper_id}/citation-graph` |

Query params:

- `limit` — optional, default `20`, min `1`, max `100`

## Behavior

1. The route verifies project ownership with `get_owned_project_or_404`.
2. It loads the local project paper with `get_project_paper_or_404`.
3. `PaperCitationService` resolves the exact upstream paper in Semantic Scholar using strict identifiers only:
   - Semantic Scholar paper id for `source="semantic_scholar"`
   - `ARXIV:<id>` or `URL:<arxiv_url>` for `source="arxiv"`
   - `DOI:<doi>` for uploaded or legacy papers that have a DOI
4. After resolution, the service calls:
   - `GET /graph/v1/paper/{paper_id}/citations`
   - `GET /graph/v1/paper/{paper_id}/references`
5. The response returns `citation_count`, `reference_count`, `cited_by`, and `references`.

## Error Mapping

- `400 Bad Request` — the local paper cannot be resolved exactly to Semantic Scholar
- `404 Not Found` — the project paper does not exist, or Semantic Scholar cannot find the exact upstream paper
- `502 Bad Gateway` — Semantic Scholar fails or times out

## Notes

- Title search is intentionally not used in v1 because it can silently match the wrong paper.
- arXiv papers are supported by resolving them through Semantic Scholar first, then reading citations and references from the resolved Semantic Scholar paper id.
- `SEMANTIC_SCHOLAR_API_KEY` is optional but recommended to avoid shared unauthenticated throttling.
