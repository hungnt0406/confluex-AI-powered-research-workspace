-- PostgreSQL schema for A20-App-143
-- Generated from backend/db/models.py

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

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
