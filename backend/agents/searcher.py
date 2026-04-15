import asyncio
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.state import AgentState
from backend.config import get_settings
from backend.db.models import Paper, Project, Summary
from backend.services import arxiv, semantic_scholar
from backend.services.llm import ClaudeStructuredOutputService, StructuredOutputError
from backend.services.paper_types import PaperRecord
from backend.services.reference_files import REFERENCE_SOURCE
from backend.services.research_utils import normalize_title, tokenize_text

SEARCH_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "focus": {"type": "string"},
                },
                "required": ["query", "focus"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["queries"],
    "additionalProperties": False,
}

QUERY_EXPANSION_SYSTEM_PROMPT = """
You are an expert academic search strategist.
Generate 5 to 8 concise, search-engine-friendly queries for finding peer-reviewed papers.
Rules:
- Stay tightly anchored to the user's topic. Do not invent application domains, datasets, tasks, or modalities that are not explicit in the topic.
- Prefer short keyword phrases that work in Semantic Scholar and arXiv.
- Avoid Boolean operators, parentheses, quotes, field syntax, and long natural-language sentences.
- If the topic names a specific model, system, method, or paper title, preserve that exact name in several queries and only vary nearby generic academic terms.
- Keep the focus labels short and concrete.
Return only JSON that matches the requested schema.
""".strip()

BOOLEAN_OPERATOR_PATTERN = re.compile(r"\b(?:AND|OR|NOT)\b", re.IGNORECASE)
PUNCTUATION_COLLAPSE_PATTERN = re.compile(r"[\"'`(){}\[\],;:]+")
WHITESPACE_PATTERN = re.compile(r"\s+")
REFERENCE_QUERY_STOPWORDS = {
    "about",
    "after",
    "analysis",
    "approach",
    "based",
    "between",
    "data",
    "dataset",
    "datasets",
    "during",
    "from",
    "into",
    "method",
    "methods",
    "model",
    "models",
    "paper",
    "result",
    "results",
    "study",
    "system",
    "that",
    "their",
    "this",
    "using",
    "with",
}


class SearchQuery(BaseModel):
    """A single expanded search query."""

    query: str = Field(min_length=3, max_length=255)
    focus: str = Field(min_length=1, max_length=255)


class SearchQueryBatch(BaseModel):
    """Structured response for query expansion."""

    queries: list[SearchQuery] = Field(min_length=5, max_length=8)


@dataclass(frozen=True)
class ReferencePaperContext:
    """Compact uploaded-paper context used to seed search."""

    title: str
    year: int | None
    abstract: str | None
    doi: str | None


class PaperSearchClient(Protocol):
    """Protocol for paper search providers."""

    async def search_papers(self, query: str, year_start: int, limit: int) -> list[PaperRecord]:
        """Search for papers matching the query."""


class SemanticScholarSearchClient:
    """Adapter for the Semantic Scholar search function."""

    async def search_papers(self, query: str, year_start: int, limit: int) -> list[PaperRecord]:
        return await semantic_scholar.search_papers(query, year_start, limit)


class ArxivSearchClient:
    """Adapter for the arXiv search function."""

    async def search_papers(self, query: str, year_start: int, limit: int) -> list[PaperRecord]:
        return await arxiv.search_papers(query, year_start, limit)


def get_candidate_metadata(
    candidate: PaperRecord,
    field_name: Literal["source_paper_id", "source_url", "pdf_url"],
) -> str | None:
    """Read optional candidate metadata without assuming legacy payloads include the key."""

    raw_value = candidate.get(field_name)
    if raw_value is None:
        return None

    normalized_value = str(raw_value).strip()
    return normalized_value or None


def serialize_paper_record(paper: Paper) -> dict[str, object]:
    """Serialize a paper ORM object into graph state."""

    return {
        "id": paper.id,
        "title": paper.title,
        "authors": list(paper.authors),
        "year": paper.year,
        "abstract": paper.abstract or "",
        "doi": paper.doi,
        "source": paper.source,
        "reference_file_id": paper.reference_file_id,
        "source_paper_id": paper.source_paper_id,
        "source_url": paper.source_url,
        "pdf_url": paper.pdf_url,
        "status": paper.status,
        "relevance_score": paper.relevance_score,
    }


