"""
ChromaDB vector store wrapper for paper metadata indexing.
"""

import logging
from typing import Optional
import chromadb
from chromadb.config import Settings

from src.config import CHROMA_PERSIST_DIR

logger = logging.getLogger(__name__)


class VectorStore:
    """Wrapper around ChromaDB for paper embedding storage and retrieval."""

    def __init__(
        self,
        collection_name: str = "papers",
        persist_dir: Optional[str] = None,
    ):
        self.persist_dir = persist_dir or CHROMA_PERSIST_DIR
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"VectorStore initialized: collection='{collection_name}', "
            f"count={self.collection.count()}, persist_dir='{self.persist_dir}'"
        )

    def add_papers(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ):
        """Add papers to the vector store.

        Args:
            ids: Unique paper identifiers (e.g., arxiv_id or DOI).
            embeddings: Pre-computed embedding vectors.
            documents: Text content (title + abstract).
            metadatas: Metadata dicts (title, year, categories, etc.).
        """
        # ChromaDB handles batching internally, but we chunk for large inserts
        batch_size = 5000
        for i in range(0, len(ids), batch_size):
            end = min(i + batch_size, len(ids))
            self.collection.upsert(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                documents=documents[i:end],
                metadatas=metadatas[i:end],
            )
        logger.info(f"Added/updated {len(ids)} papers. Total: {self.collection.count()}")

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 50,
        where: Optional[dict] = None,
        where_document: Optional[dict] = None,
    ) -> dict:
        """Search for similar papers.

        Args:
            query_embedding: The query vector.
            n_results: Number of results to return.
            where: Metadata filter (e.g., {"year": {"$gte": 2020}}).
            where_document: Document content filter.

        Returns:
            ChromaDB query results dict with ids, distances, metadatas, documents.
        """
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where
        if where_document:
            kwargs["where_document"] = where_document

        return self.collection.query(**kwargs)

    def count(self) -> int:
        """Return total number of papers in the store."""
        return self.collection.count()

    def get_by_ids(self, ids: list[str]) -> dict:
        """Retrieve papers by their IDs."""
        return self.collection.get(ids=ids, include=["embeddings", "metadatas", "documents"])

    def delete_collection(self):
        """Delete the entire collection. Use with caution."""
        self.client.delete_collection(self.collection.name)
        logger.warning(f"Collection '{self.collection.name}' deleted.")
