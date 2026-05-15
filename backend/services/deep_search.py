from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast
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

logger = logging.getLogger(__name__)

MAX_PLAN_QUESTIONS = 5
MAX_PLAN_QUESTIONS_MAX = 8
MIN_PLAN_QUESTIONS = 3
MAX_SELECTED_DEEP_SEARCH_PAPERS = 10
MAX_SOURCE_SNIPPET_CHARS = 900
MAX_SOURCE_TITLE_CHARS = 500
MAX_CHUNKS_PER_SELECTED_PAPER = 2
MAX_REPORT_TOKENS = 8_000
MAX_ADAPTIVE_LOOP_ITERATIONS = 4
MAX_DECIDER_NEXT_QUERIES = 3
MAX_DECIDER_CONTEXT_CANDIDATES = 40
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

SourceType = Literal["paper", "paper_chunk", "citation_graph", "web"]
DeepSearchEventName = Literal["run", "status", "activity", "source", "token", "done", "error"]
DeepSearchActivityEventType = Literal[
    "stage_start",
    "stage_update",
    "source_found",
    "stage_complete",
    "finalizing",
]
AcademicSearchCallable = Callable[[str, int, int], Awaitable[list[PaperRecord]]]
DeepSearchCollectionItem = (
    tuple[Literal["activity"], dict[str, Any]]
    | tuple[Literal["candidates"], list["DeepSearchSourceCandidate"]]
    | tuple[Literal["warnings"], list[str]]
    | tuple[Literal["metadata"], dict[str, Any]]
)

ALLOWED_DEEP_SEARCH_ACTIVITY_TYPES: set[str] = {
    "stage_start",
    "stage_update",
    "source_found",
    "stage_complete",
    "finalizing",
}


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


@dataclass
class DecisionPayload:
    """Output from the adaptive loop decider LLM call."""

    reasoning: str
    gaps: list[str]
    next_queries: list[str]
    done: bool


