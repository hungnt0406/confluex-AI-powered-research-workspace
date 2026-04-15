from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import Paper, Project, ReferenceFile, generate_identifier

PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
REFERENCE_SOURCE = "user_upload"
ABSTRACT_BOUNDARY_PATTERN = re.compile(
    r"\n\s*(?:keywords?|index terms|1\.?\s+introduction|introduction|background)\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"(19\d{2}|20\d{2})")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")
LINE_BREAK_PATTERN = re.compile(r"\n{3,}")


class ReferenceFileError(RuntimeError):
    """Base error for reference file handling."""


class ReferenceFileValidationError(ReferenceFileError):
    """Raised when an uploaded file is not acceptable."""


class ReferenceFileDuplicateError(ReferenceFileError):
    """Raised when a project already has the same reference file."""


@dataclass(frozen=True)
class ParsedReferenceMetadata:
    """Metadata extracted from a PDF reference file."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    text: str | None = None
    error_message: str | None = None

    @property
    def parse_status(self) -> str:
        return "parse_error" if self.error_message else "parsed"


def compute_sha256(content: bytes) -> str:
    """Return the hex SHA-256 digest for uploaded content."""

    return hashlib.sha256(content).hexdigest()


def format_file_size_limit(byte_count: int) -> str:
    """Return a compact human-readable upload limit."""

    mib = 1024 * 1024
    kib = 1024
    if byte_count > 0 and byte_count % mib == 0:
        return f"{byte_count // mib} MiB"
    if byte_count > 0 and byte_count % kib == 0:
        return f"{byte_count // kib} KiB"
    return f"{byte_count} bytes"


def validate_pdf_upload(
    *,
    filename: str,
    content_type: str | None,
    content: bytes,
    max_file_bytes: int,
) -> None:
    """Validate file type and size before storage."""

    if not filename.lower().endswith(".pdf"):
        raise ReferenceFileValidationError("Only PDF reference files are supported.")

    if content_type is not None and content_type not in PDF_CONTENT_TYPES:
        raise ReferenceFileValidationError("Only PDF reference files are supported.")

    if not content:
        raise ReferenceFileValidationError("Uploaded reference file is empty.")

    if len(content) > max_file_bytes:
        raise ReferenceFileValidationError(
            "Uploaded reference file exceeds the size limit. "
            f"Maximum allowed size is {format_file_size_limit(max_file_bytes)}."
        )

    if not content.lstrip().startswith(b"%PDF"):
        raise ReferenceFileValidationError("Uploaded reference file is not a valid PDF.")


def normalize_pdf_text(text: str, *, max_chars: int) -> str:
    """Normalize extracted PDF text while preserving section boundaries."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.split("\n")]
    normalized = "\n".join(line for line in normalized_lines if line)
    normalized = LINE_BREAK_PATTERN.sub("\n\n", normalized)
    return normalized[:max_chars].strip()


def split_authors(raw_author: str | None) -> list[str]:
    """Extract a conservative author list from PDF metadata."""

    if raw_author is None:
        return []

    candidates = re.split(r"\s*(?:;|\band\b)\s*", raw_author)
    authors = [candidate.strip() for candidate in candidates if candidate.strip()]
    return authors[:20]


def clean_metadata_value(value: object) -> str | None:
    """Return a non-empty metadata string."""

    if value is None:
        return None

    normalized = WHITESPACE_PATTERN.sub(" ", str(value)).strip()
    return normalized or None


def first_plausible_title_line(text: str) -> str | None:
    """Find a likely title line from extracted text."""

    for line in text.split("\n"):
        candidate = line.strip()
        if len(candidate) < 8 or len(candidate) > 180:
            continue
        lower_candidate = candidate.lower()
        if lower_candidate in {"abstract", "introduction", "keywords"}:
            continue
        if len(candidate.split()) < 2:
            continue
        return candidate

    return None


def extract_year(*values: str | None) -> int | None:
    """Extract the first plausible publication year from metadata or text."""

    for value in values:
        if not value:
            continue
        match = YEAR_PATTERN.search(value)
        if match is not None:
            return int(match.group(1))

    return None


def extract_abstract(text: str, *, max_chars: int = 2_000) -> str | None:
    """Extract an abstract section or fall back to a concise opening excerpt."""

    lower_text = text.lower()
    abstract_index = lower_text.find("abstract")
    if abstract_index != -1:
        start_index = abstract_index + len("abstract")
        candidate = text[start_index:]
        candidate = candidate.lstrip(" \n\t:-")
        boundary_match = ABSTRACT_BOUNDARY_PATTERN.search(candidate)
        if boundary_match is not None:
            candidate = candidate[: boundary_match.start()]
        candidate = candidate.strip()
        if candidate:
            return candidate[:max_chars].strip()

    compact_text = " ".join(text.split())
    if compact_text:
        return compact_text[:max_chars].strip()

    return None


