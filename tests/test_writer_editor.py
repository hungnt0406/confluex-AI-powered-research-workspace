"""Tests for the draft-only writer editor agent and routes."""

from __future__ import annotations

from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agents.writer_editor import (
    NewResult,
    TextSpan,
    WriterEditorAgent,
)
from backend.api.routers import writer_documents as writer_router
from backend.db.models import User
from backend.security import create_access_token, hash_password
from backend.services.tavily import TavilySearchResponse, TavilySearchResult
from backend.services.writer_editor import WriterEditorService


class FakeEditorLLM:
    def __init__(
        self,
        response: dict[str, Any] | list[dict[str, Any]] | None = None,
        configured: bool = True,
    ) -> None:
        self.responses = (
            list(response)
            if isinstance(response, list)
            else [response or {"new_text": "Revised claim.", "rationale": "Tightened wording."}]
        )
        self.configured = configured
        self.calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class FakeTavily:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
    ) -> TavilySearchResponse:
        self.calls.append(
            {"query": query, "max_results": max_results, "include_domains": include_domains}
        )
        return TavilySearchResponse(
            results=[
                TavilySearchResult(
                    title="External Result",
                    url="https://example.com/result",
                    content="External finding snippet.",
                    score=0.9,
                )
            ],
            warnings=[],
        )


