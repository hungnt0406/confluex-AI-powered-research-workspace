# Backend Component Diagram

This document maps how the backend components connect in the current codebase.

## High-Level Backend Wiring

```mermaid
flowchart TB
    Client["HTTP client<br/>browser UI, Postman, tests"] --> App["FastAPI app<br/>backend/main.py"]
    Settings["Settings<br/>backend/config.py"] --> App
    App --> Health["GET /healthz"]
    App --> Lifespan["Lifespan shutdown<br/>close DB engine"]
    App --> AuthRouter["Auth router<br/>/auth"]
    App --> ProjectsRouter["Projects router<br/>/projects"]
    App --> PipelineRouter["Pipeline router<br/>/pipeline"]

    AuthRouter --> AuthSchemas["Auth schemas"]
    AuthRouter --> Security["Security helpers<br/>password hashing, JWT"]
    AuthRouter --> DbSessionDep["DbSession dependency"]

    ProjectsRouter --> ProjectSchemas["Project schemas"]
    ProjectsRouter --> DbSessionDep
    ProjectsRouter --> CurrentUserDep["CurrentUser dependency"]
    ProjectsRouter --> PipelineServiceDep["Pipeline service dependency"]
    ProjectsRouter --> ReferenceServiceDep["Reference-file service dependency"]

    PipelineRouter --> PipelineHealthSchema["PipelineHealthResponse"]
    PipelineRouter --> PipelineNodeNames["PIPELINE_NODE_NAMES"]

    CurrentUserDep --> Bearer["HTTPBearer"]
    CurrentUserDep --> DecodeToken["decode_access_token"]
    CurrentUserDep --> LoadUser["select User by token subject"]
    DecodeToken --> Security
    LoadUser --> DbSessionDep

    DbSessionDep --> GetDbSession["get_db_session"]
    GetDbSession --> SessionManager["DatabaseSessionManager"]
    Settings --> SessionManager
    SessionManager --> AsyncEngine["SQLAlchemy AsyncEngine"]
    AsyncEngine --> Database[(Relational database)]

    PipelineServiceDep --> PipelineFactory["get_pipeline_service"]
    PipelineFactory --> LiteraturePipelineService["LiteraturePipelineService"]
    LiteraturePipelineService --> ProjectPipelineRunner["ProjectPipelineRunner<br/>LangGraph"]
    ProjectPipelineRunner --> SearcherAgent["SearcherAgent"]
    ProjectPipelineRunner --> ReaderAgent["ReaderAgent"]

    ReferenceServiceDep --> ReferenceFactory["get_reference_file_service"]
    ReferenceFactory --> ReferenceFileService["ReferenceFileService"]

    SearcherAgent --> QueryLLM["OpenRouter structured output<br/>query expansion"]
    SearcherAgent --> SemanticScholarClient["Semantic Scholar adapter"]
    SearcherAgent --> ArxivClient["arXiv adapter"]
    SearcherAgent --> ResearchUtils["research_utils"]

    ReaderAgent --> Embeddings["EmbeddingService"]
    ReaderAgent --> SummaryLLM["OpenRouter structured output<br/>summaries"]
    ReaderAgent --> ResearchUtils

    ReferenceFileService --> DocumentExtraction["PaperDocumentExtractionService<br/>uploaded PDF extraction"]
    DocumentExtraction --> OpenRouterPdf["OpenRouter file parser<br/>base64 PDF data URL"]
    ReferenceFileService --> UploadStorage[(Reference PDF storage<br/>REFERENCE_UPLOAD_DIR)]

    AuthRouter --> Models["SQLAlchemy models"]
    ProjectsRouter --> Models
    SearcherAgent --> Models
    ReaderAgent --> Models
    ReferenceFileService --> Models
    Models --> Database
    Migrations["Alembic migrations"] --> Database

    QueryLLM --> OpenRouterChat["OpenRouter<br/>/chat/completions"]
    SummaryLLM --> OpenRouterChat
    Embeddings --> OpenRouterEmbeddings["OpenRouter<br/>/embeddings"]
    SemanticScholarClient --> SemanticScholarApi["Semantic Scholar Graph API"]
    ArxivClient --> ArxivApi["arXiv Atom API"]

    Settings --> Security
    Settings --> QueryLLM
    Settings --> SummaryLLM
    Settings --> Embeddings
    Settings --> ReferenceFileService
    Settings --> SemanticScholarClient

    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;
    classDef api fill:#e7f5ff,stroke:#1c7ed6,color:#0b3558;
    classDef dependency fill:#fff4e6,stroke:#f08c00,color:#5f370e;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;
    classDef persistence fill:#f3f0ff,stroke:#7048e8,color:#2f1b70;
    classDef external fill:#fff0f6,stroke:#d6336c,color:#5c1730;

    class Client,App,Health,Lifespan,Settings entry;
    class AuthRouter,ProjectsRouter,PipelineRouter,AuthSchemas,ProjectSchemas,PipelineHealthSchema,PipelineNodeNames api;
    class DbSessionDep,CurrentUserDep,PipelineServiceDep,ReferenceServiceDep,Bearer,DecodeToken,LoadUser,GetDbSession,PipelineFactory,ReferenceFactory dependency;
    class Security,LiteraturePipelineService,ProjectPipelineRunner,SearcherAgent,ReaderAgent,ReferenceFileService,QueryLLM,SummaryLLM,Embeddings,ResearchUtils,DocumentExtraction,SemanticScholarClient,ArxivClient service;
    class SessionManager,AsyncEngine,Database,Models,Migrations,UploadStorage persistence;
    class OpenRouterChat,OpenRouterEmbeddings,SemanticScholarApi,ArxivApi external;
```

