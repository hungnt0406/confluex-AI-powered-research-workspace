from __future__ import annotations

import base64
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import Paper, PaperChunk, PaperDocument
from backend.services.ai_usage import collect_openrouter_usage
from backend.services.embeddings import EmbeddingService
from backend.services.research_utils import has_live_api_key

DEFAULT_EXTRACTION_PROMPT = (
    "Parse this PDF for downstream retrieval. "
    "Do not summarize it. Reply with a short acknowledgement only."
)
NATIVE_PDF_ENGINE = "native"
FALLBACK_PDF_ENGINE = "cloudflare-ai"
MAX_EXTRACTION_RESPONSE_TOKENS = 64
MAX_SECTION_TITLE_CHARS = 255
HEADING_NUMBER_PATTERN = re.compile(r"^\d+(?:\.\d+)*\s+[A-Za-z]")
HEADING_WHITESPACE_PATTERN = re.compile(r"\s+")
HYPHENATED_LINE_BREAK_PATTERN = re.compile(r"(?<=\w)-\n(?=\w)")
REPEATED_NEWLINE_PATTERN = re.compile(r"\n{3,}")
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+")


class DocumentExtractionError(RuntimeError):
    """Raised when a paper PDF could not be converted into retrievable chunks."""


class EmbeddingClient(Protocol):
    """Minimal protocol used by the document extraction service."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed text payloads for retrieval."""


async def embed_texts_with_feature(
    embedding_service: EmbeddingClient,
    texts: list[str],
    *,
    feature: str,
) -> list[list[float]]:
    """Pass feature names to the concrete OpenRouter embedding client when supported."""

    try:
        return await embedding_service.embed_texts(texts, feature=feature)  # type: ignore[call-arg]
    except TypeError as error:
        if "unexpected keyword" not in str(error):
            raise
        return await embedding_service.embed_texts(texts)


@dataclass(frozen=True)
class DocumentTextBlock:
    """Normalized block of PDF text with a coarse page location."""

    page_number: int
    text: str
    section_title: str | None = None


@dataclass(frozen=True)
class ChunkDraft:
    """Prepared chunk payload before persistence."""

    chunk_index: int
    page_start: int
    page_end: int
    section_title: str | None
    content: str


@dataclass(frozen=True)
class OpenRouterExtractionResult:
    """Parsed OpenRouter response details used for traceability and fallback text."""

    file_hash: str | None
    parsed_text: str | None


@dataclass(frozen=True)
class ExtractedDocument:
    """Final extracted document content ready for chunking and persistence."""

    blocks: list[DocumentTextBlock]
    page_count: int
    file_hash: str | None


