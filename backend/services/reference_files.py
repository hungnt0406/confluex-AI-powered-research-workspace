from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import Paper, Project, ReferenceFile, generate_identifier
from backend.services.document_extraction import (
    DocumentExtractionError,
    ExtractedDocument,
    PaperDocumentExtractionService,
)

PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
REFERENCE_SOURCE = "user_upload"
ABSTRACT_BOUNDARY_PATTERN = re.compile(
    r"\n\s*(?:keywords?|index terms|1\.?\s+introduction|introduction|background)\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"(19\d{2}|20\d{2})")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")
LINE_BREAK_PATTERN = re.compile(r"\n{3,}")
AUTHOR_SEPARATOR_PATTERN = re.compile(r"\s+(?:and|&)\s+|[,;]")
AUTHOR_NOTE_MARKER_PATTERN = re.compile(r"[\*∗†‡§¶#¹²³⁰¹²³⁴⁵⁶⁷⁸⁹]|\b\d+\b")
NON_AUTHOR_HEADER_PATTERN = re.compile(
    r"(@|[{}]|\b("
    r"university|institute|department|school|college|laborator(?:y|ies)|academy|faculty|"
    r"center|centre|foundation|conference|proceedings|copyright|rights reserved|email"
    r")\b)",
    re.IGNORECASE,
)
AUTHOR_SECTION_BOUNDARY_WORDS = {
    "abstract",
    "introduction",
    "keywords",
    "index terms",
    "background",
}


class ReferenceFileError(RuntimeError):
    """Base error for reference file handling."""


class ReferenceFileValidationError(ReferenceFileError):
    """Raised when an uploaded file is not acceptable."""


class ReferenceFileDuplicateError(ReferenceFileError):
    """Raised when a project already has the same reference file."""


class ReferenceExtractionClient(Protocol):
    """Minimal document extraction interface for uploaded reference PDFs."""

    async def extract_uploaded_pdf(self, *, pdf_bytes: bytes, filename: str) -> ExtractedDocument:
        """Extract a local uploaded PDF into normalized text blocks."""


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