## API Routes And Main Backend Responsibilities

```mermaid
flowchart TB
    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;
    classDef api fill:#e7f5ff,stroke:#1c7ed6,color:#0b3558;
    classDef dependency fill:#fff4e6,stroke:#f08c00,color:#5f370e;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;
    classDef persistence fill:#f3f0ff,stroke:#7048e8,color:#2f1b70;
    classDef external fill:#fff0f6,stroke:#d6336c,color:#5c1730;

    App["backend/main.py<br/>create_app"] --> Health["GET /healthz<br/>returns status ok"]
    App --> Auth["/auth router"]
    App --> Admin["/admin router"]
    App --> Projects["/projects router"]
    App --> Pipeline["/pipeline router"]

    subgraph AuthEndpoints["Auth endpoints"]
        Auth --> Register["POST /auth/register"]
        Auth --> Login["POST /auth/login"]

        Register --> CheckExistingUser["select User by email"]
        Register --> HashPassword["hash_password<br/>PBKDF2 SHA-256"]
        Register --> InsertUser["insert User"]
        Register --> RegisterToken["create_access_token"]

        Login --> LoadLoginUser["select User by email"]
        Login --> VerifyPassword["verify_password"]
        Login --> LoginToken["create_access_token"]

        RegisterToken --> AuthResponse["AuthResponse<br/>access_token<br/>token_type<br/>user"]
        LoginToken --> AuthResponse
    end

    subgraph AdminEndpoints["Admin endpoints"]
        Admin --> AdminAccess["GET /admin/access"]
        Admin --> AdminTokenUsage["GET /admin/token-usage"]

        AdminAccess --> AuthRequiredAdminAccess["CurrentUser"]
        AdminTokenUsage --> AdminRequired["AdminUser"]
        AdminTokenUsage --> GlobalUsage["summarize_admin_usage"]
    end

    subgraph ProjectEndpoints["Project endpoints"]
        Projects --> CreateProject["POST /projects"]
        Projects --> ListProjects["GET /projects"]
        Projects --> GetProject["GET /projects/{project_id}"]
        Projects --> DeleteProject["DELETE /projects/{project_id}"]
        Projects --> RunProject["POST /projects/{project_id}/run"]
        Projects --> TokenUsage["GET /projects/{project_id}/token-usage"]
        Projects --> UploadReference["POST /projects/{project_id}/reference-files"]
        Projects --> ListReferences["GET /projects/{project_id}/reference-files"]
        Projects --> DeleteReference["DELETE /projects/{project_id}/reference-files/{reference_file_id}"]
        Projects --> ListPapers["GET /projects/{project_id}/papers"]
        Projects --> PaperCitationGraph["GET /projects/{project_id}/papers/{paper_id}/citation-graph"]
        Projects --> ImportCitation["POST /projects/{project_id}/papers/import-citation"]

        CreateProject --> AuthRequiredA["CurrentUser"]
        ListProjects --> AuthRequiredB["CurrentUser"]
        GetProject --> OwnedProjectA["get_owned_project_or_404"]
        DeleteProject --> OwnedProjectB["get_owned_project_or_404"]
        RunProject --> OwnedProjectC["get_owned_project_or_404"]
        TokenUsage --> OwnedProjectUsage["get_owned_project_or_404"]
        UploadReference --> OwnedProjectD["get_owned_project_or_404"]
        ListReferences --> OwnedProjectE["get_owned_project_or_404"]
        DeleteReference --> OwnedProjectF["get_owned_project_or_404"]
        ListPapers --> OwnedProjectG["get_owned_project_or_404"]
        PaperCitationGraph --> OwnedProjectH["get_owned_project_or_404"]
        ImportCitation --> OwnedProjectI["get_owned_project_or_404"]

        DeleteProject --> DeleteProjectRows["session.delete(project)<br/>ORM + FK cascades"]
        DeleteProject --> DeleteProjectStoredPdfs["best-effort unlink of stored project PDFs"]
        RunProject --> LiteraturePipelineService["LiteraturePipelineService.run_project"]
        UploadReference --> ReferenceFileService["ReferenceFileService.create_reference_file"]
        ListReferences --> ReferenceFileRead["ReferenceFileRead.from_reference"]
        DeleteReference --> DeleteLinkedPaper["delete linked Paper if present"]
        DeleteReference --> DeleteReferenceRow["delete ReferenceFile row"]
        DeleteReference --> DeleteStoredPdf["unlink stored PDF with anyio.to_thread"]
        ListPapers --> PaperFilters["apply_paper_filters<br/>status<br/>min_relevance"]
        ListPapers --> Pagination["PaginationMeta.from_totals"]
        PaperCitationGraph --> CitationService["PaperCitationService.get_citation_graph"]
        ImportCitation --> ImportValidation["prevent duplicates by ID, DOI, or title"]
        ImportCitation --> InsertPaper["insert Paper row with status candidate"]
        CitationService --> CitationResolver["Semantic Scholar exact paper resolution<br/>paper id · ARXIV: · DOI: · URL:"]
        CitationService --> CitationEdges["GET /graph/v1/paper/{paper_id}/citations<br/>GET /graph/v1/paper/{paper_id}/references"]
    end

    subgraph PipelineEndpoints["Pipeline endpoints"]
        Pipeline --> PipelineHealth["GET /pipeline/health"]
        PipelineHealth --> NodeNames["PIPELINE_NODE_NAMES<br/>searcher_node<br/>reader_node<br/>reader_warning_node"]
    end

    AuthRequiredA --> UserModel["User"]
    AuthRequiredB --> UserModel
    OwnedProjectA --> ProjectModel["Project"]
    OwnedProjectB --> ProjectModel
    OwnedProjectC --> ProjectModel
    OwnedProjectD --> ProjectModel
    OwnedProjectE --> ProjectModel
    OwnedProjectF --> ProjectModel
    OwnedProjectG --> ProjectModel
    OwnedProjectH --> ProjectModel
    OwnedProjectI --> ProjectModel

    class App,Health entry;
    class Auth,Admin,Projects,Pipeline,Register,Login,AdminAccess,AdminTokenUsage,CreateProject,ListProjects,GetProject,DeleteProject,RunProject,TokenUsage,UploadReference,ListReferences,DeleteReference,ListPapers,PaperCitationGraph,ImportCitation,PipelineHealth,AuthResponse api;
    class AuthRequiredAdminAccess,AdminRequired,AuthRequiredA,AuthRequiredB,OwnedProjectA,OwnedProjectB,OwnedProjectC,OwnedProjectUsage,OwnedProjectD,OwnedProjectE,OwnedProjectF,OwnedProjectG,OwnedProjectH,OwnedProjectI dependency;
    class CheckExistingUser,InsertUser,LoadLoginUser,DeleteProjectRows,DeleteProjectStoredPdfs,DeleteLinkedPaper,DeleteReferenceRow,DeleteStoredPdf,InsertPaper,UserModel,ProjectModel persistence;
    class HashPassword,RegisterToken,VerifyPassword,LoginToken,GlobalUsage,LiteraturePipelineService,ReferenceFileService,ReferenceFileRead,PaperFilters,Pagination,CitationService,ImportValidation,CitationResolver,CitationEdges,NodeNames service;
```

