# Phase 3 - Writer + QA Agents

**Timeline:** Week 3  
**Goal:** Let the user select papers, then ask a grounded Writer agent to generate exactly what they need from those papers: related work, a reference section, LaTeX-ready citations, doc-friendly references, structured comparisons, or any other scoped writing request.

> Phase 3 should not assume the product always writes one full literature review automatically. The writing workflow must start from user-selected papers plus a user instruction.

---

## Summary

- Keep the Phase 2 searcher + reader flow as the paper-discovery layer.
- Reuse Phase 3A paper grounding and conversation infrastructure as the evidence layer.
- Add a new writer workspace where the user:
  - selects one or more papers
  - enters a free-form request
  - chooses an output target such as `latex`, `docs`, `markdown`, or plain text
  - chooses a citation/reference style or lets the app infer a sane default
- Writer output must stay grounded to the selected papers only.
- QA runs after writing and flags unsupported claims, missing citations, invalid reference formatting, and format-specific issues.

---

## Product Direction

### What the user should be able to do

- Select papers from the ranked paper list.
- Ask for a specific writing task, for example:
  - "Write the related work section."
  - "Generate the references in IEEE format."
  - "Turn these papers into a LaTeX-ready subsection with `\\cite{}` citations."
  - "Write a comparison of methods and datasets in a doc-friendly format."
  - "Draft a short background section using only these five papers."
  - "Give me BibTeX entries for the selected papers."
- Copy the output directly into LaTeX, Google Docs, Word, or Markdown with minimal cleanup.

### What the system should not do

- Do not cite papers outside the user-selected set.
- Do not force one fixed document shape such as intro -> themes -> gaps -> conclusion for every request.
- Do not silently invent missing metadata. If author/year/venue data is incomplete, warn and degrade gracefully.

---

## Tasks

### 1. Writer request model
File: `backend/api/schemas/projects.py`

- Add a request schema for writer generation, for example:
  ```json
  {
    "paper_ids": ["p1", "p2", "p3"],
    "instruction": "Write a related work section for my paper.",
    "output_target": "latex",
    "citation_mode": "latex_cite",
    "reference_style": "ieee",
    "include_references": true
  }
  ```
- Required inputs:
  - `paper_ids`
  - `instruction`
- Optional inputs:
  - `output_target`: `latex`, `docs`, `markdown`, `plain_text`
  - `citation_mode`: `numbered`, `author_year`, `latex_cite`, `bibtex_only`, `thebibliography`
  - `reference_style`: `ieee`, `apa`, `chicago`, `bibtex`
  - `include_references`
  - `max_words`
- Treat the instruction as the primary intent. The user can ask for "related work", "reference section", or anything else grounded in the selected papers.

### 2. Writer API and orchestration
Files:
- `backend/api/routers/projects.py`
- `backend/services/...` or `backend/agents/writer.py`

- Add a dedicated endpoint such as:
  - `POST /projects/{project_id}/writer/generate`
- Behavior:
  - verify project ownership
  - load only the selected papers
  - require at least one selected paper
  - assemble paper metadata, summaries, and grounded chunks where available
  - call the Writer agent with the user instruction and output-format settings
  - run QA on the result before returning it
- Do not tie this flow to `POST /projects/{id}/run`. Writing is user-invoked after paper selection.

### 3. Grounded writer agent
File: `backend/agents/writer.py`

- Input:
  - selected papers
  - user instruction
  - output target
  - citation/reference settings
- Prompt requirements:
  - obey the user task exactly
  - use only the provided papers
  - synthesize across papers when the task asks for narrative writing
  - stay literal and structured when the task asks for references or citation artifacts
  - never invent authors, titles, years, venues, or findings
  - if metadata is missing, say so in warnings instead of hallucinating
- Output should be structured JSON, for example:
  ```json
  {
    "body": "...",
    "references": ["..."],
    "bibtex_entries": ["..."],
    "citations_used": ["p1", "p2"],
    "warnings": ["Paper p3 is missing venue metadata."]
  }
  ```
- The Writer must support at least these request classes in v1:
  - narrative section writing
  - reference list generation
  - citation artifact generation for LaTeX
  - short comparison/summary sections
  - custom free-form writing constrained to the selected papers

### 4. Citation and reference formatter
File: `backend/services/exporter.py` or `backend/services/citations.py`