class PaperDocumentExtractionService:
    """Extract paper PDFs into persistent retrieval chunks."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        pdf_engine: str | None = None,
        pdf_download_timeout_seconds: float | None = None,
        paper_chunk_size_chars: int | None = None,
        local_pdf_roots: Sequence[str | Path] | None = None,
        http_client: httpx.AsyncClient | None = None,
        embedding_service: EmbeddingClient | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.model = model if model is not None else settings.openrouter_document_model
        self.base_url = (
            base_url.rstrip("/") if base_url is not None else settings.openrouter_base_url.rstrip("/")
        )
        self.pdf_engine = pdf_engine if pdf_engine is not None else settings.openrouter_pdf_engine
        self.pdf_download_timeout_seconds = (
            pdf_download_timeout_seconds
            if pdf_download_timeout_seconds is not None
            else settings.pdf_download_timeout_seconds
        )
        self.paper_chunk_size_chars = (
            paper_chunk_size_chars
            if paper_chunk_size_chars is not None
            else settings.paper_chunk_size_chars
        )
        configured_local_pdf_roots = (
            tuple(local_pdf_roots)
            if local_pdf_roots is not None
            else (settings.reference_upload_dir,)
        )
        self.local_pdf_roots = tuple(
            Path(root).expanduser().resolve() for root in configured_local_pdf_roots
        )
        self.http_client = http_client
        self.embedding_service = embedding_service or EmbeddingService()
        self.timeout_seconds = settings.external_api_timeout_seconds

    def is_configured(self) -> bool:
        """Return whether live OpenRouter document extraction is available."""

        return has_live_api_key(self.api_key)

    async def ensure_document_chunks(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
    ) -> PaperDocument:
        """Ensure a paper has extracted document chunks persisted for retrieval."""

        paper_id = paper.id
        pdf_url = (paper.pdf_url or "").strip()
        if not pdf_url:
            raise DocumentExtractionError("Paper does not have a PDF source.")

        filename = self._guess_filename(paper=paper)
        document = await self._get_or_create_document(
            session=session,
            paper_id=paper_id,
            source_pdf_url=pdf_url,
        )
        if await self._has_ready_chunks(
            session=session,
            paper_id=paper_id,
            document=document,
            source_pdf_url=pdf_url,
        ):
            return document

        document.status = "pending"
        document.source_pdf_url = pdf_url
        document.error_message = None
        await session.flush()

        try:
            async with session.begin_nested():
                extracted_document = await self._extract_pdf_source(
                    pdf_source=pdf_url,
                    filename=filename,
                )
                chunk_drafts = self._chunk_blocks(
                    extracted_document.blocks,
                    max_chunk_chars=self.paper_chunk_size_chars,
                )
                if not chunk_drafts:
                    raise DocumentExtractionError("No retrievable chunks were produced from the PDF.")

                embeddings = await embed_texts_with_feature(
                    self.embedding_service,
                    [chunk_draft.content for chunk_draft in chunk_drafts],
                    feature="document_chunk_embedding",
                )
                if len(embeddings) != len(chunk_drafts):
                    raise DocumentExtractionError(
                        "Embedding service returned an unexpected number of vectors."
                    )

                await session.execute(delete(PaperChunk).where(PaperChunk.paper_id == paper_id))
                for chunk_draft, embedding in zip(chunk_drafts, embeddings, strict=True):
                    session.add(
                        PaperChunk(
                            paper_id=paper_id,
                            chunk_index=chunk_draft.chunk_index,
                            page_start=chunk_draft.page_start,
                            page_end=chunk_draft.page_end,
                            section_title=chunk_draft.section_title,
                            content=chunk_draft.content,
                            embedding_json=[float(value) for value in embedding],
                        )
                    )

                document.status = "ready"
                document.openrouter_file_hash = extracted_document.file_hash
                document.page_count = extracted_document.page_count
                document.error_message = None
                document.extracted_at = datetime.now(UTC)
                await session.flush()
            return document
        except Exception as error:
            failure_message = str(error)
            document = await self._get_or_create_document(
                session=session,
                paper_id=paper_id,
                source_pdf_url=pdf_url,
            )
            await session.execute(delete(PaperChunk).where(PaperChunk.paper_id == paper_id))
            document.status = "failed"
            document.source_pdf_url = pdf_url
            document.openrouter_file_hash = None
            document.page_count = None
            document.error_message = failure_message
            document.extracted_at = datetime.now(UTC)
            await session.flush()
            if isinstance(error, DocumentExtractionError):
                raise
            raise DocumentExtractionError("Paper document extraction failed.") from error

    async def _extract_pdf_source(
        self,
        *,
        pdf_source: str,
        filename: str,
    ) -> ExtractedDocument:
        local_pdf_path = self._resolve_local_pdf_path(pdf_source)
        if local_pdf_path is not None:
            try:
                pdf_bytes = local_pdf_path.read_bytes()
            except OSError as error:
                raise DocumentExtractionError(
                    f"Local PDF file could not be read: {local_pdf_path}"
                ) from error

            return await self.extract_uploaded_pdf(pdf_bytes=pdf_bytes, filename=filename)

        return await self._extract_document(pdf_url=pdf_source, filename=filename)

    async def _has_ready_chunks(
        self,
        *,
        session: AsyncSession,
        paper_id: str,
        document: PaperDocument,
        source_pdf_url: str,
    ) -> bool:
        if document.status != "ready" or document.source_pdf_url != source_pdf_url:
            return False

        result = await session.execute(
            select(PaperChunk.id).where(PaperChunk.paper_id == paper_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_or_create_document(
        self,
        *,
        session: AsyncSession,
        paper_id: str,
        source_pdf_url: str,
    ) -> PaperDocument:
        result = await session.execute(
            select(PaperDocument).where(PaperDocument.paper_id == paper_id)
        )
        document = result.scalar_one_or_none()
        if document is not None:
            if document.source_pdf_url != source_pdf_url:
                document.source_pdf_url = source_pdf_url
            return document

        document = PaperDocument(
            paper_id=paper_id,
            status="pending",
            source_pdf_url=source_pdf_url,
        )
        session.add(document)
        await session.flush()
        return document

    async def _extract_document(self, *, pdf_url: str, filename: str) -> ExtractedDocument:
        openrouter_result: OpenRouterExtractionResult | None = None
        extraction_errors: list[str] = []

        if self.is_configured():
            try:
                openrouter_result = await self._extract_with_openrouter(
                    pdf_url=pdf_url,
                    filename=filename,
                )
            except DocumentExtractionError as error:
                extraction_errors.append(str(error))

        try:
            pdf_bytes = await self._download_pdf(pdf_url)
            blocks, page_count = self._extract_blocks_from_pdf_bytes(pdf_bytes)
            if blocks:
                return ExtractedDocument(
                    blocks=blocks,
                    page_count=page_count,
                    file_hash=None if openrouter_result is None else openrouter_result.file_hash,
                )
            extraction_errors.append("Downloaded PDF did not contain extractable text.")
        except DocumentExtractionError as error:
            extraction_errors.append(str(error))

        if openrouter_result is not None and openrouter_result.parsed_text:
            blocks = self._build_blocks_from_text(openrouter_result.parsed_text, page_number=1)
            if blocks:
                return ExtractedDocument(
                    blocks=blocks,
                    page_count=1,
                    file_hash=openrouter_result.file_hash,
                )
            extraction_errors.append("OpenRouter returned PDF content, but it could not be normalized.")

        if extraction_errors:
            error_message = "; ".join(extraction_errors)
        else:
            error_message = "No usable PDF content was extracted."

        raise DocumentExtractionError(error_message)

    def _resolve_local_pdf_path(self, pdf_url: str) -> Path | None:
        parsed_url = urlparse(pdf_url)
        if parsed_url.scheme in {"http", "https", "data"}:
            return None

        if parsed_url.scheme == "file":
            path_text = unquote(parsed_url.path)
            if parsed_url.netloc and parsed_url.netloc != "localhost":
                path_text = f"//{parsed_url.netloc}{path_text}"
            return self._ensure_allowed_local_pdf_path(Path(path_text).expanduser())

        if not parsed_url.scheme or len(parsed_url.scheme) == 1:
            return self._ensure_allowed_local_pdf_path(Path(pdf_url).expanduser())

        return None

    def _ensure_allowed_local_pdf_path(self, path: Path) -> Path:
        resolved_path = path.resolve()
        if any(
            resolved_path == local_root or local_root in resolved_path.parents
            for local_root in self.local_pdf_roots
        ):
            return resolved_path
        raise DocumentExtractionError("Local PDF source is outside the allowed upload directory.")

    async def extract_uploaded_pdf(self, *, pdf_bytes: bytes, filename: str) -> ExtractedDocument:
        """Extract an uploaded local PDF through the same OpenRouter parser pipeline."""

        if not pdf_bytes:
            raise DocumentExtractionError("Uploaded PDF was empty.")

        extraction_errors: list[str] = []
        if self.is_configured():
            try:
                openrouter_result = await self._extract_with_openrouter(
                    pdf_url=self._build_pdf_data_url(pdf_bytes),
                    filename=filename,
                )
                normalized_text = self._normalize_text(openrouter_result.parsed_text)
                if normalized_text:
                    return ExtractedDocument(
                        blocks=[
                            DocumentTextBlock(
                                page_number=1,
                                text=normalized_text,
                            )
                        ],
                        page_count=1,
                        file_hash=openrouter_result.file_hash,
                    )
                extraction_errors.append(
                    "OpenRouter returned PDF content, but it could not be normalized."
                )
            except DocumentExtractionError as error:
                extraction_errors.append(str(error))

        try:
            blocks, page_count = self._extract_blocks_from_pdf_bytes(pdf_bytes)
            if blocks:
                return ExtractedDocument(blocks=blocks, page_count=page_count, file_hash=None)
            extraction_errors.append("Uploaded PDF did not contain extractable text.")
        except DocumentExtractionError as error:
            extraction_errors.append(str(error))

        raise DocumentExtractionError("; ".join(extraction_errors))

    async def _extract_with_openrouter(
        self,
        *,
        pdf_url: str,
        filename: str,
    ) -> OpenRouterExtractionResult:
        configured_engine = (self.pdf_engine or NATIVE_PDF_ENGINE).strip() or NATIVE_PDF_ENGINE
        engines = [configured_engine]
        if configured_engine == NATIVE_PDF_ENGINE:
            engines.append(FALLBACK_PDF_ENGINE)

        errors: list[str] = []
        for engine in engines:
            try:
                return await self._request_openrouter_document(
                    pdf_url=pdf_url,
                    filename=filename,
                    engine=engine,
                )
            except DocumentExtractionError as error:
                errors.append(str(error))

        raise DocumentExtractionError("; ".join(errors))

    async def _request_openrouter_document(
        self,
        *,
        pdf_url: str,
        filename: str,
        engine: str,
    ) -> OpenRouterExtractionResult:
        if not self.is_configured():
            raise DocumentExtractionError("OpenRouter API credentials are not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DEFAULT_EXTRACTION_PROMPT},
                        {
                            "type": "file",
                            "file": {
                                "filename": filename,
                                "file_data": pdf_url,
                            },
                        },
                    ],
                }
            ],
            "plugins": [
                {
                    "id": "file-parser",
                    "pdf": {"engine": engine},
                }
            ],
            "max_tokens": MAX_EXTRACTION_RESPONSE_TOKENS,
            "temperature": 0,
            "provider": {
                "sort": "price",
                "require_parameters": True,
            },
        }

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)

        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = error.response.text.strip()
            raise DocumentExtractionError(
                f"OpenRouter PDF extraction with engine '{engine}' failed "
                f"with status {error.response.status_code}: {detail or 'no detail returned'}"
            ) from error
        except httpx.HTTPError as error:
            raise DocumentExtractionError(
                f"OpenRouter PDF extraction with engine '{engine}' failed."
            ) from error
        finally:
            if owns_client:
                await client.aclose()

        response_payload = response.json()
        collect_openrouter_usage(
            endpoint="chat/completions",
            feature="pdf_extraction",
            model=self.model,
            response_payload=response_payload,
            metadata={"pdf_engine": engine},
        )
        choices = response_payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise DocumentExtractionError(
                f"OpenRouter PDF extraction with engine '{engine}' returned no choices."
            )

        choice = choices[0]
        if not isinstance(choice, dict):
            raise DocumentExtractionError(
                f"OpenRouter PDF extraction with engine '{engine}' returned an invalid choice."
            )

        message = choice.get("message")
        if not isinstance(message, dict):
            raise DocumentExtractionError(
                f"OpenRouter PDF extraction with engine '{engine}' returned no message."
            )

        annotations = message.get("annotations")
        parsed_text = self._extract_text_from_annotations(annotations)
        if parsed_text is None:
            parsed_text = self._extract_text_from_message_content(message.get("content"))

        if parsed_text is None:
            raise DocumentExtractionError(
                f"OpenRouter PDF extraction with engine '{engine}' returned no parsed content."
            )

        return OpenRouterExtractionResult(
            file_hash=self._extract_file_hash(annotations),
            parsed_text=parsed_text,
        )

    async def _download_pdf(self, pdf_url: str) -> bytes:
        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)

        try:
            response = await client.get(
                pdf_url,
                follow_redirects=True,
                timeout=self.pdf_download_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise DocumentExtractionError("Public PDF download failed.") from error
        finally:
            if owns_client:
                await client.aclose()

        content = response.content
        if not content:
            raise DocumentExtractionError("Downloaded PDF was empty.")

        return content

    def _extract_blocks_from_pdf_bytes(self, pdf_bytes: bytes) -> tuple[list[DocumentTextBlock], int]:
        try:
            import fitz
        except ImportError as error:
            raise DocumentExtractionError("PyMuPDF is required to parse PDFs.") from error

        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
                blocks: list[DocumentTextBlock] = []
                current_section_title: str | None = None
                page_count = document.page_count

                for page_number, page in enumerate(document, start=1):
                    page_text = page.get_text("text")
                    normalized_page_text = self._normalize_text(page_text)
                    if not normalized_page_text:
                        continue

                    page_blocks, current_section_title = self._build_page_blocks(
                        normalized_page_text,
                        page_number=page_number,
                        current_section_title=current_section_title,
                    )
                    blocks.extend(page_blocks)

                return blocks, page_count
        except Exception as error:
            raise DocumentExtractionError("Downloaded PDF could not be parsed.") from error

    def _build_page_blocks(
        self,
        page_text: str,
        *,
        page_number: int,
        current_section_title: str | None,
    ) -> tuple[list[DocumentTextBlock], str | None]:
        blocks: list[DocumentTextBlock] = []

        for paragraph in self._split_into_paragraphs(page_text):
            if self._looks_like_heading(paragraph):
                current_section_title = paragraph[:MAX_SECTION_TITLE_CHARS]
                continue

            blocks.append(
                DocumentTextBlock(
                    page_number=page_number,
                    text=paragraph,
                    section_title=current_section_title,
                )
            )

        return blocks, current_section_title

    def _build_blocks_from_text(self, text: str, *, page_number: int) -> list[DocumentTextBlock]:
        normalized_text = self._normalize_text(text)
        if not normalized_text:
            return []

        blocks: list[DocumentTextBlock] = []
        current_section_title: str | None = None
        for paragraph in self._split_into_paragraphs(normalized_text):
            if self._looks_like_heading(paragraph):
                current_section_title = paragraph[:MAX_SECTION_TITLE_CHARS]
                continue

            blocks.append(
                DocumentTextBlock(
                    page_number=page_number,
                    text=paragraph,
                    section_title=current_section_title,
                )
            )

        return blocks

    def _chunk_blocks(
        self,
        blocks: list[DocumentTextBlock],
        *,
        max_chunk_chars: int,
    ) -> list[ChunkDraft]:
        if max_chunk_chars <= 0:
            raise DocumentExtractionError("Chunk size must be greater than zero.")

        normalized_blocks: list[DocumentTextBlock] = []
        for block in blocks:
            split_segments = self._split_long_text(block.text, max_chunk_chars)
            normalized_blocks.extend(
                DocumentTextBlock(
                    page_number=block.page_number,
                    text=segment,
                    section_title=block.section_title,
                )
                for segment in split_segments
            )

        chunk_drafts: list[ChunkDraft] = []
        current_text_parts: list[str] = []
        current_page_start: int | None = None
        current_page_end: int | None = None
        current_section_title: str | None = None

        def flush_current_chunk() -> None:
            nonlocal current_text_parts, current_page_start, current_page_end, current_section_title
            if not current_text_parts or current_page_start is None or current_page_end is None:
                return
            chunk_drafts.append(
                ChunkDraft(
                    chunk_index=len(chunk_drafts),
                    page_start=current_page_start,
                    page_end=current_page_end,
                    section_title=current_section_title,
                    content="\n\n".join(current_text_parts),
                )
            )
            current_text_parts = []
            current_page_start = None
            current_page_end = None
            current_section_title = None

        for block in normalized_blocks:
            proposed_parts = [*current_text_parts, block.text]
            proposed_content = "\n\n".join(proposed_parts)
            if current_text_parts and len(proposed_content) > max_chunk_chars:
                flush_current_chunk()

            if current_page_start is None:
                current_page_start = block.page_number
            current_page_end = block.page_number
            if current_section_title is None and block.section_title is not None:
                current_section_title = block.section_title
            current_text_parts.append(block.text)

        flush_current_chunk()
        return chunk_drafts

    def _split_long_text(self, text: str, max_chunk_chars: int) -> list[str]:
        if len(text) <= max_chunk_chars:
            return [text]

        sentences = SENTENCE_BOUNDARY_PATTERN.split(text)
        if len(sentences) <= 1:
            return self._split_hard(text, max_chunk_chars)

        chunks: list[str] = []
        current_chunk = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) > max_chunk_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                chunks.extend(self._split_hard(sentence, max_chunk_chars))
                continue

            proposed_chunk = sentence if not current_chunk else f"{current_chunk} {sentence}"
            if current_chunk and len(proposed_chunk) > max_chunk_chars:
                chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk = proposed_chunk

        if current_chunk:
            chunks.append(current_chunk)

        return chunks or self._split_hard(text, max_chunk_chars)

    def _split_hard(self, text: str, max_chunk_chars: int) -> list[str]:
        words = text.split()
        if not words:
            return []

        segments: list[str] = []
        current_segment = ""
        for word in words:
            if len(word) > max_chunk_chars:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = ""
                segments.extend(
                    word[index : index + max_chunk_chars]
                    for index in range(0, len(word), max_chunk_chars)
                )
                continue

            proposed_segment = word if not current_segment else f"{current_segment} {word}"
            if current_segment and len(proposed_segment) > max_chunk_chars:
                segments.append(current_segment)
                current_segment = word
            else:
                current_segment = proposed_segment

        if current_segment:
            segments.append(current_segment)

        return segments

    def _extract_text_from_annotations(self, annotations: Any) -> str | None:
        if not isinstance(annotations, list):
            return None

        content_parts: list[str] = []
        for annotation in annotations:
            if not isinstance(annotation, dict) or annotation.get("type") != "file":
                continue

            file_payload = annotation.get("file")
            if not isinstance(file_payload, dict):
                continue

            for content_part in file_payload.get("content", []):
                if not isinstance(content_part, dict):
                    continue
                if content_part.get("type") != "text":
                    continue
                text = content_part.get("text")
                if isinstance(text, str) and text.strip():
                    content_parts.append(text)

        if not content_parts:
            return None

        normalized = self._normalize_text("\n\n".join(content_parts))
        return normalized or None

    def _extract_text_from_message_content(self, content: Any) -> str | None:
        if isinstance(content, str):
            normalized = self._normalize_text(content)
            if len(normalized) < 200:
                return None
            return normalized

        if not isinstance(content, list):
            return None

        text_parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") != "text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text)

        if not text_parts:
            return None

        normalized = self._normalize_text("\n\n".join(text_parts))
        if len(normalized) < 200:
            return None
        return normalized

    def _extract_file_hash(self, annotations: Any) -> str | None:
        if not isinstance(annotations, list):
            return None

        for annotation in annotations:
            if not isinstance(annotation, dict) or annotation.get("type") != "file":
                continue
            file_payload = annotation.get("file")
            if not isinstance(file_payload, dict):
                continue
            file_hash = file_payload.get("hash")
            if isinstance(file_hash, str) and file_hash.strip():
                return file_hash.strip()

        return None

    def _build_pdf_data_url(self, pdf_bytes: bytes) -> str:
        encoded_pdf = base64.b64encode(pdf_bytes).decode("ascii")
        return f"data:application/pdf;base64,{encoded_pdf}"

    def _normalize_text(self, text: str | None) -> str:
        if text is None:
            return ""

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\x00", "")
        normalized = HYPHENATED_LINE_BREAK_PATTERN.sub("", normalized)

        normalized_lines: list[str] = []
        for line in normalized.split("\n"):
            stripped_line = HEADING_WHITESPACE_PATTERN.sub(" ", line).strip()
            if stripped_line:
                normalized_lines.append(stripped_line)
            else:
                normalized_lines.append("")

        normalized = "\n".join(normalized_lines)
        normalized = REPEATED_NEWLINE_PATTERN.sub("\n\n", normalized)
        return normalized.strip()

    def _split_into_paragraphs(self, text: str) -> list[str]:
        return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]

    def _looks_like_heading(self, text: str) -> bool:
        stripped_text = text.strip()
        if not stripped_text:
            return False
        if len(stripped_text) > 120:
            return False
        if stripped_text.endswith((".", "!", "?")):
            return False

        words = stripped_text.split()
        if not 1 <= len(words) <= 12:
            return False

        if HEADING_NUMBER_PATTERN.match(stripped_text):
            return True
        if stripped_text.isupper():
            return True

        title_cased_words = sum(1 for word in words if word[:1].isupper())
        return title_cased_words >= max(1, len(words) // 2)

    def _guess_filename(self, *, paper: Paper) -> str:
        if paper.pdf_url:
            path = urlparse(paper.pdf_url).path
            if path:
                candidate = path.rsplit("/", maxsplit=1)[-1]
                if candidate.lower().endswith(".pdf"):
                    return candidate

        normalized_title = re.sub(r"[^a-z0-9]+", "-", paper.title.lower()).strip("-")
        if normalized_title:
            return f"{normalized_title[:80]}.pdf"
        return f"{paper.id}.pdf"