## Authentication And Dependency Flow

```mermaid
sequenceDiagram
    autonumber
    participant Client as HTTP client
    participant Router as Protected route
    participant Bearer as HTTPBearer
    participant Security as backend/security.py
    participant DB as AsyncSession
    participant User as users table

    Client->>Router: Request with Authorization: Bearer token
    Router->>Bearer: Resolve HTTPAuthorizationCredentials
    alt Missing credentials
        Bearer-->>Router: None
        Router-->>Client: 401 Authentication credentials were not provided
    else Credentials present
        Router->>Security: decode_access_token(token)
        Security->>Security: jwt.decode using JWT_SECRET_KEY and JWT_ALGORITHM
        alt Invalid token or bad sub
            Security-->>Router: jwt.InvalidTokenError, KeyError, or TypeError
            Router-->>Client: 401 Invalid authentication token
        else Valid token
            Security-->>Router: payload with sub user_id
            Router->>DB: select User where id == sub
            DB->>User: Query
            User-->>DB: User row or none
            alt User missing
                Router-->>Client: 401 Authenticated user no longer exists
            else User found
                DB-->>Router: User model
                Router->>Router: Continue endpoint handler
                Router-->>Client: Endpoint response
            end
        end
    end
```

## Project Pipeline Run

`POST /projects/{project_id}/run` executes the research pipeline synchronously and returns completion metadata.

