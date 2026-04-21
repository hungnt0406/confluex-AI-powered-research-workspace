# Product Backlog — A20-App-143

> Automated Literature Review — multi-agent pipeline (Searcher → Reader → Writer → QA).

**Last updated:** 2026-04-21
**Owner:** Team AI build 143 - Trần Ngọc Hùng - Trần Gia Khánh - Nguyễn Lâm Tùng
**Sources of truth:** `CORE_FEATURES.md`, `USER_STORIES.md`, `plans/phase-*.md`, `JOURNAL.md`, `WORKLOG.md`

---

## How to use this file

- One ordered list of everything the team is doing, has done, or plans to do.
- `EPICS` come from `CORE_FEATURES.md` + cross-cutting tracks.
- `STORIES` come from `USER_STORIES.md` (and new ones discovered during grooming).
- `TASKS` come from `plans/phase-*.md` and the Repo Change Log in `JOURNAL.md`.
- **Update this file in the same PR** as the code change. Mirror P0 items to GitHub Issues if the team prefers the board view.
- Workflow: `Backlog → Ready → In Progress → In Review → Done` (archived under **Shipped**).

### Legend

| Field | Values |
|---|---|
| Priority | `P0` must · `P1` should · `P2` could · `Nice` later |
| Status   | `⬜ Todo` · `🟡 Ready` · `🔄 In Progress` · `👀 In Review` · `✅ Done` · `⛔ Blocked` · `🗄️ Deferred` |
| Phase    | `1` Foundation · `2` Searcher/Reader · `3` Paper Understanding · `3W` Writer+QA · `4` UI/Deploy · `5` Polish/Demo · `Post-MVP` |

### Definition of Ready

- [ ] Story has acceptance criteria
- [ ] Linked to an epic + phase
- [ ] Owner assigned
- [ ] No open blocker

### Definition of Done (matches `AGENTS.md`)

- [ ] PR merged with summary + changed files
- [ ] `ruff check .`, `mypy backend/`, `pytest tests/ -x` green (see `README.md`)
- [ ] `JOURNAL.md` updated with `done / doing / blocked`
- [ ] AI prompt logs auto-submitted (pre-push hook installed via `bash scripts/setup_hooks.sh`)

---

## Current focus (Week 4 – 5, Phase 4)

| ID | Item | Priority | Status |
|---|---|---|---|
| S-14 | Writer downloads: `.bib`, `.tex`, `.docx`, plain refs | P0 | 🟡 Ready |
| S-15 | Frontend — Topic-input screen | P0 | 🟡 Ready |
| S-16 | Frontend — Pipeline run screen with SSE progress | P0 | ⬜ Todo |
| S-17 | Frontend — Paper list + filters + expand summary | P0 | ⬜ Todo |
| S-18 | Frontend — Writer workspace & draft editor | P0 | ⬜ Todo |
| S-19 | Deployment: Railway (backend) + Vercel (frontend) | P0 | ⬜ Todo |

---

## Epics overview

| ID | Epic | Priority | Phase | Status |
|---|---|---|---|---|
| E01 | Topic input & query engine | P0 | 2 | ✅ Done |
| E02 | Paper search & ranking (S2 + arXiv) | P0 | 2 | ✅ Done |
| E03 | Paper summarizer (structured) | P0 | 2 | ✅ Done |
| E04 | Literature review / grounded writer | P0 | 3W | 🔄 In Progress (backend done) |
| E05 | Citation export (APA / IEEE / Chicago) | P0 | 3W | 🔄 In Progress |
| E06 | Draft export Word / LaTeX | P0 | 3W + 4 | 🔄 In Progress |
| E07 | Paper library (projects, tags, annotate) | P0 | 1 + 4 | 🔄 In Progress |
| E08 | User PDF upload + gap analysis | P1 | 5 / Post-MVP | ⬜ Todo |
| E09 | Timeline view | P1 | Post-MVP | 🗄️ Deferred |
| E10 | Citation checker | P2 | Post-MVP | 🗄️ Deferred |
| E11 | Disagreement map | P2 | Post-MVP | 🗄️ Deferred |
| E12 | Multi-project workspace | Nice | Post-MVP | 🗄️ Deferred |
| E13 | Share & collaborate | Nice | Post-MVP | 🗄️ Deferred |
| E14 | Platform / Foundations (auth, DB, CI, deploy) | P0 | 1 + 4 | 🔄 In Progress |
| E15 | Paper understanding (PDF grounding + per-paper Q&A) | P0 | 3 | ✅ Done |
| E16 | Quality, Demo & Docs | P0 | 5 | ⬜ Todo |

