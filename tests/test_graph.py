from sqlalchemy import select

from backend.agents.graph import ProjectPipelineRunner
from backend.db.models import Project


class FakeSearcherAgent:
    async def run(self, state, session, project):
        return {
            "queries": ["multi-agent systems"],
            "raw_papers": [{"title": "Candidate Paper"}],
            "errors": [],
        }


class FakeReaderAgent:
    async def run(self, state, session, project):
        return {
            "ranked_papers": [
                {"title": "Paper 1"},
                {"title": "Paper 2"},
                {"title": "Paper 3"},
            ],
            "summaries": [],
            "errors": [],
        }


async def test_pipeline_runner_adds_warning_when_fewer_than_five_ranked_papers(
    session_factory,
    sample_project,
) -> None:
    async with session_factory() as session:
        project = (
            await session.execute(select(Project).where(Project.id == sample_project["id"]))
        ).scalar_one()

        runner = ProjectPipelineRunner(
            session=session,
            project=project,
            searcher_agent=FakeSearcherAgent(),
            reader_agent=FakeReaderAgent(),
        )
        result = await runner.run()

    assert result.project_id == sample_project["id"]
    assert len(result.ranked_papers) == 3
    assert result.qa_flags == [
        "Only 3 ranked papers were available after filtering and ranking."
    ]