@dataclass
class ResearchState:
    """Mutable state accumulated across adaptive loop iterations (max mode only)."""

    original_question: str
    research_questions: list[str]
    all_candidates: list[DeepSearchSourceCandidate]
    queries_run: set[str]
    iteration: int
    consecutive_empty_iterations: int
    warnings: list[str]
    web_metadata: dict[str, Any]
    iteration_history: list[dict[str, Any]]


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

    source_type_by_url = {
        normalized_url: str(summary.get("source_type", "")).strip()
        for summary in source_summaries
        if (normalized_url := _normalize_url(str(summary.get("url") or ""))) is not None
    }
    flags: list[dict[str, str]] = []
    for sentence in _iter_claim_sentences(report_body):
        citation_urls = [
            normalized_url
            for _, url in MARKDOWN_LINK_PATTERN.findall(sentence)
            if (normalized_url := _normalize_url(url)) is not None
        ]
        if not citation_urls:
            flags.append(
                {
                    "issue": "Claim appears without a source citation.",
                    "severity": "warning",
                    "location": sentence[:160],
                }
            )
            continue

        citation_types = [
            source_type_by_url[source_url]
            for source_url in citation_urls
            if source_url in source_type_by_url
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


_STANDARD_PLANNER_PROMPT = (
    "You are a deep research strategist. Given a research question, identify the core claims "
    "worth verifying, the key debates or open problems in the field, likely knowledge gaps, "
    "and counterintuitive angles that would make the answer genuinely useful. "
    "Produce 3 to 5 specific research sub-questions that illuminate the topic — name specific "
    "methods, models, or phenomena, not generic process steps. "
    "Also produce 1-2 short keyword search queries (seed_queries) for academic APIs — "
    "concise keyword strings under 8 words each, NOT full sentences. "
    'Respond with JSON: {"questions": ["...", ...], "seed_queries": ["...", ...]}'
)

_MAX_MODE_PLANNER_PROMPT = (
    "You are a systematic research architect. Decompose the research question into 5 to 8 "
    "distinct research dimensions — one question per dimension, covering: the primary "
    "architecture or method, specific challenges it addresses, competing approaches, empirical "
    "benchmarks (Precision, Recall, F1, FPS, mAP), output representation differences "
    "(e.g. heatmap vs bounding box), training data and dataset requirements, and trade-off "
    "synthesis. Each question must name SPECIFIC things (model names, metric names, dataset "
    "names) — never generic phrases like 'recent evidence' or 'real-world examples'. "
    "Do not restate the original question verbatim. "
    "Also produce 2-3 short keyword search queries (seed_queries) for academic APIs — "
    "keyword-style under 8 words each, NOT full sentences. "
    'Respond with JSON: {"questions": ["...", ...], "seed_queries": ["...", ...]}'
)


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
        self._settings = settings
        self._explicit_api_key = api_key
        self._explicit_base_url = base_url.rstrip("/") if base_url is not None else None
        self.planner_model = planner_model or settings.deep_search_planner_model
        self.research_model = research_model or settings.deep_search_research_model
        self.summarizer_model = summarizer_model or settings.deep_search_summarizer_model
        self.writer_model = writer_model or settings.deep_search_writer_model
        self.verifier_model = verifier_model or settings.deep_search_verifier_model
        self.api_key = self._api_key_for_model(self.writer_model)
        self.base_url = self._base_url_for_model(self.writer_model)
        self.max_web_searches = max_web_searches or settings.deep_search_max_web_searches
        self.max_iterations = max_iterations or settings.deep_search_max_iterations
        self.max_results_per_query = max_results_per_query or settings.deep_search_max_results_per_query
        if use_live_llm is not None:
            self.use_live_llm = use_live_llm
        else:
            self.use_live_llm = any(
                has_live_api_key(self._api_key_for_model(model))
                for model in (
                    self.planner_model,
                    self.research_model,
                    self.summarizer_model,
                    self.writer_model,
                    self.verifier_model,
                )
            )
        self.http_client = http_client
        self.timeout_seconds = settings.external_api_timeout_seconds
        self.tavily_service = tavily_service or TavilySearchService()
        self.semantic_scholar_search = semantic_scholar_search or default_semantic_scholar_search
        self.arxiv_search = arxiv_search or default_arxiv_search

    def _api_key_for_model(self, model: str) -> str | None:
        if self._explicit_api_key is not None:
            return self._explicit_api_key
        return self._settings.llm_api_key_for_model(model)

    def _base_url_for_model(self, model: str) -> str:
        if self._explicit_base_url is not None:
            return self._explicit_base_url
        return self._settings.llm_base_url_for_model(model).rstrip("/")

    async def stream_run(
        self,
        *,
        session: AsyncSession,
        project: Project,
        question: str,
        selected_papers: list[Paper],
        mode: Literal["standard", "max"] = "standard",
    ) -> AsyncIterator[DeepSearchStreamEvent]:
        """Create, execute, persist, and stream one deep search run."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        run = DeepSearchRun(
            project_id=project.id,
            user_prompt=normalized_question,
            status="running",
            mode=mode,
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
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_start",
                    phase="planning",
                    stage="Defining the research path",
                    detail="I am defining focused research questions before gathering evidence.",
                ),
            )
            planner_task = asyncio.create_task(
                self._plan_research(
                    project_title=project.title,
                    project_topic=project.topic_description,
                    question=normalized_question,
                    mode=mode,
                )
            )
            planning_updates = [
                "I am narrowing the request into focused research questions.",
                "I am deciding which evidence paths to inspect first.",
                "I am preparing the search plan before collecting sources.",
                "I am checking that the research paths cover project, academic, and web evidence.",
            ]
            update_index = 0
            while not planner_task.done():
                planner_done, _ = await asyncio.wait({planner_task}, timeout=4)
                if not planner_done:
                    yield DeepSearchStreamEvent(
                        "activity",
                        _thinking_activity(
                            event_type="stage_update",
                            phase="planning",
                            stage="Defining the research path",
                            detail=planning_updates[update_index % len(planning_updates)],
                        ),
                    )
                    update_index += 1
            try:
                questions, seed_queries = await planner_task
            except StructuredOutputError as error:
                logger.warning("deep_search planner fell back (mode=%s): %s", mode, error)
                questions, seed_queries = self._build_local_plan_research(normalized_question, mode)
                warnings.append(f"Deep Search planner fell back to local planning: {error}")
            plan_payload: dict[str, Any] = {
                "questions": questions,
                "seed_queries": seed_queries,
                "mode": mode,
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
                    event_type="stage_complete",
                    phase="planning",
                    stage="Defining the research path",
                    detail=_planning_activity_detail(questions),
                ),
            )

            candidates: list[DeepSearchSourceCandidate] = []

            yield DeepSearchStreamEvent("status", {"phase": "project_evidence"})
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_start",
                    phase="project_evidence",
                    stage="Reading selected sources",
                    detail="I am checking the selected project papers and saved PDF chunks for usable evidence.",
                ),
            )
            project_evidence_task = asyncio.create_task(
                self._collect_project_sources(
                    session=session,
                    selected_papers=selected_papers,
                )
            )
            project_evidence_updates = [
                "I am checking the selected project papers for usable evidence.",
                "I am looking for abstracts, summaries, and PDF chunks from the selected papers.",
                "I am preparing project-local evidence before expanding to external sources.",
            ]
            pe_update_index = 0
            while not project_evidence_task.done():
                project_evidence_done, _ = await asyncio.wait({project_evidence_task}, timeout=4)
                if not project_evidence_done:
                    yield DeepSearchStreamEvent(
                        "activity",
                        _thinking_activity(
                            event_type="stage_update",
                            phase="project_evidence",
                            stage="Reading selected sources",
                            detail=project_evidence_updates[pe_update_index % len(project_evidence_updates)],
                        ),
                    )
                    pe_update_index += 1
            project_candidates = await project_evidence_task
            candidates.extend(project_candidates)
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type=_source_activity_event_type(project_candidates),
                    phase="project_evidence",
                    stage="Reading selected sources",
                    detail=_source_activity_detail(
                        project_candidates,
                        empty_detail="No selected project paper evidence was available, so I will rely on external academic and web sources.",
                        populated_detail="I found project-local evidence to anchor the search before expanding outward.",
                    ),
                    sources=_source_activity_sources(project_candidates),
                ),
            )

            web_metadata: dict[str, Any] = {}

            if mode == "max":
                state = ResearchState(
                    original_question=normalized_question,
                    research_questions=questions,
                    all_candidates=list(project_candidates),
                    queries_run=set(),
                    iteration=0,
                    consecutive_empty_iterations=0,
                    warnings=[],
                    web_metadata={},
                    iteration_history=[],
                )
                async for event in self._run_adaptive_loop(
                    state=state,
                    project=project,
                    seed_queries=seed_queries,
                ):
                    yield event
                candidates = list(state.all_candidates)
                warnings.extend(state.warnings)
                web_metadata.update(state.web_metadata)
                plan_payload["iteration_history"] = state.iteration_history
            else:
                yield DeepSearchStreamEvent("status", {"phase": "academic_search"})
                yield DeepSearchStreamEvent(
                    "activity",
                    _thinking_activity(
                        event_type="stage_start",
                        phase="academic_search",
                        stage="Searching scholarly evidence",
                        detail="I am searching academic providers for papers related to the planned questions.",
                    ),
                )
                academic_candidates: list[DeepSearchSourceCandidate] = []
                academic_warnings: list[str] = []
                async for item_type, item_payload in self._iter_academic_sources_with_activity(
                    project=project,
                    questions=questions,
                ):
                    if item_type == "activity":
                        yield DeepSearchStreamEvent("activity", cast(dict[str, Any], item_payload))
                    elif item_type == "candidates":
                        academic_candidates.extend(cast(list[DeepSearchSourceCandidate], item_payload))
                    elif item_type == "warnings":
                        academic_warnings.extend(cast(list[str], item_payload))
                candidates.extend(academic_candidates)
                warnings.extend(academic_warnings)
                yield DeepSearchStreamEvent(
                    "activity",
                    _thinking_activity(
                        event_type=_source_activity_event_type(academic_candidates),
                        phase="academic_search",
                        stage="Searching for evidence",
                        detail=_source_activity_detail(
                            academic_candidates,
                            empty_detail="The scholarly providers did not return usable abstracts for the planned questions.",
                            populated_detail="I found scholarly sources that can support or challenge the answer.",
                        ),
                        sources=_source_activity_sources(academic_candidates),
                    ),
                )

                yield DeepSearchStreamEvent("status", {"phase": "web_search"})
                yield DeepSearchStreamEvent(
                    "activity",
                    _thinking_activity(
                        event_type="stage_start",
                        phase="web_search",
                        stage="Researching websites",
                        detail="I am searching current web sources for implementation context and recent evidence.",
                    ),
                )
                web_candidates: list[DeepSearchSourceCandidate] = []
                web_warnings: list[str] = []
                async for item_type, item_payload in self._iter_web_sources_with_activity(questions):
                    if item_type == "activity":
                        yield DeepSearchStreamEvent("activity", cast(dict[str, Any], item_payload))
                    elif item_type == "candidates":
                        web_candidates.extend(cast(list[DeepSearchSourceCandidate], item_payload))
                    elif item_type == "warnings":
                        web_warnings.extend(cast(list[str], item_payload))
                    elif item_type == "metadata":
                        web_metadata.update(cast(dict[str, Any], item_payload))
                candidates.extend(web_candidates)
                warnings.extend(web_warnings)
                yield DeepSearchStreamEvent(
                    "activity",
                    _thinking_activity(
                        event_type=_source_activity_event_type(web_candidates),
                        phase="web_search",
                        stage="Searching for evidence",
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
                    event_type="stage_start",
                    phase="summarizing_sources",
                    stage="Condensing source evidence",
                    detail=(
                        f"I am turning {len(indexed_sources)} deduplicated sources into compact evidence notes "
                        "before writing the final synthesis."
                    )
                    if indexed_sources
                    else "I did not find source candidates, so I will produce a limited report with warnings.",
                ),
            )
            summarizer_task = asyncio.create_task(
                self._summarize_sources(
                    question=normalized_question,
                    indexed_sources=indexed_sources,
                )
            )
            summarizer_updates = [
                "I am condensing the collected sources into compact evidence notes.",
                "I am removing duplicate source signals and keeping the strongest evidence.",
                "I am preparing source notes for the final synthesis.",
            ]
            sum_update_index = 0
            while not summarizer_task.done():
                summarizer_done, _ = await asyncio.wait({summarizer_task}, timeout=4)
                if not summarizer_done:
                    yield DeepSearchStreamEvent(
                        "activity",
                        _thinking_activity(
                            event_type="stage_update",
                            phase="summarizing_sources",
                            stage="Condensing source evidence",
                            detail=summarizer_updates[sum_update_index % len(summarizer_updates)],
                        ),
                    )
                    sum_update_index += 1
            source_summaries, summarizer_warning = await summarizer_task
            if summarizer_warning:
                warnings.append(summarizer_warning)
            for source_summary in source_summaries:
                yield DeepSearchStreamEvent("source", source_summary)
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_complete",
                    phase="summarizing_sources",
                    stage="Condensing source evidence",
                    detail=(
                        f"I finished condensing {len(source_summaries)} source note(s) for the report."
                    )
                    if source_summaries
                    else "There were no source notes to condense for this run.",
                ),
            )

            yield DeepSearchStreamEvent("status", {"phase": "writing"})
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_start",
                    phase="writing",
                    stage="Synthesizing the answer",
                    detail="I am starting the final synthesis from the condensed source notes.",
                ),
            )
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="finalizing",
                    phase="writing",
                    stage="Synthesizing the answer",
                    detail=(
                        "I am organizing the evidence into a report and attaching named source links "
                        "to factual claims."
                    ),
                ),
            )
            report_parts: list[str] = []
            try:
                async for token in self._stream_report(
                    question=normalized_question,
                    project=project,
                    plan_questions=questions,
                    source_summaries=source_summaries,
                    warnings=_dedupe_strings(warnings),
                ):
                    report_parts.append(token)
                    yield DeepSearchStreamEvent("token", {"delta": token})
            except Exception as error:
                fallback_warning = f"Deep Search report writer fell back to local synthesis: {error}"
                logger.warning("deep_search report writer fell back: %s", error)
                warnings.append(fallback_warning)
                fallback_report = self._generate_local_report(
                    question=normalized_question,
                    project=project,
                    plan_questions=questions,
                    source_summaries=source_summaries,
                    warnings=_dedupe_strings(warnings),
                )
                report_parts = []
                for token in _chunk_report(fallback_report):
                    report_parts.append(token)
                    yield DeepSearchStreamEvent("token", {"delta": token})
            report_body = "".join(report_parts).strip()
            if not report_body:
                raise RuntimeError("Deep search report writer returned no content.")
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_complete",
                    phase="writing",
                    stage="Synthesizing the answer",
                    detail="I finished drafting the report from the available source notes.",
                ),
            )

            yield DeepSearchStreamEvent("status", {"phase": "verifying"})
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_start",
                    phase="verifying",
                    stage="Checking citation coverage",
                    detail="I am starting a citation coverage check before saving the run.",
                ),
            )
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="finalizing",
                    phase="verifying",
                    stage="Checking citation coverage",
                    detail="I am scanning the drafted report for uncited claims and weak citation patterns.",
                ),
            )
            verifier_task = asyncio.create_task(
                self._verify_report(
                    report_body=report_body,
                    source_summaries=source_summaries,
                )
            )
            verifier_updates = [
                "I am checking whether key claims have citations.",
                "I am scanning for unsupported claims and web-only evidence.",
                "I am reviewing citation coverage before completing the report.",
            ]
            ver_update_index = 0
            while not verifier_task.done():
                verifier_done, _ = await asyncio.wait({verifier_task}, timeout=4)
                if not verifier_done:
                    yield DeepSearchStreamEvent(
                        "activity",
                        _thinking_activity(
                            event_type="stage_update",
                            phase="verifying",
                            stage="Checking citation coverage",
                            detail=verifier_updates[ver_update_index % len(verifier_updates)],
                        ),
                    )
                    ver_update_index += 1
            qa_flags, verifier_warning = await verifier_task
            if verifier_warning:
                warnings.append(verifier_warning)
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_complete",
                    phase="verifying",
                    stage="Checking citation coverage",
                    detail=f"I finished checking citation coverage and found {len(qa_flags)} QA flag(s).",
                ),
            )

            await self._persist_success(
                session=session,
                run_id=run_id,
                mode=mode,
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

    async def _plan_research(
        self,
        *,
        project_title: str,
        project_topic: str,
        question: str,
        mode: Literal["standard", "max"] = "standard",
    ) -> tuple[list[str], list[str]]:
        """Return (research_questions, seed_queries) for the deep search run."""
        if self.use_live_llm:
            is_max = mode == "max"
            max_q = MAX_PLAN_QUESTIONS_MAX if is_max else MAX_PLAN_QUESTIONS
            max_seeds = 3 if is_max else 2
            parsed = await self._generate_json(
                model=self.planner_model,
                feature="deep_search_planning",
                system_prompt=_MAX_MODE_PLANNER_PROMPT if is_max else _STANDARD_PLANNER_PROMPT,
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
                            "maxItems": max_q,
                            "items": {"type": "string"},
                        },
                        "seed_queries": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": max_seeds,
                            "items": {"type": "string", "maxLength": 80},
                        },
                    },
                    "required": ["questions", "seed_queries"],
                    "additionalProperties": False,
                },
                max_tokens=900 if is_max else 700,
            )
            raw_questions = parsed.get("questions", [])
            raw_seeds = parsed.get("seed_queries", [])
            if not isinstance(raw_questions, list):
                raise StructuredOutputError("Deep search planner returned invalid questions.")
            questions = [str(item).strip() for item in raw_questions if str(item).strip()]
            if not questions:
                raise StructuredOutputError("Deep search planner returned no usable questions.")
            seed_queries = [str(q).strip() for q in raw_seeds if str(q).strip()]
            if not seed_queries:
                seed_queries = _derive_seed_queries(question)
            return _normalize_plan_questions(question, questions, max_q=max_q, skip_prepend=is_max), seed_queries

        return self._build_local_plan_research(question, mode)

    def _build_local_plan_research(self, question: str, mode: str = "standard") -> tuple[list[str], list[str]]:
        seeds = _derive_seed_queries(question)
        if mode == "max":
            questions = [
                "What is the architecture and technical design of the primary method?",
                "What specific challenges or conditions does this approach address that general methods cannot?",
                "What competing or alternative approaches exist for the same task?",
                "How does this method compare empirically on precision, recall, F1, and speed against baselines?",
                "How do the output representations differ from general-purpose detectors (e.g. heatmap vs bounding box)?",
                "What datasets and training procedures are required?",
                "What are the trade-offs between specialized and general-purpose frameworks for this task?",
            ]
            return _normalize_plan_questions(question, questions, max_q=MAX_PLAN_QUESTIONS_MAX, skip_prepend=True), seeds
        questions = [
            question,
            f"What recent academic evidence addresses {question}?",
            f"What methods, results, and limitations are reported for {question}?",
            f"What current web evidence or implementation context is relevant to {question}?",
        ]
        return _normalize_plan_questions(question, questions), seeds

    async def _decide_next_step(self, state: ResearchState) -> DecisionPayload:
        """Call the decider LLM to determine what to search next (max mode only)."""
        sources_summary = "\n".join(
            f"- [{c.source_type}] {_compact_text(c.title, limit=120)}"
            for c in state.all_candidates[:MAX_DECIDER_CONTEXT_CANDIDATES]
        )
        queries_so_far = "; ".join(sorted(state.queries_run)[:15])
        research_qs = "\n".join(f"- {q}" for q in state.research_questions[:5])

        parsed = await self._generate_json(
            model=self.research_model,
            feature="deep_search_deciding",
            system_prompt=(
                "You are a deep research agent deciding what to search next. Given the original "
                "research questions, sources gathered so far, and queries already run, decide the "
                "next 1-3 short keyword search queries (or signal done=true if the questions are "
                "well-covered). Avoid duplicating past queries. Prefer specific over generic. "
                "Keep each query under 8 words. Set done=true if evidence is sufficient."
            ),
            user_prompt=(
                f"Original question: {state.original_question}\n\n"
                f"Research questions:\n{research_qs}\n\n"
                f"Queries already run: {queries_so_far or 'none'}\n\n"
                f"Sources found so far ({len(state.all_candidates)} total):\n"
                f"{sources_summary or 'None yet'}"
            ),
            schema={
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string"},
                    "gaps": {"type": "array", "items": {"type": "string"}},
                    "next_queries": {
                        "type": "array",
                        "maxItems": MAX_DECIDER_NEXT_QUERIES,
                        "items": {"type": "string", "maxLength": 80},
                    },
                    "done": {"type": "boolean"},
                },
                "required": ["reasoning", "gaps", "next_queries", "done"],
                "additionalProperties": False,
            },
            max_tokens=400,
        )
        return DecisionPayload(
            reasoning=str(parsed.get("reasoning", "")).strip(),
            gaps=[str(g).strip() for g in (parsed.get("gaps") or []) if str(g).strip()],
            next_queries=[
                str(q).strip()
                for q in (parsed.get("next_queries") or [])
                if str(q).strip()
            ],
            done=bool(parsed.get("done", False)),
        )

    async def _run_adaptive_loop(
        self,
        *,
        state: ResearchState,
        project: Project,
        seed_queries: list[str],
    ) -> AsyncGenerator[DeepSearchStreamEvent, None]:
        """Run the adaptive search loop for max mode."""
        current_queries = list(seed_queries)
        max_iter = MAX_ADAPTIVE_LOOP_ITERATIONS

        yield DeepSearchStreamEvent("status", {"phase": "academic_search"})
        yield DeepSearchStreamEvent(
            "activity",
            _thinking_activity(
                event_type="stage_start",
                phase="academic_search",
                stage="Searching scholarly evidence",
                detail=f"Starting adaptive research — up to {max_iter} search iterations.",
            ),
        )
        yield DeepSearchStreamEvent("status", {"phase": "web_search"})
        yield DeepSearchStreamEvent(
            "activity",
            _thinking_activity(
                event_type="stage_start",
                phase="web_search",
                stage="Researching websites",
                detail="I will search web sources in parallel with academic providers each iteration.",
            ),
        )

        for iteration in range(max_iter):
            state.iteration = iteration + 1
            fresh_queries = [
                q for q in current_queries if _normalize_query(q) not in state.queries_run
            ]
            if not fresh_queries:
                break
            state.queries_run.update(_normalize_query(q) for q in fresh_queries)

            iter_label = f"Iteration {state.iteration} of {max_iter}"
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_update",
                    phase="academic_search",
                    stage="Searching scholarly evidence",
                    detail=f"{iter_label}: searching academic sources for {', '.join(fresh_queries[:2])}.",
                ),
            )
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_update",
                    phase="web_search",
                    stage="Researching websites",
                    detail=f"{iter_label}: searching web sources for {', '.join(fresh_queries[:2])}.",
                ),
            )

            acad_result, web_result = await asyncio.gather(
                self._collect_academic_sources(project=project, questions=fresh_queries),
                self._collect_web_sources(fresh_queries),
            )
            acad_candidates, acad_warnings = acad_result
            web_candidates, web_warnings, web_meta = web_result

            state.warnings.extend(acad_warnings + web_warnings)
            state.web_metadata.update(web_meta)

            new_candidates = acad_candidates + web_candidates
            if new_candidates:
                state.consecutive_empty_iterations = 0
                state.all_candidates.extend(new_candidates)
                yield DeepSearchStreamEvent(
                    "activity",
                    _thinking_activity(
                        event_type="source_found",
                        phase="academic_search",
                        stage="Sources found",
                        detail=(
                            f"{iter_label}: found {len(acad_candidates)} academic "
                            f"and {len(web_candidates)} web source(s)."
                        ),
                        sources=_source_activity_sources(new_candidates),
                    ),
                )
            else:
                state.consecutive_empty_iterations += 1
                if state.consecutive_empty_iterations >= 2:
                    break

            if not self.use_live_llm:
                break

            yield DeepSearchStreamEvent("status", {"phase": "deciding"})
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_start",
                    phase="deciding",
                    stage="Reasoning about gaps",
                    detail=f"{iter_label}: deciding what to search next.",
                ),
            )
            try:
                decision = await self._decide_next_step(state)
            except (StructuredOutputError, Exception):
                state.warnings.append(f"Decider failed at iteration {state.iteration}; stopping.")
                yield DeepSearchStreamEvent(
                    "activity",
                    _thinking_activity(
                        event_type="stage_complete",
                        phase="deciding",
                        stage="Reasoning about gaps",
                        detail="Decider encountered an error; using evidence gathered so far.",
                    ),
                )
                break

            state.iteration_history.append(
                {
                    "iteration": state.iteration,
                    "queries": fresh_queries,
                    "reasoning": decision.reasoning,
                    "gaps": decision.gaps,
                    "done": decision.done,
                }
            )
            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_update",
                    phase="deciding",
                    stage="Reasoning about gaps",
                    detail=decision.reasoning or "Deciding next search queries.",
                ),
            )

            if decision.done:
                yield DeepSearchStreamEvent(
                    "activity",
                    _thinking_activity(
                        event_type="stage_complete",
                        phase="deciding",
                        stage="Reasoning about gaps",
                        detail="Evidence is sufficient — stopping adaptive loop.",
                    ),
                )
                break

            yield DeepSearchStreamEvent(
                "activity",
                _thinking_activity(
                    event_type="stage_complete",
                    phase="deciding",
                    stage="Reasoning about gaps",
                    detail=f"Will search {len(decision.next_queries)} new quer(ies) next iteration.",
                ),
            )
            current_queries = decision.next_queries

        all_acad = [c for c in state.all_candidates if c.source_type in ("paper", "paper_chunk", "citation_graph")]
        all_web = [c for c in state.all_candidates if c.source_type == "web"]
        yield DeepSearchStreamEvent(
            "activity",
            _thinking_activity(
                event_type="stage_complete",
                phase="academic_search",
                stage="Searching scholarly evidence",
                detail=_source_activity_detail(
                    all_acad,
                    empty_detail="No academic sources found across all iterations.",
                    populated_detail="Finished academic search across all iterations.",
                ),
                sources=_source_activity_sources(all_acad),
            ),
        )
        yield DeepSearchStreamEvent(
            "activity",
            _thinking_activity(
                event_type="stage_complete",
                phase="web_search",
                stage="Researching websites",
                detail=_source_activity_detail(
                    all_web,
                    empty_detail="No web sources found across all iterations.",
                    populated_detail="Finished web search across all iterations.",
                ),
                sources=_source_activity_sources(all_web),
            ),
        )

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
        async for item_type, item_payload in self._iter_academic_sources_with_activity(
            project=project,
            questions=questions,
        ):
            if item_type == "candidates":
                candidates.extend(cast(list[DeepSearchSourceCandidate], item_payload))
            elif item_type == "warnings":
                warnings.extend(cast(list[str], item_payload))
        return candidates, _dedupe_strings(warnings)

    async def _iter_academic_sources_with_activity(
        self,
        *,
        project: Project,
        questions: list[str],
    ) -> AsyncIterator[DeepSearchCollectionItem]:
        candidates: list[DeepSearchSourceCandidate] = []
        warnings: list[str] = []
        search_questions = questions[: max(1, min(self.max_web_searches, len(questions)))]

        for query in search_questions:
            provider_calls: list[tuple[str, AcademicSearchCallable]] = [
                ("semantic_scholar", self.semantic_scholar_search),
                ("arxiv", self.arxiv_search),
            ]
            for provider_name, search in provider_calls:
                provider_stage = _academic_provider_stage(provider_name)
                yield (
                    "activity",
                    _thinking_activity(
                        event_type="stage_update",
                        phase="academic_search",
                        stage=provider_stage,
                        detail=f"{provider_stage} for: {_compact_text(query, limit=160)}.",
                    ),
                )
                try:
                    search_task: asyncio.Future[list[PaperRecord]] = asyncio.ensure_future(
                        search(query, project.year_start, self.max_results_per_query)
                    )
                    while not search_task.done():
                        search_done, _ = await asyncio.wait({search_task}, timeout=4)
                        if not search_done:
                            yield (
                                "activity",
                                _thinking_activity(
                                    event_type="stage_update",
                                    phase="academic_search",
                                    stage=provider_stage,
                                    detail=f"Waiting for {provider_stage} to respond...",
                                ),
                            )
                    papers = await search_task
                except Exception as error:
                    logger.warning(
                        "deep_search %s search failed for query %r: %s",
                        provider_name,
                        query,
                        error,
                    )
                    warnings.append(
                        f"{provider_name} search failed for query '{query}': {error}"
                    )
                    continue
                query_candidates: list[DeepSearchSourceCandidate] = []
                for paper_record in papers:
                    snippet = _compact_text(paper_record.get("abstract", ""))
                    if not snippet:
                        continue
                    query_candidates.append(
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
                if query_candidates:
                    candidates.extend(query_candidates)
                    yield (
                        "activity",
                        _thinking_activity(
                            event_type="source_found",
                            phase="academic_search",
                            stage="Sources found",
                            detail=(
                                f"{provider_stage} returned {len(query_candidates)} usable scholarly "
                                "source(s)."
                            ),
                            sources=_source_activity_sources(query_candidates),
                        ),
                    )
        yield ("candidates", candidates)
        yield ("warnings", _dedupe_strings(warnings))

    async def _collect_web_sources(
        self,
        questions: list[str],
    ) -> tuple[list[DeepSearchSourceCandidate], list[str], dict[str, Any]]:
        candidates: list[DeepSearchSourceCandidate] = []
        warnings: list[str] = []
        metadata: dict[str, Any] = {}
        async for item_type, item_payload in self._iter_web_sources_with_activity(questions):
            if item_type == "candidates":
                candidates.extend(cast(list[DeepSearchSourceCandidate], item_payload))
            elif item_type == "warnings":
                warnings.extend(cast(list[str], item_payload))
            elif item_type == "metadata":
                metadata.update(cast(dict[str, Any], item_payload))
        return candidates, _dedupe_strings(warnings), metadata

    async def _iter_web_sources_with_activity(
        self,
        questions: list[str],
    ) -> AsyncIterator[DeepSearchCollectionItem]:
        candidates: list[DeepSearchSourceCandidate] = []
        warnings: list[str] = []
        metadata = {
            "tavily_search_count": 0,
            "tavily_result_count": 0,
            "tavily_configured": self.tavily_service.is_configured(),
        }
        for query in questions[: self.max_web_searches]:
            yield (
                "activity",
                _thinking_activity(
                    event_type="stage_update",
                    phase="web_search",
                    stage="Searching web",
                    detail=f"Searching Tavily for: {_compact_text(query, limit=160)}.",
                ),
            )
            metadata["tavily_search_count"] += 1
            search_task = asyncio.create_task(
                self.tavily_service.search(
                    query,
                    max_results=self.max_results_per_query,
                )
            )
            while not search_task.done():
                web_search_done, _ = await asyncio.wait({search_task}, timeout=4)
                if not web_search_done:
                    yield (
                        "activity",
                        _thinking_activity(
                            event_type="stage_update",
                            phase="web_search",
                            stage="Searching web",
                            detail="Waiting for Tavily search results...",
                        ),
                    )
            response = await search_task
            warnings.extend(response.warnings)
            query_candidates: list[DeepSearchSourceCandidate] = []
            for result in response.results:
                snippet = _compact_text(result.content)
                if not snippet:
                    continue
                query_candidates.append(
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
            if query_candidates:
                candidates.extend(query_candidates)
                yield (
                    "activity",
                    _thinking_activity(
                        event_type="source_found",
                        phase="web_search",
                        stage="Sources found",
                        detail=f"Tavily returned {len(query_candidates)} usable web source(s).",
                        sources=_source_activity_sources(query_candidates),
                    ),
                )
        metadata["tavily_result_count"] = len(candidates)
        yield ("candidates", candidates)
        yield ("warnings", _dedupe_strings(warnings))
        yield ("metadata", metadata)

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
        api_key = self._api_key_for_model(self.writer_model)
        base_url = self._base_url_for_model(self.writer_model)
        if not has_live_api_key(api_key):
            raise RuntimeError("OpenRouter API credentials are not configured.")

        headers = {
            "Authorization": f"Bearer {api_key or ''}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.writer_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a deep research report writer. Write a concise, evidence-grounded "
                        "report. Cite factual claims with normal Markdown links whose visible text is "
                        "the source title, for example [Databricks Lakehouse](https://example.com). "
                        "Every factual sentence and every bullet key point in the answer body must "
                        "end with one or more URL-backed Markdown source links. "
                        "Never use opaque bracketed citation IDs or numeric citation labels. Never "
                        "output HTML. Never show raw URLs in the prose. End with a '## Sources' "
                        "section containing Markdown bullets "
                        "formatted as '- [Title](URL) — Publisher: domain. Supports: relevance note.' "
                        "Use only URL-backed sources for citations and final source bullets. Do not "
                        "cite headings, warnings, or the final Sources section itself."
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
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if "openrouter.ai" in base_url:
            payload["provider"] = {"sort": "price"}

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        usage_payload: dict[str, object] | None = None
        try:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
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
        mode: str,
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
                "mode": mode,
            },
        }
        await session.execute(
            update(DeepSearchRun)
            .where(DeepSearchRun.id == run_id)
            .values(
                status="completed",
                mode=mode,
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
            api_key=self._api_key_for_model(model),
            model=model,
            base_url=self._base_url_for_model(model),
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
                        f"- Title: {summary['title']} | Publisher/domain: "
                        f"{_source_domain(str(summary.get('url') or '')) or 'internal project evidence'} | "
                        f"URL: {summary.get('url') or 'none'} | Supports: {summary['note']}"
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

        url_sources = [summary for summary in source_summaries if str(summary.get("url") or "").strip()]
        top_sources = url_sources[:5]
        first_source_link = _source_markdown_link(top_sources[0]) if top_sources else ""
        first_source_citation = f" ({first_source_link})" if first_source_link else ""
        answer_lines = [
            (
                f"For **{project.title}**, the available evidence for \"{question}\" is strongest "
                f"where project papers, academic sources, and web results converge"
                f"{first_source_citation}."
            )
        ]
        for summary in top_sources[:3]:
            answer_lines.append(
                f"- {_trim_terminal_punctuation(str(summary['note']))}. "
                f"({_source_markdown_link(summary)})."
            )

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
                        f"- **{summary['title']}** ({summary['source_type']}): "
                        f"{summary['note']} ({_source_markdown_link(summary)})."
                    )
                    for summary in url_sources
                ),
                "## Sources",
                "\n".join(_source_bullet_markdown(summary) for summary in url_sources),
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


def count_report_claim_sentences(report_body: str) -> int:
    """Return how many sentences the Deep Search claim verifier evaluates."""

    return len(_iter_claim_sentences(report_body))


def _skip_verifier_line(line: str) -> bool:
    if not line:
        return True
    if line.startswith("#"):
        return True
    if (
        line.startswith(("-", "*"))
        and "— Publisher:" in line
        and "Supports:" in line
        and MARKDOWN_LINK_PATTERN.search(line)
    ):
        return True
    normalized = line.lower()
    return normalized in {"none", "- none"} or normalized.startswith("warnings:")


def _normalize_plan_questions(
    question: str,
    questions: list[str],
    max_q: int = MAX_PLAN_QUESTIONS,
    skip_prepend: bool = False,
) -> list[str]:
    # skip_prepend=True for max mode: LLM generates dimension questions, don't inject the original
    source = questions if skip_prepend else [question, *questions]
    return _dedupe_strings(source)[:max_q]


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


def _source_markdown_link(summary: dict[str, Any]) -> str:
    title = str(summary.get("title") or "Untitled source").strip()
    url = str(summary.get("url") or "").strip()
    return f"[{title}]({url})" if url else title


def _trim_terminal_punctuation(value: str) -> str:
    return value.strip().rstrip(".!?")


def _source_bullet_markdown(summary: dict[str, Any]) -> str:
    note = str(summary.get("note") or "").strip()
    publisher = _source_domain(str(summary.get("url") or ""))
    return f"- {_source_markdown_link(summary)} — Publisher: {publisher}. Supports: {note}"


def _source_domain(url: str) -> str:
    if not url:
        return ""
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


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


def _academic_provider_stage(provider_name: str) -> str:
    if provider_name == "semantic_scholar":
        return "Searching Semantic Scholar"
    if provider_name == "arxiv":
        return "Searching arXiv"
    return f"Searching {provider_name.replace('_', ' ').title()}"


def _thinking_activity(
    *,
    event_type: DeepSearchActivityEventType,
    phase: str,
    stage: str,
    detail: str,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if event_type not in ALLOWED_DEEP_SEARCH_ACTIVITY_TYPES:
        raise ValueError(f"Unsupported deep search activity event type: {event_type}")
    payload: dict[str, Any] = {
        "type": event_type,
        "event_type": event_type,
        "phase": phase,
        "stage": stage,
        "title": stage,
        "message": detail,
        "detail": detail,
        "sources": sources or [],
    }
    return payload


def _source_activity_event_type(
    candidates: list[DeepSearchSourceCandidate],
) -> DeepSearchActivityEventType:
    return "source_found" if candidates else "stage_complete"


def _activity_source_type(source_type: str) -> str:
    if source_type == "paper":
        return "paper"
    if source_type == "paper_chunk":
        return "pdf"
    if source_type == "web":
        return "website"
    if source_type == "citation_graph":
        return "paper"
    return "other"


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
            "type": _activity_source_type(candidate.source_type),
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


def _derive_seed_queries(question: str) -> list[str]:
    words = question.strip().split()
    return [" ".join(words[:6])] if words else [question[:80]]


def _normalize_query(query: str) -> str:
    return " ".join(query.lower().split())[:80]