```mermaid
sequenceDiagram
    autonumber
    participant Client as HTTP client
    participant Route as queue_project_pipeline
    participant Auth as CurrentUser dependency
    participant DB as AsyncSession
    participant Project as projects table
    participant Service as LiteraturePipelineService
    participant Runner as ProjectPipelineRunner
    participant Searcher as SearcherAgent
    participant Reader as ReaderAgent
    participant Papers as papers table
    participant Summaries as summaries table

    Client->>Route: POST /projects/{project_id}/run
    Route->>Auth: Resolve authenticated User
    Auth-->>Route: User
    Route->>DB: select Project by id and user_id
    DB->>Project: Query ownership
    Project-->>DB: Project row
    DB-->>Route: Project
    Route->>Service: run_project(session, project)
    Service->>Runner: Create ProjectPipelineRunner
    Runner->>Runner: Build LangGraph StateGraph
    Runner->>Runner: Initialize AgentState from Project
    Runner->>Searcher: searcher_node(state)
    Searcher->>Papers: Preserve user_upload papers, delete stale non-upload papers
    Searcher->>Searcher: Build reference context from uploaded papers
    Searcher->>Searcher: Expand topic into search queries
    Searcher->>Searcher: Search Semantic Scholar and arXiv concurrently
    Searcher->>Searcher: Filter by year, abstract length, DOI/title duplicates
    Searcher->>Papers: Insert candidate Paper rows
    Searcher-->>Runner: queries, raw_papers, errors
    Runner->>Reader: reader_node(state)
    Reader->>Papers: Load project Paper rows
    Reader->>Reader: Rank with embeddings and cosine similarity
    Reader->>Papers: Mark top papers ranked
    Reader->>Reader: Generate structured summaries concurrently
    Reader->>Summaries: Insert Summary rows
    Reader->>Papers: Mark papers summarized or summary_error
    Reader-->>Runner: ranked_papers, summaries, errors
    alt Fewer than 5 ranked papers
        Runner->>Runner: reader_warning_node adds qa_flags warning
    end
    Runner-->>Service: Final AgentState
    Service-->>Route: Final AgentState
    Route-->>Client: RunPipelineResponse with counts, queries, qa_flags, errors
```

## LangGraph Pipeline Topology

```mermaid
flowchart TB
    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;
    classDef state fill:#fff4e6,stroke:#f08c00,color:#5f370e;

    Start([START]) --> SearcherNode["searcher_node<br/>SearcherAgent.run"]
    SearcherNode --> ReaderNode["reader_node<br/>ReaderAgent.run"]
    ReaderNode --> Decision{"Fewer than 5 ranked papers?"}
    Decision -- yes --> WarningNode["reader_warning_node<br/>append QA warning"]
    Decision -- no --> End([END])
    WarningNode --> End

    subgraph State["AgentState fields"]
        StateProject["project_id"]
        StateTopic["topic"]
        StateLimits["year_start<br/>candidate_limit<br/>summary_limit"]
        StateQueries["queries"]
        StateRaw["raw_papers"]
        StateRanked["ranked_papers"]
        StateSummaries["summaries"]
        StateDraft["draft"]
        StateFlags["qa_flags"]
        StateErrors["errors"]
    end

    SearcherNode -. updates .-> StateQueries
    SearcherNode -. updates .-> StateRaw
    SearcherNode -. updates .-> StateErrors
    ReaderNode -. updates .-> StateRanked
    ReaderNode -. updates .-> StateSummaries
    ReaderNode -. updates .-> StateErrors
    WarningNode -. updates .-> StateFlags
    WriterNode -. reads .-> StateDraft

    class Start,End,Decision entry;
    class SearcherNode,ReaderNode,WarningNode,WriterNode service;
    class StateProject,StateTopic,StateLimits,StateQueries,StateRaw,StateRanked,StateSummaries,StateDraft,StateFlags,StateErrors state;
```

## SearcherAgent Internals