---

## Epic E01 — Topic input & query engine (P0, Phase 2) — ✅

**Goal:** Turn a natural-language topic into diverse, multi-angle search queries.

### S-01 — Auto discovery from free-text topic
As a PhD student, I want to type my topic in natural language and get a ranked list of relevant papers, so that I don't spend weeks searching manually.

**Acceptance**
- [x] `POST /projects/{id}/run` produces ≥ 5 expanded queries from one topic
- [x] Deterministic offline fallback when `OPENROUTER_API_KEY` missing
- [x] Queries persisted on the pipeline run

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-101 | LLM query-expansion prompt (5–8 queries, multi-angle) | P0 | ✅ | phase-2 §1 |
| T-102 | Pydantic `SearchQuery` structured output | P0 | ✅ | phase-2 §1 |
| T-103 | Persist queries + offline fallback | P0 | ✅ | phase-2 §1 |

---

## Epic E02 — Paper search & ranking (P0, Phase 2) — ✅

**Goal:** Multi-source retrieval + semantic ranking, not citation-count ranking.

### S-02 — Fetch and dedup from Semantic Scholar + arXiv
As a researcher, I want results from more than one source merged cleanly, so that I don't have to reconcile duplicates myself.

**Acceptance**
- [x] Semantic Scholar + arXiv fetched in parallel (`asyncio.gather`)
- [x] Dedup by DOI → normalized title
- [x] Dedup prefers candidate with `pdf_url` available (2026-04-16)
- [x] Abstract length ≥ 100 chars and year ≥ `year_start` filters

### S-03 — Rank by semantic relevance
As a PhD student, I want papers ranked by closeness to my topic, so that I read the most relevant ones first.

**Acceptance**
- [x] Topic + (title+abstract) embedded, cosine similarity → 0-100 score
- [x] Top-N kept (default 30) and written to `papers.relevance_score`
- [x] LangGraph warning branch when `ranked_papers < 5`

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-201 | Semantic Scholar async client (rate-limited) | P0 | ✅ | phase-1 §3 |
| T-202 | arXiv client (feedparser) | P0 | ✅ | phase-1 §3 |
| T-203 | Dedup + quality filter | P0 | ✅ | phase-2 §2 |
| T-204 | Dedup prefers `pdf_url` | P0 | ✅ | JOURNAL 2026-04-16 |
| T-205 | Embedding ranking pipeline | P0 | ✅ | phase-2 §3 |
| T-206 | Warning branch for sparse results | P0 | ✅ | phase-2 §6 |
| T-207 | Eval harness `tests/test_search_quality.py` | P1 | ✅ | phase-2 §5 |
| T-208 | Paginated `GET /projects/{id}/papers` | P0 | ✅ | JOURNAL 2026-04-11 |

---

## Epic E03 — Paper summarizer (P0, Phase 2) — ✅

### S-04 — Structured per-paper summary
As a PhD student, I want each paper summarized as problem/method/result/relevance, so that I can triage without reading full PDFs.

**Acceptance**
- [x] One LLM call per top-N paper, batched under `asyncio.Semaphore(5)`
- [x] Pydantic-validated JSON, retry once on parse failure
- [x] Error recorded on `summaries` row when both attempts fail

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-301 | Summary prompt + JSON schema | P0 | ✅ | phase-2 §4 |
| T-302 | Retry + error flag | P0 | ✅ | phase-2 §4 |
| T-303 | Persist to `summaries` table | P0 | ✅ | phase-2 §4 |

