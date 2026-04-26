# Feature Map

## Documentation Ownership

- Purpose: Canonical traceability map from product features to implementation, validation, and supporting documentation.
- Audience: Engineers, reviewers, and AI agents changing this repository.
- Canonical for: "Where does this feature live?" across code, tests, docs, and config/examples.
- Update when: A shipped feature gains new routes, services, tests, docs, or environment/config requirements.

## Canonical Docs By Intent

| Doc | Canonical purpose |
|---|---|
| `README.md` | Current product overview, setup, API surface, and documentation entry point |
| `docs/feature-map.md` | Traceability from shipped features to code/tests/docs/config |
| `docs/backend-diagram.md` | Backend architecture, route wiring, and data flow |
| `docs/TEST_POSTMAN.md` | Manual API verification steps and request examples |
| `docs/features/*.md` | Deep dives for feature-specific behavior and implementation |
| `docs/user-journey.md` | Product journey and UX state, with explicit shipped vs planned notes |
| `plans/*.md` | Historical phase plans and roadmap context, not current-state ownership |
| `JOURNAL.md`, `WORKLOG.md` | Historical implementation log and technical decision record |

## Main Features

| Feature | Main code locations | Related tests | Related docs | Related config/examples |
|---|---|---|---|---|
| Auth and JWT session | `backend/api/routers/auth.py`, `backend/security.py`, `backend/api/dependencies.py` | `tests/test_auth.py` | `README.md`, `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md` | `.env.example`, `backend/config.py` |
| Project CRUD and project defaults | `backend/api/routers/projects.py`, `backend/api/schemas/projects.py`, `backend/db/models.py` | `tests/test_projects.py` | `README.md`, `docs/TEST_POSTMAN.md`, `docs/user-journey.md` | `.env.example`, `database_schema.sql`, `backend/db/migrations/versions/20260411_01_create_phase_1_tables.py` |
| Project token usage telemetry | `backend/services/ai_usage.py`, `backend/services/llm.py`, `backend/services/embeddings.py`, `backend/api/routers/projects.py`, `backend/api/schemas/projects.py`, `backend/db/models.py`, `frontend/components/ContextPanel.tsx`, `frontend/components/ChatProvider.tsx`, `frontend/lib/api.ts` | `tests/test_llm_embeddings.py`, `tests/test_projects.py` | `README.md`, `docs/feature-map.md` | `database_schema.sql`, `backend/db/migrations/versions/20260426_01_ai_usage_events.py`, `OPENROUTER_API_KEY` |
| Discovery pipeline: Searcher -> Reader -> warning branch | `backend/agents/pipeline.py`, `backend/agents/graph.py`, `backend/agents/searcher.py`, `backend/agents/reader.py`, `backend/agents/state.py`, `backend/services/semantic_scholar.py`, `backend/services/arxiv.py`, `backend/services/embeddings.py`, `backend/services/llm.py` | `tests/test_pipeline.py`, `tests/test_graph.py`, `tests/test_searcher_reader.py`, `tests/test_services.py`, `tests/test_search_quality.py`, `tests/test_llm_embeddings.py` | `README.md`, `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md`, `docs/user-journey.md`, `plans/phase-2-searcher-reader.md` | `.env.example`, `backend/config.py`, `pyproject.toml` |
| Reference PDF upload and uploaded-paper seeding | `backend/services/reference_files.py`, `backend/services/document_extraction.py`, `backend/api/routers/projects.py`, `backend/db/models.py` | `tests/test_reference_files.py`, `tests/test_document_extraction.py`, `tests/test_searcher_reader.py` | `docs/features/upload_reference_file.md`, `docs/TEST_POSTMAN.md`, `docs/backend-diagram.md`, `docs/user-journey.md` | `.env.example`, `backend/config.py`, `REFERENCE_UPLOAD_DIR`, `REFERENCE_MAX_EXTRACTED_CHARS`, `OPENROUTER_DOCUMENT_MODEL`, `OPENROUTER_PDF_ENGINE` |
| Ranked paper list and pagination/filtering | `backend/api/routers/projects.py`, `backend/api/schemas/projects.py` | `tests/test_projects.py` | `README.md`, `docs/TEST_POSTMAN.md`, `docs/user-journey.md` | query params in API examples |
| Paper citation graph and exact related-paper lookup | `backend/api/routers/projects.py`, `backend/api/schemas/projects.py`, `backend/api/dependencies.py`, `backend/services/paper_citations.py`, `backend/services/semantic_scholar.py` | `tests/test_paper_citations.py`, `tests/test_projects.py`, `tests/test_services.py` | `README.md`, `docs/features/paper_citation_graph.md`, `docs/backend-diagram.md`, `docs/TEST_POSTMAN.md` | `SEMANTIC_SCHOLAR_API_KEY`, `.env.example`, `backend/config.py` |
| Grounded paper conversations over PDFs | `backend/services/paper_conversations.py`, `backend/services/project_conversations.py`, `backend/services/document_extraction.py`, `backend/api/routers/projects.py`, `backend/db/models.py` | `tests/test_paper_conversations.py`, `tests/test_project_conversations.py`, `tests/test_document_extraction.py` | `README.md`, `docs/features/paper_conversations.md`, `docs/backend-diagram.md`, `docs/user-journey.md`, `plans/phase-3a-paper-understanding.md`, `plans/multi-paper-chat-selection.md` | `.env.example`, `backend/config.py`, `OPENROUTER_DOCUMENT_MODEL`, `OPENROUTER_PDF_ENGINE`, `PAPER_RETRIEVAL_TOP_K` |
| Writer generation, citations, and QA | `backend/services/writer_outputs.py`, `backend/agents/writer.py`, `backend/agents/qa.py`, `backend/services/citations.py`, `backend/api/routers/projects.py`, `backend/db/models.py` | `tests/test_writer_outputs.py` | `README.md`, `docs/features/writer_outputs.md`, `docs/user-journey.md`, `plans/phase-3-writer-qa.md` | `.env.example`, `backend/config.py`, writer request examples in docs |
| Frontend login/chat shell, composer PDF upload, and project-driven selected-paper Q&A flow | `frontend/app/login/page.tsx`, `frontend/app/chat/page.tsx`, `frontend/components/AuthProvider.tsx`, `frontend/components/ChatProvider.tsx`, `frontend/components/Sidebar.tsx`, `frontend/components/ChatWorkspace.tsx`, `frontend/components/ContextPanel.tsx`, `frontend/lib/api.ts` | No frontend tests currently | `frontend/README.md`, `README.md`, `docs/user-journey.md`, `plans/multi-paper-chat-selection.md` | `frontend/.env.local.example`, `frontend/package.json`, `frontend/tailwind.config.ts`, `frontend/next.config.mjs` |
| DB schema, migrations, and runtime wiring | `backend/db/models.py`, `backend/db/session.py`, `backend/db/migrations/versions/*`, `backend/main.py`, `tests/conftest.py` | Coverage spread across API and service tests | `README.md`, `docs/backend-diagram.md`, `database_schema.sql` | `alembic.ini`, `pyproject.toml`, `.env.example`, `DATABASE_URL`, `TEST_DATABASE_URL` |
| AI logging hooks and repo hygiene | `scripts/setup_hooks.sh`, `scripts/log_hook.py`, `scripts/submit_log.py`, `AGENTS.md` | No direct tests | `AGENTS.md`, `README.md` | `.env.example`, `.codex/hooks.json`, `.cursor/hooks.json`, `.claude/settings.json`, `.gemini/settings.json`, `.github/hooks/hooks.json` |

## Known Ownership Gaps

- Frontend behavior is documented, but there is still no frontend test coverage for composer uploads, uploaded-paper markers, or selected-paper persistence.
- Feature deep-dive docs are now uneven only if new backend features ship without a matching `docs/features/*.md` file.
- `database_schema.sql` and the live SQLAlchemy/Alembic models can drift unless both are updated together when schema changes land.

## Naming Notes

- Use "discovery pipeline" for the always-on `searcher -> reader` flow.
- Use "writer generation" for the user-invoked writing flow; it is not part of `/pipeline/health`.
- Use "reference files" for uploaded PDFs and "uploaded papers" for the linked `Paper` rows created from them.