```mermaid
flowchart TB
    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;
    classDef persistence fill:#f3f0ff,stroke:#7048e8,color:#2f1b70;
    classDef external fill:#fff0f6,stroke:#d6336c,color:#5c1730;
    classDef state fill:#fff4e6,stroke:#f08c00,color:#5f370e;

    Run["SearcherAgent.run"] --> Prepare["prepare existing project papers"]
    Prepare --> DeleteSummaries["delete Summary rows for project papers"]
    Prepare --> DeleteStalePapers["delete non-user_upload Paper rows"]
    Prepare --> PreserveUploads["preserve user_upload Paper rows<br/>reset status and relevance_score"]

    PreserveUploads --> ReferenceContext["build ReferencePaperContext<br/>title, year, abstract, doi"]
    ReferenceContext --> Collect["collect_candidates"]
    Collect --> Expand["expand_queries"]

    Expand --> NamedEntityDecision{"Named entity topic<br/>and no uploaded context?"}
    NamedEntityDecision -- yes --> NamedEntityQueries["build named-entity queries"]
    NamedEntityDecision -- no --> LLMConfigured{"OpenRouter configured?"}
    LLMConfigured -- no --> FallbackQueries["build fallback queries"]
    LLMConfigured -- yes --> QueryPrompt["build query expansion prompt"]
    QueryPrompt --> OpenRouterChat["OpenRouterStructuredOutputService.generate_json"]
    OpenRouterChat --> CoerceQueries["coerce and validate SearchQueryBatch"]
    OpenRouterChat -- error --> FallbackQueries

    NamedEntityQueries --> QueryStrings["query strings"]
    FallbackQueries --> QueryStrings
    CoerceQueries --> QueryStrings

    QueryStrings --> SearchFanout["asyncio.gather across queries and clients"]
    SearchFanout --> SemanticScholar["Semantic Scholar search_papers"]
    SearchFanout --> Arxiv["arXiv search_papers"]
    SemanticScholar --> NormalizeSemantic["normalize Semantic Scholar payload"]
    Arxiv --> NormalizeArxiv["normalize arXiv Atom entries"]

    NormalizeSemantic --> CandidatePool["PaperRecord candidate pool"]
    NormalizeArxiv --> CandidatePool
    CandidatePool --> Filter["filter year at least project.year_start<br/>abstract exists<br/>abstract length at least minimum_abstract_length"]
    Filter --> Prioritize["prioritize DOI, abstract length,<br/>Semantic Scholar source"]
    Prioritize --> Deduplicate["deduplicate by DOI and normalized title<br/>including uploaded reference papers"]
    Deduplicate --> Limit["take project.candidate_limit"]
    Limit --> Persist["insert Paper rows<br/>status candidate<br/>source semantic_scholar or arxiv"]
    Persist --> SearcherResult["state update<br/>queries<br/>raw_papers<br/>errors"]

    class Run,NamedEntityDecision,LLMConfigured entry;
    class Prepare,ReferenceContext,Collect,Expand,NamedEntityQueries,FallbackQueries,QueryPrompt,CoerceQueries,SearchFanout,NormalizeSemantic,NormalizeArxiv,CandidatePool,Filter,Prioritize,Deduplicate,Limit service;
    class DeleteSummaries,DeleteStalePapers,PreserveUploads,Persist persistence;
    class OpenRouterChat,SemanticScholar,Arxiv external;
    class QueryStrings,SearcherResult state;
```

## ReaderAgent Internals

```mermaid
flowchart TB
    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;
    classDef persistence fill:#f3f0ff,stroke:#7048e8,color:#2f1b70;
    classDef external fill:#fff0f6,stroke:#d6336c,color:#5c1730;
    classDef state fill:#fff4e6,stroke:#f08c00,color:#5f370e;

    Run["ReaderAgent.run"] --> LoadCandidates["select Paper rows by project_id"]
    LoadCandidates --> HasCandidates{"Any candidates?"}
    HasCandidates -- no --> NoCandidates["return empty ranked_papers and summaries<br/>append error"]
    HasCandidates -- yes --> Rank["rank_papers"]

    Rank --> BuildEmbeddingInputs["Build embedding inputs<br/>topic first<br/>then title + abstract for each paper"]
    BuildEmbeddingInputs --> EmbedLive["EmbeddingService.embed_texts"]
    EmbedLive --> LiveConfigured{"OpenRouter API key configured?"}
    LiveConfigured -- yes --> OpenRouterEmbeddings["POST /embeddings"]
    LiveConfigured -- no --> LocalEmbeddings["embed_texts_locally<br/>hash-token deterministic vectors"]
    OpenRouterEmbeddings -- HTTP error --> LocalFallback["local fallback<br/>append ranking error"]
    OpenRouterEmbeddings --> Score["cosine_similarity(topic, paper) * 100"]
    LocalEmbeddings --> Score
    LocalFallback --> Score

    Score --> Sort["sort papers by relevance_score descending"]
    Sort --> TopPapers["top project.summary_limit papers"]
    TopPapers --> MarkRanked["set status ranked"]
    MarkRanked --> Summarize["summarize top papers concurrently<br/>bounded by summary_concurrency"]

    Summarize --> SummaryConfigured{"Summary generator configured?"}
    SummaryConfigured -- no --> FallbackSummary["build fallback summary from abstract sentences"]
    SummaryConfigured -- yes --> SummaryLLM["OpenRouterStructuredOutputService.generate_json<br/>problem, method, result, relevance"]
    SummaryLLM -- validation or structured-output error --> Retry{"Second attempt available?"}
    Retry -- yes --> SummaryLLM
    Retry -- no --> SummaryError["SummaryGenerationResult<br/>payload none<br/>has_error true"]
    SummaryLLM --> ParsedSummary["PaperSummaryPayload"]
    FallbackSummary --> ParsedSummary

    ParsedSummary --> PersistSummary["insert Summary row<br/>has_error false"]
    SummaryError --> PersistSummaryError["insert Summary row<br/>has_error true<br/>error_message set"]
    PersistSummary --> MarkSummarized["set Paper status summarized"]
    PersistSummaryError --> MarkSummaryError["set Paper status summary_error"]
    MarkSummarized --> Commit["commit transaction"]
    MarkSummaryError --> Commit
    Commit --> ReaderResult["state update<br/>ranked_papers<br/>summaries<br/>errors"]

    class Run,HasCandidates,LiveConfigured,Retry entry;
    class NoCandidates,Rank,BuildEmbeddingInputs,EmbedLive,LocalEmbeddings,LocalFallback,Score,Sort,TopPapers,Summarize,SummaryConfigured,FallbackSummary,SummaryError,ParsedSummary service;
    class LoadCandidates,MarkRanked,PersistSummary,PersistSummaryError,MarkSummarized,MarkSummaryError,Commit persistence;
    class OpenRouterEmbeddings,SummaryLLM external;
    class ReaderResult state;
```

