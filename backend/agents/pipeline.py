from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.graph import ProjectPipelineRunner
from backend.agents.reader import ReaderAgent
from backend.agents.searcher import SearcherAgent
from backend.agents.state import AgentState
from backend.db.models import Project


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
