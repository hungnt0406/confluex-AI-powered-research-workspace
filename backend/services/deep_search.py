from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.db.models import DeepSearchRun, DeepSearchSource, Paper, PaperChunk, Project, User
from backend.services import arxiv, semantic_scholar
from backend.services.ai_usage import collect_openrouter_usage
from backend.services.llm import OpenRouterStructuredOutputService, StructuredOutputError
from backend.services.paper_types import PaperRecord
from backend.services.research_utils import has_live_api_key
from backend.services.tavily import TavilySearchService

MAX_PLAN_QUESTIONS = 5
MIN_PLAN_QUESTIONS = 3
MAX_SELECTED_DEEP_SEARCH_PAPERS = 5
MAX_SOURCE_SNIPPET_CHARS = 900
MAX_SOURCE_TITLE_CHARS = 500
MAX_CHUNKS_PER_SELECTED_PAPER = 2
MAX_REPORT_TOKENS = 1_800
SOURCE_CITATION_PATTERN = re.compile(r"\[S(\d+)\]")

SourceType = Literal["paper", "paper_chunk", "citation_graph", "web"]
DeepSearchEventName = Literal["run", "status", "activity", "source", "token", "done", "error"]
AcademicSearchCallable = Callable[[str, int, int], Awaitable[list[PaperRecord]]]


@dataclass(frozen=True)
class DeepSearchSourceCandidate:
    """Raw source found during a deep search run before persistence."""

    source_type: SourceType
    title: str
    url: str | None
    paper_id: str | None
    snippet: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeepSearchStreamEvent:
    """Internal event emitted by DeepSearchService."""

    event: DeepSearchEventName
    data: dict[str, Any] | DeepSearchRun


async def default_semantic_scholar_search(
    query: str,
    year_start: int,
    limit: int,
) -> list[PaperRecord]:
    return await semantic_scholar.search_papers(query, year_start, limit)


async def default_arxiv_search(query: str, year_start: int, limit: int) -> list[PaperRecord]:
    return await arxiv.search_papers(query, year_start, limit)


def ensure_deep_search_allowed(current_user: User) -> None:
    """Centralized access hook for future paid gating."""

    _ = current_user


def deduplicate_source_candidates(
    candidates: list[DeepSearchSourceCandidate],
) -> list[DeepSearchSourceCandidate]:
    """Deduplicate sources by normalized URL, project paper id, provider id, then title."""

    seen_keys: set[str] = set()
    deduped: list[DeepSearchSourceCandidate] = []
    for candidate in candidates:
        key = _source_dedupe_key(candidate)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(candidate)
    return deduped


