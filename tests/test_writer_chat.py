"""Tests for the writer document chat agent, service, and router."""

from __future__ import annotations

import os
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agents.writer_chat import (
    ChatMessage,
    SectionContent,
    SectionRef,
    WriterChatAgent,
)
from backend.api.routers import writer_documents as writer_router
from backend.db.models import User
from backend.security import create_access_token, hash_password
from backend.services.chat_session_store import (
    ChatSession,
    InMemoryChatSessionStore,
)
from backend.services.writer_chat import WriterChatService


class FakeChatLLM:
    """In-memory stand-in for a StructuredOutputClient (JSON + chat)."""

    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        configured: bool = True,
    ) -> None:
        self.responses = responses or []
        self.configured = configured
        self.json_calls: list[dict[str, Any]] = []
        self.chat_calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.json_calls.append(kwargs)
        if not self.responses:
            return {"reply": "ok", "summary_for_history": "", "patches": []}
        index = min(len(self.json_calls) - 1, len(self.responses) - 1)
        return self.responses[index]

    async def generate_chat(self, **kwargs: Any) -> Any:
        self.chat_calls.append(kwargs)
        # Not used by the agent in the happy path; left as a stub.
        from backend.services.llm import ChatCompletion

        return ChatCompletion(content="{}", usage={})


