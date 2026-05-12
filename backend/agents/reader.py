import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agents.searcher import serialize_paper_record
from backend.agents.state import AgentState
from backend.config import get_settings
from backend.db.models import Paper, Project, Summary
from backend.services.embeddings import EmbeddingService, EmbeddingServiceError
from backend.services.llm import ClaudeStructuredOutputService, StructuredOutputError
from backend.services.research_utils import cosine_similarity

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "method": {"type": "string"},
        "result": {"type": "string"},
        "relevance": {"type": "string"},
    },
    "required": ["problem", "method", "result", "relevance"],
    "additionalProperties": False,
}

SUMMARY_SYSTEM_PROMPT = """
You are an academic reading assistant.
Given a paper title, abstract, and review topic, produce a concise structured JSON summary.
Focus on the problem, method, result, and why the paper matters to the topic.
Respond with JSON using exactly these keys:
{"problem": "...", "method": "...", "result": "...", "relevance": "..."}
""".strip()


class PaperSummaryPayload(BaseModel):
    """Structured summary generated for a paper."""

    problem: str = Field(min_length=1)
    method: str = Field(min_length=1)
    result: str = Field(min_length=1)
    relevance_to_topic: str = Field(
        validation_alias=AliasChoices("relevance", "relevance_to_topic"),
        min_length=1,
    )

    model_config = ConfigDict(populate_by_name=True)


@dataclass
class SummaryGenerationResult:
    """Result of attempting to summarize a ranked paper."""

    paper: Paper
    payload: PaperSummaryPayload | None
    error_message: str | None = None

    @property
    def has_error(self) -> bool:
        return self.payload is None


@dataclass
class RankingResult:
    """Result of ranking all current project papers."""

    candidate_count: int
    ranked_papers: list[Paper]
    errors: list[str] = field(default_factory=list)


class SummaryGenerator(Protocol):
    """Protocol for structured summary generation."""

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 1_024,
        feature: str = "structured_output",
    ) -> dict[str, Any]:
        """Generate a structured JSON payload."""

    def is_configured(self) -> bool:
        """Return whether live generation is configured."""


