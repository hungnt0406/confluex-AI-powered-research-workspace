# Paper Citation Graph

This feature exposes one read endpoint that returns both:

- the papers that cite a project paper
- the papers that the project paper references

It is an on-demand read-through over Semantic Scholar. The backend does not persist citation graph payloads in v1.

## API

| Purpose | Method | Path |
|---|---|---|
| Read cited-by and references for one project paper | `GET` | `/projects/{project_id}/papers/{paper_id}/citation-graph` |
| Import a citation-graph paper into the project | `POST` | `/projects/{project_id}/papers/import-citation` |

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
5. The response returns `citation_count`, `reference_count`, `cited_by`, and `references`. Each related-paper item also includes its own `citation_count` (when Semantic Scholar provides one), used by the frontend to size graph nodes.

`POST /projects/{project_id}/papers/import-citation` accepts the same related-paper metadata shape returned in `cited_by` and `references`. It creates a project paper with `status="candidate"` and no relevance score, or returns the existing project paper when it matches by provider id, DOI, or normalized title.

## Frontend visualization

The Confluex frontend renders a Connected-Papers-style citation neighborhood inline in the right-hand `ContextPanel` under a "Graph" tab.

- The seed paper is picked from a dropdown of the project's papers; only papers with a Semantic Scholar id, arXiv id, or DOI are selectable.
- Up to 10 cited-by nodes and 20 reference nodes are rendered around the seed (capped client-side from a `limit=20` request).
- Node size scales with `citation_count` (logarithmic), node color encodes recency (older publications fade toward background), and clicking a node opens an in-app preview with metadata, abstract snippet, project-library status, and a Semantic Scholar link.
- Related papers already present in the project are marked with a distinct checked border. Missing related papers can be imported from the preview with "Add to project".
- The Graph tab caches citation payloads in the chat workspace state by project, seed paper, and limit. Reopening the tab or switching back to a previously loaded seed renders from cache.
- After a foreground graph load, the frontend quietly prefetches the next few resolvable seed papers so seed switching is faster without eagerly fetching every project paper.
- A List view renders the same seed, reference, and cited-by data as semantic HTML lists for keyboard and screen-reader access.
- The graph is rendered with `react-force-graph-2d`, dynamically imported with `ssr: false` so it never executes during server-side rendering.
- The backend still does not persist graph payloads; caching is frontend session state only.

## Error Mapping

- `400 Bad Request` — the local paper cannot be resolved exactly to Semantic Scholar
- `404 Not Found` — the project paper does not exist, or Semantic Scholar cannot find the exact upstream paper
- `502 Bad Gateway` — Semantic Scholar fails or times out

## Notes

- Title search is intentionally not used in v1 because it can silently match the wrong paper.
- arXiv papers are supported by resolving them through Semantic Scholar first, then reading citations and references from the resolved Semantic Scholar paper id.
- `SEMANTIC_SCHOLAR_API_KEY` is optional but recommended to avoid shared unauthenticated throttling.