@pytest_asyncio.fixture
async def chat_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    async with session_factory() as session:
        user = User(
            email="writer-chat@example.com",
            hashed_password=hash_password("writerpass"),
            credit_balance=1_000,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return {"id": user.id, "email": user.email}


@pytest_asyncio.fixture
async def chat_auth_headers(chat_user: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(chat_user['id'])}"}


async def create_writer_document(
    client: AsyncClient,
    headers: dict[str, str],
    section_drafts: dict[int, str] | None = None,
    title: str = "Chat Doc",
) -> dict[str, Any]:
    response = await client.post(
        "/writer/documents",
        json={"topic": "writer chat tests", "title": title},
        headers=headers,
    )
    assert response.status_code == 201
    doc = response.json()
    if section_drafts:
        for idx, draft in section_drafts.items():
            section_id = doc["sections"][idx]["id"]
            edit_resp = await client.patch(
                f"/writer/documents/{doc['id']}/sections/{section_id}",
                json={"draft_latex": draft},
                headers=headers,
            )
            assert edit_resp.status_code == 200
    # Re-fetch so section drafts are reflected.
    refreshed = await client.get(
        f"/writer/documents/{doc['id']}", headers=headers
    )
    assert refreshed.status_code == 200
    return refreshed.json()


def install_chat_service(app: Any, service: WriterChatService) -> None:
    app.dependency_overrides[writer_router.get_writer_chat_service] = lambda: service


def build_service(
    *,
    responses: list[dict[str, Any]] | None = None,
    configured: bool = True,
    store: InMemoryChatSessionStore | None = None,
) -> tuple[WriterChatService, FakeChatLLM, InMemoryChatSessionStore]:
    llm = FakeChatLLM(responses=responses, configured=configured)
    chat_store = store or InMemoryChatSessionStore()
    service = WriterChatService(
        agent=WriterChatAgent(client=llm),  # type: ignore[arg-type]
        session_store=chat_store,
    )
    return service, llm, chat_store


# ----------------------------------------------------------------- agent-level tests


async def test_agent_offline_returns_stub() -> None:
    agent = WriterChatAgent(client=FakeChatLLM(configured=False))  # type: ignore[arg-type]
    result = await agent.respond(
        document_outline=[SectionRef(id="s1", title="Intro", length=10, position=0)],
        included_sections=[SectionContent(id="s1", title="Intro", draft_latex="Hello.")],
        known_citation_keys=set(),
        chat_history=[],
        user_message="tighten this",
    )
    assert result.patches == []
    assert "offline" in result.reply.lower()


async def test_agent_returns_single_section_patch() -> None:
    draft = "Hello world."
    llm = FakeChatLLM(
        responses=[
            {
                "reply": "Tightened the wording.",
                "summary_for_history": "Tightened intro.",
                "patches": [
                    {
                        "section_id": "s1",
                        "span": {"start": 0, "end": len(draft)},
                        "original_text": draft,
                        "new_text": "Hi world.",
                        "rationale": "Shorter opener.",
                    }
                ],
            }
        ]
    )
    agent = WriterChatAgent(client=llm)  # type: ignore[arg-type]
    result = await agent.respond(
        document_outline=[SectionRef(id="s1", title="Intro", length=len(draft), position=0)],
        included_sections=[SectionContent(id="s1", title="Intro", draft_latex=draft)],
        known_citation_keys=set(),
        chat_history=[],
        user_message="tighten",
    )
    assert len(result.patches) == 1
    assert result.patches[0].new_text == "Hi world."
    assert result.patches[0].original_text == draft


async def test_agent_returns_multi_section_patches() -> None:
    abstract = "Abstract draft text."
    conclusion = "Conclusion draft text."
    llm = FakeChatLLM(
        responses=[
            {
                "reply": "Reconciled the two sections.",
                "summary_for_history": "Reconciled abstract+conclusion.",
                "patches": [
                    {
                        "section_id": "s1",
                        "span": {"start": 0, "end": len(abstract)},
                        "original_text": abstract,
                        "new_text": "Updated abstract.",
                        "rationale": "Reconcile abstract.",
                    },
                    {
                        "section_id": "s2",
                        "span": {"start": 0, "end": len(conclusion)},
                        "original_text": conclusion,
                        "new_text": "Updated conclusion.",
                        "rationale": "Reconcile conclusion.",
                    },
                ],
            }
        ]
    )
    agent = WriterChatAgent(client=llm)  # type: ignore[arg-type]
    result = await agent.respond(
        document_outline=[
            SectionRef(id="s1", title="Abstract", length=len(abstract), position=0),
            SectionRef(id="s2", title="Conclusion", length=len(conclusion), position=1),
        ],
        included_sections=[
            SectionContent(id="s1", title="Abstract", draft_latex=abstract),
            SectionContent(id="s2", title="Conclusion", draft_latex=conclusion),
        ],
        known_citation_keys=set(),
        chat_history=[],
        user_message="make the abstract and conclusion consistent",
    )
    assert [p.section_id for p in result.patches] == ["s1", "s2"]


async def test_agent_drops_unknown_citation_keys() -> None:
    draft = "Foo bar."
    llm = FakeChatLLM(
        responses=[
            {
                "reply": "Updated.",
                "summary_for_history": "",
                "patches": [
                    {
                        "section_id": "s1",
                        "span": {"start": 0, "end": len(draft)},
                        "original_text": draft,
                        "new_text": "Foo \\cite{ghost} bar.",
                        "rationale": "Inserted citation.",
                    }
                ],
            }
        ]
    )
    agent = WriterChatAgent(client=llm)  # type: ignore[arg-type]
    result = await agent.respond(
        document_outline=[SectionRef(id="s1", title="Intro", length=len(draft), position=0)],
        included_sections=[SectionContent(id="s1", title="Intro", draft_latex=draft)],
        known_citation_keys=set(),
        chat_history=[],
        user_message="add citation",
    )
    assert result.patches == []
    assert "unknown citation" in result.reply.lower() or "ghost" in result.reply.lower()


# ----------------------------------------------------------------- router-level tests


async def test_create_chat_returns_empty_thread(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    service, _llm, _store = build_service()
    install_chat_service(app, service)
    doc = await create_writer_document(client, chat_auth_headers)

    response = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == doc["id"]
    assert data["messages"] == []
    assert data["id"]


async def test_post_message_offline_returns_stub_no_patches(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    service, _llm, _store = build_service(configured=False)
    install_chat_service(app, service)
    doc = await create_writer_document(client, chat_auth_headers, {1: "Some text."})

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    response = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "tighten this"},
        headers=chat_auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"]["patches"] == []
    assert "offline" in payload["assistant_message"]["content"].lower()


async def test_post_message_single_section_patch(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    draft = "Original sentence."
    doc = await create_writer_document(client, chat_auth_headers, {1: draft})
    section = doc["sections"][1]
    service, _llm, _store = build_service(
        responses=[
            {
                "reply": "Tightened.",
                "summary_for_history": "",
                "patches": [
                    {
                        "section_id": section["id"],
                        "span": {"start": 0, "end": len(draft)},
                        "original_text": draft,
                        "new_text": "Updated sentence.",
                        "rationale": "Tighter.",
                    }
                ],
            }
        ]
    )
    install_chat_service(app, service)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    response = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "tighten this"},
        headers=chat_auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    patches = payload["assistant_message"]["patches"]
    assert len(patches) == 1
    assert patches[0]["section_id"] == section["id"]
    assert patches[0]["status"] == "pending"


async def test_post_message_multi_section_patches(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    abstract = "Abstract body."
    conclusion = "Conclusion body."
    doc = await create_writer_document(
        client, chat_auth_headers, {0: abstract, 6: conclusion}
    )
    s_abstract = doc["sections"][0]
    s_conclusion = doc["sections"][6]
    service, _llm, _store = build_service(
        responses=[
            {
                "reply": "Reconciled.",
                "summary_for_history": "",
                "patches": [
                    {
                        "section_id": s_abstract["id"],
                        "span": {"start": 0, "end": len(abstract)},
                        "original_text": abstract,
                        "new_text": "New abstract.",
                        "rationale": "Reconcile.",
                    },
                    {
                        "section_id": s_conclusion["id"],
                        "span": {"start": 0, "end": len(conclusion)},
                        "original_text": conclusion,
                        "new_text": "New conclusion.",
                        "rationale": "Reconcile.",
                    },
                ],
            }
        ]
    )
    install_chat_service(app, service)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    response = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "make the abstract and conclusion consistent"},
        headers=chat_auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    patches = payload["assistant_message"]["patches"]
    assert {p["section_id"] for p in patches} == {s_abstract["id"], s_conclusion["id"]}


async def test_accept_patch_updates_section_and_creates_version(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    draft = "Original sentence."
    doc = await create_writer_document(client, chat_auth_headers, {1: draft})
    section = doc["sections"][1]
    service, _llm, _store = build_service(
        responses=[
            {
                "reply": "Done.",
                "summary_for_history": "",
                "patches": [
                    {
                        "section_id": section["id"],
                        "span": {"start": 0, "end": len(draft)},
                        "original_text": draft,
                        "new_text": "Updated sentence.",
                        "rationale": "Tighter.",
                    }
                ],
            }
        ]
    )
    install_chat_service(app, service)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    post = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "tighten"},
        headers=chat_auth_headers,
    )
    msg_id = post.json()["assistant_message"]["id"]

    accept = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message/{msg_id}/patch/0/accept",
        headers=chat_auth_headers,
    )
    assert accept.status_code == 200
    assert accept.json()["draft_latex"] == "Updated sentence."

    versions = await client.get(
        f"/writer/documents/{doc['id']}/sections/{section['id']}/versions",
        headers=chat_auth_headers,
    )
    assert versions.status_code == 200
    assert versions.json()[0]["draft_latex"] == draft

    chat = await client.get(
        f"/writer/documents/{doc['id']}/chat/{chat_id}", headers=chat_auth_headers
    )
    assert chat.json()["messages"][-1]["patches"][0]["status"] == "applied"