def verify_report_claims(
    report_body: str,
    source_summaries: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Run a small deterministic QA pass for missing and web-only citations."""

    source_type_by_id = {
        str(summary.get("id", "")).strip(): str(summary.get("source_type", "")).strip()
        for summary in source_summaries
    }
    flags: list[dict[str, str]] = []
    for sentence in _iter_claim_sentences(report_body):
        citation_ids = [f"S{match}" for match in SOURCE_CITATION_PATTERN.findall(sentence)]
        if not citation_ids:
            flags.append(
                {
                    "issue": "Claim appears without a source citation.",
                    "severity": "warning",
                    "location": sentence[:160],
                }
            )
            continue

        citation_types = [
            source_type_by_id[source_id]
            for source_id in citation_ids
            if source_id in source_type_by_id
        ]
        if citation_types and all(source_type == "web" for source_type in citation_types):
            flags.append(
                {
                    "issue": "Claim relies only on web sources.",
                    "severity": "warning",
                    "location": sentence[:160],
                }
            )
    return flags


class DeepSearchService:
    """Orchestrate project evidence, academic search, Tavily web search, and report writing."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        planner_model: str | None = None,
        research_model: str | None = None,
        summarizer_model: str | None = None,
        writer_model: str | None = None,
        verifier_model: str | None = None,
        max_web_searches: int | None = None,
        max_iterations: int | None = None,
        max_results_per_query: int | None = None,
        use_live_llm: bool | None = None,
        http_client: httpx.AsyncClient | None = None,
        tavily_service: TavilySearchService | None = None,
        semantic_scholar_search: AcademicSearchCallable | None = None,
        arxiv_search: AcademicSearchCallable | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.base_url = (
            base_url.rstrip("/") if base_url is not None else settings.openrouter_base_url.rstrip("/")
        )
        self.planner_model = planner_model or settings.deep_search_planner_model
        self.research_model = research_model or settings.deep_search_research_model
        self.summarizer_model = summarizer_model or settings.deep_search_summarizer_model
        self.writer_model = writer_model or settings.deep_search_writer_model
        self.verifier_model = verifier_model or settings.deep_search_verifier_model
        self.max_web_searches = max_web_searches or settings.deep_search_max_web_searches
        self.max_iterations = max_iterations or settings.deep_search_max_iterations
        self.max_results_per_query = max_results_per_query or settings.deep_search_max_results_per_query
        self.use_live_llm = (
            use_live_llm if use_live_llm is not None else has_live_api_key(self.api_key)
        )
        self.http_client = http_client
        self.timeout_seconds = settings.external_api_timeout_seconds
        self.tavily_service = tavily_service or TavilySearchService()
        self.semantic_scholar_search = semantic_scholar_search or default_semantic_scholar_search
        self.arxiv_search = arxiv_search or default_arxiv_search

    async def stream_run(
        self,
        *,
        session: AsyncSession,
        project: Project,
        question: str,
        selected_papers: list[Paper],
    ) -> AsyncIterator[DeepSearchStreamEvent]:
        """Create, execute, persist, and stream one deep search run."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        run = DeepSearchRun(
            project_id=project.id,
            user_prompt=normalized_question,
            status="running",
            selected_paper_ids_json=[paper.id for paper in selected_papers],
            plan_json={},
            source_summary_json={},
            warnings_json=[],
            qa_flags_json=[],
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id
        yield DeepSearchStreamEvent("run", run)

        warnings: list[str] = []

        try:
            yield DeepSearchStreamEvent("status", {"phase": "planning"})
            try:
                questions = await self._plan_questions(
                    project_title=project.title,
                    project_topic=project.topic_description,
                    question=normalized_question,
                )
            except StructuredOutputError as error:
                questions = self._build_local_plan_questions(normalized_question)
                warnings.append(f"Deep Search planner fell back to local planning: {error}")
            plan_payload = {
                "questions": questions,
                "max_iterations": self.max_iterations,
                "models": {
                    "planner": self.planner_model,
                    "research": self.research_model,
                    "summarizer": self.summarizer_model,
                    "writer": self.writer_model,
                    "verifier": self.verifier_model,
                },
            }
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    phase="planning",
                    title="Identifying research domains",
                    detail=_planning_activity_detail(questions),
                ),
            )

            candidates: list[DeepSearchSourceCandidate] = []

            yield DeepSearchStreamEvent("status", {"phase": "project_evidence"})
            project_candidates = await self._collect_project_sources(
                session=session,
                selected_papers=selected_papers,
            )
            candidates.extend(project_candidates)
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    phase="project_evidence",
                    title="Reading selected project evidence",
                    detail=_source_activity_detail(
                        project_candidates,
                        empty_detail="No selected project paper evidence was available, so I will rely on external academic and web sources.",
                        populated_detail="I found project-local evidence to anchor the search before expanding outward.",
                    ),
                    sources=_source_activity_sources(project_candidates),
                ),
            )

            yield DeepSearchStreamEvent("status", {"phase": "academic_search"})
            academic_candidates, academic_warnings = await self._collect_academic_sources(
                project=project,
                questions=questions,
            )
            candidates.extend(academic_candidates)
            warnings.extend(academic_warnings)
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    phase="academic_search",
                    title="Mapping the academic evidence",
                    detail=_source_activity_detail(
                        academic_candidates,
                        empty_detail="The scholarly providers did not return usable abstracts for the planned questions.",
                        populated_detail="I found scholarly sources that can support or challenge the answer.",
                    ),
                    sources=_source_activity_sources(academic_candidates),
                ),
            )

            yield DeepSearchStreamEvent("status", {"phase": "web_search"})
            web_candidates, web_warnings, web_metadata = await self._collect_web_sources(questions)
            candidates.extend(web_candidates)
            warnings.extend(web_warnings)
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    phase="web_search",
                    title="Researching websites",
                    detail=_source_activity_detail(
                        web_candidates,
                        empty_detail="No usable web results were returned for the planned questions.",
                        populated_detail="I found current web sources and implementation context to compare with the paper evidence.",
                    ),
                    sources=_source_activity_sources(web_candidates),
                ),
            )

            source_candidates = deduplicate_source_candidates(candidates)
            indexed_sources = [
                (f"S{source_index}", source_candidate)
                for source_index, source_candidate in enumerate(source_candidates, start=1)
            ]

            yield DeepSearchStreamEvent("status", {"phase": "summarizing_sources"})
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    phase="summarizing_sources",
                    title="Condensing source evidence",
                    detail=(
                        f"I am turning {len(indexed_sources)} deduplicated sources into compact evidence notes "
                        "before writing the final synthesis."
                    )
                    if indexed_sources
                    else "I did not find source candidates, so I will produce a limited report with warnings.",
                ),
            )
            source_summaries, summarizer_warning = await self._summarize_sources(
                question=normalized_question,
                indexed_sources=indexed_sources,
            )
            if summarizer_warning:
                warnings.append(summarizer_warning)
            for source_summary in source_summaries:
                yield DeepSearchStreamEvent("source", source_summary)

            yield DeepSearchStreamEvent("status", {"phase": "writing"})
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    phase="writing",
                    title="Synthesizing the answer",
                    detail=(
                        "I am organizing the evidence into a report and attaching source IDs "
                        "to factual claims."
                    ),
                ),
            )
            report_parts: list[str] = []
            async for token in self._stream_report(
                question=normalized_question,
                project=project,
                plan_questions=questions,
                source_summaries=source_summaries,
                warnings=_dedupe_strings(warnings),
            ):
                report_parts.append(token)
                yield DeepSearchStreamEvent("token", {"delta": token})
            report_body = "".join(report_parts).strip()
            if not report_body:
                raise RuntimeError("Deep search report writer returned no content.")

            yield DeepSearchStreamEvent("status", {"phase": "verifying"})
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    phase="verifying",
                    title="Checking citation coverage",
                    detail="I am scanning the drafted report for uncited claims and weak citation patterns.",
                ),
            )
            qa_flags, verifier_warning = await self._verify_report(
                report_body=report_body,
                source_summaries=source_summaries,
            )
            if verifier_warning:
                warnings.append(verifier_warning)

            await self._persist_success(
                session=session,
                run_id=run_id,
                plan_payload=plan_payload,
                source_candidates=indexed_sources,
                source_summaries=source_summaries,
                report_body=report_body,
                warnings=_dedupe_strings(warnings),
                qa_flags=qa_flags,
                web_metadata=web_metadata,
            )
            completed_run = await self._load_run(session=session, run_id=run_id)
            yield DeepSearchStreamEvent("done", completed_run)
        except Exception as error:
            await session.rollback()
            await self._mark_failed(session=session, run_id=run_id, detail=str(error))
            yield DeepSearchStreamEvent("error", {"detail": str(error), "run_id": run_id})

    async def _plan_questions(
        self,
        *,
        project_title: str,
        project_topic: str,
        question: str,
    ) -> list[str]:
        if self.use_live_llm:
            parsed = await self._generate_json(
                model=self.planner_model,
                feature="deep_search_planning",
                system_prompt=(
                    "You are a deep search planner. Return 3 to 5 focused research questions "
                    "that cover academic evidence, project evidence, and current web evidence."
                ),
                user_prompt=(
                    f"Project title: {project_title}\n"
                    f"Project topic: {project_topic}\n"
                    f"User question: {question}"
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "questions": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": MAX_PLAN_QUESTIONS,
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["questions"],
                    "additionalProperties": False,
                },
                max_tokens=700,
            )
            raw_questions = parsed.get("questions", [])
            if not isinstance(raw_questions, list):
                raise RuntimeError("Deep search planner returned invalid questions.")
            questions = [str(item).strip() for item in raw_questions if str(item).strip()]
            if not questions:
                raise RuntimeError("Deep search planner returned no usable questions.")
            return _normalize_plan_questions(question, questions)

        return self._build_local_plan_questions(question)

    def _build_local_plan_questions(self, question: str) -> list[str]:
        seed_questions = [
            question,
            f"What recent academic evidence addresses {question}?",
            f"What methods, results, and limitations are reported for {question}?",
            f"What current web evidence or implementation context is relevant to {question}?",
        ]
        return _normalize_plan_questions(question, seed_questions)

    async def _collect_project_sources(
        self,
        *,
        session: AsyncSession,
        selected_papers: list[Paper],
    ) -> list[DeepSearchSourceCandidate]:
        candidates: list[DeepSearchSourceCandidate] = []
        for paper in selected_papers[:MAX_SELECTED_DEEP_SEARCH_PAPERS]:
            snippet = _paper_evidence_snippet(paper)
            if snippet:
                candidates.append(
                    DeepSearchSourceCandidate(
                        source_type="paper",
                        title=paper.title,
                        url=paper.source_url,
                        paper_id=paper.id,
                        snippet=snippet,
                        metadata={
                            "authors": list(paper.authors),
                            "year": paper.year,
                            "doi": paper.doi,
                            "source": paper.source,
                            "source_paper_id": paper.source_paper_id,
                            "relevance_score": paper.relevance_score,
                        },
                    )
                )

            result = await session.execute(
                select(PaperChunk)
                .where(PaperChunk.paper_id == paper.id)
                .order_by(PaperChunk.chunk_index.asc())
                .limit(MAX_CHUNKS_PER_SELECTED_PAPER)
            )
            chunks = result.scalars().all()
            for chunk in chunks:
                candidates.append(
                    DeepSearchSourceCandidate(
                        source_type="paper_chunk",
                        title=f"{paper.title} (pages {chunk.page_start}-{chunk.page_end})",
                        url=paper.source_url or paper.pdf_url,
                        paper_id=paper.id,
                        snippet=_compact_text(chunk.content),
                        metadata={
                            "paper_title": paper.title,
                            "chunk_id": chunk.id,
                            "chunk_index": chunk.chunk_index,
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                            "section_title": chunk.section_title,
                        },
                    )
                )
        return candidates

    async def _collect_academic_sources(
        self,
        *,
        project: Project,
        questions: list[str],
    ) -> tuple[list[DeepSearchSourceCandidate], list[str]]:
        candidates: list[DeepSearchSourceCandidate] = []
        warnings: list[str] = []
        search_questions = questions[: max(1, min(self.max_web_searches, len(questions)))]

        for query in search_questions:
            provider_calls: list[tuple[str, AcademicSearchCallable]] = [
                ("semantic_scholar", self.semantic_scholar_search),
                ("arxiv", self.arxiv_search),
            ]
            for provider_name, search in provider_calls:
                try:
                    papers = await search(query, project.year_start, self.max_results_per_query)
                except Exception:
                    warnings.append(f"{provider_name} search failed for query '{query}'.")
                    continue
                for paper_record in papers:
                    snippet = _compact_text(paper_record.get("abstract", ""))
                    if not snippet:
                        continue
                    candidates.append(
                        DeepSearchSourceCandidate(
                            source_type="paper",
                            title=paper_record["title"],
                            url=paper_record["source_url"],
                            paper_id=None,
                            snippet=snippet,
                            metadata={
                                "provider": provider_name,
                                "query": query,
                                "authors": list(paper_record["authors"]),
                                "year": paper_record["year"],
                                "doi": paper_record["doi"],
                                "source": paper_record["source"],
                                "source_paper_id": paper_record["source_paper_id"],
                                "pdf_url": paper_record["pdf_url"],
                                "citation_count": paper_record["citation_count"],
                                "reference_count": paper_record["reference_count"],
                            },
                        )
                    )
        return candidates, _dedupe_strings(warnings)

    async def _collect_web_sources(
        self,
        questions: list[str],
    ) -> tuple[list[DeepSearchSourceCandidate], list[str], dict[str, Any]]:
        candidates: list[DeepSearchSourceCandidate] = []
        warnings: list[str] = []
        metadata = {
            "tavily_search_count": 0,
            "tavily_result_count": 0,
            "tavily_configured": self.tavily_service.is_configured(),
        }
        for query in questions[: self.max_web_searches]:
            metadata["tavily_search_count"] += 1
            response = await self.tavily_service.search(
                query,
                max_results=self.max_results_per_query,
            )
            warnings.extend(response.warnings)
            for result in response.results:
                snippet = _compact_text(result.content)
                if not snippet:
                    continue
                candidates.append(
                    DeepSearchSourceCandidate(
                        source_type="web",
                        title=result.title,
                        url=result.url,
                        paper_id=None,
                        snippet=snippet,
                        metadata={
                            **result.metadata,
                            "query": query,
                            "score": result.score,
                        },
                    )
                )
        metadata["tavily_result_count"] = len(candidates)
        return candidates, _dedupe_strings(warnings), metadata

    async def _summarize_sources(
        self,
        *,
        question: str,
        indexed_sources: list[tuple[str, DeepSearchSourceCandidate]],
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not indexed_sources:
            return [], None

        local_summaries = [
            _source_summary(source_id, source_candidate, note=_compact_text(source_candidate.snippet))
            for source_id, source_candidate in indexed_sources
        ]
        if not self.use_live_llm:
            return local_summaries, None

        evidence_payload = "\n\n".join(
            (
                f"{index}. [{source_id}] {source_candidate.source_type}: "
                f"{source_candidate.title}\n{source_candidate.snippet}"
            )
            for index, (source_id, source_candidate) in enumerate(indexed_sources, start=1)
        )
        try:
            parsed = await self._generate_json(
                model=self.summarizer_model,
                feature="deep_search_web_summarization",
                system_prompt=(
                    "You are an evidence compressor. Condense each source into one factual note. "
                    "Do not add facts not present in the snippet."
                ),
                user_prompt=f"Question: {question}\n\nSources:\n{evidence_payload}",
                schema={
                    "type": "object",
                    "properties": {
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source_index": {"type": "integer"},
                                    "note": {"type": "string"},
                                },
                                "required": ["source_index", "note"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["sources"],
                    "additionalProperties": False,
                },
                max_tokens=1_000,
            )
        except StructuredOutputError as error:
            return (
                local_summaries,
                f"Deep Search source summarizer fell back to local source notes: {error}",
            )
        raw_sources = parsed.get("sources", [])
        if not isinstance(raw_sources, list):
            raise RuntimeError("Deep search source summarizer returned invalid source notes.")

        notes_by_index: dict[int, str] = {}
        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            raw_index = item.get("source_index")
            raw_note = item.get("note")
            if isinstance(raw_index, int) and isinstance(raw_note, str) and raw_note.strip():
                notes_by_index[raw_index] = _compact_text(raw_note)

        summarized: list[dict[str, Any]] = []
        for index, (source_id, source_candidate) in enumerate(indexed_sources, start=1):
            note = notes_by_index.get(index) or _compact_text(source_candidate.snippet)
            summarized.append(_source_summary(source_id, source_candidate, note=note))
        return summarized, None

    async def _stream_report(
        self,
        *,
        question: str,
        project: Project,
        plan_questions: list[str],
        source_summaries: list[dict[str, Any]],
        warnings: list[str],
    ) -> AsyncGenerator[str, None]:
        if self.use_live_llm:
            async for token in self._stream_live_report(
                question=question,
                project=project,
                plan_questions=plan_questions,
                source_summaries=source_summaries,
                warnings=warnings,
            ):
                yield token
            return

        report = self._generate_local_report(
            question=question,
            project=project,
            plan_questions=plan_questions,
            source_summaries=source_summaries,
            warnings=warnings,
        )
        for chunk in _chunk_report(report):
            yield chunk
            await asyncio.sleep(0)

    async def _stream_live_report(
        self,
        *,
        question: str,
        project: Project,
        plan_questions: list[str],
        source_summaries: list[dict[str, Any]],
        warnings: list[str],
    ) -> AsyncGenerator[str, None]:
        if not has_live_api_key(self.api_key):
            raise RuntimeError("OpenRouter API credentials are not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.writer_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a deep research report writer. Write a concise, evidence-grounded "
                        "report. Cite every factual claim with source ids like [S1]."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_writer_prompt(
                        question=question,
                        project=project,
                        plan_questions=plan_questions,
                        source_summaries=source_summaries,
                        warnings=warnings,
                    ),
                },
            ],
            "max_tokens": MAX_REPORT_TOKENS,
            "temperature": 0.2,
            "provider": {"sort": "price"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
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
                        raise RuntimeError("OpenRouter deep-search writer returned invalid JSON.") from error
                    if not isinstance(event_payload, dict):
                        continue
                    if "error" in event_payload:
                        raise RuntimeError(self._format_openrouter_stream_error(event_payload["error"]))
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
                        yield content
        except httpx.HTTPError as error:
            raise RuntimeError("OpenRouter deep-search report writer failed.") from error
        finally:
            if owns_client:
                await client.aclose()

        if usage_payload is not None:
            collect_openrouter_usage(
                endpoint="chat/completions",
                feature="deep_search_report_writer",
                model=self.writer_model,
                response_payload=usage_payload,
                metadata={"stream": True, "source_count": len(source_summaries)},
            )

    async def _verify_report(
        self,
        *,
        report_body: str,
        source_summaries: list[dict[str, Any]],
    ) -> tuple[list[dict[str, str]], str | None]:
        local_flags = verify_report_claims(report_body, source_summaries)
        if not self.use_live_llm:
            return local_flags, None

        try:
            parsed = await self._generate_json(
                model=self.verifier_model,
                feature="deep_search_verifier",
                system_prompt=(
                    "You are a deep search verifier. Return QA flags for uncited claims, weak "
                    "evidence, and web-only claims. Use severity warning or error."
                ),
                user_prompt=(
                    f"Report:\n{report_body}\n\nSource summaries:\n"
                    f"{json.dumps(source_summaries, ensure_ascii=True)}"
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "qa_flags": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "issue": {"type": "string"},
                                    "severity": {"type": "string", "enum": ["warning", "error"]},
                                    "location": {"type": "string"},
                                },
                                "required": ["issue", "severity", "location"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["qa_flags"],
                    "additionalProperties": False,
                },
                max_tokens=900,
            )
        except StructuredOutputError as error:
            return local_flags, f"Deep Search verifier fell back to local QA checks: {error}"
        raw_flags = parsed.get("qa_flags", [])
        if not isinstance(raw_flags, list):
            raise RuntimeError("Deep search verifier returned invalid QA flags.")
        return _normalize_qa_flags(raw_flags), None

    async def _persist_success(
        self,
        *,
        session: AsyncSession,
        run_id: str,
        plan_payload: dict[str, Any],
        source_candidates: list[tuple[str, DeepSearchSourceCandidate]],
        source_summaries: list[dict[str, Any]],
        report_body: str,
        warnings: list[str],
        qa_flags: list[dict[str, str]],
        web_metadata: dict[str, Any],
    ) -> None:
        completed_at = datetime.now(UTC)
        source_summary = {
            "sources": source_summaries,
            "metadata": {
                **web_metadata,
                "source_count": len(source_summaries),
            },
        }
        await session.execute(
            update(DeepSearchRun)
            .where(DeepSearchRun.id == run_id)
            .values(
                status="completed",
                plan_json=plan_payload,
                report_body=report_body,
                source_summary_json=source_summary,
                warnings_json=warnings,
                qa_flags_json=qa_flags,
                completed_at=completed_at,
                updated_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )

        notes_by_id = {
            str(summary.get("id", "")).strip(): str(summary.get("note", "")).strip()
            for summary in source_summaries
        }
        for source_id, source_candidate in source_candidates:
            metadata = {
                **source_candidate.metadata,
                "source_id": source_id,
                "note": notes_by_id.get(source_id, ""),
            }
            session.add(
                DeepSearchSource(
                    run_id=run_id,
                    source_type=source_candidate.source_type,
                    title=_truncate(source_candidate.title, MAX_SOURCE_TITLE_CHARS),
                    url=source_candidate.url,
                    paper_id=source_candidate.paper_id,
                    snippet=_compact_text(source_candidate.snippet),
                    metadata_json=metadata,
                )
            )
        await session.commit()

    async def _mark_failed(self, *, session: AsyncSession, run_id: str, detail: str) -> None:
        completed_at = datetime.now(UTC)
        await session.execute(
            update(DeepSearchRun)
            .where(DeepSearchRun.id == run_id)
            .values(
                status="failed",
                warnings_json=[detail],
                completed_at=completed_at,
                updated_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )
        await session.commit()

    async def _get_run_for_update(self, *, session: AsyncSession, run_id: str) -> DeepSearchRun:
        run = await session.get(DeepSearchRun, run_id)
        if run is None:
            raise RuntimeError("Deep search run could not be loaded.")
        return run

    async def _load_run(self, *, session: AsyncSession, run_id: str) -> DeepSearchRun:
        result = await session.execute(
            select(DeepSearchRun)
            .options(selectinload(DeepSearchRun.sources))
            .execution_options(populate_existing=True)
            .where(DeepSearchRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise RuntimeError("Deep search run could not be reloaded.")
        return run

    async def _generate_json(
        self,
        *,
        model: str,
        feature: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
    ) -> dict[str, Any]:
        service = OpenRouterStructuredOutputService(
            api_key=self.api_key,
            model=model,
            base_url=self.base_url,
            http_client=self.http_client,
        )
        return await service.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
            max_tokens=max_tokens,
            feature=feature,
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
        return "OpenRouter deep-search report writer failed."

    def _build_writer_prompt(
        self,
        *,
        question: str,
        project: Project,
        plan_questions: list[str],
        source_summaries: list[dict[str, Any]],
        warnings: list[str],
    ) -> str:
        return "\n".join(
            [
                f"Project: {project.title}",
                f"Topic: {project.topic_description}",
                f"User question: {question}",
                "",
                "Research questions:",
                *[f"- {plan_question}" for plan_question in plan_questions],
                "",
                "Evidence notes:",
                *[
                    (
                        f"- [{summary['id']}] {summary['source_type']} | "
                        f"{summary['title']} | {summary['note']}"
                    )
                    for summary in source_summaries
                ],
                "",
                "Warnings:",
                *(f"- {warning}" for warning in warnings),
            ]
        ).strip()

    def _generate_local_report(
        self,
        *,
        question: str,
        project: Project,
        plan_questions: list[str],
        source_summaries: list[dict[str, Any]],
        warnings: list[str],
    ) -> str:
        if not source_summaries:
            return "\n\n".join(
                [
                    "# Deep Search Report",
                    "## Answer",
                    (
                        "I could not find project, academic, or web evidence for this run. "
                        "Try selecting papers, uploading PDFs, or configuring Tavily for web search."
                    ),
                    "## Search Plan",
                    "\n".join(f"- {plan_question}" for plan_question in plan_questions),
                    "## Warnings",
                    "\n".join(f"- {warning}" for warning in warnings) if warnings else "- None",
                ]
            )

        top_sources = source_summaries[:5]
        answer_lines = [
            (
                f"For **{project.title}**, the available evidence for \"{question}\" is strongest "
                f"where project papers, academic sources, and web results converge."
            )
        ]
        for summary in top_sources[:3]:
            answer_lines.append(f"- {summary['note']} [{summary['id']}]")

        return "\n\n".join(
            [
                "# Deep Search Report",
                "## Answer",
                "\n".join(answer_lines),
                "## Search Plan",
                "\n".join(f"- {plan_question}" for plan_question in plan_questions),
                "## Evidence Notes",
                "\n".join(
                    (
                        f"- [{summary['id']}] **{summary['title']}** "
                        f"({summary['source_type']}): {summary['note']}"
                    )
                    for summary in source_summaries
                ),
                "## Warnings",
                "\n".join(f"- {warning}" for warning in warnings) if warnings else "- None",
            ]
        )


def _source_dedupe_key(candidate: DeepSearchSourceCandidate) -> str:
    normalized_url = _normalize_url(candidate.url)
    if normalized_url:
        return f"url:{normalized_url}"
    if candidate.source_type == "paper_chunk":
        chunk_id = candidate.metadata.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id.strip():
            return f"paper_chunk:{chunk_id.strip()}"
    if candidate.paper_id:
        return f"paper:{candidate.paper_id}"
    provider = candidate.metadata.get("provider")
    source_paper_id = candidate.metadata.get("source_paper_id")
    if isinstance(provider, str) and isinstance(source_paper_id, str) and source_paper_id.strip():
        return f"{provider}:{source_paper_id.strip().lower()}"
    title = " ".join(candidate.title.lower().split())
    return f"{candidate.source_type}:title:{title}"


def _normalize_url(url: str | None) -> str | None:
    if url is None:
        return None
    normalized = url.strip()
    if not normalized:
        return None
    parts = urlsplit(normalized)
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", "")).rstrip("/")


def _iter_claim_sentences(report_body: str) -> list[str]:
    candidates: list[str] = []
    for raw_line in report_body.splitlines():
        line = raw_line.strip()
        if _skip_verifier_line(line):
            continue
        candidates.extend(
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", line)
            if sentence.strip() and not _skip_verifier_line(sentence.strip())
        )
    return candidates


def _skip_verifier_line(line: str) -> bool:
    if not line:
        return True
    if line.startswith("#"):
        return True
    if line.startswith(("-", "*")) and SOURCE_CITATION_PATTERN.search(line):
        return True
    normalized = line.lower()
    return normalized in {"none", "- none"} or normalized.startswith("warnings:")


def _normalize_plan_questions(question: str, questions: list[str]) -> list[str]:
    normalized = _dedupe_strings([question, *questions])
    return normalized[:MAX_PLAN_QUESTIONS]


def _paper_evidence_snippet(paper: Paper) -> str:
    parts = [paper.abstract or ""]
    if paper.summary is not None and not paper.summary.has_error:
        parts.extend(
            [
                paper.summary.problem or "",
                paper.summary.method or "",
                paper.summary.result or "",
                paper.summary.relevance_to_topic or "",
            ]
        )
    return _compact_text(" ".join(part for part in parts if part))


def _source_summary(
    source_id: str,
    source_candidate: DeepSearchSourceCandidate,
    *,
    note: str,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "source_type": source_candidate.source_type,
        "title": _truncate(source_candidate.title, MAX_SOURCE_TITLE_CHARS),
        "url": source_candidate.url,
        "paper_id": source_candidate.paper_id,
        "note": _compact_text(note),
    }


def _thinking_activity(
    *,
    phase: str,
    title: str,
    detail: str,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phase": phase,
        "title": title,
        "detail": detail,
    }
    if sources:
        payload["sources"] = sources
    return payload


def _planning_activity_detail(questions: list[str]) -> str:
    focus_items = "; ".join(_compact_text(question, limit=140) for question in questions[:3])
    if not focus_items:
        return "I am defining focused research questions before gathering evidence."
    return f"I am separating the request into focused research paths: {focus_items}."


def _source_activity_detail(
    candidates: list[DeepSearchSourceCandidate],
    *,
    empty_detail: str,
    populated_detail: str,
) -> str:
    if not candidates:
        return empty_detail
    source_types = sorted({candidate.source_type.replace("_", " ") for candidate in candidates})
    source_label = ", ".join(source_types)
    return f"{populated_detail} Current pool: {len(candidates)} {source_label} source(s)."


def _source_activity_sources(
    candidates: list[DeepSearchSourceCandidate],
    *,
    limit: int = 18,
) -> list[dict[str, Any]]:
    deduped_candidates = deduplicate_source_candidates(candidates)
    return [
        {
            "id": f"preview-{index}",
            "source_type": candidate.source_type,
            "title": _truncate(candidate.title, MAX_SOURCE_TITLE_CHARS),
            "url": candidate.url,
            "paper_id": candidate.paper_id,
        }
        for index, candidate in enumerate(deduped_candidates[:limit], start=1)
    ]


def _compact_text(text: str, *, limit: int = MAX_SOURCE_SNIPPET_CHARS) -> str:
    normalized = " ".join(text.split())
    return _truncate(normalized, limit)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _normalize_qa_flags(raw_flags: list[object]) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    for raw_flag in raw_flags:
        if not isinstance(raw_flag, dict):
            continue
        issue = str(raw_flag.get("issue", "")).strip()
        severity = str(raw_flag.get("severity", "")).strip()
        location = str(raw_flag.get("location", "")).strip()
        if not issue:
            continue
        if severity not in {"warning", "error"}:
            severity = "warning"
        flags.append(
            {
                "issue": issue,
                "severity": severity,
                "location": location,
            }
        )
    return flags


def _chunk_report(report: str) -> list[str]:
    chunks: list[str] = []
    paragraphs = report.split("\n\n")
    for index, paragraph in enumerate(paragraphs):
        suffix = "\n\n" if index < len(paragraphs) - 1 else ""
        chunks.append(f"{paragraph}{suffix}")
    return chunks
