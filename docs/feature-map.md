# Feature Map

## Documentation Ownership

- Purpose: Canonical traceability map from product features to implementation and validation assets.
- Audience: Engineers, reviewers, and AI agents making changes in this repository.
- Canonical for: "Where does this feature live?" across code, tests, docs, and config.
- Update when: Any feature path, test coverage, or related documentation/config changes.

## Main Features

| Feature | Main code locations | Related tests | Related docs | Related config/examples |
|---|---|---|---|---|
| App shell, auth, dashboard | `app.py`, `src/auth/auth_manager.py`, `src/db/session.py`, `src/db/models.py` | No direct page/auth tests | `PLAN.md`, `AGENTS.md`, `JOURNAL.md` | `src/config.py`, `scripts/run_app.sh`, `Dockerfile`, `railway.toml` |
| New review workflow and live pipeline UI | `pages/1_New_Review.py` | `tests/test_preflight.py` | `PLAN.md`, `JOURNAL.md`, `journals/week1/2026-04-07.md` | `src/config.py` |
| Pipeline orchestration and state | `src/pipeline/orchestrator.py`, `src/pipeline/state.py` | `tests/test_pipeline_stages.py`, `tests/test_repro_zero_papers.py` | `PLAN.md`, `WORKLOG.md` | `src/config.py` |
| Search and source fusion | `src/pipeline/search.py`, `src/sources/factory.py`, `src/sources/*.py` | `tests/test_sources.py`, `tests/test_pipeline_stages.py` | `PLAN.md`, `WORKLOG.md` | `src/config.py`, `scripts/test_sources.py` |
| Embedding filter and ranking | `src/pipeline/filter.py`, `src/pipeline/rank.py`, `src/pipeline/topic_quality.py`, `src/indexing/embedder.py` | `tests/test_pipeline_stages.py` | `PLAN.md`, `JOURNAL.md` | `src/config.py` |
| Full text fetch and cache | `src/pipeline/fetch_node.py`, `src/sources/pdf_handler.py` | `tests/test_pdf_handler.py`, `tests/test_pipeline_stages.py` | `PLAN.md`, `WORKLOG.md` | `src/config.py`, `data/papers/` |
| LLM synthesis and quality gate | `src/pipeline/synthesize.py`, `src/pipeline/quality.py`, `src/llm/wrapper.py`, `src/pipeline/preflight.py` | `tests/test_pipeline_stages.py`, `tests/test_llm_wrapper.py`, `tests/test_preflight.py` | `PLAN.md`, `WORKLOG.md` | `src/config.py`, `pages/4_Settings.py` |
| Output generation and persistence | `src/pipeline/output_node.py`, `src/output/docx_generator.py`, `src/output/latex_generator.py`, `src/db/review_repository.py` | `tests/test_output.py` | `PLAN.md`, `WORKLOG.md` | `src/output/templates/review_template.tex`, `Dockerfile` |
| My Reviews page and downloads | `pages/2_My_Reviews.py`, `src/db/review_repository.py` | Partial repository coverage in `tests/test_output.py` | `PLAN.md`, `JOURNAL.md` | `src/config.py` |
| Paper Library page and paper-review linkage | `pages/3_Paper_Library.py`, `src/db/paper_repository.py` | `tests/test_paper_library.py` | `PLAN.md`, `journals/week1/2026-04-07.md` | `src/config.py` |
| Settings and admin user CRUD | `pages/4_Settings.py`, `src/auth/auth_manager.py`, `src/db/models.py` | No direct page/admin tests | `PLAN.md`, `JOURNAL.md` | `src/config.py` |
| Local indexing pipeline | `scripts/build_index.py`, `src/indexing/dataset_loader.py`, `src/indexing/vector_store.py`, `src/sources/local_source.py` | No direct indexing script tests | `PLAN.md`, `JOURNAL.md` | `src/config.py`, `scripts/build_index.py --help` |
| Deployment and AI logging hooks | `Dockerfile`, `railway.toml`, `scripts/run_app.sh`, `scripts/setup_hooks.sh`, `scripts/log_hook.py`, `scripts/submit_log.py` | No direct deployment/hook tests | `AGENTS.md`, `README.md` | Railway and Docker configuration files |

## Known Ownership Gaps

- No dedicated tests for auth flow, dashboard rendering, Settings UI, and admin CRUD workflows.
- Runtime docs previously assumed `venv/bin/python` exists; environment bootstrap was not explicit.
- Legacy starter files `src/agent.py` and `src/tools.py` still exist and can be mistaken for active product paths.

## Naming Notes

Use the term "local paper index" in documentation. Code may still refer to `local_arxiv` and `local_index`; both map to the same capability.