async def test_reject_patch_marks_status_and_does_not_write(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    draft = "Original sentence."
    doc = await create_writer_document(client, chat_auth_headers, {1: draft})
    section = doc["sections"][1]
    service, _llm, _store = build_service(
        responses=[
            {
                "reply": "Done.",
                "summary_for_history": "",
                "patches": [
                    {
                        "section_id": section["id"],
                        "span": {"start": 0, "end": len(draft)},
                        "original_text": draft,
                        "new_text": "Updated sentence.",
                        "rationale": "Tighter.",
                    }
                ],
            }
        ]
    )
    install_chat_service(app, service)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    post = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "tighten"},
        headers=chat_auth_headers,
    )
    msg_id = post.json()["assistant_message"]["id"]

    reject = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message/{msg_id}/patch/0/reject",
        headers=chat_auth_headers,
    )
    assert reject.status_code == 200
    assert reject.json() == {"ok": True}

    refreshed = await client.get(
        f"/writer/documents/{doc['id']}", headers=chat_auth_headers
    )
    section_after = next(s for s in refreshed.json()["sections"] if s["id"] == section["id"])
    assert section_after["draft_latex"] == draft

    chat = await client.get(
        f"/writer/documents/{doc['id']}/chat/{chat_id}", headers=chat_auth_headers
    )
    assert chat.json()["messages"][-1]["patches"][0]["status"] == "rejected"


async def test_undo_patch_restores_previous_version(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    draft = "Original sentence."
    doc = await create_writer_document(client, chat_auth_headers, {1: draft})
    section = doc["sections"][1]
    service, _llm, _store = build_service(
        responses=[
            {
                "reply": "Done.",
                "summary_for_history": "",
                "patches": [
                    {
                        "section_id": section["id"],
                        "span": {"start": 0, "end": len(draft)},
                        "original_text": draft,
                        "new_text": "Updated sentence.",
                        "rationale": "Tighter.",
                    }
                ],
            }
        ]
    )
    install_chat_service(app, service)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    post = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "tighten"},
        headers=chat_auth_headers,
    )
    msg_id = post.json()["assistant_message"]["id"]

    accept = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message/{msg_id}/patch/0/accept",
        headers=chat_auth_headers,
    )
    assert accept.status_code == 200

    undo = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message/{msg_id}/patch/0/undo",
        headers=chat_auth_headers,
    )
    assert undo.status_code == 200
    assert undo.json()["draft_latex"] == draft


