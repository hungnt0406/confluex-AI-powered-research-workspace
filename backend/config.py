from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = Field(default="Literature Review API", alias="APP_NAME")
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