## Reference File Upload Flow

```mermaid
sequenceDiagram
    autonumber
    participant Client as HTTP client
    participant Route as upload_project_reference_file
    participant Auth as CurrentUser dependency
    participant DB as AsyncSession
    participant Service as ReferenceFileService
    participant Storage as REFERENCE_UPLOAD_DIR
    participant Extractor as PaperDocumentExtractionService
    participant RefTable as reference_files table
    participant PaperTable as papers table

    Client->>Route: POST /projects/{project_id}/reference-files with multipart PDF
    Route->>Auth: Resolve authenticated User
    Auth-->>Route: User
    Route->>DB: get_owned_project_or_404(project_id, user_id)
    DB-->>Route: Project
    Route->>Route: Read multipart file bytes
    Route->>Service: create_reference_file(session, project, filename, content_type, content)
    Service->>Service: Sanitize filename with Path(...).name
    Service->>Service: validate_pdf_upload
    alt Invalid file
        Service-->>Route: ReferenceFileValidationError
        Route-->>Client: 400 Bad Request
    else Valid PDF
        Service->>Service: compute_sha256(content)
        Service->>DB: select ReferenceFile by project_id and sha256
        alt Duplicate file
            Service-->>Route: ReferenceFileDuplicateError
            Route-->>Client: 409 Conflict
        else New file
            Service->>Storage: mkdir data/reference_uploads/{project_id}
            Service->>Storage: write {reference_file_id}.pdf
            Service->>Extractor: extract_uploaded_pdf(pdf_bytes, filename)
            Extractor-->>Service: ExtractedDocument from OpenRouter or local fallback
            Service->>Service: Build ParsedReferenceMetadata from extracted text
            Service->>RefTable: Insert ReferenceFile row
            alt parse_status == parsed
                Service->>PaperTable: Insert linked Paper row with source user_upload
            else parse_status == parse_error
                Service->>RefTable: Keep error_message, no linked Paper
            end
            Service->>DB: commit and refresh ReferenceFile
            Service-->>Route: ReferenceFile
            Route->>DB: reload ReferenceFile with linked Paper
            Route-->>Client: 201 ReferenceFileRead with Location header
        end
    end
```

## Reference File Delete Flow

```mermaid
flowchart TB
    classDef api fill:#e7f5ff,stroke:#1c7ed6,color:#0b3558;
    classDef dependency fill:#fff4e6,stroke:#f08c00,color:#5f370e;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;
    classDef persistence fill:#f3f0ff,stroke:#7048e8,color:#2f1b70;
    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;

    DeleteRoute["DELETE /projects/{project_id}/reference-files/{reference_file_id}"] --> CurrentUser["CurrentUser dependency"]
    DeleteRoute --> OwnedProject["get_owned_project_or_404"]
    OwnedProject --> LoadReference["get_project_reference_file_or_404<br/>select ReferenceFile with linked Paper"]
    LoadReference --> HasPaper{"Linked Paper exists?"}
    HasPaper -- yes --> DeletePaper["session.delete(reference_file.paper)"]
    HasPaper -- no --> DeleteReference["session.delete(reference_file)"]
    DeletePaper --> DeleteReference
    DeleteReference --> Commit["session.commit"]
    Commit --> Unlink["anyio.to_thread.run_sync<br/>Path(storage_path).unlink(missing_ok=True)"]
    Unlink --> IgnoreOSError["OSError ignored"]
    IgnoreOSError --> NoContent["204 No Content"]

    class DeleteRoute,NoContent api;
    class CurrentUser,OwnedProject dependency;
    class LoadReference,DeletePaper,DeleteReference,Commit persistence;
    class HasPaper entry;
    class Unlink,IgnoreOSError service;
```

## Database Relationships