async def test_accept_returns_409_when_draft_changed(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    draft = "Original sentence."
    doc = await create_writer_document(client, chat_auth_headers, {1: draft})
    section = doc["sections"][1]
    service, _llm, _store = build_service(
        responses=[
            {
                "reply": "Done.",
                "summary_for_history": "",
                "patches": [
                    {
                        "section_id": section["id"],
                        "span": {"start": 0, "end": len(draft)},
                        "original_text": draft,
                        "new_text": "Updated sentence.",
                        "rationale": "Tighter.",
                    }
                ],
            }
        ]
    )
    install_chat_service(app, service)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    post = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "tighten"},
        headers=chat_auth_headers,
    )
    msg_id = post.json()["assistant_message"]["id"]

    # User edits in between.
    await client.patch(
        f"/writer/documents/{doc['id']}/sections/{section['id']}",
        json={"draft_latex": "Drastically different text."},
        headers=chat_auth_headers,
    )

    accept = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message/{msg_id}/patch/0/accept",
        headers=chat_auth_headers,
    )
    assert accept.status_code == 409

    chat = await client.get(
        f"/writer/documents/{doc['id']}/chat/{chat_id}", headers=chat_auth_headers
    )
    assert chat.json()["messages"][-1]["patches"][0]["status"] == "stale"


async def test_context_budget_window_slices_history(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    """After more turns than the window, older assistant turns fold into history_summary."""

    draft = "Original sentence."
    doc = await create_writer_document(client, chat_auth_headers, {1: draft})
    section = doc["sections"][1]

    def response_for_turn(reply: str) -> dict[str, Any]:
        return {
            "reply": reply,
            "summary_for_history": reply[:40],
            "patches": [
                {
                    "section_id": section["id"],
                    "span": {"start": 0, "end": len(draft)},
                    "original_text": draft,
                    "new_text": draft,
                    "rationale": "noop",
                }
            ],
        }

    responses = [response_for_turn(f"Reply turn {i}") for i in range(10)]
    service, llm, _store = build_service(responses=responses)
    install_chat_service(app, service)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]

    for i in range(8):
        post = await client.post(
            f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
            json={"content": f"turn {i}"},
            headers=chat_auth_headers,
        )
        assert post.status_code == 200

    # The agent's last call should have received only the windowed history.
    last_prompt = llm.json_calls[-1]["user_prompt"]
    assert "turn 7" in last_prompt
    # Earlier turns must be folded into the rolling summary.
    assert "turn 0" not in last_prompt or "summary" in last_prompt.lower()

    chat = await client.get(
        f"/writer/documents/{doc['id']}/chat/{chat_id}", headers=chat_auth_headers
    )
    assert chat.json()["history_summary"]


async def test_post_message_charges_credits_for_non_admin(
    client: AsyncClient,
    app: Any,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(
            email="chat-empty@example.com",
            hashed_password=hash_password("writerpass"),
            credit_balance=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    service, _llm, _store = build_service(configured=False)
    install_chat_service(app, service)
    doc = await create_writer_document(client, headers)
    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=headers
    )
    chat_id = create.json()["id"]
    response = await client.post(
        f"/writer/documents/{doc['id']}/chat/{chat_id}/message",
        json={"content": "tighten"},
        headers=headers,
    )
    assert response.status_code == 402
    assert response.json()["required"] == 3


async def test_session_ttl_evicts_in_memory_store(
    client: AsyncClient,
    app: Any,
    chat_auth_headers: dict[str, str],
) -> None:
    store = InMemoryChatSessionStore()
    fake_now = [1_000.0]
    store.set_clock(lambda: fake_now[0])
    service, _llm, _store = build_service(store=store)
    install_chat_service(app, service)
    doc = await create_writer_document(client, chat_auth_headers)

    create = await client.post(
        f"/writer/documents/{doc['id']}/chat", headers=chat_auth_headers
    )
    chat_id = create.json()["id"]
    # Push the fake clock past the TTL window.
    from backend.config import get_settings

    fake_now[0] += get_settings().writer_chat_session_ttl_seconds + 1

    get_resp = await client.get(
        f"/writer/documents/{doc['id']}/chat/{chat_id}", headers=chat_auth_headers
    )
    assert get_resp.status_code == 404


# ----------------------------------------------------------------- redis path


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="requires REDIS_URL")
async def test_redis_chat_session_store_roundtrip() -> None:
    from backend.services.chat_session_store import RedisChatSessionStore
    from backend.services.redis_client import get_redis

    client = await get_redis()
    assert client is not None, "REDIS_URL set but no redis client available"
    store = RedisChatSessionStore(client)
    chat = ChatSession(
        id="test-chat-1",
        document_id="doc-1",
        user_id="user-1",
        messages=[],
        last_active_at=0.0,
        history_summary="",
    )
    await store.put(chat.id, chat, ttl_seconds=10)
    got = await store.get(chat.id)
    assert got is not None and got.id == "test-chat-1"
    metas = await store.list_for_document("doc-1", "user-1")
    assert any(m.id == "test-chat-1" for m in metas)
    await store.delete(chat.id)


async def test_chat_message_includes_history_summary_attribute() -> None:
    """Smoke test: ChatMessage carries optional summary metadata for the agent."""

    msg = ChatMessage(role="user", content="hi")
    assert msg.summary_for_history == ""
