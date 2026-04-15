from pathlib import Path

import fitz
import pytest
from sqlalchemy import select

from backend.api.dependencies import get_reference_file_service
from backend.db.models import Paper, ReferenceFile, User
from backend.security import create_access_token, hash_password
from backend.services.reference_files import (
    ReferenceFileService,
    compute_sha256,
    parse_pdf_metadata,
)


def build_pdf_bytes(
    body: str,
    *,
    title: str = "Uploaded Transformer Study",
    author: str = "Jane Doe; John Roe",
    creation_date: str = "D:20240101000000",
) -> bytes:
    document = fitz.open()
    document.set_metadata(
        {
            "title": title,
            "author": author,
            "creationDate": creation_date,
        }
    )
    page = document.new_page()
    page.insert_text((72, 72), body)
    return document.tobytes()


def build_empty_pdf_bytes() -> bytes:
    document = fitz.open()
    document.new_page()
    return document.tobytes()


def override_reference_service(app, upload_dir: Path, *, max_file_bytes: int = 20_971_520) -> None:
    app.dependency_overrides[get_reference_file_service] = lambda: ReferenceFileService(
        upload_dir=upload_dir,
        max_file_bytes=max_file_bytes,
    )


def clear_reference_service_override(app) -> None:
    app.dependency_overrides.pop(get_reference_file_service, None)


def test_parse_pdf_metadata_extracts_title_year_authors_and_abstract(tmp_path: Path) -> None:
    pdf_path = tmp_path / "reference.pdf"
    pdf_path.write_bytes(
        build_pdf_bytes(
            "\n".join(
                [
                    "A visible first title line",
                    "Abstract",
                    "This paper studies transformer retrieval for literature review workflows.",
                    "Keywords: transformers, retrieval",
                    "Introduction",
                    "The introduction starts here.",
                ]
            )
        )
    )

    metadata = parse_pdf_metadata(pdf_path, max_extracted_chars=10_000)

    assert metadata.parse_status == "parsed"
    assert metadata.title == "Uploaded Transformer Study"
    assert metadata.authors == ["Jane Doe", "John Roe"]
    assert metadata.year == 2024
    assert metadata.abstract == "This paper studies transformer retrieval for literature review workflows."


def test_parse_pdf_metadata_records_parse_error_for_empty_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(build_empty_pdf_bytes())

    metadata = parse_pdf_metadata(pdf_path, max_extracted_chars=10_000)

    assert metadata.parse_status == "parse_error"
    assert metadata.error_message == "No extractable text was found in the uploaded PDF."
    assert metadata.text is None


@pytest.mark.asyncio
async def test_upload_list_and_delete_reference_file(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory,
    tmp_path: Path,
) -> None:
    override_reference_service(app, tmp_path)
    pdf_content = build_pdf_bytes(
        "Uploaded Paper Title\nAbstract\nThis paper studies uploaded references for research."
    )

    try:
        upload_response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            headers=auth_headers,
            files={"file": ("seed.pdf", pdf_content, "application/pdf")},
        )
        assert upload_response.status_code == 201
        payload = upload_response.json()
        assert payload["parse_status"] == "parsed"
        assert payload["original_filename"] == "seed.pdf"
        assert payload["linked_paper_id"] is not None
        assert payload["sha256"] == compute_sha256(pdf_content)

        list_response = await client.get(
            f"/projects/{sample_project['id']}/reference-files",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        assert [item["id"] for item in list_response.json()] == [payload["id"]]

        delete_response = await client.delete(
            f"/projects/{sample_project['id']}/reference-files/{payload['id']}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 204

        async with session_factory() as session:
            papers = (
                await session.execute(
                    select(Paper).where(Paper.reference_file_id == payload["id"])
                )
            ).scalars().all()
            reference_files = (
                await session.execute(
                    select(ReferenceFile).where(ReferenceFile.id == payload["id"])
                )
            ).scalars().all()
        assert papers == []
        assert reference_files == []
    finally:
        clear_reference_service_override(app)


@pytest.mark.asyncio
async def test_upload_reference_file_rejects_duplicate(
    app,
    client,
    auth_headers,
    sample_project,
    tmp_path: Path,
) -> None:
    override_reference_service(app, tmp_path)
    pdf_content = build_pdf_bytes("Reference\nAbstract\nThis is a duplicate reference.")

    try:
        first_response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            headers=auth_headers,
            files={"file": ("seed.pdf", pdf_content, "application/pdf")},
        )
        duplicate_response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            headers=auth_headers,
            files={"file": ("seed.pdf", pdf_content, "application/pdf")},
        )

        assert first_response.status_code == 201
        assert duplicate_response.status_code == 409
        assert duplicate_response.json()["detail"] == "This reference file has already been uploaded."
    finally:
        clear_reference_service_override(app)


@pytest.mark.asyncio
async def test_upload_reference_file_rejects_non_pdf(
    app,
    client,
    auth_headers,
    sample_project,
    tmp_path: Path,
) -> None:
    override_reference_service(app, tmp_path)

    try:
        response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            headers=auth_headers,
            files={"file": ("notes.txt", b"not a pdf", "text/plain")},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Only PDF reference files are supported."
    finally:
        clear_reference_service_override(app)


@pytest.mark.asyncio
async def test_upload_reference_file_rejects_oversized_pdf(
    app,
    client,
    auth_headers,
    sample_project,
    tmp_path: Path,
) -> None:
    override_reference_service(app, tmp_path, max_file_bytes=8)

    try:
        response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            headers=auth_headers,
            files={"file": ("large.pdf", b"%PDF-1.4\n0123456789", "application/pdf")},
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]
            == "Uploaded reference file exceeds the size limit. Maximum allowed size is 8 bytes."
        )
    finally:
        clear_reference_service_override(app)


@pytest.mark.asyncio
async def test_reference_file_upload_requires_authentication(
    app,
    client,
    sample_project,
    tmp_path: Path,
) -> None:
    override_reference_service(app, tmp_path)
    pdf_content = build_pdf_bytes("Reference\nAbstract\nThis should require authentication.")

    try:
        response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            files={"file": ("seed.pdf", pdf_content, "application/pdf")},
        )

        assert response.status_code == 401
    finally:
        clear_reference_service_override(app)


@pytest.mark.asyncio
async def test_reference_file_upload_requires_project_ownership(
    app,
    client,
    sample_project,
    session_factory,
    tmp_path: Path,
) -> None:
    override_reference_service(app, tmp_path)
    pdf_content = build_pdf_bytes("Reference\nAbstract\nThis should not be accepted.")

    async with session_factory() as session:
        other_user = User(
            email="other.researcher@example.com",
            hashed_password=hash_password("supersecret123"),
        )
        session.add(other_user)
        await session.commit()
        await session.refresh(other_user)
        other_headers = {"Authorization": f"Bearer {create_access_token(other_user.id)}"}

    try:
        response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            headers=other_headers,
            files={"file": ("seed.pdf", pdf_content, "application/pdf")},
        )

        assert response.status_code == 404
    finally:
        clear_reference_service_override(app)
