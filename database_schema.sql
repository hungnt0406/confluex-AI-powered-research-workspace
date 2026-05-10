-- PostgreSQL schema for A20-App-143
-- Generated from backend/db/models.py

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255),
    auth_provider VARCHAR(32) NOT NULL DEFAULT 'email',
    google_sub VARCHAR(255) UNIQUE,
    credit_balance INTEGER NOT NULL DEFAULT 0,
    country_code VARCHAR(8) NOT NULL DEFAULT 'VN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub);

CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    topic_description TEXT NOT NULL,
    citation_format VARCHAR(100) NOT NULL,
    year_start INTEGER NOT NULL DEFAULT 2018,
    candidate_limit INTEGER NOT NULL DEFAULT 60,
    summary_limit INTEGER NOT NULL DEFAULT 30,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects (user_id);

CREATE TABLE IF NOT EXISTS ai_usage_events (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider VARCHAR(64) NOT NULL,
    endpoint VARCHAR(128) NOT NULL,
    feature VARCHAR(128) NOT NULL,
    model VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'success',
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    reasoning_tokens INTEGER,
    cached_tokens INTEGER,
    cost_credits DOUBLE PRECISION,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ai_usage_events_user_id ON ai_usage_events (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_events_project_id ON ai_usage_events (project_id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_events_project_created_at ON ai_usage_events (project_id, created_at);

CREATE TABLE IF NOT EXISTS credit_transactions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delta INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    kind VARCHAR(32) NOT NULL,
    feature VARCHAR(64),
    reference_id VARCHAR(64),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_credit_transactions_user_id ON credit_transactions (user_id);
CREATE INDEX IF NOT EXISTS ix_credit_transactions_user_created_at
    ON credit_transactions (user_id, created_at);

CREATE TABLE IF NOT EXISTS payment_orders (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pack_id VARCHAR(32) NOT NULL,
    credits INTEGER NOT NULL,
    usd_amount INTEGER NOT NULL,
    vnd_amount INTEGER NOT NULL,
    fx_rate_usd_to_vnd DOUBLE PRECISION NOT NULL,
    reference_code VARCHAR(32) NOT NULL UNIQUE,
    sepay_va_account VARCHAR(64),
    sepay_va_bank_bin VARCHAR(16),
    qr_payload TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    sepay_transaction_id VARCHAR(64) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_payment_orders_user_id ON payment_orders (user_id);
CREATE INDEX IF NOT EXISTS ix_payment_orders_user_created_at
    ON payment_orders (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_payment_orders_status_expires_at
    ON payment_orders (status, expires_at);

CREATE TABLE IF NOT EXISTS reference_files (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    original_filename VARCHAR(500) NOT NULL,
    content_type VARCHAR(255),
    byte_size INTEGER NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    storage_path TEXT NOT NULL,
    parse_status VARCHAR(32) NOT NULL DEFAULT 'parsed',
    extracted_title VARCHAR(500),
    extracted_authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    extracted_year INTEGER,
    extracted_abstract TEXT,
    extracted_text TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_reference_files_project_sha256 UNIQUE (project_id, sha256)
);

CREATE INDEX IF NOT EXISTS ix_reference_files_project_id ON reference_files (project_id);
CREATE INDEX IF NOT EXISTS ix_reference_files_sha256 ON reference_files (sha256);

CREATE TABLE IF NOT EXISTS papers (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    year INTEGER,
    abstract TEXT,
    doi VARCHAR(255),
    source VARCHAR(100) NOT NULL,
    reference_file_id VARCHAR(36) UNIQUE REFERENCES reference_files(id) ON DELETE CASCADE,
    source_paper_id VARCHAR(255),
    source_url TEXT,
    pdf_url TEXT,
    citation_count INTEGER,
    reference_count INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'candidate',
    relevance_score DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS ix_papers_project_id ON papers (project_id);
CREATE INDEX IF NOT EXISTS ix_papers_reference_file_id ON papers (reference_file_id);

CREATE TABLE IF NOT EXISTS paper_documents (
    id VARCHAR(36) PRIMARY KEY,
    paper_id VARCHAR(36) NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    source_pdf_url TEXT NOT NULL,
    openrouter_file_hash VARCHAR(255),
    page_count INTEGER,
    error_message TEXT,
    extracted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_paper_documents_paper_id ON paper_documents (paper_id);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id VARCHAR(36) PRIMARY KEY,
    paper_id VARCHAR(36) NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section_title VARCHAR(255),
    content TEXT NOT NULL,
    embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    CONSTRAINT uq_paper_chunks_paper_chunk_index UNIQUE (paper_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS ix_paper_chunks_paper_id ON paper_chunks (paper_id);

CREATE TABLE IF NOT EXISTS paper_conversations (
    id VARCHAR(36) PRIMARY KEY,
    paper_id VARCHAR(36) NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_paper_conversations_paper_id ON paper_conversations (paper_id);

CREATE TABLE IF NOT EXISTS paper_messages (
    id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL REFERENCES paper_conversations(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_paper_messages_conversation_id ON paper_messages (conversation_id);

CREATE TABLE IF NOT EXISTS project_conversations (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    selected_paper_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_project_conversations_project_id ON project_conversations (project_id);

CREATE TABLE IF NOT EXISTS project_messages (
    id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL REFERENCES project_conversations(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_project_messages_conversation_id ON project_messages (conversation_id);

CREATE TABLE IF NOT EXISTS deep_search_runs (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_prompt TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    selected_paper_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_body TEXT NOT NULL DEFAULT '',
    source_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    qa_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_deep_search_runs_project_id ON deep_search_runs (project_id);
CREATE INDEX IF NOT EXISTS ix_deep_search_runs_project_created_at ON deep_search_runs (project_id, created_at);

CREATE TABLE IF NOT EXISTS deep_search_sources (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES deep_search_runs(id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL,
    title VARCHAR(500) NOT NULL,
    url TEXT,
    paper_id VARCHAR(36) REFERENCES papers(id) ON DELETE SET NULL,
    snippet TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_deep_search_sources_run_id ON deep_search_sources (run_id);
CREATE INDEX IF NOT EXISTS ix_deep_search_sources_paper_id ON deep_search_sources (paper_id);

CREATE TABLE IF NOT EXISTS summaries (
    id VARCHAR(36) PRIMARY KEY,
    paper_id VARCHAR(36) NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE,
    problem TEXT,
    method TEXT,
    result TEXT,
    relevance_to_topic TEXT,
    has_error BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS ix_summaries_paper_id ON summaries (paper_id);

CREATE TABLE IF NOT EXISTS drafts (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    outline_json JSONB,
    content TEXT,
    word_count INTEGER NOT NULL DEFAULT 0,
    qa_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_drafts_project_id ON drafts (project_id);

CREATE TABLE IF NOT EXISTS writer_outputs (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    selected_paper_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    paper_snapshot_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    instruction TEXT NOT NULL,
    output_target VARCHAR(32) NOT NULL,
    citation_mode VARCHAR(32) NOT NULL,
    reference_style VARCHAR(32) NOT NULL,
    include_references BOOLEAN NOT NULL DEFAULT TRUE,
    max_words INTEGER,
    body TEXT NOT NULL DEFAULT '',
    references_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    bibtex_entries_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    thebibliography_text TEXT,
    citations_used_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    qa_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_writer_outputs_project_id ON writer_outputs (project_id);

-- Writer workspace tables (added 2026-05-09)
CREATE TABLE IF NOT EXISTS writer_documents (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL DEFAULT 'Untitled Paper',
    topic TEXT NOT NULL,
    thesis TEXT,
    paper_type VARCHAR(32) NOT NULL DEFAULT 'imrad',
    citation_style VARCHAR(32) NOT NULL DEFAULT 'ieee',
    preamble TEXT,
    source_paper_ids_json JSON NOT NULL,
    bib_text TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'outline',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_writer_documents_project_id ON writer_documents (project_id);

CREATE TABLE IF NOT EXISTS writer_sections (
    id VARCHAR(36) PRIMARY KEY,
    writer_document_id VARCHAR(36) NOT NULL REFERENCES writer_documents(id) ON DELETE CASCADE,
    section_type VARCHAR(64) NOT NULL,
    order_index INTEGER NOT NULL,
    title VARCHAR(500) NOT NULL,
    outline_text TEXT,
    user_inputs_json JSON NOT NULL,
    draft_latex TEXT,
    low_confidence_spans_json JSON NOT NULL,
    cited_paper_ids_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'planned',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_writer_sections_writer_document_id ON writer_sections (writer_document_id);

CREATE TABLE IF NOT EXISTS writer_section_versions (
    id VARCHAR(36) PRIMARY KEY,
    writer_section_id VARCHAR(36) NOT NULL REFERENCES writer_sections(id) ON DELETE CASCADE,
    draft_latex TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_writer_section_versions_section_id ON writer_section_versions (writer_section_id);