def parse_pdf_metadata(path: Path, *, max_extracted_chars: int) -> ParsedReferenceMetadata:
    """Extract metadata and usable text from a PDF file."""

    try:
        import fitz
    except ImportError as error:
        raise ReferenceFileValidationError("PyMuPDF is required to parse PDF files.") from error

    try:
        with fitz.open(path) as document:
            metadata = document.metadata or {}
            raw_text_parts: list[str] = []
            extracted_chars = 0

            for page in document:
                page_text = page.get_text("text")
                if not page_text:
                    continue

                remaining_chars = max_extracted_chars - extracted_chars
                if remaining_chars <= 0:
                    break
                raw_text_parts.append(page_text[:remaining_chars])
                extracted_chars += min(len(page_text), remaining_chars)

            text = normalize_pdf_text("".join(raw_text_parts), max_chars=max_extracted_chars)
            if not text:
                return ParsedReferenceMetadata(
                    title=clean_metadata_value(metadata.get("title")) or path.stem,
                    authors=split_authors(clean_metadata_value(metadata.get("author"))),
                    year=extract_year(
                        clean_metadata_value(metadata.get("creationDate")),
                        clean_metadata_value(metadata.get("modDate")),
                    ),
                    error_message="No extractable text was found in the uploaded PDF.",
                )

            title = clean_metadata_value(metadata.get("title")) or first_plausible_title_line(text)
            if title is None:
                title = path.stem

            metadata_year = extract_year(
                clean_metadata_value(metadata.get("creationDate")),
                clean_metadata_value(metadata.get("modDate")),
            )
            year = metadata_year or extract_year(text)

            return ParsedReferenceMetadata(
                title=title[:500],
                authors=split_authors(clean_metadata_value(metadata.get("author"))),
                year=year,
                abstract=extract_abstract(text),
                text=text,
            )
    except ReferenceFileValidationError:
        raise
    except Exception as error:
        return ParsedReferenceMetadata(
            title=path.stem,
            error_message=f"PDF parsing failed: {error}",
        )


class ReferenceFileService:
    """Persist uploaded project reference PDFs and linked paper records."""

    def __init__(
        self,
        *,
        upload_dir: str | Path | None = None,
        max_file_bytes: int | None = None,
        max_extracted_chars: int | None = None,
    ) -> None:
        settings = get_settings()
        self.upload_dir = Path(upload_dir if upload_dir is not None else settings.reference_upload_dir)
        self.max_file_bytes = (
            max_file_bytes if max_file_bytes is not None else settings.reference_max_file_bytes
        )
        self.max_extracted_chars = (
            max_extracted_chars
            if max_extracted_chars is not None
            else settings.reference_max_extracted_chars
        )

    async def create_reference_file(
        self,
        *,
        session: AsyncSession,
        project: Project,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> ReferenceFile:
        """Validate, store, parse, and persist a project reference PDF."""

        safe_filename = Path(filename or "reference.pdf").name
        validate_pdf_upload(
            filename=safe_filename,
            content_type=content_type,
            content=content,
            max_file_bytes=self.max_file_bytes,
        )
        digest = compute_sha256(content)

        existing_reference = await session.execute(
            select(ReferenceFile).where(
                ReferenceFile.project_id == project.id,
                ReferenceFile.sha256 == digest,
            )
        )
        if existing_reference.scalar_one_or_none() is not None:
            raise ReferenceFileDuplicateError("This reference file has already been uploaded.")

        reference_id = generate_identifier()
        project_upload_dir = self.upload_dir / project.id
        project_upload_dir.mkdir(parents=True, exist_ok=True)
        storage_path = project_upload_dir / f"{reference_id}.pdf"
        storage_path.write_bytes(content)

        parsed = parse_pdf_metadata(storage_path, max_extracted_chars=self.max_extracted_chars)
        reference = ReferenceFile(
            id=reference_id,
            project_id=project.id,
            original_filename=safe_filename,
            content_type=content_type,
            byte_size=len(content),
            sha256=digest,
            storage_path=str(storage_path),
            parse_status=parsed.parse_status,
            extracted_title=parsed.title,
            extracted_authors=parsed.authors,
            extracted_year=parsed.year,
            extracted_abstract=parsed.abstract,
            extracted_text=parsed.text,
            error_message=parsed.error_message,
        )
        session.add(reference)

        if parsed.parse_status == "parsed":
            paper = Paper(
                project_id=project.id,
                title=parsed.title,
                authors=parsed.authors,
                year=parsed.year,
                abstract=parsed.abstract or parsed.text,
                doi=None,
                source=REFERENCE_SOURCE,
                reference_file_id=reference.id,
                source_paper_id=reference.id,
                source_url=None,
                pdf_url=str(storage_path),
                status="candidate",
                relevance_score=None,
            )
            reference.paper = paper
            session.add(paper)

        await session.commit()
        await session.refresh(reference)
        return reference
