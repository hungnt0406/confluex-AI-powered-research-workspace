# Phase 3 — Writer + QA Agents

**Timeline:** Week 3  
**Goal:** A draft literature review with narrative flow, inline citations, and QA flags — exportable as Word.

> The Writer's system prompt is 70% of the quality. Spend a full day on prompt engineering before touching any other code this week.

---

## Tasks

### 1. Writer agent — theme clustering
File: `backend/agents/writer.py`

- Input: list of 30 ranked + summarized papers
- LLM call: group papers into 4–6 thematic clusters
- Prompt: "Given these paper summaries, identify the major research themes. Return JSON with theme names and which paper IDs belong to each."
- Output:
  ```json
  [
    { "theme": "CNN-based detection methods", "paper_ids": ["p1", "p4", "p7"] },
    { "theme": "Transformer architectures", "paper_ids": ["p2", "p5"] },
    ...
  ]
  ```
- Also generate a section outline: intro → theme_1 → theme_2 → ... → research gaps → conclusion
- Store outline in `drafts.outline_json`

### 2. Writer agent — section drafting
- One LLM call per section (intro + N themes + gaps + conclusion)
- Run section calls in parallel: `asyncio.gather(*[draft_section(theme) for theme in themes])`
- System prompt (craft carefully — this is the most important prompt in the project):
  ```
  You are an academic writer producing a literature review section.
  
  Rules:
  - Write in flowing academic prose. NO bullet points. NO headers within your output.
  - Each claim must be supported by a citation in the format [Author, Year].
  - Reference only the papers provided. Do not invent papers.
  - Synthesize across papers — do not describe each paper one by one.
  - Length: 300–450 words per section.
  - Tone: formal, objective, third-person.
  - End each section with a sentence linking to the next theme or identifying a gap.
  ```
- Each section references a subset of papers by ID → look up actual citation info after generation

### 3. Writer agent — citation injector
- Post-process each drafted section:
  - Replace `[Author, Year]` placeholders with `[N]` numbered references
  - Build a unified reference list in selected format (APA / IEEE / Chicago)
  - Validate: every `[N]` in the text has a corresponding entry in the reference list
- Store full draft text + reference list in `drafts` table

### 4. QA agent — claim checker
File: `backend/agents/qa.py`

- Split draft into sentences
- LLM call (fast, cheap model): "Does this sentence make a factual or quantitative claim? If yes, does it have an inline citation?"
- Flag sentences that make claims without citations → return as `qa_flags` with:
  ```json
  { "sentence": "...", "issue": "Quantitative claim without citation", "severity": "warning" }
  ```
- Also flag: duplicate sentences, suspiciously short sections (< 150 words)

### 5. QA agent — coherence check
- Single LLM call on the full draft:
  ```
  Review this literature review draft. Identify:
  1. Any logical gaps between sections
  2. Redundant content across sections  
  3. Missing transitions between paragraphs
  4. Any claim that contradicts another in the draft
  
  Return JSON: list of issues with location and suggested fix.
  ```
- Add coherence issues to `qa_flags`
- Store all flags in `drafts.qa_flags_json`

### 6. Word export
File: `backend/services/exporter.py`

- `python-docx` to generate `.docx`:
  - Title: project topic
  - Sections with `Heading 2` style
  - Body text with `Normal` style
  - Inline citations as plain text (e.g., `[1]`)
  - Full reference list at the end with `Heading 2` + numbered list
- `GET /projects/{id}/export/docx` → returns `.docx` as file download
- Also expose `GET /projects/{id}/export/citations` → plain text reference list

### 7. LangGraph wiring
- Replace stub `writer_node` and `qa_node` with real implementations
- Full graph now runs: searcher → reader → writer → qa
- Add error boundary: if writer fails, set `draft = ""` and continue to QA (which flags the empty draft)

---

## End-of-phase checkpoint

- [ ] Full 4-agent pipeline runs end-to-end on a real topic
- [ ] Draft is coherent narrative prose, not a list of paper descriptions
- [ ] Every inline citation maps to a real entry in the reference list
- [ ] QA flags returned (at minimum: missing-citation warnings)
- [ ] `.docx` download works and opens correctly in Word
- [ ] Cost per full run < $0.50

---

## Key decisions to make this week

- **Section length?** → 300–450 words keeps the draft tight and reviewable. Longer sections tend to drift into listing papers rather than synthesizing.
- **How to handle papers with no summary?** → Skip them in the Writer. Don't hallucinate summaries.
- **One big LLM call or many small ones?** → Many small calls per section. Easier to retry, easier to parallelize, cheaper per call.

---

## Cost estimate for this phase

| Operation | Calls | Est. tokens | Est. cost |
|---|---|---|---|
| Theme clustering | 1 | ~4K | ~$0.01 |
| Section drafting | 6 sections | ~30K | ~$0.09 |
| QA claim check | ~80 sentences | ~20K | ~$0.06 |
| QA coherence | 1 | ~6K | ~$0.02 |
| **Total per run** | | | **~$0.18** |

Combined with Phase 2: ~$0.26 per full pipeline run.
