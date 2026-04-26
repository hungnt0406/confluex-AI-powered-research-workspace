from pathlib import Path

import fitz
import pytest
from sqlalchemy import select

from backend.api.dependencies import get_reference_file_service
from backend.db.models import Paper, ReferenceFile, User
from backend.security import create_access_token, hash_password
from backend.services.document_extraction import (
    DocumentExtractionError,
    DocumentTextBlock,
    ExtractedDocument,
)
from backend.services.reference_files import (
    ReferenceFileService,
    compute_sha256,
)


class FakeReferenceExtractionService:
    """Controllable extractor stub for reference upload tests."""

    def __init__(
        self,
        *,
        text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.text = text or (
            "LLM Extracted Uploaded Paper\n\n"
            "Abstract\n\n"
            "This paper studies uploaded references for research workflows in 2024."
        )
        self.error_message = error_message
        self.calls: list[tuple[bytes, str]] = []

    async def extract_uploaded_pdf(self, *, pdf_bytes: bytes, filename: str) -> ExtractedDocument:
        self.calls.append((pdf_bytes, filename))
        if self.error_message is not None:
            raise DocumentExtractionError(self.error_message)
        return ExtractedDocument(
            blocks=[DocumentTextBlock(page_number=1, text=self.text)],
            page_count=1,
            file_hash="fake-openrouter-hash",
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


def override_reference_service(
    app,
    upload_dir: Path,
    *,
    extraction_service: FakeReferenceExtractionService | None = None,
) -> FakeReferenceExtractionService:
    extractor = extraction_service or FakeReferenceExtractionService()
    app.dependency_overrides[get_reference_file_service] = lambda: ReferenceFileService(
        upload_dir=upload_dir,
        extraction_service=extractor,
    )
    return extractor


def clear_reference_service_override(app) -> None:
    app.dependency_overrides.pop(get_reference_file_service, None)


@pytest.mark.asyncio
async def test_upload_list_and_delete_reference_file(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory,
    tmp_path: Path,
) -> None:
    extractor = override_reference_service(app, tmp_path)
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
        assert payload["extracted_title"] == "LLM Extracted Uploaded Paper"
        assert payload["extracted_year"] == 2024
        assert payload["linked_paper_id"] is not None
        assert payload["sha256"] == compute_sha256(pdf_content)
        assert extractor.calls == [(pdf_content, "seed.pdf")]

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
async def test_upload_reference_file_records_parse_error_when_extraction_fails(
    app,
    client,
    auth_headers,
    sample_project,
    tmp_path: Path,
) -> None:
    override_reference_service(
        app,
        tmp_path,
        extraction_service=FakeReferenceExtractionService(error_message="OpenRouter parser failed."),
    )
    pdf_content = build_pdf_bytes("Reference\nAbstract\nThis PDF cannot be extracted.")

    try:
        response = await client.post(
            f"/projects/{sample_project['id']}/reference-files",
            headers=auth_headers,
            files={"file": ("broken.pdf", pdf_content, "application/pdf")},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["parse_status"] == "parse_error"
        assert payload["linked_paper_id"] is None
        assert payload["extracted_title"] == "broken"
        assert payload["error_message"] == "PDF extraction failed: OpenRouter parser failed."
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