---

## Epic E15 — Paper understanding (P0, Phase 3) — ✅

**Goal:** User can pick one paper and have a grounded, persisted conversation about it.

### S-05 — PDF grounding infrastructure
As a researcher, I want the system to read the actual PDF (not just abstract), so that answers cite real content from the paper.

**Acceptance**
- [x] `paper_documents` + `paper_chunks` tables with embeddings
- [x] OpenRouter `native` PDF engine with `cloudflare-ai` retry
- [x] On-demand extraction triggered from first-ask endpoint
- [x] NUL-byte sanitization before PostgreSQL insert (2026-04-16 hotfix)
- [x] Graceful fallback to title + abstract + summary when grounding fails

### S-06 — First ask + follow-up turns
As a researcher, I want to chat with one paper and have the system remember the thread server-side.

**Acceptance**
- [x] `POST /projects/{id}/papers/{paper_id}/conversations` creates first turn
- [x] `POST …/conversations/{conversation_id}/messages` appends grounded follow-ups
- [x] Recent-history + top-k chunk retrieval per follow-up
- [x] `GET` list/detail endpoints for persisted conversations
- [x] Cross-user, cross-project, mismatched `paper_id/conversation_id` rejected

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-401 | Persist `source_paper_id`, `source_url`, `pdf_url` on `papers` | P0 | ✅ | phase-3a Phase 3A |
| T-402 | OpenRouter document extraction service | P0 | ✅ | phase-3a Phase 3B |
| T-403 | `paper_documents` + `paper_chunks` migrations | P0 | ✅ | phase-3a Phase 3B |
| T-404 | Chunking + embedding persistence | P0 | ✅ | phase-3a Phase 3B |
| T-405 | `paper_conversations` + `paper_messages` tables | P0 | ✅ | phase-3a Phase 3C |
| T-406 | First-ask endpoint | P0 | ✅ | phase-3a Phase 3D |
| T-407 | Follow-up message endpoint | P0 | ✅ | phase-3a Phase 3E |
| T-408 | List/detail read APIs | P0 | ✅ | phase-3a Phase 3F |
| T-409 | Nested tx + NUL-byte fix for extraction | P0 | ✅ | JOURNAL 2026-04-16 |

---

## Epic E04 — Grounded writer & literature review (P0, Phase 3W) — 🔄

**Goal:** User selects papers + writes an instruction → grounded writer produces prose / references / LaTeX artifacts, with QA.

### S-07 — User-invoked writer generation
As a researcher, I want to select papers and describe what I want written, so that the output fits my current writing task (related work, background, comparison, …).

**Acceptance**
- [x] `POST /projects/{id}/writer/generate` accepts `paper_ids`, `instruction`, `output_target`, `citation_mode`, `reference_style`
- [x] Writer output is grounded only to selected papers
- [x] Persisted `writer_outputs` row with snapshot + QA flags
- [x] `GET /projects/{id}/writer/outputs/{output_id}` rehydrates without regenerating
- [x] Discovery graph kept at `searcher → reader`; writer is on-demand

### S-08 — Writer QA validation
As a researcher, I want the system to flag unsupported claims, missing references, and malformed LaTeX, so that I can trust what I paste into my draft.

**Acceptance**
- [x] Body-citation → reference-entry integrity check
- [x] Missing core metadata flagged as warning
- [x] Malformed `thebibliography` / `\cite{}` flagged as error
- [x] Empty/near-empty output flagged

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-501 | Writer request schema | P0 | ✅ | phase-3W §1 |
| T-502 | `POST /projects/{id}/writer/generate` endpoint | P0 | ✅ | phase-3W §2 |
| T-503 | `backend/agents/writer.py` grounded agent | P0 | ✅ | phase-3W §3 |
| T-504 | `backend/agents/qa.py` writer QA | P0 | ✅ | phase-3W §5 |
| T-505 | `writer_outputs` persistence + migration | P0 | ✅ | phase-3W §7 |
| T-506 | `GET /writer/outputs/{id}` rehydrate endpoint | P0 | ✅ | phase-3W §7 |
| T-507 | Focused writer tests `tests/test_writer_outputs.py` | P0 | ✅ | JOURNAL 2026-04-17 |

