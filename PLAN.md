# Project Plan — AI20K-026: Automated Literature Review

> Multi-Agent Research Survey with RAG-First Architecture

**Last Updated:** 2026-04-05  
**Status:** Planning → Awaiting approval to begin Phase 1

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [RAG-First Design](#3-rag-first-design)
4. [Tech Stack](#4-tech-stack)
5. [Project Structure](#5-project-structure)
6. [Database Schema](#6-database-schema)
7. [Pipeline Stages (Detailed)](#7-pipeline-stages-detailed)
8. [Sprint Plan](#8-sprint-plan)
9. [API Integration Details](#9-api-integration-details)
10. [Deployment](#10-deployment)
11. [Risk Register](#11-risk-register)
12. [Future: GraphRAG Extension](#12-future-graphrag-extension)

---

## 1. Overview

### The Problem

PhD candidates spend 2–4 months on literature reviews, reading 100–200 papers (60%+ are irrelevant). Advisor feedback often triggers repetitive search cycles.

### Our Solution

A web application that automates the research survey workflow using a **RAG-first pipeline**:

1. **Search** academic databases (Semantic Scholar, arXiv, PubMed) + local metadata index
2. **Filter** papers using embedding similarity (no LLM)
3. **Rank** and deduplicate using composite scoring (no LLM)
4. **Synthesize** a literature review using a single LLM call
5. **Quality check** the output with one additional LLM call

### Why RAG-First?

| Approach | LLM Calls/Review | Est. Cost (GPT-4o) |
|---|---|---|
| LLM at every stage | ~50-100 | $2-5 |
| **RAG-first (ours)** | **3-5** | **$0.10-0.30** |

**LLM is expensive.** We reserve it for what it does best — synthesizing text — and use embeddings + traditional NLP for everything else.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ New      │  │ My       │  │ Paper    │  │ Settings    │  │
│  │ Review   │  │ Reviews  │  │ Library  │  │ (API Keys)  │  │
│  └────┬─────┘  └──────────┘  └──────────┘  └─────────────┘  │
│       │        Auth Layer (streamlit-authenticator)         │
└───────┼─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│              LangGraph Pipeline Orchestrator                │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ Stage 1  │→ │ Stage 2  │→ │ Stage 3  │  ← NO LLM         │
│  │ Search   │  │ Filter   │  │ Rank     │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
│       │                                                     │
│       │        ┌──────────┐  ┌──────────┐                   │
│       └──────→ │ Stage 4  │⟷│ Stage 5  │  ← LLM HERE       │
│                │ Synth.   │  │ Quality  │                   │
│                └──────────┘  └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
        │                              │
        ▼                              ▼
┌──────────────────────┐   ┌────────────────────────┐
│   Data Sources       │   │   Output Generation    │
│ • Semantic Scholar   │   │ • python-docx → .docx  │
│ • arXiv API          │   │ • Jinja2 → .tex        │
│ • PubMed E-utils     │   │ • pdflatex → .pdf      │
│ • Local ChromaDB     │   └────────────────────────┘
└──────────────────────┘
        │
        ▼
┌─────────────────-──┐
│   Storage          │
│ • PostgreSQL (DB)  │
│ • ChromaDB (Index) │
└─────────────────-──┘
```

---

## 3. RAG-First Design

### Pipeline Flow

```
User enters research topic + constraints
         │
         ▼
  ┌──────────────────────────────────────┐
  │  STAGE 1: SEARCH (NO LLM)            │
  │                                      │
  │  • BM25 keyword expansion (NLP)      │
  │  • Query Semantic Scholar API        │
  │  • Query arXiv API                   │
  │  • Query PubMed API                  │
  │  • Search local ChromaDB index       │
  │  • Merge all candidates              │
  │                                      │
  │  Output: 100-500 raw candidates      │
  └──────────────┬───────────────────────┘
                 ▼
  ┌──────────────────────────────────────┐
  │  STAGE 2: EMBED & FILTER (NO LLM)    │
  │                                      │
  │  • Embed topic with SPECTER2/MiniLM  │
  │  • Embed each paper abstract         │
  │  • Cosine similarity ranking         │
  │  • Keep papers > threshold (0.3)     │
  │                                      │
  │  Output: 30-100 filtered papers      │
  └──────────────┬───────────────────────┘
                 ▼
  ┌──────────────────────────────────────┐
  │  STAGE 3: RANK & DEDUP (NO LLM)      │
  │                                      │
  │  • Dedup by DOI + normalized title   │
  │  • Score = α·relevance               │
  │         + β·log(citations + 1)       │
  │         + γ·recency_score            │
  │  • Select top-N (default N=20)       │
  │                                      │
  │  Output: Top 20 ranked papers        │
  └──────────────┬───────────────────────┘
                 ▼
  ┌──────────────────────────────────────┐
  │  STAGE 4: SYNTHESIZE (LLM ✦)         │
  │                                      │
  │  • Build prompt from top-N abstracts │
  │  • Single LLM call → literature      │
  │    review with sections:             │
  │    - Introduction                    │
  │    - Thematic Analysis               │
  │    - Methodology Comparison          │
  │    - Key Findings                    │
  │    - Gaps & Future Directions        │
  │    - Conclusion                      │
  │  • Parse into structured output      │
  │                                      │
  │  Output: Structured review text      │
  └──────────────┬───────────────────────┘
                 ▼
  ┌──────────────────────────────────────┐
  │  STAGE 5: QUALITY CHECK (LLM ✦)      │
  │                                      │
  │  • Score: coherence, coverage,       │
  │    citation accuracy (each 1-10)     │
  │  • If avg < 7: feedback → Stage 4    │
  │    (max 2 retries)                   │
  │  • If avg >= 7: approve              │
  │                                      │
  │  Output: Approved review + scores    │
  └──────────────┬───────────────────────┘
                 ▼
  ┌──────────────────────────────────────┐
  │  OUTPUT GENERATION                   │
  │                                      │
  │  • Generate .docx (python-docx)      │
  │  • Generate .tex (Jinja2 template)   │
  │  • Compile .tex → .pdf (pdflatex)    │
  │                                      │
  │  Output: Downloadable files          │
  └──────────────────────────────────────┘
```

### Local Metadata Dataset

We use pre-downloaded academic paper metadata for fast, free pre-filtering:

| Dataset | Source | Size | Papers |
|---|---|---|---|
| arXiv Metadata | Kaggle (`Cornell-University/arxiv`) | ~4GB JSON | 2.4M+ |
| Semantic Scholar ORC | HuggingFace / S2 API | Subsets | 200M+ |
| PubMed Baseline | NCBI FTP | ~30GB XML | 36M+ |

**Starter:** arXiv metadata from Kaggle. Filter to relevant categories (cs.AI, cs.CL, cs.LG, cs.CV, etc.) → ~300K papers.

**Indexing pipeline:**
1. Download dataset → parse JSON
2. Filter by categories
3. Embed abstracts with SPECTER2 or `all-MiniLM-L6-v2`
4. Store in ChromaDB with metadata fields
5. At query time: embed topic → cosine similarity search → return candidates

---

## 4. Tech Stack

### Confirmed Choices

| Component | Technology | Why |
|---|---|---|
| **Orchestration** | LangGraph | Graph-based pipeline with explicit state management |
| **Database** | PostgreSQL (Railway addon) | Concurrent web access, production-grade |
| **Vector Store** | ChromaDB | Developer-friendly, metadata filtering, persistent |
| **Embeddings** | SPECTER2 / all-MiniLM-L6-v2 | Scientific domain expertise / lightweight fallback |
| **LLM** | OpenAI GPT-4o / GPT-4o-mini | Cost-efficient, configurable per user |
| **Frontend** | Streamlit | Required by project spec |
| **Auth** | streamlit-authenticator | Simple, YAML-based |
| **Doc Output** | python-docx + Jinja2+LaTeX | .docx and .tex/.pdf |
| **Deployment** | Railway | Required by project spec |

### Dependencies

```
# Pipeline
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0
langchain-anthropic>=0.2.0

# Embedding & Vector Search
sentence-transformers>=3.0.0
chromadb>=0.5.0
torch>=2.0.0

# Data Sources
semanticscholar>=0.8.0
arxiv>=2.1.0
biopython>=1.84

# Dataset Loading
datasets>=3.0.0

# Web UI
streamlit>=1.40.0
streamlit-authenticator>=0.4.0

# Database
sqlalchemy>=2.0.0
alembic>=1.14.0
psycopg2-binary>=2.9.0

# Document Generation
python-docx>=1.1.0
Jinja2>=3.1.0

# Core
anthropic>=0.40.0
openai>=1.50.0
python-dotenv>=1.0.0
httpx>=0.27.0
pydantic>=2.0.0

# Testing
pytest>=8.0.0
```

---

## 5. Project Structure

```
A20-App-143/
├── app.py                          # Streamlit entry point
├── requirements.txt                # All dependencies
├── Dockerfile                      # Python + texlive-base
├── railway.toml                    # Railway config
├── .streamlit/
│   └── config.toml                 # Theme/settings
│
├── src/
│   ├── __init__.py
│   ├── config.py                   # Env vars, constants, LLM config
│   │
│   ├── pipeline/                   # LangGraph pipeline
│   │   ├── __init__.py
│   │   ├── graph.py                # Orchestrator (wires all stages)
│   │   ├── state.py                # Shared Pydantic state schema
│   │   ├── search.py               # Stage 1: Multi-source search
│   │   ├── filter.py               # Stage 2: Embedding filter
│   │   ├── rank.py                 # Stage 3: Rank & dedup
│   │   ├── synthesize.py           # Stage 4: LLM synthesis
│   │   └── quality.py              # Stage 5: LLM quality check
│   │
│   ├── sources/                    # API clients
│   │   ├── __init__.py
│   │   ├── base.py                 # Base client (rate limit, retry)
│   │   ├── semantic_scholar.py
│   │   ├── arxiv_client.py
│   │   └── pubmed_client.py
│   │
│   ├── indexing/                   # Local metadata index
│   │   ├── __init__.py
│   │   ├── dataset_loader.py       # Load Kaggle/HF datasets
│   │   ├── embedder.py             # SPECTER2 / MiniLM wrapper
│   │   ├── vector_store.py         # ChromaDB operations
│   │   └── index_builder.py        # Build/update index
│   │
│   ├── output/                     # Document generation
│   │   ├── __init__.py
│   │   ├── docx_generator.py
│   │   ├── latex_generator.py      # Jinja2 → .tex → pdflatex → .pdf
│   │   └── templates/
│   │       └── review_template.tex
│   │
│   ├── db/                         # Database
│   │   ├── __init__.py
│   │   ├── models.py               # SQLAlchemy models
│   │   ├── session.py              # Session management
│   │   └── migrations/             # Alembic
│   │
│   └── auth/                       # Authentication
│       ├── __init__.py
│       └── auth_manager.py
│
├── pages/                          # Streamlit pages
│   ├── 1_🔍_New_Review.py
│   ├── 2_📚_My_Reviews.py
│   ├── 3_📄_Paper_Library.py
│   └── 4_⚙️_Settings.py
│
├── tests/
│   ├── test_sources.py
│   ├── test_indexing.py
│   ├── test_pipeline.py
│   └── test_output.py
│
├── data/                           # gitignored
│   ├── arxiv-metadata/
│   └── chroma_db/
│
├── scripts/
│   ├── setup_hooks.sh
│   ├── log_hook.py
│   ├── submit_log.py
│   └── build_index.py             # Download + embed + store
│
├── PLAN.md                         # ← this file
├── AGENTS.md
├── JOURNAL.md
├── WORKLOG.md
└── README.md
```

---

## 6. Database Schema

### `users`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| username | VARCHAR UNIQUE | |
| email | VARCHAR UNIQUE | |
| password_hash | VARCHAR | bcrypt |
| role | VARCHAR | `admin` or `user` |
| created_at | TIMESTAMP | |

### `reviews`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| user_id | FK → users | |
| title | VARCHAR | User-given title |
| topic | TEXT | Research topic string |
| constraints | JSONB | `{year_min, year_max, categories, max_papers, keywords}` |
| status | VARCHAR | `pending → searching → filtering → ranking → synthesizing → reviewing → done / failed` |
| result_text | TEXT | Final generated review |
| paper_count | INT | |
| quality_score | FLOAT | Average from quality check |
| created_at | TIMESTAMP | |
| completed_at | TIMESTAMP | |

### `papers`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| doi | VARCHAR UNIQUE | Nullable if not available |
| arxiv_id | VARCHAR | |
| title | VARCHAR | |
| authors | JSONB | Array of author names |
| source | VARCHAR | `semantic_scholar`, `arxiv`, `pubmed`, `local_index` |
| year | INT | |
| abstract | TEXT | |
| pdf_url | VARCHAR | |
| citation_count | INT | |
| categories | JSONB | Array of category codes |
| fetched_at | TIMESTAMP | |

### `review_papers`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| review_id | FK → reviews | |
| paper_id | FK → papers | |
| relevance_score | FLOAT | Cosine similarity |
| composite_score | FLOAT | Weighted final score |
| summary | TEXT | Generated during synthesis |
| status | VARCHAR | `candidate → filtered → ranked → cited` |

### `review_outputs`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| review_id | FK → reviews | |
| format | VARCHAR | `docx`, `tex`, `pdf` |
| file_data | BYTEA | Binary file content |
| version | INT | |
| generated_at | TIMESTAMP | |

---

## 7. Pipeline Stages (Detailed)

### Stage 1: Search — `src/pipeline/search.py`

**Purpose:** Gather candidate papers from multiple sources.  
**LLM Used:** ❌ None

**Logic:**
```python
def search_node(state: PipelineState) -> PipelineState:
    topic = state.topic
    constraints = state.constraints
    
    # 1. Generate keyword variants (NLP, no LLM)
    keywords = expand_keywords(topic)  # synonyms, stemming, n-grams
    
    # 2. Search in parallel
    results = []
    results += semantic_scholar.search(keywords, constraints)
    results += arxiv_client.search(keywords, constraints)
    results += pubmed_client.search(keywords, constraints)
    results += vector_store.search(topic_embedding, constraints)  # local index
    
    # 3. Merge
    state.candidates = merge_results(results)
    state.status = "filtering"
    return state
```

**Rate Limit Handling:**
- Semantic Scholar: 100 requests/5 min (no key), 1 req/sec (with key)
- arXiv: 1 request/3 seconds (mandatory delay per ToS)
- PubMed: 3 req/sec (no key), 10 req/sec (with API key)
- If user provides API key → use it, otherwise → respect default limits

---

### Stage 2: Embed & Filter — `src/pipeline/filter.py`

**Purpose:** Use embedding similarity to remove irrelevant papers.  
**LLM Used:** ❌ None (uses local embedding model)

**Embedding Model Options:**
| Model | Size | Domain | Speed |
|---|---|---|---|
| `allenai/specter2_base` + proximity adapter | 440MB | Scientific papers (citation-trained) | Slower |
| `all-MiniLM-L6-v2` | 80MB | General purpose | Fast |

**Default:** `all-MiniLM-L6-v2` for dev/Railway (lighter). SPECTER2 as optional upgrade.

**Logic:**
```python
def filter_node(state: PipelineState) -> PipelineState:
    topic_embedding = embedder.encode(state.topic)
    
    for paper in state.candidates:
        text = f"{paper.title}. {paper.abstract}"
        paper_embedding = embedder.encode(text)
        paper.relevance_score = cosine_similarity(topic_embedding, paper_embedding)
    
    # Filter by threshold
    state.candidates = [p for p in state.candidates if p.relevance_score > 0.3]
    state.status = "ranking"
    return state
```

---

### Stage 3: Rank & Dedup — `src/pipeline/rank.py`

**Purpose:** Remove duplicates and rank by composite score.  
**LLM Used:** ❌ None

**Scoring Formula:**
```
composite_score = α × relevance_score 
                + β × log(citation_count + 1) / log(max_citations + 1)
                + γ × recency_score

Where:
  α = 0.6 (relevance weight)
  β = 0.2 (citation weight, normalized log scale)
  γ = 0.2 (recency weight: 1.0 for current year, decays linearly)
```

**Deduplication:**
1. Exact DOI match
2. Normalized title similarity (lowercase, remove punctuation, Jaccard > 0.85)

---

### Stage 4: Synthesize — `src/pipeline/synthesize.py`

**Purpose:** Generate the actual literature review.  
**LLM Used:** ✅ Yes — single large call

**Prompt Template:**
```
You are an expert academic researcher. Given the following {N} papers 
related to the topic "{topic}", write a comprehensive literature review.

## Papers:
{for each paper: [i] Title (Year) — Abstract}

## Required Sections:
1. Introduction — Context and scope of the review
2. Thematic Analysis — Group papers by themes/approaches
3. Methodology Comparison — Compare research methods used
4. Key Findings — Synthesize the main results
5. Gaps & Future Directions — Identify research gaps
6. Conclusion — Summarize the state of the field

## Requirements:
- Cite papers as [1], [2], etc.
- Write in formal academic style
- Ensure smooth narrative flow between sections
- Be critical and analytical, not just descriptive
```

**Model:** GPT-4o (128K context) or Claude Sonnet. User-configurable in Settings.

---

### Stage 5: Quality Check — `src/pipeline/quality.py`

**Purpose:** Validate the generated review.  
**LLM Used:** ✅ Yes — single scoring call

**Scoring Prompt:**
```
Score this literature review on a 1-10 scale for each:
1. Coherence: Does it flow logically?
2. Coverage: Does it adequately cover the topic?
3. Citation Accuracy: Are citations used correctly?
4. Writing Quality: Is it well-written, academic?

Return JSON: {"coherence": N, "coverage": N, "accuracy": N, "quality": N, "feedback": "..."}
```

**Logic:**
- If average < 7: return feedback to Stage 4, retry (max 2)
- If average >= 7: approve, proceed to output
- Use `gpt-4o-mini` for this (cheaper, scoring is simpler)

---

## 8. Sprint Plan

### Phase 1 — Foundation & Data Infra (Week 1-2)

| Task | Owner | Status |
|---|---|---|
| Restructure project directories | tungnguyenlam | ⏳ |
| PostgreSQL models + Alembic migrations | Member B | ⏳ |
| `streamlit-authenticator` login flow | Member C | ⏳ |
| Streamlit multi-page skeleton | tungnguyenlam | ⏳ |
| Download arXiv metadata dataset | tungnguyenlam | ⏳ |
| Build embedding index (MiniLM + ChromaDB) | Member B | ⏳ |
| Update requirements.txt | tungnguyenlam | ⏳ |
| Streamlit theme config | Member C | ⏳ |

**Exit:** Login works. ChromaDB index with ~100K papers (dev). DB tables created.

---

### Phase 2 — Data Source Clients (Week 3)

| Task | Owner | Status |
|---|---|---|
| Base client interface (rate limit, retry) | tungnguyenlam | ⏳ |
| Semantic Scholar client | Member B | ⏳ |
| arXiv API client | Member C | ⏳ |
| PubMed E-utilities client | tungnguyenlam | ⏳ |
| Local ChromaDB search integration | Member B | ⏳ |
| Unit tests | Member C | ⏳ |

**Exit:** Each client returns typed Paper objects. Rate limits respected.

---

### Phase 3 — RAG Pipeline (Weeks 4-5)

| Task | Owner | Status |
|---|---|---|
| Shared state schema (Pydantic) | tungnguyenlam | ⏳ |
| Stage 1: Search node | Member B | ⏳ |
| Stage 2: Embedding filter node | tungnguyenlam | ⏳ |
| Stage 3: Rank & dedup node | Member C | ⏳ |
| Stage 4: LLM synthesis node | tungnguyenlam | ⏳ |
| Stage 5: Quality check node | Member B | ⏳ |
| LangGraph orchestrator | tungnguyenlam | ⏳ |
| Quality→Synthesis feedback loop | Member C | ⏳ |
| Pipeline tests | All | ⏳ |

**Exit:** Full pipeline runs end-to-end. LLM called only in stages 4-5.

---

### Phase 4 — Document Generation (Week 6)

| Task | Owner | Status |
|---|---|---|
| LaTeX template (Jinja2) | Member C | ⏳ |
| LaTeX → PDF generation | tungnguyenlam | ⏳ |
| DOCX generator | Member B | ⏳ |
| Wire to pipeline | tungnguyenlam | ⏳ |

**Exit:** Pipeline produces .docx, .tex, .pdf files.

---

### Phase 5 — UI Polish (Week 7)

| Task | Owner | Status |
|---|---|---|
| New Review page (input + progress) | tungnguyenlam | ⏳ |
| My Reviews page (list + download) | Member B | ⏳ |
| Paper Library page | Member C | ⏳ |
| Settings page (API keys) | Member B | ⏳ |
| Real-time pipeline progress | tungnguyenlam | ⏳ |
| Admin user CRUD | Member C | ⏳ |

**Exit:** Full user flow: login → create → progress → download.

---

### Phase 6 — Deployment (Week 8)

| Task | Owner | Status |
|---|---|---|
| Dockerfile (Python + texlive-base) | tungnguyenlam | ⏳ |
| railway.toml | tungnguyenlam | ⏳ |
| PostgreSQL addon | tungnguyenlam | ⏳ |
| ChromaDB index upload | Member B | ⏳ |
| Env vars + verification | All | ⏳ |

**Exit:** Public URL accessible. Pipeline works in production.

---

### Phase 7 — Hardening & Demo (Week 9)

| Task | Owner | Status |
|---|---|---|
| Error handling (API + LLM) | tungnguyenlam | ⏳ |
| Loading states + error UX | Member B | ⏳ |
| Integration tests | Member C | ⏳ |
| README + JOURNAL + WORKLOG update | All | ⏳ |
| Demo prep | All | ⏳ |

---

### Phase 8 — GraphRAG (Post-MVP, Optional)

| Task | Description |
|---|---|
| Citation graph extraction | Build graph from Semantic Scholar citation data |
| Graph-based re-ranking | PageRank on citation subgraph |
| Entity extraction | Key entities from abstracts (methods, datasets, metrics) |
| Knowledge graph | Entity-relationship graph across papers |
| Graph-aware synthesis | Use graph structure for review organization |

---

## 9. API Integration Details

### Semantic Scholar

- **Endpoint:** `https://api.semanticscholar.org/graph/v1/paper/search`
- **Auth:** Optional API key (request from [semanticscholar.org](https://www.semanticscholar.org/product/api))
- **Rate Limit:** 100 requests/5min (no key) → user key unlocks more
- **Fields:** `title,abstract,authors,year,citationCount,externalIds,url`
- **Python:** `pip install semanticscholar`

### arXiv

- **Endpoint:** `http://export.arxiv.org/api/query`
- **Auth:** None required
- **Rate Limit:** 1 request/3 seconds (per ToS, mandatory)
- **Format:** Atom XML → use `arxiv` Python library
- **Python:** `pip install arxiv`

### PubMed (E-utilities)

- **Endpoint:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`
- **Auth:** Email required. API key optional (3→10 req/sec)
- **Flow:** `esearch` (find PMIDs) → `efetch` (get details)
- **Python:** `from Bio import Entrez` (biopython)

### API Key Behavior

```python
# Default: respect site rate limits, no special auth
# If user provides key in Settings page:
#   → Store encrypted in DB
#   → Pass to API clients
#   → Unlock higher rate limits
```

---

## 10. Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim

# Install texlive for LaTeX → PDF compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-base \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download embedding model at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
```

### railway.toml

```toml
[build]
builder = "dockerfile"

[deploy]
startCommand = "streamlit run app.py --server.address 0.0.0.0 --server.port $PORT"
healthcheckPath = "/"
restartPolicyType = "on_failure"

[[services]]
name = "web"
```

### Environment Variables (Railway Dashboard)

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...  (optional)
DATABASE_URL=postgresql://...   (auto from Railway addon)
DEFAULT_MODEL=gpt-4o
LOG_LEVEL=INFO
```

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| arXiv dataset too large for Railway | Medium | High | Filter to CS categories → ~300K papers ≈ 2GB index |
| Embedding model too heavy | Medium | High | Use `all-MiniLM-L6-v2` (80MB). Pre-download in Docker build |
| LLM context overflow (too many papers) | Low | Medium | Cap at 20 papers. Abstract-only. Chunk if needed |
| Semantic Scholar rate limits | High | Medium | Cache all results. Use local index first. API as supplement |
| texlive Docker image size | Medium | Low | Use `texlive-base` (~150MB) not full texlive (~4GB) |
| ChromaDB persistence on Railway | Medium | Medium | Use Railway volume mount or rebuild on deploy |
| API costs spike | Low | Medium | RAG-first: only 3-5 LLM calls/review. Monitor usage |

---

## 12. Future: GraphRAG Extension

After basic RAG pipeline is stable, we can add graph-based features:

1. **Citation Graph Traversal**
   - Use Semantic Scholar's citation/reference endpoints
   - Find papers that cite (or are cited by) our top candidates
   - Expand the candidate pool with highly-connected papers

2. **Graph-Based Re-ranking**
   - Build a citation subgraph from our candidate papers
   - Apply PageRank or HITS algorithm
   - Papers that are "hubs" (cite many good papers) or "authorities" (cited by many) get boosted

3. **Knowledge Graph Construction**
   - Extract entities: methods, datasets, metrics, findings
   - Build entity-relationship graph
   - Enable queries like "which methods were tested on dataset X?"

4. **Graph-Aware Synthesis**
   - Use graph clusters to automatically organize review sections
   - Citation relationships inform narrative flow
   - Identify "bridge papers" between research areas

**Implementation:** Will use NetworkX for graph operations, potentially neo4j for persistent graph storage if needed.

---

## Team

| Member | GitHub | Role |
|---|---|---|
| tungnguyenlam | @tungnguyenlam | Lead / Pipeline / Deployment |
| Member B | TBD | Database / API Clients / UI |
| Member C | TBD | Auth / Testing / Templates |

---

*This plan is a living document. Update as decisions are made and sprint progress happens.*