def validate_pdf_upload(
    *,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> None:
    """Validate that an upload is a non-empty PDF before storage."""

    if not filename.lower().endswith(".pdf"):
        raise ReferenceFileValidationError("Only PDF reference files are supported.")

    if content_type is not None and content_type not in PDF_CONTENT_TYPES:
        raise ReferenceFileValidationError("Only PDF reference files are supported.")

    if not content:
        raise ReferenceFileValidationError("Uploaded reference file is empty.")

    if not content.lstrip().startswith(b"%PDF"):
        raise ReferenceFileValidationError("Uploaded reference file is not a valid PDF.")


def normalize_pdf_text(text: str, *, max_chars: int) -> str:
    """Normalize extracted PDF text while preserving section boundaries."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.split("\n")]
    normalized = "\n".join(line for line in normalized_lines if line)
    normalized = LINE_BREAK_PATTERN.sub("\n\n", normalized)
    return normalized[:max_chars].strip()


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


def extract_authors_from_header(text: str, *, title: str) -> list[str]:
    """Infer simple author lines between the title and affiliation/abstract header."""

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    title_index = next((index for index, line in enumerate(lines) if line == title), None)
    if title_index is None:
        return []

    authors: list[str] = []
    seen_authors: set[str] = set()
    for line in lines[title_index + 1 : title_index + 9]:
        normalized_line = line.strip(" :-").lower()
        if normalized_line in AUTHOR_SECTION_BOUNDARY_WORDS:
            break
        if NON_AUTHOR_HEADER_PATTERN.search(line):
            break

        for author in split_author_line(line):
            author_key = author.casefold()
            if author_key in seen_authors:
                continue
            seen_authors.add(author_key)
            authors.append(author)

    return authors


def split_author_line(line: str) -> list[str]:
    """Split a first-page author line into cleaned author names."""

    authors: list[str] = []
    for raw_part in AUTHOR_SEPARATOR_PATTERN.split(line):
        candidate = AUTHOR_NOTE_MARKER_PATTERN.sub("", raw_part)
        candidate = WHITESPACE_PATTERN.sub(" ", candidate).strip(" .,:;")
        if not candidate:
            continue
        if any(character.isdigit() for character in candidate):
            continue
        if NON_AUTHOR_HEADER_PATTERN.search(candidate):
            continue
        if not 2 <= len(candidate.split()) <= 6:
            continue
        if len(candidate) > 80:
            continue
        authors.append(candidate)

    return authors


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


def metadata_from_extracted_document(
    document: ExtractedDocument,
    *,
    fallback_title: str,
    max_extracted_chars: int,
) -> ParsedReferenceMetadata:
    """Derive reference metadata from the shared document extraction output."""

    text = normalize_pdf_text(
        "\n\n".join(block.text for block in document.blocks),
        max_chars=max_extracted_chars,
    )
    if not text:
        return ParsedReferenceMetadata(
            title=fallback_title,
            error_message="No extractable text was found in the uploaded PDF.",
        )

    title = first_plausible_title_line(text) or fallback_title
    return ParsedReferenceMetadata(
        title=title[:500],
        authors=extract_authors_from_header(text, title=title),
        year=extract_year(text),
        abstract=extract_abstract(text),
        text=text,
    )


class ReferenceFileService:
    """Persist uploaded project reference PDFs and linked paper records."""

    def __init__(
        self,
        *,
        upload_dir: str | Path | None = None,
        max_extracted_chars: int | None = None,
        extraction_service: ReferenceExtractionClient | None = None,
    ) -> None:
        settings = get_settings()
        self.upload_dir = Path(upload_dir if upload_dir is not None else settings.reference_upload_dir)
        self.max_extracted_chars = (
            max_extracted_chars
            if max_extracted_chars is not None
            else settings.reference_max_extracted_chars
        )
        self.extraction_service = extraction_service or PaperDocumentExtractionService()

    async def create_reference_file(
        self,
        *,
        session: AsyncSession,
        project: Project | None = None,
        user_id: str | None = None,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> ReferenceFile:
        """Validate, store, parse, and persist a project or writer reference PDF."""

        effective_user_id = project.user_id if project is not None else user_id
        if effective_user_id is None:
            raise ReferenceFileValidationError("Reference files require a user or project owner.")

        safe_filename = Path(filename or "reference.pdf").name
        validate_pdf_upload(
            filename=safe_filename,
            content_type=content_type,
            content=content,
        )
        digest = compute_sha256(content)

        existing_reference = await session.execute(
            select(ReferenceFile).where(
                ReferenceFile.project_id == (project.id if project is not None else None),
                ReferenceFile.user_id == effective_user_id,
                ReferenceFile.sha256 == digest,
            )
        )
        if existing_reference.scalar_one_or_none() is not None:
            raise ReferenceFileDuplicateError("This reference file has already been uploaded.")

        reference_id = generate_identifier()
        owner_dir = project.id if project is not None else f"writer-{effective_user_id}"
        upload_dir = self.upload_dir / owner_dir
        upload_dir.mkdir(parents=True, exist_ok=True)
        storage_path = upload_dir / f"{reference_id}.pdf"
        storage_path.write_bytes(content)

        fallback_title = Path(safe_filename).stem or "reference"
        try:
            extracted_document = await self.extraction_service.extract_uploaded_pdf(
                pdf_bytes=content,
                filename=safe_filename,
            )
            parsed = metadata_from_extracted_document(
                extracted_document,
                fallback_title=fallback_title,
                max_extracted_chars=self.max_extracted_chars,
            )
        except DocumentExtractionError as error:
            parsed = ParsedReferenceMetadata(
                title=fallback_title,
                error_message=f"PDF extraction failed: {error}",
            )

        reference = ReferenceFile(
            id=reference_id,
            user_id=effective_user_id,
            project_id=project.id if project is not None else None,
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
                user_id=effective_user_id,
                project_id=project.id if project is not None else None,
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
