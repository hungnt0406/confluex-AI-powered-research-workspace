import json

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_deep_search_service
from backend.api.routers.projects import encode_sse_event
from backend.db.models import AIUsageEvent, DeepSearchRun, Paper, PaperChunk, Summary, User
from backend.security import create_access_token, hash_password
from backend.services.deep_search import (
    DeepSearchService,
    DeepSearchSourceCandidate,
    deduplicate_source_candidates,
    verify_report_claims,
)
from backend.services.paper_types import PaperRecord
from backend.services.tavily import TavilySearchService


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def test_deep_search_sse_padding_keeps_event_parseable() -> None:
    frame = encode_sse_event("status", {"phase": "planning"}, pad=True)

    assert frame.startswith(": ")
    assert len(frame) > 1024
    assert parse_sse_events(frame) == [("status", {"phase": "planning"})]


async def no_academic_results(
    query: str,
    year_start: int,
    limit: int,
) -> list[PaperRecord]:
    return []


async def one_academic_result(
    query: str,
    year_start: int,
    limit: int,
) -> list[PaperRecord]:
    return [
        {
            "title": f"Academic result for {query}",
            "authors": ["Ada Lovelace"],
            "year": 2025,
            "abstract": "A compact academic source snippet.",
            "doi": "10.1234/deep-search",
            "source": "semantic_scholar",
            "source_paper_id": "paper-123",
            "source_url": "https://papers.example.com/deep-search",
            "pdf_url": "https://papers.example.com/deep-search.pdf",
            "citation_count": 12,
            "reference_count": 4,
            "relevance_score": None,
        }
    ]


async def create_deep_search_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    title: str = "Selected Deep Search Paper",
) -> Paper:
    async with session_factory() as session:
        paper = Paper(
            project_id=project_id,
            title=title,
            authors=["Grace Hopper"],
            year=2024,
            abstract=f"{title} abstract about grounded research.",
            doi="10.1000/deep-search-paper",
            source="semantic_scholar",
            source_paper_id="selected-paper-1",
            source_url="https://papers.example.com/selected-paper",
            pdf_url="https://papers.example.com/selected-paper.pdf",
            status="summarized",
            relevance_score=91.0,
        )
        session.add(paper)
        await session.flush()
        session.add(
            Summary(
                paper_id=paper.id,
                problem="The paper studies research agents.",
                method="It evaluates retrieval and summarization.",
                result="It improves grounded synthesis.",
                relevance_to_topic="Directly relevant to deep search.",
                has_error=False,
                error_message=None,
            )
        )
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=0,
                page_start=2,
                page_end=3,
                section_title="Findings",
                content="The selected paper provides page-grounded findings for deep search.",
                embedding_json=[1.0, 0.0],
            )
        )
        await session.commit()
        await session.refresh(paper)
        return paper


async def create_auth_headers_for_email(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
) -> dict[str, str]:
    async with session_factory() as session:
        user = User(email=email, hashed_password=hash_password("supersecret123"))
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def local_deep_search_service() -> DeepSearchService:
    return DeepSearchService(
        api_key="",
        use_live_llm=False,
        tavily_service=TavilySearchService(api_key=""),
        semantic_scholar_search=no_academic_results,
        arxiv_search=no_academic_results,
    )