```mermaid
erDiagram
    USERS ||--o{ PROJECTS : owns
    PROJECTS ||--o{ PAPERS : contains
    PROJECTS ||--o{ DRAFTS : has
    PROJECTS ||--o{ REFERENCE_FILES : uploads
    REFERENCE_FILES ||--o| PAPERS : creates_linked_upload_paper
    PAPERS ||--o| SUMMARIES : summarized_by

    USERS {
        string id PK
        string email UK
        string hashed_password
        datetime created_at
    }

    PROJECTS {
        string id PK
        string user_id FK
        string title
        text topic_description
        string citation_format
        int year_start
        int candidate_limit
        int summary_limit
        datetime created_at
    }

    REFERENCE_FILES {
        string id PK
        string project_id FK
        string original_filename
        string content_type
        int byte_size
        string sha256
        text storage_path
        string parse_status
        string extracted_title
        json extracted_authors
        int extracted_year
        text extracted_abstract
        text extracted_text
        text error_message
        datetime created_at
        datetime updated_at
    }

    PAPERS {
        string id PK
        string project_id FK
        string reference_file_id FK
        string title
        json authors
        int year
        text abstract
        string doi
        string source
        string source_paper_id
        text source_url
        text pdf_url
        string status
        float relevance_score
    }

    SUMMARIES {
        string id PK
        string paper_id FK
        text problem
        text method
        text result
        text relevance_to_topic
        bool has_error
        text error_message
    }

    DRAFTS {
        string id PK
        string project_id FK
        json outline_json
        text content
        int word_count
        json qa_flags_json
        datetime created_at
    }
```

## Data Ownership And Cascade Rules

```mermaid
flowchart TB
    User["User"] -->|cascade delete-orphan via ORM<br/>FK ondelete CASCADE| Project["Project"]
    Project -->|cascade delete-orphan via ORM<br/>FK ondelete CASCADE| Paper["Paper"]
    Project -->|cascade delete-orphan via ORM<br/>FK ondelete CASCADE| Draft["Draft"]
    Project -->|cascade delete-orphan via ORM<br/>FK ondelete CASCADE| ReferenceFile["ReferenceFile"]
    Paper -->|one-to-one<br/>cascade delete-orphan via ORM<br/>FK ondelete CASCADE| Summary["Summary"]
    ReferenceFile -->|optional one-to-one<br/>FK ondelete CASCADE<br/>unique reference_file_id| UploadedPaper["Paper with source user_upload"]

    ReferenceFile --> UniqueHash["Unique per project<br/>project_id + sha256"]
    User --> UniqueEmail["Unique email"]
    Paper --> Status["status lifecycle<br/>candidate<br/>ranked<br/>summarized<br/>summary_error"]
    ReferenceFile --> ParseStatus["parse_status lifecycle<br/>parsed<br/>parse_error"]
```

## Configuration And Runtime Settings

```mermaid
flowchart LR
    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;
    classDef external fill:#fff0f6,stroke:#d6336c,color:#5c1730;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;
    classDef dependency fill:#fff4e6,stroke:#f08c00,color:#5f370e;

    Env["Environment variables<br/>.env supported by pydantic-settings"] --> Settings["Settings<br/>backend/config.py<br/>get_settings cached by lru_cache"]

    Settings --> AppName["APP_NAME"]
    Settings --> DatabaseUrl["DATABASE_URL"]
    Settings --> Jwt["JWT_SECRET_KEY<br/>JWT_ALGORITHM<br/>ACCESS_TOKEN_EXPIRE_MINUTES"]
    Settings --> OpenRouter["OPENROUTER_API_KEY<br/>OPENROUTER_BASE_URL<br/>OPENROUTER_MODEL<br/>OPENROUTER_EMBEDDING_MODEL"]
    Settings --> DeclaredProjectDefaults["Declared project defaults<br/>DEFAULT_YEAR_START<br/>DEFAULT_CANDIDATE_LIMIT<br/>DEFAULT_SUMMARY_LIMIT"]
    Settings --> SearchTuning["Searcher defaults<br/>SEARCH_RESULTS_PER_QUERY<br/>MINIMUM_ABSTRACT_LENGTH"]
    Settings --> RuntimeTuning["SUMMARY_CONCURRENCY<br/>EMBEDDING_DIMENSIONS<br/>EXTERNAL_API_TIMEOUT_SECONDS"]
    Settings --> UploadTuning["REFERENCE_UPLOAD_DIR<br/>REFERENCE_MAX_EXTRACTED_CHARS"]
    Settings --> SemanticScholarKey["SEMANTIC_SCHOLAR_API_KEY"]

    DatabaseUrl --> SessionManager["DatabaseSessionManager"]
    Jwt --> Security["backend/security.py"]
    OpenRouter --> LLM["OpenRouterStructuredOutputService"]
    OpenRouter --> Embeddings["EmbeddingService"]
    DeclaredProjectDefaults --> ProjectDefaultsNote["Current ProjectCreate and Project model defaults<br/>are hard-coded to the same values"]
    SearchTuning --> Searcher["SearcherAgent"]
    RuntimeTuning --> Reader["ReaderAgent and HTTP clients"]
    UploadTuning --> ReferenceFileService["ReferenceFileService"]
    SemanticScholarKey --> SemanticScholar["Semantic Scholar API headers"]

    class Env,AppName,DatabaseUrl,Jwt,OpenRouter,DeclaredProjectDefaults,SearchTuning,RuntimeTuning,UploadTuning,SemanticScholarKey entry;
    class Settings dependency;
    class SessionManager,Security,LLM,Embeddings,ProjectDefaultsNote,Searcher,Reader,ReferenceFileService service;
    class SemanticScholar external;
```