@pytest_asyncio.fixture
async def writer_editor_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    async with session_factory() as session:
        user = User(
            email="writer-editor@example.com",
            hashed_password=hash_password("writerpass"),
            credit_balance=100,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return {"id": user.id, "email": user.email}


@pytest_asyncio.fixture
async def writer_editor_headers(writer_editor_user: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(writer_editor_user['id'])}"}


async def create_document_with_draft(
    client: AsyncClient,
    headers: dict[str, str],
    draft: str,
) -> tuple[str, str]:
    response = await client.post(
        "/writer/documents",
        json={"topic": "draft editing", "title": "Draft Editing"},
        headers=headers,
    )
    assert response.status_code == 201
    doc = response.json()
    section_id = doc["sections"][1]["id"]
    edit_response = await client.patch(
        f"/writer/documents/{doc['id']}/sections/{section_id}",
        json={"draft_latex": draft},
        headers=headers,
    )
    assert edit_response.status_code == 200
    return doc["id"], section_id


async def test_edit_revises_selected_span_and_preserves_citation_macro() -> None:
    agent = WriterEditorAgent(
        llm_client=FakeEditorLLM({"new_text": "Revised claim.", "rationale": "Fixed grammar."})  # type: ignore[arg-type]
    )
    draft = r"Awkward claim \cite{paper-1} remains."

    patch = await agent.edit(
        draft=draft,
        instruction="Fix grammar.",
        section_heading="Body",
        span=TextSpan(start=0, end=len(draft)),
        known_citation_keys={"paper-1"},
    )

    assert patch.new_text.startswith("Revised claim.")
    assert r"\cite{paper-1}" in patch.new_text
    assert patch.original_text == draft


async def test_edit_paraphrase_retries_when_provider_returns_same_text() -> None:
    selected = (
        r"\subsection{Scope} "
        r"This survey focuses on methods for high-speed object tracking. \cite{paper-1}"
    )
    llm = FakeEditorLLM(
        [
            {"new_text": selected, "rationale": "Revised draft text."},
            {
                "new_text": (
                    r"\subsection{Scope} "
                    r"This survey examines approaches to high-speed object tracking. \cite{paper-1}"
                ),
                "rationale": "Rephrased the sentence while preserving the citation.",
            },
        ]
    )
    agent = WriterEditorAgent(llm_client=llm)  # type: ignore[arg-type]

    patch = await agent.edit(
        draft=selected,
        instruction="paraphrase this paragraph",
        section_heading="Body",
        span=TextSpan(start=0, end=len(selected)),
        known_citation_keys={"paper-1"},
    )

    assert len(llm.calls) == 2
    assert patch.new_text != selected
    assert "examines approaches" in patch.new_text
    assert r"\cite{paper-1}" in patch.new_text


async def test_edit_paraphrase_noop_uses_deterministic_fallback() -> None:
    selected = "This survey focuses on methods for high-speed object tracking."
    agent = WriterEditorAgent(
        llm_client=FakeEditorLLM({"new_text": selected, "rationale": "Revised draft text."})  # type: ignore[arg-type]
    )

    patch = await agent.edit(
        draft=selected,
        instruction="please paraphrase",
        section_heading="Body",
        span=TextSpan(start=0, end=len(selected)),
    )

    assert patch.new_text != selected
    assert "examines" in patch.new_text
    assert patch.rationale == "Paraphrased selected text while preserving citations."


async def test_edit_insertion_offline_returns_deterministic_insert() -> None:
    agent = WriterEditorAgent(llm_client=FakeEditorLLM(configured=False))  # type: ignore[arg-type]
    draft = r"\section{Results} Existing paragraph."

    patch = await agent.edit(
        draft=draft,
        instruction="Add robustness finding",
        section_heading="Results",
        insertion_offset=len(draft),
    )

    assert patch.span.start == patch.span.end
    assert "Add robustness finding" in patch.new_text
    assert patch.rationale == "offline_stub"
    assert r"\cite{" not in patch.new_text


async def test_edit_insertion_replaces_prompt_echo_with_paragraph() -> None:
    topic = (
        "Explain the research gap: existing trackers often work well on ordinary "
        "motion but degrade when targets are blurred, occluded, or visible for only a few frames."
    )
    agent = WriterEditorAgent(
        llm_client=FakeEditorLLM({"new_text": topic, "rationale": "Revised draft text."})  # type: ignore[arg-type]
    )
    draft = r"\section{Introduction} Prior paragraph."

    patch = await agent.edit(
        draft=draft,
        instruction=topic,
        section_heading="Introduction",
        insertion_offset=len(draft),
    )

    assert patch.new_text.strip() != topic
    assert "Explain the research gap" not in patch.new_text
    assert "standard trackers can perform adequately" in patch.new_text
    assert patch.rationale == "Generated a paragraph from the requested topic."


async def test_edit_revision_with_findings_offline_appends_citation() -> None:
    agent = WriterEditorAgent(llm_client=FakeEditorLLM(configured=False))  # type: ignore[arg-type]
    draft = "Baseline result is stable."

    patch = await agent.edit(
        draft=draft,
        instruction="Incorporate the ablation finding.",
        section_heading="Results",
        span=TextSpan(start=0, end=len(draft)),
        new_results=[
            NewResult(
                text="The ablation improves F1 by two points.",
                source_ref="Ablation Table 1",
                attach_as_citation=True,
            )
        ],
    )

    assert "ablation improves F1" in patch.new_text
    assert r"\cite{Ablation_Table_1}" in patch.new_text


async def test_preview_with_web_search_returns_web_citations(
    client: AsyncClient,
    app,
    writer_editor_headers: dict[str, str],
) -> None:
    tavily = FakeTavily()
    service = WriterEditorService(
        agent=WriterEditorAgent(llm_client=FakeEditorLLM(configured=False)),  # type: ignore[arg-type]
        tavily_service=tavily,  # type: ignore[arg-type]
    )
    app.dependency_overrides[writer_router.get_writer_editor_service] = lambda: service
    doc_id, section_id = await create_document_with_draft(
        client,
        writer_editor_headers,
        r"\section{Results} Existing paragraph.",
    )

    response = await client.post(
        f"/writer/documents/{doc_id}/sections/{section_id}/edit",
        json={
            "instruction": "new retrieval result",
            "insertion_offset": 36,
            "web_search": True,
            "web_query": "retrieval result",
        },
        headers=writer_editor_headers,
    )

    assert response.status_code == 200
    assert response.json()["web_citations"][0]["url"] == "https://example.com/result"
    assert tavily.calls[0]["max_results"] == 5


async def test_apply_rejects_stale_patch(
    client: AsyncClient,
    writer_editor_headers: dict[str, str],
) -> None:
    doc_id, section_id = await create_document_with_draft(
        client,
        writer_editor_headers,
        "Original sentence.",
    )
    preview = await client.post(
        f"/writer/documents/{doc_id}/sections/{section_id}/edit",
        json={
            "instruction": "tighten the wording",
            "span": {"start": 0, "end": len("Original sentence.")},
        },
        headers=writer_editor_headers,
    )
    assert preview.status_code == 200
    await client.patch(
        f"/writer/documents/{doc_id}/sections/{section_id}",
        json={"draft_latex": "Changed sentence."},
        headers=writer_editor_headers,
    )

    response = await client.post(
        f"/writer/documents/{doc_id}/sections/{section_id}/edit/apply",
        json=preview.json(),
        headers=writer_editor_headers,
    )

    assert response.status_code == 409


async def test_apply_uses_section_versioning(
    client: AsyncClient,
    writer_editor_headers: dict[str, str],
) -> None:
    doc_id, section_id = await create_document_with_draft(
        client,
        writer_editor_headers,
        "Original sentence.",
    )
    patch = {
        "span": {"start": 0, "end": len("Original sentence.")},
        "new_text": "Updated sentence.",
        "rationale": "Test patch.",
        "web_citations": [],
        "original_text": "Original sentence.",
    }

    response = await client.post(
        f"/writer/documents/{doc_id}/sections/{section_id}/edit/apply",
        json=patch,
        headers=writer_editor_headers,
    )

    assert response.status_code == 200
    assert response.json()["draft_latex"] == "Updated sentence."
    versions = await client.get(
        f"/writer/documents/{doc_id}/sections/{section_id}/versions",
        headers=writer_editor_headers,
    )
    assert versions.status_code == 200
    assert versions.json()[0]["draft_latex"] == "Original sentence."


async def test_preview_requires_credits(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(
            email="writer-editor-empty@example.com",
            hashed_password=hash_password("writerpass"),
            credit_balance=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    doc_id, section_id = await create_document_with_draft(client, headers, "Original sentence.")
    response = await client.post(
        f"/writer/documents/{doc_id}/sections/{section_id}/edit",
        json={
            "instruction": "tighten the wording",
            "span": {"start": 0, "end": 8},
        },
        headers=headers,
    )

    assert response.status_code == 402
    assert response.json()["required"] == 2


async def test_edit_request_requires_span_or_insertion_offset(
    client: AsyncClient,
    writer_editor_headers: dict[str, str],
) -> None:
    doc_id, section_id = await create_document_with_draft(
        client,
        writer_editor_headers,
        "Original sentence.",
    )

    response = await client.post(
        f"/writer/documents/{doc_id}/sections/{section_id}/edit",
        json={"instruction": "do something"},
        headers=writer_editor_headers,
    )

    assert response.status_code == 422
    assert "span or insertion_offset" in response.text