@pytest.mark.asyncio
async def test_stream_deep_search_creates_run_streams_sources_and_persists(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_deep_search_paper(session_factory, project_id=sample_project["id"])
    service = local_deep_search_service()
    app.dependency_overrides[get_deep_search_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/deep-search/stream",
        headers=auth_headers,
        json={"paper_ids": [paper.id], "question": "What evidence supports deep search?"},
    )
    app.dependency_overrides.pop(get_deep_search_service, None)

    assert response.status_code == 201
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse_events(response.text)
    event_names = [event_name for event_name, _ in events]
    assert event_names[0] == "run"
    assert "status" in event_names
    assert "source" in event_names
    assert "token" in event_names
    assert event_names[-1] == "done"

    run_payload = events[0][1]
    done_payload = events[-1][1]
    assert done_payload["id"] == run_payload["id"]
    assert done_payload["status"] == "completed"
    assert done_payload["selected_paper_ids"] == [paper.id]
    assert done_payload["report_body"].startswith("# Deep Search Report")
    assert done_payload["sources"]
    assert any("Tavily API key is not configured" in warning for warning in done_payload["warnings"])

    async with session_factory() as session:
        run = await session.get(DeepSearchRun, done_payload["id"])
        assert run is not None
        assert run.status == "completed"
        assert run.user_prompt == "What evidence supports deep search?"


@pytest.mark.asyncio
async def test_deep_search_run_reads_enforce_project_ownership(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = local_deep_search_service()
    app.dependency_overrides[get_deep_search_service] = lambda: service
    create_response = await client.post(
        f"/projects/{sample_project['id']}/deep-search/stream",
        headers=auth_headers,
        json={"paper_ids": [], "question": "Run ownership test."},
    )
    app.dependency_overrides.pop(get_deep_search_service, None)
    run_id = parse_sse_events(create_response.text)[-1][1]["id"]

    own_list_response = await client.get(
        f"/projects/{sample_project['id']}/deep-search-runs",
        headers=auth_headers,
    )
    own_detail_response = await client.get(
        f"/projects/{sample_project['id']}/deep-search-runs/{run_id}",
        headers=auth_headers,
    )
    missing_run_response = await client.get(
        f"/projects/{sample_project['id']}/deep-search-runs/missing-run",
        headers=auth_headers,
    )
    other_headers = await create_auth_headers_for_email(
        session_factory,
        email="deep-search-intruder@example.com",
    )
    unauthorized_response = await client.get(
        f"/projects/{sample_project['id']}/deep-search-runs",
        headers=other_headers,
    )

    assert own_list_response.status_code == 200
    assert own_list_response.json()[0]["id"] == run_id
    assert own_detail_response.status_code == 200
    assert own_detail_response.json()["id"] == run_id
    assert missing_run_response.status_code == 404
    assert missing_run_response.json() == {"detail": "Deep search run not found."}
    assert unauthorized_response.status_code == 404
    assert unauthorized_response.json() == {"detail": "Project not found."}


@pytest.mark.asyncio
async def test_tavily_search_uses_expected_payload_and_bearer_auth() -> None:
    captured_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert request.headers["authorization"] == "Bearer tvly-test"
        payload = json.loads(request.content)
        captured_payloads.append(payload)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Deep search web result",
                        "url": "https://web.example.com/deep-search",
                        "content": "Web source snippet.",
                        "score": 0.87,
                    }
                ],
                "response_time": 0.2,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        service = TavilySearchService(
            api_key="tvly-test",
            base_url="https://api.tavily.com",
            max_results=3,
            http_client=http_client,
        )
        result = await service.search("deep search question")

    assert captured_payloads == [
        {
            "query": "deep search question",
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": 3,
        }
    ]
    assert result.results[0].url == "https://web.example.com/deep-search"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_tavily_failure_continues_deep_search_with_warning(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "upstream unavailable"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        service = DeepSearchService(
            api_key="",
            use_live_llm=False,
            tavily_service=TavilySearchService(
                api_key="tvly-test",
                http_client=http_client,
            ),
            semantic_scholar_search=no_academic_results,
            arxiv_search=no_academic_results,
        )
        app.dependency_overrides[get_deep_search_service] = lambda: service
        response = await client.post(
            f"/projects/{sample_project['id']}/deep-search/stream",
            headers=auth_headers,
            json={"paper_ids": [], "question": "Handle Tavily failure."},
        )
        app.dependency_overrides.pop(get_deep_search_service, None)

    events = parse_sse_events(response.text)
    assert response.status_code == 201
    assert events[-1][0] == "done"
    assert any("Tavily web search failed" in warning for warning in events[-1][1]["warnings"])


@pytest.mark.asyncio
async def test_deep_search_failure_marks_run_failed_and_streams_error(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    class FailingDeepSearchService(DeepSearchService):
        async def _plan_questions(self, *, project_title: str, project_topic: str, question: str) -> list[str]:
            raise RuntimeError("planner failed")

    service = FailingDeepSearchService(
        api_key="",
        use_live_llm=False,
        tavily_service=TavilySearchService(api_key=""),
        semantic_scholar_search=no_academic_results,
        arxiv_search=no_academic_results,
    )
    app.dependency_overrides[get_deep_search_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/deep-search/stream",
        headers=auth_headers,
        json={"paper_ids": [], "question": "Trigger planner failure."},
    )
    app.dependency_overrides.pop(get_deep_search_service, None)

    events = parse_sse_events(response.text)
    assert [event_name for event_name, _ in events] == ["run", "status", "error"]
    run_id = events[0][1]["id"]
    assert events[-1][1] == {"detail": "planner failed", "run_id": run_id}

    async with session_factory() as session:
        run = await session.get(DeepSearchRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert "planner failed" in run.warnings_json


@pytest.mark.asyncio
async def test_deep_search_openrouter_usage_events_are_flushed(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    def openrouter_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload.get("stream") is True:
            body = "\n\n".join(
                [
                    'data: {"choices":[{"delta":{"content":"# Live Report\\n\\nEvidence [S1]."}}]}',
                    'data: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":5,"total_tokens":14}}',
                    "data: [DONE]",
                    "",
                ]
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

        system_prompt = payload["messages"][0]["content"]
        if "planner" in system_prompt.lower():
            content = {"questions": ["What evidence supports deep search?"]}
        elif "compressor" in system_prompt.lower():
            content = {"sources": [{"source_index": 1, "note": "Condensed evidence note."}]}
        else:
            content = {"qa_flags": []}

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    transport = httpx.MockTransport(openrouter_handler)
    async with httpx.AsyncClient(transport=transport) as openrouter_client:
        service = DeepSearchService(
            api_key="sk-test",
            use_live_llm=True,
            planner_model="planner-model",
            summarizer_model="summarizer-model",
            writer_model="writer-model",
            verifier_model="verifier-model",
            http_client=openrouter_client,
            tavily_service=TavilySearchService(api_key=""),
            semantic_scholar_search=one_academic_result,
            arxiv_search=no_academic_results,
        )
        app.dependency_overrides[get_deep_search_service] = lambda: service
        response = await client.post(
            f"/projects/{sample_project['id']}/deep-search/stream",
            headers=auth_headers,
            json={"paper_ids": [], "question": "Use live LLMs."},
        )
        app.dependency_overrides.pop(get_deep_search_service, None)

    assert response.status_code == 201
    assert parse_sse_events(response.text)[-1][0] == "done"

    async with session_factory() as session:
        result = await session.execute(
            select(AIUsageEvent.feature).where(AIUsageEvent.project_id == sample_project["id"])
        )
        features = set(result.scalars().all())

    assert {
        "deep_search_planning",
        "deep_search_web_summarization",
        "deep_search_report_writer",
        "deep_search_verifier",
    }.issubset(features)


@pytest.mark.asyncio
async def test_deep_search_structured_output_truncation_falls_back_without_failing(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
) -> None:
    def openrouter_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload.get("stream") is True:
            body = "\n\n".join(
                [
                    'data: {"choices":[{"delta":{"content":"# Fallback Report\\n\\nEvidence [S1]."}}]}',
                    'data: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":5,"total_tokens":14}}',
                    "data: [DONE]",
                    "",
                ]
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"truncated": true'},
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    transport = httpx.MockTransport(openrouter_handler)
    async with httpx.AsyncClient(transport=transport) as openrouter_client:
        service = DeepSearchService(
            api_key="sk-test",
            use_live_llm=True,
            http_client=openrouter_client,
            tavily_service=TavilySearchService(api_key=""),
            semantic_scholar_search=one_academic_result,
            arxiv_search=no_academic_results,
        )
        app.dependency_overrides[get_deep_search_service] = lambda: service
        response = await client.post(
            f"/projects/{sample_project['id']}/deep-search/stream",
            headers=auth_headers,
            json={"paper_ids": [], "question": "Handle truncated structured output."},
        )
        app.dependency_overrides.pop(get_deep_search_service, None)

    events = parse_sse_events(response.text)
    done_payload = events[-1][1]

    assert response.status_code == 201
    assert events[-1][0] == "done"
    assert done_payload["status"] == "completed"
    assert "Fallback Report" in done_payload["report_body"]
    assert any("planner fell back" in warning for warning in done_payload["warnings"])
    assert any("summarizer fell back" in warning for warning in done_payload["warnings"])
    assert any("verifier fell back" in warning for warning in done_payload["warnings"])


@pytest.mark.asyncio
async def test_deep_search_finalizes_without_run_reload_helper(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    class NoReloadDeepSearchService(DeepSearchService):
        async def _get_run_for_update(self, *, session: AsyncSession, run_id: str) -> DeepSearchRun:
            raise RuntimeError("Deep search run could not be loaded.")

    service = NoReloadDeepSearchService(
        api_key="",
        use_live_llm=False,
        tavily_service=TavilySearchService(api_key=""),
        semantic_scholar_search=one_academic_result,
        arxiv_search=no_academic_results,
    )
    app.dependency_overrides[get_deep_search_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/deep-search/stream",
        headers=auth_headers,
        json={"paper_ids": [], "question": "Finalize without reloading the running row."},
    )
    app.dependency_overrides.pop(get_deep_search_service, None)

    events = parse_sse_events(response.text)
    done_payload = events[-1][1]

    assert response.status_code == 201
    assert events[-1][0] == "done"
    assert done_payload["status"] == "completed"
    assert done_payload["report_body"].startswith("# Deep Search Report")

    async with session_factory() as session:
        run = await session.get(DeepSearchRun, done_payload["id"])
        assert run is not None
        assert run.status == "completed"


def test_deep_search_source_deduplication_and_local_verifier_flags() -> None:
    candidates = [
        DeepSearchSourceCandidate(
            source_type="web",
            title="Duplicate URL",
            url="https://example.com/source",
            paper_id=None,
            snippet="First snippet.",
            metadata={},
        ),
        DeepSearchSourceCandidate(
            source_type="web",
            title="Duplicate URL Copy",
            url="https://example.com/source/",
            paper_id=None,
            snippet="Second snippet.",
            metadata={},
        ),
        DeepSearchSourceCandidate(
            source_type="paper",
            title="Duplicate Paper",
            url=None,
            paper_id="paper-1",
            snippet="Paper snippet.",
            metadata={},
        ),
        DeepSearchSourceCandidate(
            source_type="paper",
            title="Duplicate Paper Copy",
            url=None,
            paper_id="paper-1",
            snippet="Paper snippet copy.",
            metadata={},
        ),
    ]

    deduped = deduplicate_source_candidates(candidates)
    flags = verify_report_claims(
        "This claim has no source citation.",
        [{"id": "S1", "source_type": "paper"}],
    )
    web_only_flags = verify_report_claims(
        "This claim relies on the web only [S1].",
        [{"id": "S1", "source_type": "web"}],
    )

    assert len(deduped) == 2
    assert flags[0]["issue"] == "Claim appears without a source citation."
    assert web_only_flags[0]["issue"] == "Claim relies only on web sources."