---

## Epic E05 — Citation export (P0, Phase 3W) — 🔄

### S-09 — Deterministic citation & reference formatter
As a researcher, I want references rendered correctly for my target (LaTeX/docs/markdown) and style (IEEE/APA/Chicago/BibTeX), so that I paste into my paper with no cleanup.

**Acceptance**
- [x] `latex + latex_cite` → `\cite{key}` + BibTeX entries
- [x] `latex + thebibliography` → ready-to-paste block
- [x] `docs/markdown + numbered` → `[1]`, `[2]` + formatted reference list
- [x] `docs + author_year` → `(Author, Year)` + human-readable list
- [x] Deterministic, stable citation keys
- [x] Every body citation maps to a generated reference artifact

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-601 | `backend/services/citations.py` formatter layer | P0 | ✅ | phase-3W §4 |
| T-602 | Stable citation-key generator | P0 | ✅ | phase-3W §4 |
| T-603 | Reference-style coverage (IEEE/APA/Chicago/BibTeX) | P0 | ✅ | phase-3W §4 |

---

## Epic E06 — Draft export Word / LaTeX (P0, Phase 3W + Phase 4) — 🔄

### S-14 — Writer output downloads
As a researcher, I want to download the writer output as `.bib`, `.tex`, `.docx`, or plain-text references, so that I can drop it straight into my editor.

**Acceptance**
- [ ] `GET /projects/{id}/writer/outputs/{output_id}/download?format=bib|tex|docx|txt`
- [ ] `.docx` via `python-docx` passes Word on Windows + Mac + Google Docs
- [ ] Proper `Content-Disposition` and CORS headers for direct download
- [ ] Empty/invalid format → 400 with actionable error

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-701 | `.bib` download endpoint | P0 | ⬜ Todo | phase-3W §7, JOURNAL 2026-04-18 |
| T-702 | `.tex` download endpoint | P0 | ⬜ Todo | phase-3W §7 |
| T-703 | `.docx` download endpoint (python-docx) | P0 | ⬜ Todo | phase-4 Screen 4 |
| T-704 | Plain-text references endpoint | P1 | ⬜ Todo | phase-3W §7 |
| T-705 | Cross-platform Word/Docs open test | P0 | ⬜ Todo | phase-5 §1 |

---

## Epic E07 — Paper library (P0, Phase 1 + Phase 4) — 🔄

### S-10 — Project CRUD + paper library
As a user, I want to organize papers inside projects, so that I can come back to them later.

**Acceptance**
- [x] `POST /projects`, `GET /projects`, `GET /projects/{id}`
- [x] Paginated `GET /projects/{id}/papers`
- [ ] Frontend list view with status (candidate / ranked / summarized)
- [ ] Per-project citation format and year range editable from UI
- [ ] Per-paper include/exclude checkbox feeds writer selection

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-801 | Project CRUD backend | P0 | ✅ | phase-1 §5 |
| T-802 | `GET /projects/{id}/papers` pagination | P0 | ✅ | JOURNAL 2026-04-11 |
| T-803 | Frontend `/projects` list | P0 | ⬜ Todo | phase-4 Shared |
| T-804 | Frontend `/projects/{id}/papers` grid | P0 | ⬜ Todo | phase-4 Screen 3 |
| T-805 | Paper tagging + notes | P1 | 🗄️ Deferred | CORE_FEATURES E07 |

---

## Epic E14 — Platform / Foundations (P0, Phase 1 + Phase 4) — 🔄

