import json

import httpx
import pytest
import respx
from sqlalchemy import select

from backend.db.models import AIUsageEvent
from backend.services.ai_usage import (
    collect_openrouter_usage,
    flush_usage_events,
    start_usage_collection,
)
from backend.services.embeddings import EmbeddingService
from backend.services.llm import OpenRouterStructuredOutputService


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_structured_output_service_posts_chat_completion_request() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"queries":[{"query":"agent systems","focus":"broad"}]}'
                        },
                    }
                ]
            },
        )

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(side_effect=handler)
    service = OpenRouterStructuredOutputService(
        api_key="sk-or-test-key",
        model="google/gemma-4-31b-it:free",
    )

    payload = await service.generate_json(
        system_prompt="System prompt",
        user_prompt="User prompt",
        schema={
            "type": "object",
            "properties": {
                "queries": {"type": "array"},
            },
            "required": ["queries"],
            "additionalProperties": False,
        },
    )

    assert route.called
    assert payload == {"queries": [{"query": "agent systems", "focus": "broad"}]}
    assert captured_request is not None
    request_body = json.loads(captured_request.content.decode("utf-8"))
    assert request_body["model"] == "google/gemma-4-31b-it:free"
    assert request_body["messages"][0] == {"role": "system", "content": "System prompt"}
    assert request_body["messages"][1] == {"role": "user", "content": "User prompt"}
    assert request_body["response_format"]["type"] == "json_schema"
    assert request_body["provider"]["require_parameters"] is True


@pytest.mark.asyncio
@respx.mock
async def test_embedding_service_posts_openrouter_embeddings_request() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ]
            },
        )

    route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(side_effect=handler)
    service = EmbeddingService(
        api_key="sk-or-test-key",
        model="openai/text-embedding-3-small",
        dimensions=3,
    )

    embeddings = await service.embed_texts(["topic", "paper"])

    assert route.called
    assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert captured_request is not None
    request_body = json.loads(captured_request.content.decode("utf-8"))
    assert request_body["model"] == "openai/text-embedding-3-small"
    assert request_body["dimensions"] == 3
    assert request_body["provider"]["sort"] == "price"


@pytest.mark.asyncio
async def test_openrouter_usage_extraction_handles_partial_usage(
    session_factory,
    sample_user,
    sample_project,
) -> None:
    start_usage_collection()
    collect_openrouter_usage(
        endpoint="chat/completions",
        feature="query_expansion",
        model="test/chat",
        response_payload={
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 3},
                "cost": 0,
            }
        },
    )
    collect_openrouter_usage(
        endpoint="embeddings",
        feature="ranking_embedding",
        model="openai/text-embedding-3-small",
        response_payload={
            "usage": {
                "prompt_tokens": 5,
                "total_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 2},
            }
        },
    )

    async with session_factory() as session:
        await flush_usage_events(
            session=session,
            user_id=sample_user["id"],
            project_id=sample_project["id"],
        )
        events = (
            await session.execute(
                select(AIUsageEvent).order_by(AIUsageEvent.endpoint.asc())
            )
        ).scalars().all()

    assert len(events) == 2
    chat_event = next(event for event in events if event.endpoint == "chat/completions")
    assert chat_event.feature == "query_expansion"
    assert chat_event.prompt_tokens == 7
    assert chat_event.completion_tokens is None
    assert chat_event.total_tokens is None
    assert chat_event.reasoning_tokens == 3
    assert chat_event.cost_credits == 0

    embedding_event = next(event for event in events if event.endpoint == "embeddings")
    assert embedding_event.feature == "ranking_embedding"
    assert embedding_event.prompt_tokens == 5
    assert embedding_event.total_tokens == 5
    assert embedding_event.cached_tokens == 2