class ReaderAgent:
    """Rank candidate papers and generate structured summaries."""

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService | None = None,
        summary_generator: ClaudeStructuredOutputService | None = None,
        summary_concurrency: int | None = None,
    ) -> None:
        settings = get_settings()
        self.embedding_service = embedding_service or EmbeddingService()
        self.summary_generator = summary_generator or ClaudeStructuredOutputService()
        self.summary_concurrency = (
            summary_concurrency if summary_concurrency is not None else settings.summary_concurrency
        )

    async def run(
        self,
        state: AgentState,
        session: AsyncSession,
        project: Project,
    ) -> dict[str, Any]:
        """Rank candidate papers and write structured summaries."""

        ranking_result = await self.rank_project_papers(session=session, project=project)
        summary_payloads, summary_errors = await self.summarize_ranked_papers(
            session=session,
            project=project,
            ranked_papers=ranking_result.ranked_papers,
        )

        return {
            "ranked_papers": [
                serialize_paper_record(paper) for paper in ranking_result.ranked_papers
            ],
            "summaries": summary_payloads,
            "errors": [*state.errors, *ranking_result.errors, *summary_errors],
        }

    async def rank_project_papers(
        self,
        *,
        session: AsyncSession,
        project: Project,
    ) -> RankingResult:
        """Rank current project papers and persist ranked status before summaries."""

        result = await session.execute(
            select(Paper)
            .options(selectinload(Paper.summary))
            .where(Paper.project_id == project.id)
        )
        candidate_papers = list(result.scalars().all())

        if not candidate_papers:
            return RankingResult(
                candidate_count=0,
                ranked_papers=[],
                errors=["No candidate papers were available for ranking."],
            )

        ranked_papers, ranking_errors = await self.rank_papers(
            project.topic_description,
            candidate_papers,
        )
        top_papers = ranked_papers[: project.summary_limit]

        for paper in top_papers:
            paper.status = "ranked"

        await session.commit()
        return RankingResult(
            candidate_count=len(candidate_papers),
            ranked_papers=top_papers,
            errors=ranking_errors,
        )

    async def stream_summary_results(
        self,
        *,
        session: AsyncSession,
        project: Project,
        ranked_papers: list[Paper],
    ) -> AsyncIterator[SummaryGenerationResult]:
        """Persist ranked-paper summaries one by one and yield each updated paper."""

        if not ranked_papers:
            return

        async for summary_result in self._stream_summary_generation(
            project.topic_description,
            ranked_papers,
        ):
            self._persist_summary_result(session=session, summary_result=summary_result)
            await session.commit()
            yield summary_result

    async def summarize_ranked_papers(
        self,
        *,
        session: AsyncSession,
        project: Project,
        ranked_papers: list[Paper],
    ) -> tuple[list[dict[str, object]], list[str]]:
        """Collect per-paper summary updates for synchronous pipeline runs."""

        summary_payloads: list[dict[str, object]] = []
        summary_errors: list[str] = []

        async for summary_result in self.stream_summary_results(
            session=session,
            project=project,
            ranked_papers=ranked_papers,
        ):
            summary_payloads.append(self._serialize_summary_result(summary_result))
            if summary_result.error_message is not None:
                summary_errors.append(summary_result.error_message)

        return summary_payloads, summary_errors

    async def rank_papers(
        self,
        topic_description: str,
        candidate_papers: list[Paper],
    ) -> tuple[list[Paper], list[str]]:
        """Rank candidate papers by cosine similarity to the topic embedding."""

        embedding_inputs = [
            topic_description,
            *[
                f"{paper.title}\n\n{paper.abstract or ''}"
                for paper in candidate_papers
            ],
        ]

        ranking_errors: list[str] = []
        try:
            embeddings = await self.embedding_service.embed_texts(
                embedding_inputs,
                feature="ranking_embedding",
            )
        except EmbeddingServiceError as error:
            embeddings = self.embedding_service.embed_texts_locally(embedding_inputs)
            ranking_errors.append(f"Embedding fallback used: {error}")

        topic_embedding = embeddings[0]
        paper_embeddings = embeddings[1:]

        for paper, paper_embedding in zip(candidate_papers, paper_embeddings, strict=True):
            similarity = cosine_similarity(topic_embedding, paper_embedding)
            paper.relevance_score = round(max(similarity, 0.0) * 100, 2)

        ranked_papers = sorted(
            candidate_papers,
            key=lambda paper: paper.relevance_score if paper.relevance_score is not None else 0.0,
            reverse=True,
        )

        return ranked_papers, ranking_errors

    def _persist_summary_result(
        self,
        *,
        session: AsyncSession,
        summary_result: SummaryGenerationResult,
    ) -> None:
        payload = summary_result.payload
        summary_record = summary_result.paper.summary
        if summary_record is None:
            summary_record = Summary(paper_id=summary_result.paper.id)
            session.add(summary_record)
            summary_result.paper.summary = summary_record

        summary_record.problem = payload.problem if payload is not None else None
        summary_record.method = payload.method if payload is not None else None
        summary_record.result = payload.result if payload is not None else None
        summary_record.relevance_to_topic = (
            payload.relevance_to_topic if payload is not None else None
        )
        summary_record.has_error = summary_result.has_error
        summary_record.error_message = summary_result.error_message
        summary_result.paper.status = "summary_error" if summary_result.has_error else "summarized"

    def _serialize_summary_result(
        self,
        summary_result: SummaryGenerationResult,
    ) -> dict[str, object]:
        summary_record = summary_result.paper.summary
        if summary_record is None:
            raise RuntimeError("Summary result was serialized before persistence.")

        return {
            "paper_id": summary_result.paper.id,
            "problem": summary_record.problem,
            "method": summary_record.method,
            "result": summary_record.result,
            "relevance_to_topic": summary_record.relevance_to_topic,
            "has_error": summary_record.has_error,
            "error_message": summary_record.error_message,
        }

    async def _stream_summary_generation(
        self,
        topic_description: str,
        ranked_papers: list[Paper],
    ) -> AsyncIterator[SummaryGenerationResult]:
        semaphore = asyncio.Semaphore(self.summary_concurrency)

        async def summarize_single_paper(paper: Paper) -> SummaryGenerationResult:
            async with semaphore:
                return await self._summarize_paper_with_retry(topic_description, paper)

        tasks = [asyncio.create_task(summarize_single_paper(paper)) for paper in ranked_papers]
        try:
            for task in asyncio.as_completed(tasks):
                yield await task
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _summarize_paper_with_retry(
        self,
        topic_description: str,
        paper: Paper,
    ) -> SummaryGenerationResult:
        if not self.summary_generator.is_configured():
            return SummaryGenerationResult(
                paper=paper,
                payload=self._build_fallback_summary(topic_description, paper),
            )

        last_error: str | None = None
        for _attempt in range(2):
            try:
                payload = await self.summary_generator.generate_json(
                    system_prompt=SUMMARY_SYSTEM_PROMPT,
                    user_prompt=self._build_summary_prompt(topic_description, paper),
                    schema=SUMMARY_SCHEMA,
                    max_tokens=900,
                    feature="paper_summary",
                )
                if not payload.get("relevance") and not payload.get("relevance_to_topic"):
                    payload["relevance"] = f"Relevant to the topic: {topic_description[:200]}"
                parsed_payload = PaperSummaryPayload.model_validate(payload)
                return SummaryGenerationResult(paper=paper, payload=parsed_payload)
            except (StructuredOutputError, ValidationError) as error:
                last_error = str(error)

        return SummaryGenerationResult(
            paper=paper,
            payload=None,
            error_message=(
                f"Summary generation failed for '{paper.title}' after two attempts: {last_error}"
            ),
        )

    def _build_summary_prompt(self, topic_description: str, paper: Paper) -> str:
        abstract = paper.abstract or ""
        return (
            f"Topic: {topic_description}\n"
            f"Paper title: {paper.title}\n"
            f"Paper abstract: {abstract}\n"
            "Summarize the paper into the required structured fields."
        )

    def _build_fallback_summary(
        self,
        topic_description: str,
        paper: Paper,
    ) -> PaperSummaryPayload:
        abstract = (paper.abstract or "").strip()
        sentences = [item.strip() for item in SENTENCE_SPLIT_PATTERN.split(abstract) if item.strip()]

        problem = sentences[0] if sentences else f"This paper studies {paper.title}."
        method = (
            sentences[1]
            if len(sentences) > 1
            else f"The paper proposes or evaluates an approach related to {paper.title}."
        )
        result = (
            sentences[2]
            if len(sentences) > 2
            else "The abstract reports findings that support the proposed approach."
        )
        relevance = (
            f"This paper is relevant to {topic_description} because it directly studies "
            f"{paper.title.lower()} and provides evidence that can inform the review topic."
        )

        return PaperSummaryPayload(
            problem=problem,
            method=method,
            result=result,
            relevance_to_topic=relevance,
        )
