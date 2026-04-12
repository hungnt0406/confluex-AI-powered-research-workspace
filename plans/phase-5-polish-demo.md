# Phase 5 — Polish, Demo Prep & Handoff

**Timeline:** Week 6  
**Goal:** A demo that runs flawlessly in 5 minutes and wows the audience. Don't build new features — make what exists shine.

> The killer demo moment: show the QA agent catching a claim that needs a citation. It proves the multi-agent system is doing real work, not just wrapping GPT.

---

## Tasks

### 1. Real user testing
- Recruit 3 real NCS or researchers (not teammates)
- Give them a task: "Use this to generate a literature review for your thesis topic"
- Observe — do not help. Note every moment of confusion.
- Fix the top 5 friction points from sessions before anything else

Common issues to watch for:
- Topic input too vague → add placeholder examples in the UI
- Paper results feel irrelevant → check embedding model and similarity threshold
- Draft quality disappoints → revisit Writer system prompt
- QA flags unclear → improve flag message wording
- Export file doesn't open properly → test on Windows Word + Mac Word + Google Docs

### 2. Demo scenario preparation
Pick one compelling, specific topic that produces great results:
- Recommended: "Vision transformers for medical image segmentation, 2020–2024"
- Why: enough papers on Semantic Scholar, clear themes, impressive output

Demo script (5 minutes):

| Time | What to show |
|---|---|
| 0:00 | Open the app. "This is what a researcher sees." |
| 0:30 | Type the topic. Explain the problem: NCS spend weeks on this. |
| 1:00 | Hit run. Show real-time agent pipeline. Narrate each step. |
| 2:00 | Paper list loaded. Show relevance scores. Expand one paper summary. |
| 3:00 | Draft loaded. Read one paragraph aloud. Show it synthesizes — not lists. |
| 3:30 | Click a QA flag. "The system caught a claim that needs a citation." |
| 4:00 | Download the Word file. Open it. |
| 4:30 | "This took 90 seconds. The same thing used to take 4 weeks." |

- Pre-warm the search: run the demo topic once the night before. Cache the paper results so the live demo skips the 60s API wait if needed.
- Have a backup: a pre-recorded screen recording in case live demo fails.

### 3. Performance optimization
Target: full pipeline < 90 seconds for 30 papers

- Cache embeddings: if the same abstract was embedded before, skip the API call (hash abstract → lookup in `embedding_cache` table)
- Cache paper search: if the same query was run in the last 7 days, return cached results
- Add loading skeleton UI so the wait feels shorter
- Profile the pipeline: `time.perf_counter()` at each step → log to DB → find the bottleneck

### 4. Optional P1 feature: PDF upload
High demo impact — do if time allows (est. 1 day).

- UI: "Upload papers you already have" drag-and-drop zone
- Backend: `POST /projects/{id}/papers/upload` → accept PDF
- Extract abstract with `PyMuPDF` (`fitz.open(pdf).get_page_text(0)`)
- Embed the uploaded paper's abstract
- Gap analysis: compare uploaded papers to search results → highlight papers NOT already in user's collection
- Show gap papers with "You might be missing this" badge in the paper list

### 5. README + pitch document
- README must include:
  - One-line description
  - Live URL
  - Demo GIF (use LICEcap or Kap — record the 5-minute demo, cut to 60s)
  - Tech stack badge row
  - Local setup in < 5 commands
  - Architecture diagram (copy from PRD)
- 1-page pitch (PDF):
  - Problem: NCS spend 2–4 months on literature review
  - Solution: 4-agent pipeline (Searcher → Reader → Writer → QA)
  - Demo link
  - Team + contact

### 6. Bug buffer
Keep the last 2 days of the week completely empty.

Things that always break during rehearsal:
- Railway database resets on redeploy (add `alembic upgrade head` to startup)
- CORS blocks file download (add `Content-Disposition` header to export endpoint)
- Pipeline hangs if Semantic Scholar is slow (add 10s timeout per request)
- Word file corrupts on Windows (test `python-docx` output on actual Windows)

---

## End-of-phase checkpoint

- [ ] Demo script rehearsed 3+ times without breaking
- [ ] 3 real users have tested and top friction points fixed
- [ ] Pipeline runs in < 90 seconds on the demo topic
- [ ] README has live URL + demo GIF
- [ ] Pitch document ready (1 page PDF)
- [ ] Backup screen recording exists
- [ ] The QA flag moment is clearly visible in the demo

---

## What "done" looks like

A researcher opens the app, types their thesis topic, and 90 seconds later has:
1. A ranked list of 30 relevant papers with structured summaries
2. A 2,000-word draft literature review with narrative flow and inline citations
3. A Word file they can paste directly into their thesis
4. A list of QA flags showing exactly which claims need more evidence

That is the product. Ship that.
