import pytest

from backend.agents.state import AgentState
from backend.api.dependencies import get_pipeline_service
from backend.db.models import Paper, Summary


@pytest.mark.asyncio
async def test_create_and_list_projects(client, auth_headers) -> None:
    create_response = await client.post(
        "/projects",
        headers=auth_headers,
        json={
            "title": "Graph Agents",
            "topic_description": "Review graph-based multi-agent workflows.",
            "citation_format": "IEEE",
            "year_start": 2020,
            "candidate_limit": 40,
            "summary_limit": 20,
        },
    )

    assert create_response.status_code == 201
    project = create_response.json()
    assert project["title"] == "Graph Agents"
    assert project["year_start"] == 2020
    assert project["candidate_limit"] == 40
    assert project["summary_limit"] == 20

    list_response = await client.get("/projects", headers=auth_headers)

    assert list_response.status_code == 200
    projects = list_response.json()
    assert len(projects) == 1
    assert projects[0]["id"] == project["id"]


@pytest.mark.asyncio
async def test_get_project_returns_owned_project(client, auth_headers, sample_project) -> None:
    response = await client.get(f"/projects/{sample_project['id']}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == sample_project["id"]
    assert payload["title"] == sample_project["title"]


@pytest.mark.asyncio
async def test_run_project_pipeline_returns_completed_result(
    app,
    client,
    auth_headers,
    sample_project,
) -> None:
    class FakePipelineService:
        async def run_project(self, *, session, project) -> AgentState:
            return AgentState(
                project_id=project.id,
                topic=project.topic_description,
                queries=["agentic systems survey", "multi-agent workflow review"],
                raw_papers=[{"title": "Candidate Paper"}],
                ranked_papers=[{"title": "Ranked Paper"}],
                summaries=[{"paper_id": "paper-1"}],
                qa_flags=[],
                errors=[],
            )

    app.dependency_overrides[get_pipeline_service] = lambda: FakePipelineService()
    response = await client.post(f"/projects/{sample_project['id']}/run", headers=auth_headers)
    app.dependency_overrides.pop(get_pipeline_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["project_id"] == sample_project["id"]
    assert payload["queries"] == ["agentic systems survey", "multi-agent workflow review"]
    assert payload["candidate_count"] == 1
    assert payload["ranked_count"] == 1
    assert payload["summary_count"] == 1


@pytest.mark.asyncio
async def test_list_project_papers_supports_filters_and_pagination(
    client,
    auth_headers,
    sample_project,
    session_factory,
) -> None:
    async with session_factory() as session:
        paper = Paper(
            project_id=sample_project["id"],
            title="Ranking Multi-Agent Systems",
            authors=["Jane Doe"],
            year=2024,
            abstract="This paper evaluates multi-agent ranking systems." * 4,
            doi="10.1000/ranking",
            source="semantic_scholar",
            status="summarized",
            relevance_score=93.4,
        )
        session.add(paper)
        await session.flush()
        session.add(
            Summary(
                paper_id=paper.id,
                problem="Rank multi-agent systems",
                method="Evaluate and compare retrieval pipelines",
                result="The ranking pipeline improved recall.",
                relevance_to_topic="It studies the same retrieval domain.",
                has_error=False,
                error_message=None,
            )
        )
        await session.commit()

    response = await client.get(
        f"/projects/{sample_project['id']}/papers?page=1&per_page=10&status=summarized&min_relevance=90",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"] == {"total": 1, "page": 1, "per_page": 10, "total_pages": 1}
    assert len(payload["data"]) == 1
    assert payload["data"][0]["status"] == "summarized"
    assert payload["data"][0]["summary"]["problem"] == "Rank multi-agent systems"
