"""
Index builder — Downloads dataset, computes embeddings, and populates ChromaDB.

Usage:
    python scripts/build_index.py --file data/arxiv-metadata/arxiv-metadata-oai-snapshot.json \
                                  --categories cs.AI cs.CL cs.LG cs.CV \
                                  --year-min 2018 \
                                  --max-records 100000
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.indexing.dataset_loader import load_arxiv_metadata
from src.indexing.embedder import embed_texts
from src.indexing.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 512  # papers per embedding batch


def build_index(
    file_path: str,
    categories: list[str] | None = None,
    year_min: int | None = None,
    max_records: int | None = None,
    collection_name: str = "papers",
):
    """Build the ChromaDB index from an arXiv metadata file."""

    logger.info(f"Building index from: {file_path}")
    logger.info(f"Filters: categories={categories}, year_min={year_min}, max_records={max_records}")

    store = VectorStore(collection_name=collection_name)
    logger.info(f"Existing papers in index: {store.count()}")

    # Batch processing
    batch_ids = []
    batch_texts = []
    batch_metadatas = []
    total_indexed = 0

    for paper in load_arxiv_metadata(
        file_path=file_path,
        categories_filter=categories,
        year_min=year_min,
        max_records=max_records,
    ):
        paper_id = f"arxiv:{paper['id']}"
        text = f"{paper['title']}. {paper['abstract']}"

        batch_ids.append(paper_id)
        batch_texts.append(text)
        batch_metadatas.append({
            "title": paper["title"][:500],  # ChromaDB metadata value size limit
            "year": paper["year"] or 0,
            "categories": " ".join(paper["categories"]),
            "doi": paper.get("doi", ""),
            "authors": ", ".join(paper["authors"][:5]),
            "arxiv_id": paper["id"],
        })

        if len(batch_ids) >= BATCH_SIZE:
            _flush_batch(store, batch_ids, batch_texts, batch_metadatas)
            total_indexed += len(batch_ids)
            logger.info(f"Indexed {total_indexed} papers...")
            batch_ids, batch_texts, batch_metadatas = [], [], []

    # Flush remaining
    if batch_ids:
        _flush_batch(store, batch_ids, batch_texts, batch_metadatas)
        total_indexed += len(batch_ids)

    logger.info(f"✅ Index complete. Total papers: {store.count()}")


def _flush_batch(store: VectorStore, ids: list, texts: list, metadatas: list):
    """Embed a batch and insert into the vector store."""
    embeddings = embed_texts(texts, batch_size=len(texts))
    store.add_papers(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=metadatas,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build paper vector index from arXiv metadata.")
    parser.add_argument("--file", required=True, help="Path to arXiv metadata JSON lines file.")
    parser.add_argument("--categories", nargs="*", default=["cs.AI", "cs.CL", "cs.LG", "cs.CV"],
                        help="arXiv categories to include.")
    parser.add_argument("--year-min", type=int, default=2018, help="Minimum year filter.")
    parser.add_argument("--max-records", type=int, default=None, help="Max papers to index.")
    parser.add_argument("--collection", default="papers", help="ChromaDB collection name.")

    args = parser.parse_args()
    build_index(
        file_path=args.file,
        categories=args.categories,
        year_min=args.year_min,
        max_records=args.max_records,
        collection_name=args.collection,
    )