### S-11 — Auth + base API scaffold
**Acceptance**
- [x] JWT `POST /auth/register`, `POST /auth/login`
- [x] Async FastAPI + SQLAlchemy 2.0 + Alembic
- [x] GitHub Actions CI (ruff + mypy + pytest)
- [x] `.env.example` with required keys
- [x] Pre-commit hooks (`scripts/setup_hooks.sh`)

### S-12 — SSE streaming for pipeline progress
As a user, I want real-time progress while the pipeline runs, so that I know the system is alive during the long call.

**Acceptance**
- [ ] `GET /projects/{id}/stream` returns `text/event-stream`
- [ ] Event schema: `{ agent, status, message, progress }`
- [ ] Frontend hook updates UI on every event
- [ ] Pipeline timeout 120s; failed run surfaces error to user

### S-13 — Deployment
**Acceptance**
- [ ] Backend Dockerfile → Railway, PostgreSQL add-on, `/health` endpoint
- [ ] Frontend → Vercel with `NEXT_PUBLIC_API_URL`
- [ ] `alembic upgrade head` on startup (Railway resets DB on redeploy)
- [ ] CORS allows the deployed Vercel domain
- [ ] `pipeline_runs` table tracks `total_tokens`, `total_cost_usd`
- [ ] Hard abort if estimated cost > $2.00

### S-19 — Token budget guard
**Acceptance**
- [ ] `max_tokens` cap per agent call (Writer 800, QA 600)
- [ ] Per-run token/cost logged to DB

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-901 | FastAPI scaffold + routers | P0 | ✅ | phase-1 §5 |
| T-902 | JWT auth + password hashing | P0 | ✅ | phase-1 §5 |
| T-903 | Alembic migrations baseline | P0 | ✅ | phase-1 §2 |
| T-904 | GitHub Actions CI | P0 | ✅ | phase-1 §6 |
| T-905 | Pre-commit hooks | P0 | ✅ | phase-1 §1 |
| T-906 | SSE endpoint `/projects/{id}/stream` | P0 | ⬜ Todo | phase-4 Week 5 |
| T-907 | Frontend `EventSource` hook | P0 | ⬜ Todo | phase-4 Week 5 |
| T-908 | Backend Dockerfile | P0 | ⬜ Todo | phase-4 Deploy |
| T-909 | Railway deploy + PG add-on + `/health` | P0 | ⬜ Todo | phase-4 Deploy |
| T-910 | Vercel deploy + env | P0 | ⬜ Todo | phase-4 Deploy |
| T-911 | Alembic on startup | P0 | ⬜ Todo | phase-5 §6 |
| T-912 | `pipeline_runs` table + cost guard | P0 | ⬜ Todo | phase-4 Token budget |
| T-913 | CORS for Vercel domain | P0 | ⬜ Todo | phase-4 Deploy |

---

## Epic E16 — Quality, Demo & Docs (P0, Phase 5) — ⬜

### S-15 — Frontend: Topic input screen
Route `/projects/new` — textarea, year range, max papers, citation format toggle, submit → `POST /projects` → redirect.

### S-16 — Frontend: Pipeline run screen
Route `/projects/{id}/run` — 4-step progress bar with SSE events; auto-redirect on completion.

### S-17 — Frontend: Paper list screen
Route `/projects/{id}/papers` — sortable table, relevance pill, expandable summary, year/score filters, include-in-writer checkbox.

### S-18 — Frontend: Writer workspace & draft editor
Route `/projects/{id}/writer` + `/projects/{id}/draft` — multi-select paper picker, prompt box, output-target + citation-style selectors, starter actions (`Related work`, `Reference section`, `LaTeX subsection`, `BibTeX`, `Compare methods`), result preview, QA flags highlighted inline, copy/download actions.

### S-20 — Edge-case hardening
Run on 10 adversarial topics and fix crashes (very broad, very narrow, non-English abstracts, special chars, offline).

### S-21 — Performance < 90s per full run
- [ ] Embedding cache (`embedding_cache` table keyed by abstract hash)
- [ ] Paper-search cache (7-day TTL)
- [ ] Loading skeleton UI
- [ ] Profile each step via `time.perf_counter` → log to DB

