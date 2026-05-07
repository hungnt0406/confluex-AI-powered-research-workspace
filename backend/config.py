from dataclasses import dataclass
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://172.18.64.1:3000",
)


@dataclass(frozen=True)
class CreditPack:
    """Static one-time top-up pack definition."""

    id: str
    name: str
    usd_cents: int
    credits: int
    badge: str | None = None


CREDIT_PACK_CATALOG: tuple[CreditPack, ...] = (
    CreditPack(id="student", name="Student", usd_cents=800, credits=800, badge="student"),
    CreditPack(
        id="pro",
        name="Researcher Pro",
        usd_cents=2_400,
        credits=2_400,
        badge="featured",
    ),
    CreditPack(
        id="lab_starter",
        name="Lab Starter",
        usd_cents=6_600,
        credits=6_600,
        badge="lab",
    ),
    CreditPack(
        id="topup_deep",
        name="Deep Search Top-up",
        usd_cents=600,
        credits=800,
        badge="topup",
    ),
    CreditPack(
        id="topup_storage",
        name="PDF Upload Credit Bump",
        usd_cents=400,
        credits=600,
        badge="topup",
    ),
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = Field(default="Literature Review API", alias="APP_NAME")
    cors_allowed_origins: str = Field(
        default=",".join(DEFAULT_CORS_ALLOWED_ORIGINS),
        alias="CORS_ALLOWED_ORIGINS",
    )
    admin_emails: str = Field(default="", alias="ADMIN_EMAILS")
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_model: str = Field(
        default="google/gemma-4-31b-it:free",
        validation_alias=AliasChoices("OPENROUTER_MODEL", "ANTHROPIC_MODEL"),
    )
    openrouter_document_model: str = Field(
        default="google/gemini-2.5-flash-lite",
        alias="OPENROUTER_DOCUMENT_MODEL",
    )
    openrouter_pdf_engine: str = Field(default="native", alias="OPENROUTER_PDF_ENGINE")
    openrouter_embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        validation_alias=AliasChoices("OPENROUTER_EMBEDDING_MODEL", "OPENAI_EMBEDDING_MODEL"),
    )
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    tavily_base_url: str = Field(default="https://api.tavily.com", alias="TAVILY_BASE_URL")
    deep_search_planner_model: str = Field(
        default="google/gemini-2.5-flash-lite",
        alias="DEEP_SEARCH_PLANNER_MODEL",
    )
    deep_search_research_model: str = Field(
        default="google/gemini-2.5-flash-lite",
        alias="DEEP_SEARCH_RESEARCH_MODEL",
    )
    deep_search_summarizer_model: str = Field(
        default="google/gemini-2.5-flash-lite",
        alias="DEEP_SEARCH_SUMMARIZER_MODEL",
    )
    deep_search_writer_model: str = Field(
        default="deepseek/deepseek-chat-v3.1",
        alias="DEEP_SEARCH_WRITER_MODEL",
    )
    deep_search_verifier_model: str = Field(
        default="google/gemini-2.5-flash-lite",
        alias="DEEP_SEARCH_VERIFIER_MODEL",
    )
    deep_search_max_web_searches: int = Field(default=5, alias="DEEP_SEARCH_MAX_WEB_SEARCHES")
    deep_search_max_iterations: int = Field(default=2, alias="DEEP_SEARCH_MAX_ITERATIONS")
    deep_search_max_results_per_query: int = Field(
        default=5,
        alias="DEEP_SEARCH_MAX_RESULTS_PER_QUERY",
    )
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/literature_review",
        alias="DATABASE_URL",
    )
    semantic_scholar_api_key: str | None = Field(default=None, alias="SEMANTIC_SCHOLAR_API_KEY")
    jwt_secret_key: str = Field(default="development-secret-key", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    default_year_start: int = Field(default=2018, alias="DEFAULT_YEAR_START")
    default_candidate_limit: int = Field(default=60, alias="DEFAULT_CANDIDATE_LIMIT")
    default_summary_limit: int = Field(default=30, alias="DEFAULT_SUMMARY_LIMIT")
    search_results_per_query: int = Field(default=10, alias="SEARCH_RESULTS_PER_QUERY")
    minimum_abstract_length: int = Field(default=100, alias="MINIMUM_ABSTRACT_LENGTH")
    summary_concurrency: int = Field(default=5, alias="SUMMARY_CONCURRENCY")
    embedding_dimensions: int = Field(default=256, alias="EMBEDDING_DIMENSIONS")
    external_api_timeout_seconds: float = Field(default=20.0, alias="EXTERNAL_API_TIMEOUT_SECONDS")
    pdf_download_timeout_seconds: float = Field(default=20.0, alias="PDF_DOWNLOAD_TIMEOUT_SECONDS")
    paper_chunk_size_chars: int = Field(default=3_000, alias="PAPER_CHUNK_SIZE_CHARS")
    paper_retrieval_top_k: int = Field(default=5, alias="PAPER_RETRIEVAL_TOP_K")
    reference_upload_dir: str = Field(default="data/reference_uploads", alias="REFERENCE_UPLOAD_DIR")
    reference_max_extracted_chars: int = Field(
        default=120_000,
        alias="REFERENCE_MAX_EXTRACTED_CHARS",
    )
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    sepay_api_key: str | None = Field(default=None, alias="SEPAY_API_KEY")
    sepay_webhook_api_key: str | None = Field(default=None, alias="SEPAY_WEBHOOK_API_KEY")
    sepay_account_number: str = Field(default="", alias="SEPAY_ACCOUNT_NUMBER")
    sepay_account_bank_bin: str = Field(default="", alias="SEPAY_ACCOUNT_BANK_BIN")
    usd_to_vnd_rate: float = Field(default=25_500.0, alias="USD_TO_VND_RATE")
    credit_cost_deep_search: int = Field(default=80, alias="CREDIT_COST_DEEP_SEARCH")
    credit_cost_writer: int = Field(default=40, alias="CREDIT_COST_WRITER")
    credit_cost_paper_chat: int = Field(default=2, alias="CREDIT_COST_PAPER_CHAT")
    credit_cost_pdf_upload: int = Field(default=5, alias="CREDIT_COST_PDF_UPLOAD")
    credit_cost_pipeline_run: int = Field(default=20, alias="CREDIT_COST_PIPELINE_RUN")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admin_email_set(self) -> frozenset[str]:
        """Return normalized allowlisted admin emails."""

        return frozenset(
            email.strip().lower()
            for email in self.admin_emails.split(",")
            if email.strip()
        )

    @property
    def cors_allowed_origin_list(self) -> tuple[str, ...]:
        """Return normalized CORS origins, falling back to local frontend defaults."""

        configured_origins = tuple(
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        )
        return configured_origins or DEFAULT_CORS_ALLOWED_ORIGINS

    @property
    def credit_pack_catalog(self) -> tuple[CreditPack, ...]:
        """Return the static credit pack catalog."""

        return CREDIT_PACK_CATALOG

    @property
    def credit_pack_by_id(self) -> dict[str, CreditPack]:
        """Return the credit pack catalog keyed by pack id."""

        return {pack.id: pack for pack in self.credit_pack_catalog}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
