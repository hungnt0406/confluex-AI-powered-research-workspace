"""
Application configuration — loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM Providers ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o")
CHEAP_MODEL = os.getenv("CHEAP_MODEL", "gpt-4o-mini")

# --- Database ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost:5432/literaturereview",
)

# --- Data Source API Keys (optional — improves rate limits) ---
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
PUBMED_EMAIL = os.getenv("PUBMED_EMAIL", "")
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY", "")

# --- Embedding ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")

# --- Pipeline Defaults ---
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "200"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.3"))
TOP_N_PAPERS = int(os.getenv("TOP_N_PAPERS", "20"))
QUALITY_THRESHOLD = float(os.getenv("QUALITY_THRESHOLD", "7.0"))
MAX_QUALITY_RETRIES = int(os.getenv("MAX_QUALITY_RETRIES", "2"))

# --- Scoring Weights ---
RELEVANCE_WEIGHT = float(os.getenv("RELEVANCE_WEIGHT", "0.6"))
CITATION_WEIGHT = float(os.getenv("CITATION_WEIGHT", "0.2"))
RECENCY_WEIGHT = float(os.getenv("RECENCY_WEIGHT", "0.2"))

# --- General ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
