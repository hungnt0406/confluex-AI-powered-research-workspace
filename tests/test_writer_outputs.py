import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import Paper, Summary, User, WriterOutput
from backend.security import create_access_token, hash_password


async def create_writer_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    title: str,
    authors: list[str],
    year: int,
    abstract: str,
    problem: str,
    method: str,
    result: str,
) -> Paper:
    async with session_factory() as session:
        paper = Paper(
            project_id=project_id,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            doi=None,
            source="semantic_scholar",
            source_paper_id=f"source-{title.lower().replace(' ', '-')}",
            source_url=None,
            pdf_url=None,
            status="summarized",
            relevance_score=90.0,
        )
        session.add(paper)
        await session.flush()
        session.add(
            Summary(
                paper_id=paper.id,
                problem=problem,
                method=method,
                result=result,
                relevance_to_topic="Directly relevant to writer-grounded review generation.",
                has_error=False,
                error_message=None,
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


@pytest.mark.asyncio
async def test_generate_writer_output_infers_docs_author_year_defaults_and_persists_output(
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper_one = await create_writer_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Grounded Retrieval for Scientific Writing",
        authors=["Ada Lovelace", "Grace Hopper"],
        year=2024,
        abstract="This paper studies grounded retrieval for scientific writing assistants.",
        problem="scientific writing systems need paper-grounded evidence",
        method="retrieval over persisted document chunks",
        result="grounded generation improves citation faithfulness",
    )
    paper_two = await create_writer_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Structured Summaries for Literature Reviews",
        authors=["Katherine Johnson"],
        year=2023,
        abstract="This paper studies structured summaries for literature review workflows.",
        problem="literature reviews need compact evidence representations",
        method="paper summaries aligned to review tasks",
        result="structured summaries improve synthesis speed",
    )

    response = await client.post(
        f"/projects/{sample_project['id']}/writer/generate",
        headers=auth_headers,
        json={
            "paper_ids": [paper_one.id, paper_two.id],
            "instruction": "Write a related work section grounded in these papers.",
            "output_target": "docs",
            "include_references": True,
            "max_words": 180,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project_id"] == sample_project["id"]
    assert payload["citation_mode"] == "author_year"
    assert payload["reference_style"] == "apa"
    assert payload["selected_paper_ids"] == [paper_one.id, paper_two.id]
    assert payload["body"].startswith("## Related Work")
    assert "(Lovelace, 2024" in payload["body"] or "(Johnson, 2023" in payload["body"]
    assert len(payload["references"]) == 2
    assert payload["bibtex_entries"] == []
    assert payload["thebibliography"] is None
    assert payload["citations_used"] == [paper_one.id, paper_two.id]
    assert payload["qa_flags"] == []
    assert response.headers["Location"].endswith(f"/projects/{sample_project['id']}/writer/outputs/{payload['id']}")

    async with session_factory() as session:
        stored_output = await session.get(WriterOutput, payload["id"])

    assert stored_output is not None
    assert stored_output.output_target == "docs"


@pytest.mark.asyncio
async def test_generate_writer_output_returns_latex_thebibliography_artifacts(
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_writer_paper(
        session_factory,
        project_id=sample_project["id"],
        title="LaTeX-Friendly Citation Pipelines",
        authors=["Donald Knuth"],
        year=2022,
        abstract="This paper studies citation pipelines for LaTeX workflows.",
        problem="LaTeX users need stable citation artifacts",
        method="deterministic citation key generation",
        result="stable citation keys reduce formatting churn",
    )

    response = await client.post(
        f"/projects/{sample_project['id']}/writer/generate",
        headers=auth_headers,
        json={
            "paper_ids": [paper.id],
            "instruction": "Write a related work subsection in LaTeX and include thebibliography output.",
            "output_target": "latex",
            "citation_mode": "thebibliography",
            "reference_style": "ieee",
            "include_references": True,
            "max_words": 120,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["citation_mode"] == "thebibliography"
    assert payload["body"].startswith("\\subsection{Related Work}")
    assert "\\cite{" in payload["body"]
    assert payload["references"] == []
    assert payload["bibtex_entries"] == []
    assert payload["thebibliography"] is not None
    assert payload["thebibliography"].startswith("\\begin{thebibliography}{99}")
    assert payload["thebibliography"].endswith("\\end{thebibliography}")
    assert payload["qa_flags"] == []


@pytest.mark.asyncio
async def test_get_writer_output_requires_project_ownership(
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_writer_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Persisted Writer Outputs",
        authors=["Barbara Liskov"],
        year=2021,
        abstract="This paper studies persistence for generated research artifacts.",
        problem="writer artifacts need revisitability",
        method="persisted output snapshots",
        result="stored artifacts reduce unnecessary regeneration",
    )
    create_response = await client.post(
        f"/projects/{sample_project['id']}/writer/generate",
        headers=auth_headers,
        json={
            "paper_ids": [paper.id],
            "instruction": "Write a short background paragraph using this paper.",
            "output_target": "markdown",
            "include_references": True,
            "max_words": 100,
        },
    )
    output_id = create_response.json()["id"]

    get_response = await client.get(
        f"/projects/{sample_project['id']}/writer/outputs/{output_id}",
        headers=auth_headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == output_id

    other_headers = await create_auth_headers_for_email(
        session_factory,
        email="other-writer@example.com",
    )
    other_response = await client.get(
        f"/projects/{sample_project['id']}/writer/outputs/{output_id}",
        headers=other_headers,
    )

    assert other_response.status_code == 404
    assert other_response.json() == {"detail": "Project not found."}


@pytest.mark.asyncio
async def test_generate_writer_output_returns_404_for_missing_selected_paper(
    client,
    auth_headers,
    sample_project,
) -> None:
    response = await client.post(
        f"/projects/{sample_project['id']}/writer/generate",
        headers=auth_headers,
        json={
            "paper_ids": ["missing-paper-id"],
            "instruction": "Write a grounded paragraph.",
            "output_target": "markdown",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "One or more selected papers were not found in the project."}