### S-22 — Real-user testing (3 NCS / researchers)
- [ ] 3 observation sessions, no helping
- [ ] Top-5 friction points fixed before demo

### S-23 — Demo prep
- [ ] Demo topic chosen and pre-warmed the night before
- [ ] 5-minute script rehearsed 3+ times
- [ ] Pre-recorded backup screen recording
- [ ] QA-flag "wow moment" clearly visible

### S-24 — README + pitch
- [ ] Live URL + demo GIF in README
- [ ] Tech-stack badge row
- [ ] Local setup in < 5 commands
- [ ] Architecture diagram
- [ ] 1-page pitch PDF

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-1001 | `/projects/new` page | P0 | ⬜ Todo | phase-4 Screen 1 |
| T-1002 | `/projects/{id}/run` SSE progress page | P0 | ⬜ Todo | phase-4 Screen 2 |
| T-1003 | `/projects/{id}/papers` list + filters | P0 | ⬜ Todo | phase-4 Screen 3 |
| T-1004 | `/projects/{id}/draft` editor + QA flags | P0 | ⬜ Todo | phase-4 Screen 4 |
| T-1005 | `/projects/{id}/writer` workspace | P0 | ⬜ Todo | phase-3W §6 |
| T-1006 | Auth pages `/login`, `/register` | P0 | ⬜ Todo | phase-4 Shared |
| T-1007 | Top nav + project name + logout | P0 | ⬜ Todo | phase-4 Shared |
| T-1008 | Embedding cache table + lookup | P1 | ⬜ Todo | phase-5 §3 |
| T-1009 | Paper-search cache (7-day) | P1 | ⬜ Todo | phase-5 §3 |
| T-1010 | Step-timing profiler | P1 | ⬜ Todo | phase-5 §3 |
| T-1011 | 10-topic adversarial run | P0 | ⬜ Todo | phase-4 edge cases |
| T-1012 | Recruit + run 3 user tests | P0 | ⬜ Todo | phase-5 §1 |
| T-1013 | Demo script + rehearsal | P0 | ⬜ Todo | phase-5 §2 |
| T-1014 | Pre-recorded backup video | P0 | ⬜ Todo | phase-5 §2 |
| T-1015 | README demo GIF + live URL + architecture | P0 | ⬜ Todo | phase-5 §5 |
| T-1016 | 1-page pitch PDF | P0 | ⬜ Todo | phase-5 §5 |

---

## Epic E08 — User PDF upload + gap analysis (P1, Phase 5 / Post-MVP)

### S-25 — Upload existing papers
As a researcher, I want to upload PDFs I already have, so that the system can complete my collection.

**Acceptance**
- [ ] `POST /projects/{id}/papers/upload` accepts PDF multipart
- [ ] Extract abstract via `PyMuPDF` (`fitz`)
- [ ] Embed uploaded abstract and store in `papers`
- [ ] Gap analysis: search results not in user collection → `"You might be missing this"` badge
- [ ] Feature flagged off behind `ENABLE_PDF_UPLOAD` while under test

| ID | Task | Priority | Status | Source |
|---|---|---|---|---|
| T-1101 | Upload endpoint + storage | P1 | ⬜ Todo | phase-5 §4 |
| T-1102 | PyMuPDF extraction pipeline | P1 | ⬜ Todo | phase-5 §4 |
| T-1103 | Gap-analysis ranker | P1 | ⬜ Todo | phase-5 §4 |
| T-1104 | UI "missing" badge + upload dropzone | P1 | ⬜ Todo | phase-5 §4 |

---

## Later (Post-MVP)

| Epic | Story | Priority | Notes |
|---|---|---|---|
| E09 | Timeline view (concept evolution, D3.js) | P1 | Visualize topic growth 2015 → now |
| E10 | Citation checker on user-pasted draft | P2 | Scan draft → flag claims without citation |
| E11 | Disagreement map (conflicting results) | P2 | LLM claim extraction + comparison |
| E12 | Multi-project workspace / tenants | Nice | Postgres multi-tenant |
| E13 | Share project with advisor + comments | Nice | Real-time vs async collab — to be decided |