- Build a formatter layer that converts selected paper metadata into output-target-specific artifacts.
- Support at minimum:
  - `latex` + `latex_cite`:
    - body text uses `\\cite{key}` style placeholders
    - return BibTeX entries and/or a `thebibliography` block
  - `latex` + `thebibliography`:
    - return a ready-to-paste `thebibliography` environment
  - `docs` or `markdown` + `numbered`:
    - body uses `[1]`, `[2]`
    - reference list is plain formatted text
  - `docs` + `author_year`:
    - body uses `(Author, Year)`
    - reference list is formatted for human reading
- Citation keys for LaTeX should be deterministic and stable enough to avoid churn between repeated runs on the same paper.
- Every citation emitted in the body must map to a generated reference artifact.

### 5. QA agent for writing outputs
File: `backend/agents/qa.py`

- Replace the old "claim checker for one auto-draft" idea with QA that validates user-requested output.
- Checks:
  - claims or comparisons without support from selected papers
  - citation markers in body with no matching reference entry
  - reference entries with missing core metadata
  - LaTeX output that contains invalid citation markers or malformed `thebibliography`
  - suspiciously generic text that does not mention the selected papers at all
  - empty or near-empty output
- Return machine-readable flags, for example:
  ```json
  [
    {
      "issue": "Citation key appears in body but no BibTeX entry was generated.",
      "severity": "error",
      "location": "body"
    }
  ]
  ```

### 6. Frontend writer workspace
File: `frontend/app/...`

- Add a writer panel after papers are listed.
- UI elements:
  - multi-select paper picker
  - prompt box for free-form writer instruction
  - output target selector
  - citation/reference style selector
  - toggle for including references
  - generate button
  - result preview with copy actions
- Provide starter actions:
  - `Related work`
  - `Reference section`
  - `LaTeX subsection`
  - `BibTeX`
  - `Compare methods`
- The user must still be able to overwrite the starter text and ask for anything custom.

### 7. Persistence and exports
Files:
- `backend/db/models.py`
- `backend/db/migrations/...`
- `backend/services/exporter.py`

- Persist writer outputs so a generated artifact can be revisited without regenerating immediately.
- Suggested fields:
  - selected paper IDs snapshot
  - raw instruction
  - output target
  - citation mode
  - reference style
  - generated body
  - generated references or BibTeX
  - QA flags
- Export helpers:
  - `GET /projects/{id}/writer/outputs/{output_id}`
  - optional download endpoints for:
    - `.bib`
    - `.tex`
    - `.docx`
    - plain text references

### 8. LangGraph and workflow boundaries
Files:
- `backend/agents/graph.py`
- `backend/agents/pipeline.py`

- Keep the discovery pipeline focused on searcher + reader.
- Do not force `searcher -> reader -> writer -> qa` as one always-on graph.
- Preferred flow:
  - pipeline graph: `searcher -> reader`
  - writer graph or service: `writer -> qa`
- If LangGraph is still used for writer + QA, invoke it only when the user explicitly asks for writing.

---

## End-of-phase checkpoint

- [ ] User can select papers and submit a custom writer request
- [ ] Writer output stays grounded to the selected papers only
- [ ] User can generate at least:
  - related work prose
  - a reference section
  - LaTeX-ready citation output
  - doc-friendly references
- [ ] Every citation in the body maps to a generated reference artifact
- [ ] QA flags malformed or unsupported output
- [ ] Generated output can be copied or downloaded with minimal cleanup

---

## Key decisions to make this week

- **Is writing automatic or user-invoked?**  
  User-invoked. Writing should happen only after the user selects papers and gives an instruction.

- **What is the primary abstraction: "section type" or "instruction"?**  
  Instruction first. Preset section types are shortcuts, not the core contract.

- **Where should formatting logic live?**  
  In a deterministic formatter layer after or alongside generation, not only inside the LLM prompt.

- **What if selected papers have weak metadata?**  
  Generate the best grounded output possible, but surface warnings and avoid hallucinated references.

---

## Cost estimate for this phase

Cost now depends on the user request size and number of selected papers.

| Operation | Calls | Est. tokens | Est. cost |
|---|---|---|---|
| Writer generation | 1 per request | ~4K-20K | ~$0.01-$0.06 |
| QA validation | 1-2 per request | ~2K-8K | ~$0.01-$0.03 |
| Reference formatting | deterministic | n/a | negligible |
| **Total per writer request** | | | **~$0.02-$0.09** |

This keeps writing flexible: a short BibTeX request should be cheaper than a long related-work section.
