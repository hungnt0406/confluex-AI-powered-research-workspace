from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.graph import ProjectPipelineRunner
from backend.agents.reader import ReaderAgent, SummaryGenerationResult
from backend.agents.searcher import SearcherAgent
from backend.agents.state import AgentState
from backend.db.models import Paper, Project


@dataclass(frozen=True)
class PipelineStreamEvent:
    """One incremental event from the project discovery pipeline."""

    event: Literal["status", "papers", "summary", "done", "error"]
    data: Any


@dataclass(frozen=True)
class PipelinePapersEventData:
    """Ranked-paper payload emitted once ranking has committed."""

    project_id: str
    queries: list[str]
    candidate_count: int
    ranked_count: int
    ranked_papers: list[Paper]


@dataclass(frozen=True)
class PipelineSummaryEventData:
    """One per-paper summary update emitted after persistence."""

    paper: Paper


class LiteraturePipelineService:
    """Run the phase-2 literature pipeline for a project."""

    def __init__(
        self,
        *,
        searcher_agent: SearcherAgent | None = None,
        reader_agent: ReaderAgent | None = None,
    ) -> None:
        self.searcher_agent = searcher_agent or SearcherAgent()
        self.reader_agent = reader_agent or ReaderAgent()

    async def run_project(self, *, session: AsyncSession, project: Project) -> AgentState:
        runner = ProjectPipelineRunner(
            session=session,
            project=project,
            searcher_agent=self.searcher_agent,
            reader_agent=self.reader_agent,
        )
        return await runner.run()

    async def stream_project(
        self,
        *,
        session: AsyncSession,
        project: Project,
    ) -> AsyncIterator[PipelineStreamEvent]:
        """Run the discovery pipeline with incremental ranked-paper and summary events."""

        state = AgentState(
            project_id=project.id,
            topic=project.topic_description,
            year_start=project.year_start,
            candidate_limit=project.candidate_limit,
            summary_limit=project.summary_limit,
        )

        yield PipelineStreamEvent("status", {"phase": "searching"})
        search_update = await self.searcher_agent.run(state, session, project)
        state = _apply_state_update(state, search_update)

        yield PipelineStreamEvent("status", {"phase": "ranking"})
        ranking_result = await self.reader_agent.rank_project_papers(session=session, project=project)
        state = _apply_state_update(
            state,
            {
                "ranked_papers": [
                    paper_to_state_payload(paper) for paper in ranking_result.ranked_papers
                ],
                "errors": [*state.errors, *ranking_result.errors],
            },
        )
        yield PipelineStreamEvent(
            "papers",
            PipelinePapersEventData(
                project_id=project.id,
                queries=list(state.queries),
                candidate_count=len(state.raw_papers),
                ranked_count=len(ranking_result.ranked_papers),
                ranked_papers=ranking_result.ranked_papers,
            ),
        )

        yield PipelineStreamEvent("status", {"phase": "summarizing"})
        summaries: list[dict[str, object]] = []
        summary_errors: list[str] = []
        async for summary_result in self.reader_agent.stream_summary_results(
            session=session,
            project=project,
            ranked_papers=ranking_result.ranked_papers,
        ):
            summaries.append(summary_to_state_payload(summary_result))
            if summary_result.error_message is not None:
                summary_errors.append(summary_result.error_message)
            yield PipelineStreamEvent(
                "summary",
                PipelineSummaryEventData(paper=summary_result.paper),
            )

        qa_flags = list(state.qa_flags)
        if len(ranking_result.ranked_papers) < 5:
            qa_flags.append(
                f"Only {len(ranking_result.ranked_papers)} ranked papers were available after filtering and ranking."
            )

        state = _apply_state_update(
            state,
            {
                "summaries": summaries,
                "qa_flags": qa_flags,
                "errors": [*state.errors, *summary_errors],
            },
        )
        yield PipelineStreamEvent("status", {"phase": "completed"})
        yield PipelineStreamEvent("done", state)


def paper_to_state_payload(paper: Paper) -> dict[str, object]:
    """Serialize an ORM paper into pipeline state format."""

    from backend.agents.searcher import serialize_paper_record

    return serialize_paper_record(paper)


def summary_to_state_payload(summary_result: SummaryGenerationResult) -> dict[str, object]:
    """Serialize a persisted summary result into pipeline state format."""

    summary = summary_result.paper.summary
    if summary is None:
        raise RuntimeError("Summary stream emitted before the summary relationship was attached.")

    return {
        "paper_id": summary_result.paper.id,
        "problem": summary.problem,
        "method": summary.method,
        "result": summary.result,
        "relevance_to_topic": summary.relevance_to_topic,
        "has_error": summary.has_error,
        "error_message": summary.error_message,
    }


def _apply_state_update(state: AgentState, update: dict[str, Any]) -> AgentState:
    """Merge one pipeline node update into the shared state."""

    return replace(state, **update)