class SearcherAgent:
    """Expand topic queries, search multiple sources, deduplicate, and persist candidates."""

    def __init__(
        self,
        *,
        llm_service: ClaudeStructuredOutputService | None = None,
        search_clients: list[PaperSearchClient] | None = None,
        minimum_abstract_length: int | None = None,
        per_query_limit: int | None = None,
    ) -> None:
        settings = get_settings()
        self.llm_service = llm_service or ClaudeStructuredOutputService()
        self.search_clients = search_clients or [
            SemanticScholarSearchClient(),
            ArxivSearchClient(),
        ]
        self.minimum_abstract_length = (
            minimum_abstract_length
            if minimum_abstract_length is not None
            else settings.minimum_abstract_length
        )
        self.per_query_limit = (
            per_query_limit if per_query_limit is not None else settings.search_results_per_query
        )

    async def run(
        self,
        state: AgentState,
        session: AsyncSession,
        project: Project,
    ) -> dict[str, Any]:
        """Populate candidate papers for the project."""

        reference_papers = await self._prepare_existing_project_papers(session, project.id)
        reference_context = self._build_reference_context(reference_papers)
        queries, candidates, errors = await self.collect_candidates(
            topic=project.topic_description,
            year_start=project.year_start,
            candidate_limit=project.candidate_limit,
            reference_context=reference_context,
            existing_papers=reference_papers,
        )

        paper_models: list[Paper] = []
        for candidate in candidates:
            paper = Paper(
                project_id=project.id,
                title=candidate["title"],
                authors=list(candidate["authors"]),
                year=candidate["year"],
                abstract=candidate["abstract"],
                doi=candidate["doi"],
                source=candidate["source"],
                source_paper_id=candidate.get("source_paper_id"),
                source_url=candidate.get("source_url"),
                pdf_url=candidate.get("pdf_url"),
                status="candidate",
                relevance_score=None,
            )
            session.add(paper)
            paper_models.append(paper)

        await session.flush()
        await session.commit()

        return {
            "queries": queries,
            "raw_papers": [
                serialize_paper_record(paper)
                for paper in [*reference_papers, *paper_models]
            ],
            "errors": [*state.errors, *errors],
        }

    async def _prepare_existing_project_papers(
        self,
        session: AsyncSession,
        project_id: str,
    ) -> list[Paper]:
        """Clear stale search outputs while preserving uploaded reference papers."""

        project_paper_ids = select(Paper.id).where(Paper.project_id == project_id)
        await session.execute(delete(Summary).where(Summary.paper_id.in_(project_paper_ids)))
        await session.execute(
            delete(Paper).where(
                Paper.project_id == project_id,
                Paper.source != REFERENCE_SOURCE,
            )
        )

        result = await session.execute(
            select(Paper).where(
                Paper.project_id == project_id,
                Paper.source == REFERENCE_SOURCE,
            )
        )
        reference_papers = list(result.scalars().all())
        for paper in reference_papers:
            paper.status = "candidate"
            paper.relevance_score = None

        return reference_papers

    def _build_reference_context(self, reference_papers: list[Paper]) -> list[ReferencePaperContext]:
        """Build compact reference context from uploaded papers."""

        return [
            ReferencePaperContext(
                title=paper.title,
                year=paper.year,
                abstract=paper.abstract,
                doi=paper.doi,
            )
            for paper in reference_papers
        ]

    async def collect_candidates(
        self,
        *,
        topic: str,
        year_start: int,
        candidate_limit: int,
        reference_context: list[ReferencePaperContext] | None = None,
        existing_papers: list[Paper] | None = None,
    ) -> tuple[list[str], list[PaperRecord], list[str]]:
        """Expand a topic into queries and collect deduplicated candidate papers."""

        query_batch, query_errors = await self.expand_queries(
            topic,
            reference_context=reference_context,
        )
        query_strings = [item.query for item in query_batch]
        per_query_limit = min(candidate_limit, self.per_query_limit)

        search_tasks = [
            client.search_papers(query_string, year_start, per_query_limit)
            for query_string in query_strings
            for client in self.search_clients
        ]
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        collected_papers: list[PaperRecord] = []
        errors = list(query_errors)
        for result in results:
            if isinstance(result, BaseException):
                errors.append(str(result))
                continue
            collected_papers.extend(result)

        candidates = self._filter_and_deduplicate(
            papers=collected_papers,
            year_start=year_start,
            candidate_limit=candidate_limit,
            existing_papers=existing_papers or [],
        )
        return query_strings, candidates, errors

    async def expand_queries(
        self,
        topic: str,
        *,
        reference_context: list[ReferencePaperContext] | None = None,
    ) -> tuple[list[SearchQuery], list[str]]:
        """Expand a project topic into diverse search queries."""

        reference_context = reference_context or []
        if self._should_use_named_entity_queries(topic) and not reference_context:
            return self._build_named_entity_queries(topic), []

        if not self.llm_service.is_configured():
            return self._build_fallback_queries(topic, reference_context=reference_context), []

        user_prompt = self._build_query_expansion_prompt(topic, reference_context)

        try:
            payload = await self.llm_service.generate_json(
                system_prompt=QUERY_EXPANSION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=SEARCH_QUERY_SCHEMA,
            )
            queries = self._coerce_query_payload(payload, topic)
            query_batch = SearchQueryBatch(queries=queries)
        except (StructuredOutputError, ValidationError, ValueError) as error:
            fallback_queries = self._build_fallback_queries(
                topic,
                reference_context=reference_context,
            )
            return fallback_queries, [f"Query expansion fallback used: {error}"]

        return query_batch.queries, []

    def _build_query_expansion_prompt(
        self,
        topic: str,
        reference_context: list[ReferencePaperContext],
    ) -> str:
        """Build the query expansion prompt with optional uploaded-reference context."""

        prompt = (
            "Generate 5 to 8 academic search queries for this literature review topic.\n"
            f"Topic: {topic}"
        )
        if not reference_context:
            return prompt

        reference_lines = []
        for index, reference in enumerate(reference_context[:5], start=1):
            year = f" ({reference.year})" if reference.year is not None else ""
            abstract = (reference.abstract or "").replace("\n", " ")[:700]
            reference_lines.append(
                f"{index}. {reference.title}{year}. Abstract/snippet: {abstract}"
            )

        return (
            f"{prompt}\n\n"
            "The user has already uploaded these seed reference papers. Use them to generate "
            "queries for related work, missing background, and adjacent papers. Do not simply "
            "repeat only the uploaded titles.\n"
            + "\n".join(reference_lines)
        )

    def _build_fallback_queries(
        self,
        topic: str,
        *,
        reference_context: list[ReferencePaperContext] | None = None,
    ) -> list[SearchQuery]:
        normalized_topic = self._sanitize_query_text(topic)
        query_candidates = [
            (normalized_topic, "broad"),
            (f"{normalized_topic} survey", "broad-survey"),
            (f"{normalized_topic} systematic review", "review"),
            (f"{normalized_topic} recent advances", "recent"),
            (f"{normalized_topic} benchmark dataset", "dataset"),
            (f"{normalized_topic} neural network methods", "technique"),
            (f"{normalized_topic} application study", "application"),
            (f"{normalized_topic} empirical evaluation", "evaluation"),
        ]

        for reference_query in self._build_reference_fallback_queries(
            normalized_topic,
            reference_context or [],
        ):
            query_candidates.append(reference_query)

        deduplicated_queries: list[SearchQuery] = []
        seen_queries: set[str] = set()
        for raw_query, focus in query_candidates:
            normalized_query = raw_query.lower().strip()
            if normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            deduplicated_queries.append(SearchQuery(query=raw_query, focus=focus))

        return deduplicated_queries[:8]

    def _build_reference_fallback_queries(
        self,
        normalized_topic: str,
        reference_context: list[ReferencePaperContext],
    ) -> list[tuple[str, str]]:
        if not reference_context:
            return []

        token_counts: Counter[str] = Counter()
        for reference in reference_context:
            token_counts.update(
                token
                for token in tokenize_text(f"{reference.title} {reference.abstract or ''}")
                if len(token) > 3 and token not in REFERENCE_QUERY_STOPWORDS
            )

        queries: list[tuple[str, str]] = []
        top_terms = [token for token, _count in token_counts.most_common(8)]
        for index in range(0, len(top_terms), 2):
            term_pair = " ".join(top_terms[index : index + 2])
            if term_pair:
                queries.append((f"{normalized_topic} {term_pair}", "uploaded-reference"))

        return queries[:3]

    def _build_named_entity_queries(self, topic: str) -> list[SearchQuery]:
        normalized_topic = self._sanitize_query_text(topic)
        query_candidates = [
            (normalized_topic, "exact-name"),
            (f"{normalized_topic} paper", "paper"),
            (f"{normalized_topic} model", "model"),
            (f"{normalized_topic} architecture", "architecture"),
            (f"{normalized_topic} benchmark", "benchmark"),
            (f"{normalized_topic} survey", "survey"),
            (f"{normalized_topic} evaluation", "evaluation"),
            (f"{normalized_topic} recent work", "recent"),
        ]
        return self._deduplicate_queries(
            SearchQuery(query=query, focus=focus)
            for query, focus in query_candidates
        )[:6]

    def _coerce_query_payload(self, payload: dict[str, Any], topic: str) -> list[SearchQuery]:
        raw_queries = payload.get("queries")
        if not isinstance(raw_queries, list):
            raise ValueError("Model response did not contain a queries list.")

        queries: list[SearchQuery] = []
        for raw_item in raw_queries:
            if not isinstance(raw_item, dict):
                continue

            query_text = self._sanitize_query_text(str(raw_item.get("query", "")))
            focus = self._normalize_focus(str(raw_item.get("focus", "")))
            if len(query_text) < 3 or not focus:
                continue

            queries.append(SearchQuery(query=query_text, focus=focus))

        if not queries:
            raise ValueError("Model response did not contain usable queries.")

        deduplicated_queries = self._deduplicate_queries(queries)
        if len(deduplicated_queries) < 5:
            fallback_queries = self._build_fallback_queries(topic)
            deduplicated_queries = self._deduplicate_queries([*deduplicated_queries, *fallback_queries])

        return deduplicated_queries[:8]

    def _deduplicate_queries(self, queries: list[SearchQuery] | Any) -> list[SearchQuery]:
        deduplicated_queries: list[SearchQuery] = []
        seen_queries: set[str] = set()
        for query in queries:
            normalized_query = query.query.lower().strip()
            if normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            deduplicated_queries.append(query)
        return deduplicated_queries

    def _sanitize_query_text(self, text: str) -> str:
        sanitized = BOOLEAN_OPERATOR_PATTERN.sub(" ", text)
        sanitized = PUNCTUATION_COLLAPSE_PATTERN.sub(" ", sanitized)
        sanitized = WHITESPACE_PATTERN.sub(" ", sanitized).strip()
        return sanitized[:255]

    def _normalize_focus(self, focus: str) -> str:
        normalized_focus = WHITESPACE_PATTERN.sub(" ", focus).strip()
        if not normalized_focus:
            return "general"
        return normalized_focus[:255]

    def _should_use_named_entity_queries(self, topic: str) -> bool:
        normalized_topic = " ".join(topic.split())
        topic_tokens = normalized_topic.split()
        if not normalized_topic or len(topic_tokens) > 4:
            return False

        if any(character.isdigit() for character in normalized_topic):
            return True
        if any(character.isupper() for character in normalized_topic[1:]):
            return True
        return len(topic_tokens) == 1 and normalized_topic[:1].isupper()

    def _filter_and_deduplicate(
        self,
        *,
        papers: list[PaperRecord],
        year_start: int,
        candidate_limit: int,
        existing_papers: list[Paper] | None = None,
    ) -> list[PaperRecord]:
        filtered_papers = [
            paper
            for paper in papers
            if paper["year"] is not None
            and paper["year"] >= year_start
            and paper["abstract"].strip()
            and len(paper["abstract"].strip()) >= self.minimum_abstract_length
        ]

        prioritized_papers = sorted(
            filtered_papers,
            key=lambda paper: (
                paper["doi"] is not None,
                len(paper["abstract"]),
                paper["source"] == "semantic_scholar",
            ),
            reverse=True,
        )

        unique_papers: list[PaperRecord] = []
        seen_dois: set[str] = {
            paper.doi.lower().strip()
            for paper in existing_papers or []
            if paper.doi is not None and paper.doi.strip()
        }
        seen_titles: set[str] = {
            normalize_title(paper.title)
            for paper in existing_papers or []
            if paper.title.strip()
        }

        for paper in prioritized_papers:
            normalized_doi = paper["doi"].lower().strip() if paper["doi"] is not None else None
            normalized_paper_title = normalize_title(paper["title"])

            if normalized_doi is not None and normalized_doi in seen_dois:
                continue
            if normalized_paper_title in seen_titles:
                continue

            if normalized_doi is not None:
                seen_dois.add(normalized_doi)
            seen_titles.add(normalized_paper_title)
            unique_papers.append(paper)

        return unique_papers[:candidate_limit]
