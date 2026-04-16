from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.db.models import Paper, PaperChunk, PaperConversation, PaperMessage
from backend.services.document_extraction import (
    DocumentExtractionError,
    PaperDocumentExtractionService,
)
from backend.services.embeddings import EmbeddingService
from backend.services.research_utils import cosine_similarity, has_live_api_key

DEFAULT_MAX_ANSWER_TOKENS = 800
MAX_LOCAL_SNIPPET_CHARS = 280


class DocumentExtractionClient(Protocol):
    """Minimal document extraction interface used by paper conversations."""

    async def ensure_document_chunks(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
    ) -> object:
        """Ensure chunk grounding exists for a paper."""


class EmbeddingClient(Protocol):
    """Minimal embedding interface used by paper conversations."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for the provided texts."""


@dataclass(frozen=True)
class RetrievedPaperChunk:
    """Paper chunk plus retrieval score for answer construction."""

    chunk: PaperChunk
    similarity: float


@dataclass(frozen=True)
class PaperConversationCreationResult:
    """Conversation plus metadata about the first grounded answer."""

    conversation: PaperConversation
    used_metadata_fallback: bool


class PaperConversationService:
    """Create and ground paper-specific conversations."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        retrieval_top_k: int | None = None,
        http_client: httpx.AsyncClient | None = None,
        extraction_service: DocumentExtractionClient | None = None,
        embedding_service: EmbeddingClient | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.model = model if model is not None else settings.openrouter_model
        self.base_url = (
            base_url.rstrip("/") if base_url is not None else settings.openrouter_base_url.rstrip("/")
        )
        self.retrieval_top_k = (
            retrieval_top_k if retrieval_top_k is not None else settings.paper_retrieval_top_k
        )
        self.http_client = http_client
        self.timeout_seconds = settings.external_api_timeout_seconds
        self.extraction_service = extraction_service or PaperDocumentExtractionService()
        self.embedding_service = embedding_service or EmbeddingService()

    def is_configured(self) -> bool:
        """Return whether live OpenRouter answer synthesis is available."""

        return has_live_api_key(self.api_key)

    async def create_conversation(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
        question: str,
    ) -> PaperConversationCreationResult:
        """Create a conversation, persist the first turn, and return the stored conversation."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        retrieved_chunks, extraction_error = await self._retrieve_relevant_chunks(
            session=session,
            paper=paper,
            question=normalized_question,
        )
        used_metadata_fallback = not retrieved_chunks
        answer = await self._generate_answer(
            paper=paper,
            question=normalized_question,
            retrieved_chunks=retrieved_chunks,
            extraction_error=extraction_error,
        )

        conversation = PaperConversation(paper_id=paper.id)
        session.add(conversation)
        await session.flush()

        session.add(
            PaperMessage(
                conversation_id=conversation.id,
                role="user",
                content=normalized_question,
            )
        )
        session.add(
            PaperMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
            )
        )
        await session.commit()

        loaded_conversation = await self._load_conversation(
            session=session,
            conversation_id=conversation.id,
        )
        return PaperConversationCreationResult(
            conversation=loaded_conversation,
            used_metadata_fallback=used_metadata_fallback,
        )

    async def _retrieve_relevant_chunks(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
        question: str,
    ) -> tuple[list[RetrievedPaperChunk], str | None]:
        extraction_error: str | None = None
        chunks = await self._load_chunks(session=session, paper_id=paper.id)

        if not chunks and paper.pdf_url:
            try:
                await self.extraction_service.ensure_document_chunks(session=session, paper=paper)
            except DocumentExtractionError as error:
                extraction_error = str(error)
            chunks = await self._load_chunks(session=session, paper_id=paper.id)

        if not chunks:
            return [], extraction_error

        question_embedding = await self._embed_question(question)
        scored_chunks: list[RetrievedPaperChunk] = []
        for chunk in chunks:
            chunk_embedding = [float(value) for value in chunk.embedding_json]
            if not chunk_embedding:
                continue
            try:
                similarity = cosine_similarity(question_embedding, chunk_embedding)
            except ValueError:
                continue
            scored_chunks.append(RetrievedPaperChunk(chunk=chunk, similarity=similarity))

        scored_chunks.sort(key=lambda item: item.similarity, reverse=True)
        return scored_chunks[: self.retrieval_top_k], extraction_error

    async def _embed_question(self, question: str) -> list[float]:
        try:
            embeddings = await self.embedding_service.embed_texts([question])
        except Exception as error:
            if isinstance(self.embedding_service, EmbeddingService):
                return self.embedding_service.embed_texts_locally([question])[0]
            raise RuntimeError("Question embedding failed.") from error

        if not embeddings:
            raise RuntimeError("Question embedding returned no vectors.")
        return embeddings[0]

    async def _generate_answer(
        self,
        *,
        paper: Paper,
        question: str,
        retrieved_chunks: list[RetrievedPaperChunk],
        extraction_error: str | None,
    ) -> str:
        if self.is_configured():
            try:
                return await self._generate_live_answer(
                    paper=paper,
                    question=question,
                    retrieved_chunks=retrieved_chunks,
                    extraction_error=extraction_error,
                )
            except RuntimeError:
                pass

        return self._generate_local_answer(
            paper=paper,
            question=question,
            retrieved_chunks=retrieved_chunks,
            extraction_error=extraction_error,
        )

    async def _generate_live_answer(
        self,
        *,
        paper: Paper,
        question: str,
        retrieved_chunks: list[RetrievedPaperChunk],
        extraction_error: str | None,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("OpenRouter API credentials are not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer questions about one academic paper. "
                        "Use retrieved paper chunks as the primary source of truth. "
                        "If chunk grounding is unavailable, answer only from the provided metadata "
                        "and explicitly say the answer is limited."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        paper=paper,
                        question=question,
                        retrieved_chunks=retrieved_chunks,
                        extraction_error=extraction_error,
                    ),
                },
            ],
            "max_tokens": DEFAULT_MAX_ANSWER_TOKENS,
            "temperature": 0.2,
            "provider": {"sort": "price"},
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
        except httpx.HTTPError as error:
            raise RuntimeError("OpenRouter paper-answer request failed.") from error
        finally:
            if owns_client:
                await client.aclose()

        response_payload = response.json()
        choices = response_payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenRouter paper-answer response choices were missing.")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise RuntimeError("OpenRouter paper-answer response choice was invalid.")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("OpenRouter paper-answer response message was missing.")

        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter paper-answer response did not contain text content.")

        return content.strip()

    def _build_prompt(
        self,
        *,
        paper: Paper,
        question: str,
        retrieved_chunks: list[RetrievedPaperChunk],
        extraction_error: str | None,
    ) -> str:
        prompt_sections = [
            f"Question: {question}",
            "",
            "Paper metadata:",
            f"- Title: {paper.title}",
            f"- Authors: {', '.join(paper.authors) if paper.authors else 'Unknown'}",
            f"- Year: {paper.year if paper.year is not None else 'Unknown'}",
        ]

        if paper.abstract:
            prompt_sections.extend(["", "Abstract:", paper.abstract])

        if paper.summary is not None and not paper.summary.has_error:
            summary_lines = [
                value
                for value in [
                    paper.summary.problem,
                    paper.summary.method,
                    paper.summary.result,
                    paper.summary.relevance_to_topic,
                ]
                if value
            ]
            if summary_lines:
                prompt_sections.extend(["", "Structured summary:", "\n".join(summary_lines)])

        if retrieved_chunks:
            prompt_sections.extend(["", "Retrieved paper chunks:"])
            for index, retrieved_chunk in enumerate(retrieved_chunks, start=1):
                chunk = retrieved_chunk.chunk
                prompt_sections.extend(
                    [
                        (
                            f"[Chunk {index}] pages {chunk.page_start}-{chunk.page_end}, "
                            f"score={retrieved_chunk.similarity:.3f}"
                        ),
                        chunk.content,
                        "",
                    ]
                )
        else:
            prompt_sections.extend(
                [
                    "",
                    "No retrieved chunk grounding is available.",
                    "Answer only from metadata and explicitly say the answer is limited.",
                ]
            )

        if extraction_error:
            prompt_sections.extend(["", f"Grounding note: {extraction_error}"])

        return "\n".join(prompt_sections).strip()

    def _generate_local_answer(
        self,
        *,
        paper: Paper,
        question: str,
        retrieved_chunks: list[RetrievedPaperChunk],
        extraction_error: str | None,
    ) -> str:
        if retrieved_chunks:
            relevant_passages = " ".join(
                self._format_chunk_snippet(retrieved_chunk)
                for retrieved_chunk in retrieved_chunks[:2]
            )
            return (
                f"Question: {question}\n\n"
                f"Based on the extracted text for '{paper.title}', the most relevant evidence is: "
                f"{relevant_passages}\n\n"
                "This response was produced by the deterministic fallback path because live answer "
                "synthesis is unavailable in the current environment."
            )

        metadata_sections = [
            (
                "I could not ground this answer in extracted PDF chunks, so this response is limited "
                "to the stored paper metadata."
            ),
            f"Title: {paper.title}",
            f"Authors: {', '.join(paper.authors) if paper.authors else 'Unknown'}",
            f"Year: {paper.year if paper.year is not None else 'Unknown'}",
        ]

        if paper.abstract:
            metadata_sections.append(f"Abstract: {paper.abstract}")

        if paper.summary is not None and not paper.summary.has_error:
            summary_fragments = [
                value
                for value in [
                    paper.summary.problem,
                    paper.summary.method,
                    paper.summary.result,
                    paper.summary.relevance_to_topic,
                ]
                if value
            ]
            if summary_fragments:
                metadata_sections.append("Stored summary: " + " ".join(summary_fragments))

        if extraction_error:
            metadata_sections.append(f"Grounding note: {extraction_error}")

        metadata_sections.append(
            "If you need a deeper answer, make sure the paper has a usable public pdf_url so chunk "
            "grounding can succeed."
        )
        return "\n\n".join(metadata_sections)

    def _format_chunk_snippet(self, retrieved_chunk: RetrievedPaperChunk) -> str:
        chunk = retrieved_chunk.chunk
        normalized_content = " ".join(chunk.content.split())
        snippet = normalized_content[:MAX_LOCAL_SNIPPET_CHARS].rstrip()
        return (
            f"(pages {chunk.page_start}-{chunk.page_end}, score {retrieved_chunk.similarity:.2f}) "
            f"{snippet}"
        )

    async def _load_chunks(self, *, session: AsyncSession, paper_id: str) -> list[PaperChunk]:
        result = await session.execute(
            select(PaperChunk)
            .where(PaperChunk.paper_id == paper_id)
            .order_by(PaperChunk.chunk_index.asc())
        )
        return list(result.scalars())

    async def _load_conversation(
        self,
        *,
        session: AsyncSession,
        conversation_id: str,
    ) -> PaperConversation:
        result = await session.execute(
            select(PaperConversation)
            .options(selectinload(PaperConversation.messages))
            .where(PaperConversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise RuntimeError("Created conversation could not be reloaded.")
        return conversation
