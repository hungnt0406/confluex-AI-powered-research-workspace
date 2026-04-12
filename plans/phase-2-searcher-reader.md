# Phase 2 — Searcher + Reader Agents

**Timeline:** Week 2  
**Goal:** Given a topic description, find and rank relevant papers with relevance scores and structured summaries.

> Use `asyncio.gather()` for parallel API calls — sequential fetching for 50 papers is 2+ minutes. Target under 30 seconds total.

---

## Tasks

### 1. Searcher agent — query expansion
File: `backend/agents/searcher.py`

- LLM call (Claude Sonnet) with topic → generate 5–8 diverse search queries
- Prompt strategy: produce queries at different levels of specificity:
  - Broad: the general field
  - Narrow: the specific method or dataset
  - By technique: e.g., "transformer-based", "CNN approach"
  - By application domain
  - By year: "recent advances 2022–2024"
- Return structured output (Pydantic model): `list[SearchQuery]`
- Store queries in `AgentState.queries`

### 2. Searcher agent — multi-source fetch & dedup
- Run all queries against Semantic Scholar AND arXiv in parallel:
  ```python
  results = await asyncio.gather(
      *[semantic_scholar.search(q) for q in queries],
      *[arxiv.search(q) for q in queries]
  )
  ```
- Dedup by DOI first, then by normalized title (lowercase + strip punctuation)
- Filter: year ≥ `project.year_start`, must have abstract
- Cap at `N` candidates (default 60, configurable per project)
- Save raw candidates to `papers` table with `status = "candidate"`

### 3. Reader agent — embedding + relevance ranking
File: `backend/agents/reader.py`

- Embed the topic description once: `topic_embedding = embed(topic)`
- Embed each paper's title + abstract: `paper_embedding = embed(title + " " + abstract)`
- Compute cosine similarity → relevance score (0–100)
- Sort descending, keep top N (default 30)
- Update `papers.relevance_score` in DB
- Store ranked list in `AgentState.ranked_papers`

**Embedding model:** OpenAI `text-embedding-3-small` (cheap, fast) or Anthropic via LangChain.

### 4. Reader agent — structured paper summary
- One LLM call per paper (batch with rate limiting via `asyncio.Semaphore(5)`)
- System prompt enforces structured JSON output:
  ```json
  {
    "problem": "What problem does this paper address?",
    "method": "What approach/technique did they use?",
    "result": "What were the key findings or metrics?",
    "relevance": "Why is this relevant to [topic]? 1–2 sentences."
  }
  ```
- Parse with Pydantic. On parse failure: retry once, then store `null` with error flag.
- Write to `summaries` table
- Store in `AgentState.summaries`

### 5. Evaluation harness
File: `tests/test_search_quality.py`

- Define 5 golden test cases:
  ```python
  GOLDEN = [
      {
          "topic": "deep learning for lung cancer detection in CT scans",
          "must_include_titles": ["A Survey of Deep Learning for Lung Cancer Detection", ...]
      },
      ...
  ]
  ```
- Assert: top-10 results contain ≥ 1 known ground-truth paper per topic (recall@10 ≥ 80%)
- Run as a separate pytest mark (`@pytest.mark.eval`) so it doesn't block regular CI

### 6. LangGraph node wiring
- Replace dummy `searcher_node` and `reader_node` with real implementations
- Add conditional edge: if `len(ranked_papers) < 5` → log warning + continue (don't crash)
- Update `AgentState` at each step; confirm state flows correctly through to `writer_node` (still a stub)

---

## End-of-phase checkpoint

- [ ] `POST /projects/{id}/run` triggers real Searcher + Reader
- [ ] 30+ papers returned, ranked, with relevance scores stored in DB
- [ ] Each paper has a structured summary (problem / method / result / relevance)
- [ ] Full pipeline (search + embed + summarize 30 papers) runs in < 60 seconds
- [ ] Eval harness passes for ≥ 4/5 golden test cases

---

## Key decisions to make this week

- **How many papers to summarize?** → Rank first, then summarize only the top 30. Summarizing 60+ is slow and expensive.
- **Embedding model?** → `text-embedding-3-small` costs ~$0.002 per 1M tokens — essentially free at this scale. Use it.
- **What if arXiv/Semantic Scholar returns garbage?** → Add a minimum-quality filter: abstract length ≥ 100 chars, year within range. Drop the rest silently.

---

## Cost estimate for this phase

| Operation | Papers | Est. tokens | Est. cost |
|---|---|---|---|
| Query expansion | 1 call | ~500 | < $0.01 |
| Embeddings | 60 papers | ~60K | < $0.01 |
| Summaries | 30 papers | ~45K | ~$0.07 |
| **Total per run** | | | **~$0.08** |