---

## Cross-cutting / engineering backlog

| ID | Item | Priority | Status | Notes |
|---|---|---|---|---|
| X-01 | Replace Python `fitz` dependency or gate `tests/test_reference_files.py` | P1 | ⬜ Todo | JOURNAL 2026-04-16: missing in local env |
| X-02 | Startup health/migration check | P1 | ⬜ Todo | JOURNAL 2026-04-18 lesson learned |
| X-03 | OpenRouter key-invalid early degradation | P1 | ⬜ Todo | JOURNAL 2026-04-18 lesson learned |
| X-04 | Observability: per-agent tokens, latency, cost | P1 | ⬜ Todo | phase-4 Token budget |
| X-05 | Graceful handling of publisher-blocked PDF URLs | P1 | ⬜ Todo | JOURNAL 2026-04-18 |
| X-06 | Eval harness coverage 5 → 10 golden topics | P2 | ⬜ Todo | phase-2 §5 |
| X-07 | Writer quality when only metadata fallback is available | P1 | ⬜ Todo | JOURNAL 2026-04-18 plan |
| X-08 | Writer additional QA rules (unsupported synthesis) | P1 | ⬜ Todo | JOURNAL 2026-04-18 plan |

---

## Shipped (archive)

Derived from `JOURNAL.md` Repo Change Log — most-recent first.

- **2026-04-18** — Weekly summaries reformatted to match `## Tuần N — DD/MM/YYYY` template; Weeks 2–3 backfilled.
- **2026-04-17** — Phase 3 Writer + QA backend slice shipped: `writer_outputs` model & migration, `POST /writer/generate`, `GET /writer/outputs/{id}`, `backend/agents/{writer,qa}.py`, `backend/services/{citations,writer_outputs}.py`, discovery graph narrowed to `searcher → reader`. Tests green (47 passed, 3 skipped).
- **2026-04-17** — Phase 3 plan rewritten to user-invoked writer workflow (see `plans/phase-3-writer-qa.md`).
- **2026-04-16** — Paper-conversation `500` hotfix: NUL-byte stripping + nested-tx isolation for extraction. Regression test added.
- **2026-04-16** — Dedup now prefers `pdf_url` over Semantic Scholar source bias.
- **2026-04-16** — Phase 3E follow-up messages + Phase 3F list/detail APIs shipped (41 passed, 3 skipped).
- **2026-04-16** — Phase 3C conversation persistence shipped (`paper_conversations`, `paper_messages`, first-ask endpoint).
- **2026-04-16** — Phase 3B OpenRouter PDF extraction shipped (`paper_documents`, `paper_chunks`, `native → cloudflare-ai` retry, deterministic offline fallback).
- **2026-04-14** — Phase 3A paper metadata foundation shipped (`source_paper_id`, `source_url`, `pdf_url`).
- **2026-04-11** — Phase 2 Searcher + Reader shipped: query expansion, multi-source retrieval, embedding ranking, structured summaries, warning-branch routing, paginated `GET /projects/{id}/papers`.
- **2026-04-11** — Phase 1 foundation shipped: FastAPI async scaffold, auth, project CRUD, pipeline placeholder, Alembic, CI, frontend shell.

---

## Grooming cadence

- **Monday 30 min:** reorder Backlog, promote items to Ready, split anything > 2 days.
- **Daily:** one `P0` in `In Progress` per person. Update this file + `JOURNAL.md` in the same PR.
- **End of phase:** tick phase's checkpoint in `plans/phase-*.md`, move stories to `Shipped`, archive above.

## PR hygiene

- Reference the task/story ID in the PR title — e.g. `T-701 / S-14: writer .bib download endpoint`.
- Follow PR description format in `AGENTS.md` (Summary + Changes).
- Run `bash scripts/setup_hooks.sh` once per clone so AI prompts log on push.
