"""
Dataset loader for arXiv metadata from Kaggle / HuggingFace.
Parses JSON lines and prepares data for embedding + indexing.
"""

import json
import logging
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


def load_arxiv_metadata(
    file_path: str,
    categories_filter: Optional[list[str]] = None,
    year_min: Optional[int] = None,
    max_records: Optional[int] = None,
) -> Iterator[dict]:
    """Load arXiv metadata JSON lines file with optional filtering.

    The Kaggle arxiv dataset (Cornell-University/arxiv) is a single JSON lines file
    where each line is a JSON object with fields:
        id, submitter, authors, title, comments, journal-ref, doi,
        report-no, categories, license, abstract, versions, update_date, authors_parsed

    Args:
        file_path: Path to the JSON lines file.
        categories_filter: Only include papers with at least one matching category.
                          e.g., ["cs.AI", "cs.CL", "cs.LG"]
        year_min: Only include papers updated on or after this year.
        max_records: Maximum number of records to yield.

    Yields:
        Parsed paper dicts with normalized fields:
        {id, title, abstract, authors, categories, year, doi}
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset file not found: {file_path}\n"
            f"Download from: https://www.kaggle.com/datasets/Cornell-University/arxiv"
        )

    count = 0
    skipped = 0

    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if max_records and count >= max_records:
                break

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            # Extract year from update_date (format: "YYYY-MM-DD" or "YYYY-MM")
            update_date = record.get("update_date", "")
            year = None
            if update_date:
                try:
                    year = int(update_date[:4])
                except (ValueError, IndexError):
                    pass

            # Year filter
            if year_min and (year is None or year < year_min):
                skipped += 1
                continue

            # Category filter
            paper_categories = record.get("categories", "").split()
            if categories_filter:
                if not any(cat in paper_categories for cat in categories_filter):
                    skipped += 1
                    continue

            # Normalize output
            title = record.get("title", "").replace("\n", " ").strip()
            abstract = record.get("abstract", "").replace("\n", " ").strip()

            if not title or not abstract:
                skipped += 1
                continue

            # Parse authors
            authors_parsed = record.get("authors_parsed", [])
            authors = []
            for author in authors_parsed[:10]:  # cap at 10 authors
                if isinstance(author, list) and len(author) >= 2:
                    authors.append(f"{author[1]} {author[0]}".strip())

            yield {
                "id": record.get("id", ""),
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": paper_categories,
                "year": year,
                "doi": record.get("doi", ""),
            }
            count += 1

            if count % 10000 == 0:
                logger.info(f"Loaded {count} papers (skipped {skipped})...")

    logger.info(f"Done. Loaded {count} papers total (skipped {skipped}).")
