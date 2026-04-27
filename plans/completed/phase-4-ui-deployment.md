# Phase 4 — UI, Streaming & Deployment

**Timeline:** Week 4–5  
**Goal:** Deployed URL, working login, full pipeline visible in the browser — shareable for demo day.

> Run the full pipeline 10 times with different topics before calling this phase done. Fix what breaks at the edges — empty results, very broad topics, non-English abstracts.

---

## Tasks

### Week 4 — UI

#### Screen 1: Topic input
Route: `/projects/new`

- Textarea: topic description (placeholder: "Describe your research topic in natural language...")
- Two inputs in a row: year range start + max papers (defaults: 2018, 30)
- Citation format toggle: IEEE (default) / APA / Chicago
- Submit button → `POST /projects` then redirect to pipeline screen

#### Screen 2: Pipeline status (real-time)
Route: `/projects/{id}/run`

- 4-step progress bar: Searcher → Reader → Writer → QA
- Each step shows: pending / in-progress (spinner) / done (checkmark) / failed (×)
- Live log line below the bar: "Reader: summarizing paper 23 of 30..."
- On completion: auto-redirect to results screen

#### Screen 3: Paper list
Route: `/projects/{id}/papers`

- Table/card list sorted by relevance score (descending)
- Each row: title, authors, year, source badge (Semantic Scholar / arXiv), relevance % pill
- Click row → expand to show full structured summary (problem / method / result / relevance)
- Checkbox per paper: include/exclude from draft regeneration
- Filter bar: by year range, by relevance threshold (slider), search by keyword

#### Screen 4: Draft editor
Route: `/projects/{id}/draft`

- Left sidebar: outline (section names, click to jump)
- Main area: read-only draft text with QA flags highlighted inline
  - Yellow highlight: missing citation warning
  - Orange highlight: coherence issue
- Right panel (collapsible): QA flag list — click flag to jump to sentence
- Bottom bar: word count, paper count, citation count
- Export buttons: "Download Word" / "Copy citations"

#### Shared components
- Auth pages: `/login`, `/register`
- Project list: `/projects` — cards with topic, date, status, paper count
- Top nav: project name, user avatar, logout

### Week 5 — Streaming, deployment, hardening

#### Real-time pipeline streaming
- Backend: FastAPI SSE endpoint
  ```python
  @router.get("/projects/{id}/stream")
  async def stream_pipeline(id: str):
      async def event_generator():
          async for event in run_pipeline(id):
              yield f"data: {event.model_dump_json()}\n\n"
      return StreamingResponse(event_generator(), media_type="text/event-stream")
  ```
- Event schema:
  ```json
  { "agent": "reader", "status": "running", "message": "Summarizing paper 23 of 30", "progress": 0.76 }
  ```
- Frontend: `EventSource` in a React hook that updates pipeline state in real time

#### Deployment
- **Backend → Railway:**
  - `Dockerfile` for FastAPI app
  - Environment variables: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`
  - PostgreSQL add-on on Railway (managed)
  - Health check: `GET /health` → `{ "status": "ok" }`
- **Frontend → Vercel:**
  - `NEXT_PUBLIC_API_URL` pointing to Railway backend
  - Auto-deploy on push to `main`
- **CORS:** allow Vercel domain in FastAPI CORS middleware

#### Token budget guard
- Add `max_tokens` cap per agent call (Writer: 800, QA: 600, etc.)
- Log token usage per pipeline run to DB: `pipeline_runs` table with `total_tokens`, `total_cost_usd`
- Hard cap: if estimated cost > $2.00, abort pipeline and return error to user

#### Edge case hardening
Run the pipeline on these adversarial inputs and fix any crashes:
- Very broad topic: "machine learning"
- Very narrow topic with < 5 papers: "temporal graph neural networks for ICU mortality prediction 2023"
- Non-English papers in results (abstracts in Chinese/French)
- Topic with special characters: "C++ memory safety & Rust"
- User with no internet (graceful degradation)

---

## End-of-phase checkpoint

- [ ] Live URL accessible (Vercel + Railway both up)
- [ ] Register + login + logout works
- [ ] Pipeline runs end-to-end in browser with real-time progress
- [ ] Paper list loads with relevance scores and expandable summaries
- [ ] Draft viewer shows QA flags highlighted inline
- [ ] Word download works and opens in Microsoft Word
- [ ] 10 different topics tested without crashes

---

## Key technical decisions

- **SSE vs WebSocket for streaming?** → SSE. Simpler, one-directional, works without extra infrastructure. WebSocket only needed if user needs to send messages mid-pipeline (they don't).
- **State management on frontend?** → Zustand or React Context. No Redux — overkill for this scope.
- **Background job queue?** → For now, run pipeline in a FastAPI background task (`BackgroundTasks`). If it times out, switch to Celery + Redis in Phase 5.
- **Pipeline timeout?** → Set 120s max. If exceeded, mark run as failed and surface error to user.
