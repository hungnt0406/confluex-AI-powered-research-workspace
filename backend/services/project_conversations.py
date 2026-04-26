from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.db.models import (
    Paper,
    PaperChunk,
    ProjectConversation,
    ProjectMessage,
)
from backend.services.ai_usage import collect_openrouter_usage
from backend.services.document_extraction import (
    DocumentExtractionError,
    PaperDocumentExtractionService,
    embed_texts_with_feature,
)
from backend.services.embeddings import EmbeddingService
from backend.services.paper_conversations import (
    BRACKETED_CHUNK_PATTERN,
    CHUNK_LABEL_PATTERN,
    CHUNK_LABEL_WITH_PAGES_PATTERN,
    DEFAULT_MAX_ANSWER_TOKENS,
    INTERNAL_GROUNDING_LINE_PREFIXES,
    LIVE_ANSWER_SYSTEM_PROMPT,
    MAX_LOCAL_SNIPPET_CHARS,
    RAW_PROVIDER_ERROR_MARKERS,
    RECENT_HISTORY_MESSAGE_LIMIT,
    SCORE_SEGMENT_PATTERN,
    DefaultSemanticScholarDetailsClient,
    DocumentExtractionClient,
    EmbeddingClient,
    SemanticScholarDetailsClient,
)
from backend.services.research_utils import cosine_similarity, has_live_api_key
from backend.services.semantic_scholar import (
    SemanticScholarPaperLookupError,
    SemanticScholarPaperNotFoundError,
    SemanticScholarProviderError,
)

MAX_SELECTED_PAPERS = 5
MAX_TOTAL_RETRIEVED_SNIPPETS = 5
MAX_SNIPPETS_PER_PAPER = 2
PROJECT_GROUNDING_UNAVAILABLE_MESSAGE = (
    "PDF text extraction was unavailable for one or more selected papers, "
    "so no page-grounded excerpts could be retrieved."
)


@dataclass(frozen=True)
class RetrievedProjectChunk:
    """Paper chunk plus its parent paper and retrieval score."""

    paper: Paper
    chunk: PaperChunk
    similarity: float


@dataclass(frozen=True)
class ProjectConversationCreationResult:
    """Conversation plus metadata about whether chunk grounding was unavailable."""

    conversation: ProjectConversation
    used_metadata_fallback: bool


@dataclass(frozen=True)
class ProjectConversationStreamEvent:
    """Internal event emitted while streaming a project conversation turn."""

    event: Literal["status", "conversation", "token", "done", "error"]
    data: dict[str, object] | ProjectConversation


@dataclass(frozen=True)
class ProjectConversationTurnContext:
    """Prepared state shared by synchronous and streaming project chat turns."""

    conversation: ProjectConversation
    selected_papers: list[Paper]
    question: str
    recent_messages: list[ProjectMessage]
    retrieved_chunks: list[RetrievedProjectChunk]
    extraction_errors: list[str]
    used_metadata_fallback: bool
    touch_updated_at: bool


