# Writer Xiaomi LLM Source Ranker Plan

## Summary
Add an LLM source ranker for Writer, but hard-wire it to the Xiaomi MiMo OpenAI-compatible endpoint. It will fetch a larger source pool, locally dedupe/filter candidates, ask MiMo to rank them for the exact document/section, then keep the best 7 for manual suggestions and auto-drafting.

## Key Changes
- Add Writer source-ranker logic inside `WriterDocumentService`.
  - Tavily retrieval pool: `12`.
  - arXiv retrieval pool: `7`.
  - Final kept sources: `7`.
- Add config:
  - `WRITER_SOURCE_RANKER_MODEL`, default `mimo-v2.5-pro`.
  - Use existing `XIAOMI_MIMO_API_KEY`.
  - Use existing `XIAOMI_MIMO_BASE_URL`, default `https://token-plan-sgp.xiaomimimo.com/v1`.
- Ranker must instantiate the existing structured-output client with:
  - `api_key=settings.xiaomi_mimo_api_key`
  - `base_url=settings.xiaomi_mimo_base_url`
  - `model=settings.writer_source_ranker_model`
- Do not fall back to OpenRouter for this ranker. If Xiaomi key is missing or MiMo fails, use deterministic local ranking.

## Ranker Behavior
- Local pre-filter:
  - Drop candidates without title.
  - Drop candidates with neither URL nor source ID.
  - Dedupe by arXiv ID, source paper ID, and normalized URL.
  - Exclude already-attached document sources.
- MiMo prompt input:
  - Document topic, thesis, section title, outline text, user answers, and `__notes__`.
  - Candidate title, source type, URL/domain, abstract/snippet, PDF availability, arXiv ID, Tavily score.
- MiMo JSON output:
  - `ranked_candidates`: ordered `{candidate_id, relevance_score, keep, rationale}`.
  - `warnings`: short recoverable issues.
- Keep only `keep=true`, capped at 7.
- If MiMo returns invalid IDs or too few kept candidates, fill remaining slots using local hybrid ranking.

## Writer Flow Changes
- Manual source search:
  - Search arXiv + Tavily.
  - Normalize candidates.
  - MiMo rerank.
  - Return top 7 in the existing `SourceCandidate` API shape.
- Auto draft:
  - Build section-aware query from topic, thesis, section title, outline, answers, and notes.
  - Search Tavily with `max_results=12`.
  - MiMo rerank for that section.
  - Persist top 7 new sources as metadata-only `Paper` records.
- Draft generation and assemble remain unchanged after source selection.

## Test Plan
- Unit tests:
  - MiMo ranker order is respected.
  - Off-topic candidates marked `keep=false` are dropped.
  - Duplicate source URLs/arXiv IDs are removed before ranking.
  - Existing attached sources are excluded.
  - Missing Xiaomi key uses local fallback, not OpenRouter.
  - Invalid MiMo output falls back locally.
- Service tests:
  - Manual source suggestions return top 7 in MiMo order.
  - Auto draft asks Tavily for 12, persists at most 7.
- Regression tests:
  - Metadata-only attach still works.
  - Auto draft still dedupes sources.
  - Citation/reference assemble still works.
  - Frontend source API shape remains unchanged.

## Assumptions
- Xiaomi MiMo is the only LLM provider allowed for source ranking.
- If `XIAOMI_MIMO_API_KEY` is absent, source ranking must degrade locally instead of calling OpenRouter.
- Ranking rationale stays backend-internal for v1.
