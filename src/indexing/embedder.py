"""
Embedding wrapper for SPECTER2 / all-MiniLM-L6-v2.
Handles model loading and batch encoding.
"""

import logging
from functools import lru_cache
import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    """Load embedding model (cached — only loaded once)."""
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    logger.info(f"Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")
    return model


def embed_texts(texts: list[str], batch_size: int = 64, show_progress: bool = False) -> np.ndarray:
    """Encode a list of texts into embeddings.

    Args:
        texts: List of strings to embed.
        batch_size: Batch size for encoding.
        show_progress: Show progress bar.

    Returns:
        np.ndarray of shape (len(texts), embedding_dim).
    """
    model = _load_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        normalize_embeddings=True,  # L2 normalize for cosine similarity via dot product
    )
    return embeddings


def embed_single(text: str) -> np.ndarray:
    """Encode a single text into an embedding vector.

    Returns:
        np.ndarray of shape (embedding_dim,).
    """
    return embed_texts([text])[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.
    If vectors are already L2-normalized, this is just dot product."""
    return float(np.dot(a, b))


def batch_cosine_similarity(query: np.ndarray, corpus: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between a query and all corpus vectors.

    Args:
        query: Shape (embedding_dim,)
        corpus: Shape (n, embedding_dim)

    Returns:
        np.ndarray of shape (n,) with similarity scores.
    """
    return np.dot(corpus, query)