class ProjectConversationService:
    """Create and continue project-scoped grounded conversations across selected papers."""

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
        semantic_scholar_client: SemanticScholarDetailsClient | None = None,
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
        self.semantic_scholar_client = semantic_scholar_client or DefaultSemanticScholarDetailsClient()

    def is_configured(self) -> bool:
        """Return whether live answer synthesis is available."""

        return has_live_api_key(self.api_key)

    async def create_conversation(
        self,
        *,
        session: AsyncSession,
        project_id: str,
        selected_papers: list[Paper],
        question: str,
    ) -> ProjectConversationCreationResult:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        conversation = ProjectConversation(
            project_id=project_id,
            selected_paper_ids_json=[paper.id for paper in selected_papers],
        )
        session.add(conversation)
        await session.flush()

        turn_context = await self._prepare_turn(
            session=session,
            conversation=conversation,
            selected_papers=selected_papers,
            question=normalized_question,
            recent_messages=[],
            touch_updated_at=False,
        )
        answer = await self._generate_answer(
            selected_papers=turn_context.selected_papers,
            question=turn_context.question,
            recent_messages=turn_context.recent_messages,
            retrieved_chunks=turn_context.retrieved_chunks,
            extraction_errors=turn_context.extraction_errors,
        )
        return await self._persist_prepared_turn(
            session=session,
            turn_context=turn_context,
            answer=answer,
        )

    async def continue_conversation(
        self,
        *,
        session: AsyncSession,
        conversation: ProjectConversation,
        selected_papers: list[Paper],
        question: str,
    ) -> ProjectConversationCreationResult:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        recent_messages = await self._load_recent_messages(
            session=session,
            conversation_id=conversation.id,
            limit=RECENT_HISTORY_MESSAGE_LIMIT,
        )
        turn_context = await self._prepare_turn(
            session=session,
            conversation=conversation,
            selected_papers=selected_papers,
            question=normalized_question,
            recent_messages=recent_messages,
            touch_updated_at=True,
        )
        answer = await self._generate_answer(
            selected_papers=turn_context.selected_papers,
            question=turn_context.question,
            recent_messages=turn_context.recent_messages,
            retrieved_chunks=turn_context.retrieved_chunks,
            extraction_errors=turn_context.extraction_errors,
        )
        return await self._persist_prepared_turn(
            session=session,
            turn_context=turn_context,
            answer=answer,
        )

    async def stream_create_conversation(
        self,
        *,
        session: AsyncSession,
        project_id: str,
        selected_papers: list[Paper],
        question: str,
    ) -> AsyncIterator[ProjectConversationStreamEvent]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        conversation = ProjectConversation(
            project_id=project_id,
            selected_paper_ids_json=[paper.id for paper in selected_papers],
        )
        session.add(conversation)
        await session.flush()
        yield ProjectConversationStreamEvent("conversation", conversation)

        async for event in self._stream_turn(
            session=session,
            conversation=conversation,
            selected_papers=selected_papers,
            question=normalized_question,
            recent_messages=[],
            touch_updated_at=False,
        ):
            yield event

    async def stream_continue_conversation(
        self,
        *,
        session: AsyncSession,
        conversation: ProjectConversation,
        selected_papers: list[Paper],
        question: str,
    ) -> AsyncIterator[ProjectConversationStreamEvent]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        recent_messages = await self._load_recent_messages(
            session=session,
            conversation_id=conversation.id,
            limit=RECENT_HISTORY_MESSAGE_LIMIT,
        )
        yield ProjectConversationStreamEvent("conversation", conversation)

        async for event in self._stream_turn(
            session=session,
            conversation=conversation,
            selected_papers=selected_papers,
            question=normalized_question,
            recent_messages=recent_messages,
            touch_updated_at=True,
        ):
            yield event

    async def _stream_turn(
        self,
        *,
        session: AsyncSession,
        conversation: ProjectConversation,
        selected_papers: list[Paper],
        question: str,
        recent_messages: list[ProjectMessage],
        touch_updated_at: bool,
    ) -> AsyncIterator[ProjectConversationStreamEvent]:
        yield ProjectConversationStreamEvent("status", {"phase": "retrieving"})
        turn_context = await self._prepare_turn(
            session=session,
            conversation=conversation,
            selected_papers=selected_papers,
            question=question,
            recent_messages=recent_messages,
            touch_updated_at=touch_updated_at,
        )

        yield ProjectConversationStreamEvent("status", {"phase": "generating"})
        answer_parts: list[str] = []
        try:
            async for token in self._stream_answer(turn_context):
                answer_parts.append(token)
                yield ProjectConversationStreamEvent("token", {"delta": token})
        except RuntimeError as error:
            await session.rollback()
            yield ProjectConversationStreamEvent("error", {"detail": str(error)})
            return

        answer = "".join(answer_parts)
        yield ProjectConversationStreamEvent("status", {"phase": "persisting"})
        result = await self._persist_prepared_turn(
            session=session,
            turn_context=turn_context,
            answer=answer,
        )
        yield ProjectConversationStreamEvent("done", result.conversation)

    async def _prepare_turn(
        self,
        *,
        session: AsyncSession,
        conversation: ProjectConversation,
        selected_papers: list[Paper],
        question: str,
        recent_messages: list[ProjectMessage],
        touch_updated_at: bool,
    ) -> ProjectConversationTurnContext:
        selection_changed = list(conversation.selected_paper_ids_json) != [paper.id for paper in selected_papers]
        if selection_changed:
            conversation.selected_paper_ids_json = [paper.id for paper in selected_papers]
            session.add(
                ProjectMessage(
                    conversation_id=conversation.id,
                    role="system",
                    content=self._build_selection_change_message(selected_papers),
                )
            )

        retrieved_chunks, extraction_errors = await self._retrieve_relevant_chunks(
            session=session,
            selected_papers=selected_papers,
            question=question,
        )

        return ProjectConversationTurnContext(
            conversation=conversation,
            selected_papers=selected_papers,
            question=question,
            recent_messages=recent_messages,
            retrieved_chunks=retrieved_chunks,
            extraction_errors=extraction_errors,
            used_metadata_fallback=not retrieved_chunks,
            touch_updated_at=touch_updated_at,
        )

    async def _persist_prepared_turn(
        self,
        *,
        session: AsyncSession,
        turn_context: ProjectConversationTurnContext,
        answer: str,
    ) -> ProjectConversationCreationResult:
        final_answer = self._append_grounding_recovery_note(
            answer=self._sanitize_user_visible_text(answer),
            selected_papers=turn_context.selected_papers,
            retrieved_chunks=turn_context.retrieved_chunks,
        )
        session.add(
            ProjectMessage(
                conversation_id=turn_context.conversation.id,
                role="user",
                content=turn_context.question,
            )
        )
        session.add(
            ProjectMessage(
                conversation_id=turn_context.conversation.id,
                role="assistant",
                content=final_answer,
            )
        )
        if turn_context.touch_updated_at:
            turn_context.conversation.updated_at = datetime.now(UTC)
        await session.commit()

        loaded_conversation = await self._load_conversation(
            session=session,
            conversation_id=turn_context.conversation.id,
        )
        return ProjectConversationCreationResult(
            conversation=loaded_conversation,
            used_metadata_fallback=turn_context.used_metadata_fallback,
        )

    async def _retrieve_relevant_chunks(
        self,
        *,
        session: AsyncSession,
        selected_papers: list[Paper],
        question: str,
    ) -> tuple[list[RetrievedProjectChunk], list[str]]:
        if not selected_papers:
            return [], []

        question_embedding = await self._embed_question(question)
        scored_chunks: list[RetrievedProjectChunk] = []
        extraction_errors: list[str] = []

        for paper in selected_papers:
            paper_pdf_url = await self._ensure_grounding_pdf_url(session=session, paper=paper)
            chunks = await self._load_chunks(session=session, paper_id=paper.id)
            if not chunks and paper_pdf_url:
                try:
                    await self.extraction_service.ensure_document_chunks(session=session, paper=paper)
                except DocumentExtractionError as error:
                    extraction_errors.append(f"{paper.title}: {error}")
                    await self._refresh_paper(session=session, paper_id=paper.id)
                chunks = await self._load_chunks(session=session, paper_id=paper.id)

            for chunk in chunks:
                chunk_embedding = [float(value) for value in chunk.embedding_json]
                if not chunk_embedding:
                    continue
                try:
                    similarity = cosine_similarity(question_embedding, chunk_embedding)
                except ValueError:
                    continue
                scored_chunks.append(
                    RetrievedProjectChunk(
                        paper=paper,
                        chunk=chunk,
                        similarity=similarity,
                    )
                )

        scored_chunks.sort(key=lambda item: item.similarity, reverse=True)

        selected_chunks: list[RetrievedProjectChunk] = []
        paper_counts: dict[str, int] = {}
        for retrieved_chunk in scored_chunks:
            count = paper_counts.get(retrieved_chunk.paper.id, 0)
            if count >= MAX_SNIPPETS_PER_PAPER:
                continue
            selected_chunks.append(retrieved_chunk)
            paper_counts[retrieved_chunk.paper.id] = count + 1
            if len(selected_chunks) >= MAX_TOTAL_RETRIEVED_SNIPPETS:
                break

        return selected_chunks, extraction_errors

    async def _ensure_grounding_pdf_url(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
    ) -> str | None:
        existing_pdf_url = (paper.pdf_url or "").strip()
        if existing_pdf_url:
            return existing_pdf_url

        candidate_identifiers = self._build_pdf_resolution_candidates(paper)
        if not candidate_identifiers:
            return None

        paper_details: object | None = None
        for paper_identifier in candidate_identifiers:
            try:
                paper_details = await self.semantic_scholar_client.get_paper_details(paper_identifier)
                break
            except (SemanticScholarPaperLookupError, SemanticScholarPaperNotFoundError):
                continue
            except SemanticScholarProviderError:
                return None

        if paper_details is None:
            return None

        updated = False

        resolved_pdf_url = getattr(paper_details, "pdf_url", None)
        if isinstance(resolved_pdf_url, str) and resolved_pdf_url.strip():
            paper.pdf_url = resolved_pdf_url.strip()
            updated = True

        resolved_source_url = getattr(paper_details, "source_url", None)
        if not paper.source_url and isinstance(resolved_source_url, str) and resolved_source_url.strip():
            paper.source_url = resolved_source_url.strip()
            updated = True

        resolved_citation_count = getattr(paper_details, "citation_count", None)
        if isinstance(resolved_citation_count, int) and paper.citation_count != resolved_citation_count:
            paper.citation_count = resolved_citation_count
            updated = True

        resolved_reference_count = getattr(paper_details, "reference_count", None)
        if isinstance(resolved_reference_count, int) and paper.reference_count != resolved_reference_count:
            paper.reference_count = resolved_reference_count
            updated = True

        if updated:
            await session.flush()

        normalized_pdf_url = (paper.pdf_url or "").strip()
        return normalized_pdf_url or None

    def _build_pdf_resolution_candidates(self, paper: Paper) -> list[str]:
        candidates: list[str] = []
        seen_identifiers: set[str] = set()

        def add_candidate(raw_identifier: str | None) -> None:
            if raw_identifier is None:
                return
            normalized_identifier = raw_identifier.strip()
            if not normalized_identifier or normalized_identifier in seen_identifiers:
                return
            seen_identifiers.add(normalized_identifier)
            candidates.append(normalized_identifier)

        if paper.source == "semantic_scholar":
            add_candidate(paper.source_paper_id)
            add_candidate(f"URL:{paper.source_url}" if paper.source_url else None)

        add_candidate(f"DOI:{paper.doi}" if paper.doi else None)
        return candidates

    async def _embed_question(self, question: str) -> list[float]:
        try:
            embeddings = await embed_texts_with_feature(
                self.embedding_service,
                [question],
                feature="project_chat_answer",
            )
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
        selected_papers: list[Paper],
        question: str,
        recent_messages: list[ProjectMessage],
        retrieved_chunks: list[RetrievedProjectChunk],
        extraction_errors: list[str],
    ) -> str:
        if self.is_configured():
            try:
                answer = await self._generate_live_answer(
                    selected_papers=selected_papers,
                    question=question,
                    recent_messages=recent_messages,
                    retrieved_chunks=retrieved_chunks,
                    extraction_errors=extraction_errors,
                )
            except RuntimeError:
                answer = self._generate_local_answer(
                    selected_papers=selected_papers,
                    question=question,
                    recent_messages=recent_messages,
                    retrieved_chunks=retrieved_chunks,
                    extraction_errors=extraction_errors,
                )
        else:
            answer = self._generate_local_answer(
                selected_papers=selected_papers,
                question=question,
                recent_messages=recent_messages,
                retrieved_chunks=retrieved_chunks,
                extraction_errors=extraction_errors,
            )

        return self._sanitize_user_visible_text(answer)

    async def _stream_answer(
        self,
        turn_context: ProjectConversationTurnContext,
    ) -> AsyncGenerator[str, None]:
        if self.is_configured():
            live_stream = self._stream_live_answer(
                selected_papers=turn_context.selected_papers,
                question=turn_context.question,
                recent_messages=turn_context.recent_messages,
                retrieved_chunks=turn_context.retrieved_chunks,
                extraction_errors=turn_context.extraction_errors,
            )
            try:
                first_token = await asyncio.wait_for(
                    anext(live_stream),
                    timeout=self.timeout_seconds,
                )
                yield first_token
                async for token in live_stream:
                    yield token
                return
            except (StopAsyncIteration, TimeoutError):
                await live_stream.aclose()
            except RuntimeError as error:
                await live_stream.aclose()
                if str(error) == "OpenRouter project-answer stream failed before content.":
                    pass
                else:
                    raise

        fallback_answer = self._generate_local_answer(
            selected_papers=turn_context.selected_papers,
            question=turn_context.question,
            recent_messages=turn_context.recent_messages,
            retrieved_chunks=turn_context.retrieved_chunks,
            extraction_errors=turn_context.extraction_errors,
        )
        yield fallback_answer

    async def _stream_live_answer(
        self,
        *,
        selected_papers: list[Paper],
        question: str,
        recent_messages: list[ProjectMessage],
        retrieved_chunks: list[RetrievedProjectChunk],
        extraction_errors: list[str],
    ) -> AsyncGenerator[str, None]:
        if not self.is_configured():
            raise RuntimeError("OpenRouter project-answer stream failed before content.")

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": LIVE_ANSWER_SYSTEM_PROMPT.replace(
                        "one academic paper", "a selected set of academic papers"
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        selected_papers=selected_papers,
                        question=question,
                        recent_messages=recent_messages,
                        retrieved_chunks=retrieved_chunks,
                        extraction_errors=extraction_errors,
                    ),
                },
            ],
            "max_tokens": DEFAULT_MAX_ANSWER_TOKENS,
            "temperature": 0.2,
            "provider": {"sort": "price"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        tokens_started = False
        usage_payload: dict[str, object] | None = None
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for frame in self._iter_openrouter_sse_data(response):
                    if frame == "[DONE]":
                        break
                    try:
                        event_payload = json.loads(frame)
                    except json.JSONDecodeError as error:
                        raise RuntimeError("OpenRouter project-answer stream returned invalid JSON.") from error
                    if not isinstance(event_payload, dict):
                        continue
                    if "error" in event_payload:
                        detail = self._format_openrouter_stream_error(event_payload["error"])
                        raise RuntimeError(detail)
                    usage = event_payload.get("usage")
                    if isinstance(usage, dict):
                        usage_payload = {"usage": usage}
                    choices = event_payload.get("choices", [])
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content")
                    if isinstance(content, list):
                        content = "".join(
                            block.get("text", "")
                            for block in content
                            if isinstance(block, dict) and block.get("type") == "text"
                        )
                    if isinstance(content, str) and content:
                        tokens_started = True
                        yield content
        except httpx.HTTPError as error:
            if tokens_started:
                raise RuntimeError("OpenRouter project-answer stream failed.") from error
            raise RuntimeError("OpenRouter project-answer stream failed before content.") from error
        finally:
            if owns_client:
                await client.aclose()

        if usage_payload is not None:
            collect_openrouter_usage(
                endpoint="chat/completions",
                feature="project_chat_answer",
                model=self.model,
                response_payload=usage_payload,
                metadata={"selected_paper_count": len(selected_papers), "stream": True},
            )

    async def _iter_openrouter_sse_data(
        self,
        response: httpx.Response,
    ) -> AsyncIterator[str]:
        data_lines: list[str] = []
        async for line in response.aiter_lines():
            if line == "":
                if data_lines:
                    yield "\n".join(data_lines)
                    data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if data_lines:
            yield "\n".join(data_lines)

    def _format_openrouter_stream_error(self, error_payload: object) -> str:
        if isinstance(error_payload, dict):
            message = error_payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return "OpenRouter project-answer stream failed."

    async def _generate_live_answer(
        self,
        *,
        selected_papers: list[Paper],
        question: str,
        recent_messages: list[ProjectMessage],
        retrieved_chunks: list[RetrievedProjectChunk],
        extraction_errors: list[str],
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
                    "content": LIVE_ANSWER_SYSTEM_PROMPT.replace(
                        "one academic paper", "a selected set of academic papers"
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        selected_papers=selected_papers,
                        question=question,
                        recent_messages=recent_messages,
                        retrieved_chunks=retrieved_chunks,
                        extraction_errors=extraction_errors,
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
            raise RuntimeError("OpenRouter project-answer request failed.") from error
        finally:
            if owns_client:
                await client.aclose()

        response_payload = response.json()
        collect_openrouter_usage(
            endpoint="chat/completions",
            feature="project_chat_answer",
            model=self.model,
            response_payload=response_payload,
            metadata={"selected_paper_count": len(selected_papers)},
        )
        choices = response_payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenRouter project-answer response choices were missing.")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise RuntimeError("OpenRouter project-answer response choice was invalid.")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("OpenRouter project-answer response message was missing.")

        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter project-answer response did not contain text content.")

        return self._sanitize_user_visible_text(content.strip())

    def _build_prompt(
        self,
        *,
        selected_papers: list[Paper],
        question: str,
        recent_messages: list[ProjectMessage],
        retrieved_chunks: list[RetrievedProjectChunk],
        extraction_errors: list[str],
    ) -> str:
        if not selected_papers:
            prompt_sections = [
                f"Question: {question}",
                "",
                "Answering rules:",
                "- Answer the current question directly as general knowledge.",
                "- No papers are selected, so do not cite or claim support from any project paper.",
                "- Do not mention the ranked paper list unless the user asks about it.",
                "- If the question requires paper-specific evidence, ask the user to select one or more papers.",
                "",
                "Selection state: no papers selected.",
            ]
            if recent_messages:
                prompt_sections.extend(["", "Recent conversation history:"])
                for message in recent_messages:
                    prompt_sections.append(f"{message.role.title()}: {message.content}")
            return "\n".join(prompt_sections).strip()

        prompt_sections = [
            f"Question: {question}",
            "",
            "Answering rules:",
            "- Answer the current question directly.",
            "- Synthesize across the selected papers when the evidence supports comparison.",
            "- Use recent conversation history only to resolve references from the current question.",
            "- Prefer retrieved excerpts over metadata or stored summaries.",
            "- If the evidence is insufficient, say exactly what is missing instead of guessing.",
            "- When citing evidence, mention page numbers and paper titles only.",
            "",
            "Selected paper set:",
        ]

        for paper in selected_papers:
            prompt_sections.extend(
                [
                    f"- Title: {paper.title}",
                    f"  Authors: {', '.join(paper.authors) if paper.authors else 'Unknown'}",
                    f"  Year: {paper.year if paper.year is not None else 'Unknown'}",
                ]
            )
            if paper.abstract:
                prompt_sections.append(f"  Abstract: {paper.abstract}")
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
                    prompt_sections.append(f"  Structured summary: {' '.join(summary_lines)}")
            prompt_sections.append("")

        if recent_messages:
            prompt_sections.extend(["Recent conversation history:"])
            for message in recent_messages:
                prompt_sections.append(f"{message.role.title()}: {message.content}")
            prompt_sections.append("")

        if retrieved_chunks:
            prompt_sections.append("Retrieved excerpts:")
            for retrieved_chunk in retrieved_chunks:
                chunk = retrieved_chunk.chunk
                prompt_sections.extend(
                    [
                        f"Paper: {retrieved_chunk.paper.title}",
                        f"Pages: {chunk.page_start}-{chunk.page_end}",
                        chunk.content,
                        "",
                    ]
                )
        else:
            prompt_sections.extend(
                [
                    "Retrieved paper excerpts are unavailable for this turn.",
                    "Use metadata only and include a concise limitation that PDF grounding is unavailable.",
                    "",
                ]
            )

        if extraction_errors:
            prompt_sections.extend(["Grounding status:", PROJECT_GROUNDING_UNAVAILABLE_MESSAGE])

        return "\n".join(prompt_sections).strip()

    def _generate_local_answer(
        self,
        *,
        selected_papers: list[Paper],
        question: str,
        recent_messages: list[ProjectMessage],
        retrieved_chunks: list[RetrievedProjectChunk],
        extraction_errors: list[str],
    ) -> str:
        if not selected_papers:
            response_sections = [
                "## Answer",
                (
                    "No papers are selected yet, so this is a general answer rather than a "
                    "paper-grounded one."
                ),
                "",
                "## Next Steps",
                (
                    "Select one or more papers when you want the answer grounded in retrieved "
                    "PDF chunks, abstracts, or stored summaries."
                ),
            ]
            return self._sanitize_user_visible_text("\n\n".join(response_sections))

        if retrieved_chunks:
            evidence_lines = [
                f"- **{retrieved_chunk.paper.title}** {self._format_chunk_snippet(retrieved_chunk)}"
                for retrieved_chunk in retrieved_chunks
            ]
            response_sections = [
                "## Answer",
                (
                    f"Based on the selected paper set, the question *\"{question}\"* can be answered "
                    "using the retrieved excerpts below."
                ),
                "",
                "## Evidence",
                "\n".join(evidence_lines),
            ]
            if extraction_errors:
                response_sections.extend(["", "## Grounding Note", PROJECT_GROUNDING_UNAVAILABLE_MESSAGE])
            return self._sanitize_user_visible_text("\n\n".join(response_sections))

        metadata_sections = [
            "## Answer",
            (
                "I could not ground this answer in extracted PDF chunks, so this response is limited "
                "to the stored metadata across the selected papers."
            ),
            "",
            "## Selected Papers",
        ]
        for paper in selected_papers:
            metadata_sections.append(
                f"- **{paper.title}** ({paper.year if paper.year is not None else 'Unknown'})"
            )
        if extraction_errors:
            metadata_sections.extend(["", "## Grounding Note", PROJECT_GROUNDING_UNAVAILABLE_MESSAGE])
        metadata_sections.extend(
            [
                "",
                "## Next Steps",
                "Make sure the selected papers have accessible PDFs so chunk grounding can succeed, or try uploading PDFs directly.",
            ]
        )
        return self._sanitize_user_visible_text("\n\n".join(metadata_sections))

    def _format_chunk_snippet(self, retrieved_chunk: RetrievedProjectChunk) -> str:
        normalized_content = " ".join(retrieved_chunk.chunk.content.split())
        snippet = normalized_content[:MAX_LOCAL_SNIPPET_CHARS].rstrip()
        return f"(pages {retrieved_chunk.chunk.page_start}-{retrieved_chunk.chunk.page_end}) {snippet}"

    def _append_grounding_recovery_note(
        self,
        *,
        answer: str,
        selected_papers: list[Paper],
        retrieved_chunks: list[RetrievedProjectChunk],
    ) -> str:
        if retrieved_chunks:
            return answer

        source_urls = [
            source_url
            for source_url in ((paper.source_url or "").strip() for paper in selected_papers)
            if source_url
        ]
        if not source_urls:
            return answer

        note_sections = [
            answer.strip(),
            "## Access Note",
            (
                "This answer is based on abstracts and stored metadata because I could not access "
                "usable PDFs for grounding in the current environment."
            ),
            "You can visit these paper pages and upload the PDFs here for more grounded follow-up questions:",
            *[f"- {source_url}" for source_url in source_urls[:MAX_SELECTED_PAPERS]],
        ]
        return self._sanitize_user_visible_text("\n\n".join(note_sections))

    def _format_recent_history(self, recent_messages: list[ProjectMessage]) -> str | None:
        if not recent_messages:
            return None

        return " | ".join(
            (
                f"{message.role}: "
                f"{self._sanitize_user_visible_text(' '.join(message.content.split()))[:MAX_LOCAL_SNIPPET_CHARS].rstrip()}"
            )
            for message in recent_messages
        )

    def _sanitize_user_visible_text(self, text: str) -> str:
        sanitized = CHUNK_LABEL_WITH_PAGES_PATTERN.sub(r"(pages \1)", text)
        sanitized = BRACKETED_CHUNK_PATTERN.sub(r"pages \1", sanitized)
        sanitized = CHUNK_LABEL_PATTERN.sub(r"pages \1", sanitized)
        sanitized = SCORE_SEGMENT_PATTERN.sub("", sanitized)
        sanitized = self._remove_internal_grounding_lines(sanitized)
        sanitized = sanitized.replace("\r\n", "\n")
        sanitized = sanitized.replace("\r", "\n")
        while "\n\n\n" in sanitized:
            sanitized = sanitized.replace("\n\n\n", "\n\n")
        return sanitized.strip()

    def _remove_internal_grounding_lines(self, text: str) -> str:
        visible_lines: list[str] = []
        for line in text.split("\n"):
            normalized_line = line.strip().lower()
            if not normalized_line:
                visible_lines.append(line)
                continue
            if normalized_line.startswith(INTERNAL_GROUNDING_LINE_PREFIXES):
                continue
            if any(marker in normalized_line for marker in RAW_PROVIDER_ERROR_MARKERS):
                continue
            visible_lines.append(line)
        return "\n".join(visible_lines)

    def _build_selection_change_message(self, selected_papers: list[Paper]) -> str:
        titles = [paper.title for paper in selected_papers]
        if not titles:
            return "Selected papers cleared."
        if len(titles) == 1:
            return f"Selected paper updated: {titles[0]}"
        return "Selected papers updated: " + "; ".join(titles)

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
    ) -> ProjectConversation:
        result = await session.execute(
            select(ProjectConversation)
            .options(selectinload(ProjectConversation.messages))
            .execution_options(populate_existing=True)
            .where(ProjectConversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise RuntimeError("Created conversation could not be reloaded.")
        return conversation

    async def _load_recent_messages(
        self,
        *,
        session: AsyncSession,
        conversation_id: str,
        limit: int,
    ) -> list[ProjectMessage]:
        result = await session.execute(
            select(ProjectMessage)
            .where(ProjectMessage.conversation_id == conversation_id)
            .order_by(ProjectMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def _refresh_paper(self, *, session: AsyncSession, paper_id: str) -> None:
        result = await session.execute(select(Paper).where(Paper.id == paper_id))
        refreshed_paper = result.scalar_one_or_none()
        if refreshed_paper is None:
            raise RuntimeError("Paper could not be refreshed after extraction failure.")