## External Integration Boundaries

```mermaid
flowchart TB
    classDef entry fill:#f6f8fa,stroke:#6e7781,color:#24292f;
    classDef external fill:#fff0f6,stroke:#d6336c,color:#5c1730;
    classDef persistence fill:#f3f0ff,stroke:#7048e8,color:#2f1b70;
    classDef service fill:#ebfbee,stroke:#37b24d,color:#163b1f;

    Backend["Backend process"] --> OpenRouterChat["OpenRouter chat completions<br/>query expansion<br/>structured summaries"]
    Backend --> OpenRouterEmbeddings["OpenRouter embeddings<br/>ranking vectors"]
    Backend --> SemanticScholar["Semantic Scholar Graph API<br/>paper search"]
    Backend --> Arxiv["arXiv API<br/>paper search"]
    Backend --> LocalDisk["Local filesystem<br/>reference PDF storage"]
    Backend --> Database[(Relational database<br/>async SQLAlchemy)]

    OpenRouterChat --> ChatFallback["If not configured or invalid output:<br/>query fallback or summary error/fallback"]
    OpenRouterEmbeddings --> EmbeddingFallback["If not configured or request fails:<br/>deterministic local embeddings"]
    SemanticScholar --> SearchErrorHandling["Provider exceptions are collected<br/>into pipeline errors"]
    Arxiv --> SearchErrorHandling
    LocalDisk --> UploadCleanup["Reference/project delete attempts to unlink PDFs<br/>OSError is ignored"]

    class Backend entry;
    class OpenRouterChat,OpenRouterEmbeddings,SemanticScholar,Arxiv external;
    class LocalDisk,Database persistence;
    class ChatFallback,EmbeddingFallback,SearchErrorHandling,UploadCleanup service;
```

## File-To-Responsibility Map

| Area | Files | Responsibility |
| --- | --- | --- |
| App entrypoint | `backend/main.py` | Creates the FastAPI app, registers routers, exposes `/healthz`, and closes the default database engine during shutdown. |
| Configuration | `backend/config.py` | Loads cached runtime settings from environment variables and `.env`. |
| Security | `backend/security.py` | Password hashing and verification, JWT creation, and JWT decoding. |
| API dependencies | `backend/api/dependencies.py` | Provides `DbSession`, authenticated `CurrentUser`, allowlisted `AdminUser`, `LiteraturePipelineService`, and `ReferenceFileService`. |
| Routers | `backend/api/routers/auth.py`, `backend/api/routers/admin.py`, `backend/api/routers/projects.py`, `backend/api/routers/pipeline.py` | Own HTTP endpoint behavior and convert service/domain errors into HTTP responses. |
| Schemas | `backend/api/schemas/auth.py`, `backend/api/schemas/admin.py`, `backend/api/schemas/projects.py` | Define request and response payloads. |
| Database | `backend/db/base.py`, `backend/db/session.py`, `backend/db/models.py`, `backend/db/migrations/` | Define ORM models, async sessions, and Alembic schema changes. |
| Pipeline orchestration | `backend/agents/pipeline.py`, `backend/agents/graph.py`, `backend/agents/state.py` | Build and run the LangGraph pipeline for a project. |
| Search agent | `backend/agents/searcher.py` | Expands queries, calls search providers, filters and deduplicates candidates, and persists candidate papers. |
| Reader agent | `backend/agents/reader.py` | Ranks papers with embeddings, generates structured summaries, and persists summary records. |
| Reference uploads | `backend/services/reference_files.py` | Validates, stores, parses, and persists uploaded reference PDFs and linked paper rows. |
| AI usage telemetry | `backend/services/ai_usage.py`, `backend/db/models.py` | Collect provider-reported OpenRouter usage per successful project request and aggregate it by project, day, feature, model, user, and recent event. |
| External clients | `backend/services/semantic_scholar.py`, `backend/services/arxiv.py`, `backend/services/llm.py`, `backend/services/embeddings.py` | Integrate with external search, chat, and embedding APIs while providing local fallbacks where available. |
| Shared utilities | `backend/services/paper_types.py`, `backend/services/research_utils.py` | Define normalized paper payloads and shared research text/math utilities. |
