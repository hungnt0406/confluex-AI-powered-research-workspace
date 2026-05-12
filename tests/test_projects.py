import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.agents.pipeline import (
    PipelinePapersEventData,
    PipelineStreamEvent,
    PipelineSummaryEventData,
)
from backend.agents.state import AgentState
from backend.api.dependencies import get_paper_citation_service, get_pipeline_service
from backend.db.models import AIUsageEvent, Paper, Project, ReferenceFile, Summary, User
from backend.security import hash_password
from backend.services.ai_usage import collect_openrouter_usage
from backend.services.paper_citations import (
    CitationGraphResult,
    CitationNotFoundError,
    CitationProviderError,
    CitationResolutionError,
)


def parse_sse_events(response_text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in response_text.strip().split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


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
async def test_patch_project_renames_owned_project(client, auth_headers, sample_project) -> None:
    response = await client.patch(
        f"/projects/{sample_project['id']}",
        headers=auth_headers,
        json={"title": "  Renamed Research Thread  "},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == sample_project["id"]
    assert payload["title"] == "Renamed Research Thread"


@pytest.mark.asyncio
async def test_delete_project_removes_owned_project_and_uploaded_files(
    client,
    auth_headers,
    sample_project,
    session_factory,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "seed.pdf"
    storage_path.write_bytes(b"%PDF-1.4\nproject delete cleanup")

    async with session_factory() as session:
        reference_file = ReferenceFile(
            project_id=sample_project["id"],
            original_filename="seed.pdf",
            content_type="application/pdf",
            byte_size=storage_path.stat().st_size,
            sha256="a" * 64,
            storage_path=str(storage_path),
            parse_status="parsed",
        )
        session.add(reference_file)
        await session.flush()

        session.add(
            Paper(
                project_id=sample_project["id"],
                reference_file_id=reference_file.id,
                title="Uploaded Seed Paper",
                authors=["Jane Doe"],
                year=2024,
                abstract="Reference-backed paper for project deletion coverage.",
                doi=None,
                source="user_upload",
                status="candidate",
                relevance_score=None,
            )
        )
        await session.commit()

    response = await client.delete(f"/projects/{sample_project['id']}", headers=auth_headers)

    assert response.status_code == 204

    async with session_factory() as session:
        project = await session.get(Project, sample_project["id"])
        reference_files = (
            await session.execute(
                select(ReferenceFile).where(ReferenceFile.project_id == sample_project["id"])
            )
        ).scalars().all()
        papers = (
            await session.execute(select(Paper).where(Paper.project_id == sample_project["id"]))
        ).scalars().all()

    assert project is None
    assert reference_files == []
    assert papers == []
    assert not storage_path.exists()


@pytest.mark.asyncio
async def test_delete_project_returns_404_for_unowned_project(
    client,
    auth_headers,
    session_factory,
) -> None:
    async with session_factory() as session:
        other_user = User(
            email="other-researcher@example.com",
            hashed_password=hash_password("supersecret123"),
        )
        session.add(other_user)
        await session.flush()

        project = Project(
            user_id=other_user.id,
            title="Someone Else's Project",
            topic_description="This project should not be deletable by another user.",
            citation_format="APA",
            year_start=2019,
            candidate_limit=50,
            summary_limit=25,
        )
        session.add(project)
        await session.commit()
        project_id = project.id

    response = await client.delete(f"/projects/{project_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."

    async with session_factory() as session:
        persisted_project = await session.get(Project, project_id)

    assert persisted_project is not None


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
async def test_stream_project_pipeline_emits_papers_before_summaries(
    app,
    client,
    auth_headers,
    sample_project,
) -> None:
    class FakePipelineService:
        async def stream_project(self, *, session, project):
            yield PipelineStreamEvent("status", {"phase": "searching"})
            yield PipelineStreamEvent("status", {"phase": "ranking"})
            paper = Paper(
                project_id=project.id,
                title="Progressive Ranking",
                authors=["Jane Doe"],
                year=2025,
                abstract="A paper about progressive literature review ranking.",
                doi="10.1000/progressive",
                source="semantic_scholar",
                status="ranked",
                relevance_score=98.5,
            )
            session.add(paper)
            await session.commit()

            yield PipelineStreamEvent(
                "papers",
                PipelinePapersEventData(
                    project_id=project.id,
                    queries=["progressive related papers"],
                    candidate_count=1,
                    ranked_count=1,
                    ranked_papers=[paper],
                ),
            )

            yield PipelineStreamEvent("status", {"phase": "summarizing"})
            summary = Summary(
                paper_id=paper.id,
                problem="Slow first-message discovery",
                method="Stream ranked papers before summaries finish",
                result="Users can inspect candidates sooner",
                relevance_to_topic="Directly relevant to progressive paper discovery.",
                has_error=False,
                error_message=None,
            )
            session.add(summary)
            paper.summary = summary
            paper.status = "summarized"
            await session.commit()

            yield PipelineStreamEvent("summary", PipelineSummaryEventData(paper=paper))
            yield PipelineStreamEvent("status", {"phase": "completed"})
            yield PipelineStreamEvent(
                "done",
                AgentState(
                    project_id=project.id,
                    topic=project.topic_description,
                    queries=["progressive related papers"],
                    raw_papers=[{"id": paper.id}],
                    ranked_papers=[{"id": paper.id}],
                    summaries=[{"paper_id": paper.id}],
                    qa_flags=["Only 1 ranked papers were available after filtering and ranking."],
                    errors=[],
                ),
            )

    app.dependency_overrides[get_pipeline_service] = lambda: FakePipelineService()
    response = await client.post(f"/projects/{sample_project['id']}/run/stream", headers=auth_headers)
    app.dependency_overrides.pop(get_pipeline_service, None)

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [event_name for event_name, _payload in events]
    assert event_names[:2] == ["status", "status"]
    assert event_names.index("papers") < event_names.index("summary")
    assert event_names[-1] == "done"

    status_payloads = [payload for event_name, payload in events if event_name == "status"]
    assert [payload["phase"] for payload in status_payloads] == [
        "searching",
        "ranking",
        "summarizing",
        "completed",
    ]

    papers_payload = next(payload for event_name, payload in events if event_name == "papers")
    assert papers_payload["queries"] == ["progressive related papers"]
    assert papers_payload["project_id"] == sample_project["id"]
    assert papers_payload["candidate_count"] == 1
    assert papers_payload["ranked_count"] == 1
    assert papers_payload["papers"][0]["status"] == "ranked"
    assert papers_payload["papers"][0]["summary"] is None

    summary_payload = next(payload for event_name, payload in events if event_name == "summary")
    assert summary_payload["paper"]["status"] == "summarized"
    assert summary_payload["paper"]["summary"]["problem"] == "Slow first-message discovery"

    done_payload = next(payload for event_name, payload in events if event_name == "done")
    assert done_payload["status"] == "completed"
    assert done_payload["summary_count"] == 1


@pytest.mark.asyncio
async def test_run_project_pipeline_persists_openrouter_usage(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory,
) -> None:
    class FakePipelineService:
        async def run_project(self, *, session, project) -> AgentState:
            collect_openrouter_usage(
                endpoint="chat/completions",
                feature="query_expansion",
                model="google/gemma-test",
                response_payload={
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 7,
                        "total_tokens": 18,
                        "cost": 0.002,
                    }
                },
            )
            collect_openrouter_usage(
                endpoint="embeddings",
                feature="ranking_embedding",
                model="openai/text-embedding-3-small",
                response_payload={"usage": {"prompt_tokens": 3, "total_tokens": 3}},
            )

            return AgentState(
                project_id=project.id,
                topic=project.topic_description,
                queries=["agentic systems survey"],
                raw_papers=[],
                ranked_papers=[],
                summaries=[],
                qa_flags=[],
                errors=[],
            )

    app.dependency_overrides[get_pipeline_service] = lambda: FakePipelineService()
    response = await client.post(f"/projects/{sample_project['id']}/run", headers=auth_headers)
    app.dependency_overrides.pop(get_pipeline_service, None)

    assert response.status_code == 200
    async with session_factory() as session:
        events = (
            await session.execute(
                select(AIUsageEvent).where(AIUsageEvent.project_id == sample_project["id"])
            )
        ).scalars().all()

    assert {(event.feature, event.endpoint) for event in events} == {
        ("query_expansion", "chat/completions"),
        ("ranking_embedding", "embeddings"),
    }
    assert sum(event.total_tokens or 0 for event in events) == 21


@pytest.mark.asyncio
async def test_get_project_token_usage_returns_owner_scoped_aggregates(
    client,
    auth_headers,
    sample_project,
    sample_user,
    session_factory,
) -> None:
    async with session_factory() as session:
        other_user = User(
            email="usage-other@example.com",
            hashed_password=hash_password("supersecret123"),
        )
        session.add(other_user)
        await session.flush()
        other_project = Project(
            user_id=other_user.id,
            title="Private Project",
            topic_description="Not visible to sample user.",
            citation_format="APA",
            year_start=2020,
            candidate_limit=10,
            summary_limit=5,
        )
        session.add(other_project)
        await session.flush()
        session.add_all(
            [
                AIUsageEvent(
                    user_id=sample_user["id"],
                    project_id=sample_project["id"],
                    provider="openrouter",
                    endpoint="chat/completions",
                    feature="paper_summary",
                    model="model-a",
                    status="success",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                    reasoning_tokens=2,
                    cached_tokens=1,
                    cost_credits=0.01,
                    metadata_json={},
                ),
                AIUsageEvent(
                    user_id=sample_user["id"],
                    project_id=sample_project["id"],
                    provider="openrouter",
                    endpoint="embeddings",
                    feature="ranking_embedding",
                    model="model-b",
                    status="success",
                    prompt_tokens=8,
                    completion_tokens=0,
                    total_tokens=8,
                    reasoning_tokens=None,
                    cached_tokens=None,
                    cost_credits=0.002,
                    metadata_json={},
                ),
                AIUsageEvent(
                    user_id=other_user.id,
                    project_id=other_project.id,
                    provider="openrouter",
                    endpoint="chat/completions",
                    feature="paper_summary",
                    model="model-a",
                    status="success",
                    prompt_tokens=99,
                    completion_tokens=99,
                    total_tokens=198,
                    metadata_json={},
                ),
            ]
        )
        await session.commit()
        other_project_id = other_project.id

    response = await client.get(
        f"/projects/{sample_project['id']}/token-usage",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == sample_project["id"]
    assert payload["total_tokens"] == 23
    assert payload["prompt_tokens"] == 18
    assert payload["completion_tokens"] == 5
    assert payload["reasoning_tokens"] == 2
    assert payload["cached_tokens"] == 1
    assert payload["request_count"] == 2
    assert payload["cost_credits"] == pytest.approx(0.012)
    assert payload["by_feature"][0]["key"] == "paper_summary"
    assert payload["by_feature"][0]["total_tokens"] == 15
    assert {row["key"] for row in payload["by_model"]} == {"model-a", "model-b"}
    assert payload["by_day"][0]["total_tokens"] == 23

    forbidden_response = await client.get(
        f"/projects/{other_project_id}/token-usage",
        headers=auth_headers,
    )
    assert forbidden_response.status_code == 404


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
            citation_count=42,
            reference_count=11,
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
    assert payload["data"][0]["citation_count"] == 42
    assert payload["data"][0]["reference_count"] == 11
    assert payload["data"][0]["summary"]["problem"] == "Rank multi-agent systems"


@pytest.mark.asyncio
async def test_get_project_paper_citation_graph_returns_related_papers(
    app,
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
            source_paper_id="semantic-001",
            source_url="https://www.semanticscholar.org/paper/semantic-001",
            pdf_url="https://pdf.example.com/semantic-001.pdf",
            status="summarized",
            relevance_score=93.4,
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)

    class FakePaperCitationService:
        async def get_citation_graph(self, *, session, paper, limit) -> CitationGraphResult:
            assert paper.id
            assert limit == 7
            return CitationGraphResult(
                paper_id=paper.id,
                resolved_by="semantic_scholar_paper_id",
                resolved_source_paper_id="semantic-001",
                citation_count=12,
                reference_count=8,
                cited_by=[
                    {
                        "title": "Citing Paper",
                        "authors": ["Alice"],
                        "year": 2025,
                        "abstract": "Cites the target paper.",
                        "doi": "10.1000/citing",
                        "source": "semantic_scholar",
                        "source_paper_id": "semantic-100",
                        "source_url": "https://www.semanticscholar.org/paper/semantic-100",
                        "pdf_url": "https://pdf.example.com/semantic-100.pdf",
                    }
                ],
                references=[
                    {
                        "title": "Referenced Paper",
                        "authors": ["Bob"],
                        "year": 2022,
                        "abstract": "Referenced by the target paper.",
                        "doi": "10.1000/referenced",
                        "source": "semantic_scholar",
                        "source_paper_id": "semantic-200",
                        "source_url": "https://www.semanticscholar.org/paper/semantic-200",
                        "pdf_url": "https://pdf.example.com/semantic-200.pdf",
                    }
                ],
            )

    app.dependency_overrides[get_paper_citation_service] = lambda: FakePaperCitationService()
    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph?limit=7",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(get_paper_citation_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["paper_id"] == paper.id
    assert payload["resolved_by"] == "semantic_scholar_paper_id"
    assert payload["resolved_source_paper_id"] == "semantic-001"
    assert payload["citation_count"] == 12
    assert payload["reference_count"] == 8
    assert payload["cited_by"][0]["title"] == "Citing Paper"
    assert payload["references"][0]["title"] == "Referenced Paper"


@pytest.mark.asyncio
async def test_import_project_citation_graph_paper_creates_and_deduplicates(
    client,
    auth_headers,
    sample_project,
    session_factory,
) -> None:
    payload = {
        "title": "Citing Paper",
        "authors": ["Alice"],
        "year": 2025,
        "abstract": "Cites the target paper.",
        "doi": "10.1000/citing",
        "source": "semantic_scholar",
        "source_paper_id": "semantic-100",
        "source_url": "https://www.semanticscholar.org/paper/semantic-100",
        "pdf_url": "https://pdf.example.com/semantic-100.pdf",
        "citation_count": 42,
    }

    response = await client.post(
        f"/projects/{sample_project['id']}/papers/import-citation",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["paper"]["title"] == "Citing Paper"
    assert body["paper"]["status"] == "candidate"
    assert body["paper"]["relevance_score"] is None
    assert body["paper"]["reference_count"] is None
    created_paper_id = body["paper"]["id"]

    duplicate_response = await client.post(
        f"/projects/{sample_project['id']}/papers/import-citation",
        headers=auth_headers,
        json={**payload, "title": "Citing Paper With Updated Title"},
    )

    assert duplicate_response.status_code == 200
    duplicate_body = duplicate_response.json()
    assert duplicate_body["created"] is False
    assert duplicate_body["paper"]["id"] == created_paper_id

    async with session_factory() as session:
        count = int(
            (
                await session.execute(
                    select(func.count()).select_from(Paper).where(Paper.project_id == sample_project["id"])
                )
            ).scalar_one()
        )

    assert count == 1


@pytest.mark.asyncio
async def test_get_project_paper_citation_graph_returns_400_for_unresolvable_paper(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory,
) -> None:
    async with session_factory() as session:
        paper = Paper(
            project_id=sample_project["id"],
            title="Uploaded Paper",
            authors=["Jane Doe"],
            year=2024,
            abstract="This paper has no DOI or upstream id." * 4,
            doi=None,
            source="user_upload",
            source_paper_id="reference-001",
            source_url=None,
            pdf_url="/tmp/reference.pdf",
            status="candidate",
            relevance_score=None,
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)

    class FakePaperCitationService:
        async def get_citation_graph(self, *, session, paper, limit) -> CitationGraphResult:
            del session, paper, limit
            raise CitationResolutionError("Paper cannot be resolved exactly to Semantic Scholar.")

    app.dependency_overrides[get_paper_citation_service] = lambda: FakePaperCitationService()
    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(get_paper_citation_service, None)

    assert response.status_code == 400
    assert "cannot be resolved" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_project_paper_citation_graph_returns_404_when_upstream_misses_exact_paper(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory,
) -> None:
    async with session_factory() as session:
        paper = Paper(
            project_id=sample_project["id"],
            title="Arxiv Paper",
            authors=["Jane Doe"],
            year=2024,
            abstract="This paper only exists locally in the test." * 4,
            doi=None,
            source="arxiv",
            source_paper_id="2401.12345v1",
            source_url="https://arxiv.org/abs/2401.12345v1",
            pdf_url="https://arxiv.org/pdf/2401.12345v1.pdf",
            status="summarized",
            relevance_score=91.2,
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)

    class FakePaperCitationService:
        async def get_citation_graph(self, *, session, paper, limit) -> CitationGraphResult:
            del session, paper, limit
            raise CitationNotFoundError("Exact paper was not found in Semantic Scholar.")

    app.dependency_overrides[get_paper_citation_service] = lambda: FakePaperCitationService()
    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(get_paper_citation_service, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Exact paper was not found in Semantic Scholar."


@pytest.mark.asyncio
async def test_get_project_paper_citation_graph_returns_502_for_provider_failure(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory,
) -> None:
    async with session_factory() as session:
        paper = Paper(
            project_id=sample_project["id"],
            title="Semantic Scholar Paper",
            authors=["Jane Doe"],
            year=2024,
            abstract="This paper simulates an upstream failure." * 4,
            doi="10.1000/provider",
            source="semantic_scholar",
            source_paper_id="semantic-500",
            source_url="https://www.semanticscholar.org/paper/semantic-500",
            pdf_url=None,
            status="summarized",
            relevance_score=88.1,
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)

    class FakePaperCitationService:
        async def get_citation_graph(self, *, session, paper, limit) -> CitationGraphResult:
            del session, paper, limit
            raise CitationProviderError("Semantic Scholar request failed.")

    app.dependency_overrides[get_paper_citation_service] = lambda: FakePaperCitationService()
    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(get_paper_citation_service, None)

    assert response.status_code == 502
    assert response.json()["detail"] == "Semantic Scholar request failed."


@pytest.mark.asyncio
async def test_get_project_paper_citation_graph_validates_limit_query_param(
    client,
    auth_headers,
    sample_project,
) -> None:
    response = await client.get(
        f"/projects/{sample_project['id']}/papers/paper-1/citation-graph?limit=0",
        headers=auth_headers,
    )

    assert response.status_code == 422
