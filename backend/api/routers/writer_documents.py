"""Writer workspace router — IMRaD document creation and drafting."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from backend.api.dependencies import (
    CurrentUser,
    DbSession,
    require_credits,
)
from backend.api.schemas.writer_documents import (
    AssembleResponse,
    AttachPaperIdRequest,
    OutlineApplyRequest,
    OutlineProposeResponse,
    QAReport,
    SectionInputsUpdate,
    SectionManualEdit,
    SectionVersionRead,
    SourceAttachRequest,
    SourceAttachResponse,
    SourceCandidate,
    SourceSuggestRequest,
    SourceSuggestResponse,
    WriterDocumentCreate,
    WriterDocumentRead,
    WriterDocumentSummaryRead,
    WriterDocumentUpdate,
    WriterSectionDraftResponse,
    WriterSectionRead,
)
from backend.services.writer_documents import (
    WriterDocumentNotFoundError,
    WriterDocumentPermissionError,
    WriterDocumentService,
    WriterSectionNotFoundError,
)

router = APIRouter(tags=["writer-documents"])

OUTLINE_PROPOSE_CREDITS = 2
SECTION_DRAFT_CREDITS = 5
SOURCE_SUGGEST_CREDITS = 1


def get_writer_document_service() -> WriterDocumentService:
    return WriterDocumentService()


WriterDocumentServiceDependency = Annotated[
    WriterDocumentService, Depends(get_writer_document_service)
]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.post(
    "/projects/{project_id}/writer/documents",
    response_model=WriterDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_writer_document(
    project_id: str,
    body: WriterDocumentCreate,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterDocumentRead:
    doc = await svc.create_document(
        session=session,
        project_id=project_id,
        title=body.title,
        topic=body.topic,
        thesis=body.thesis,
        paper_type=body.paper_type,
        citation_style=body.citation_style,
    )
    return WriterDocumentRead.model_validate(doc)


@router.get(
    "/projects/{project_id}/writer/documents",
    response_model=list[WriterDocumentSummaryRead],
)
async def list_writer_documents(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> list[WriterDocumentSummaryRead]:
    docs = await svc.list_documents(session=session, project_id=project_id)
    return [WriterDocumentSummaryRead.model_validate(d) for d in docs]


@router.get(
    "/writer/documents/{document_id}",
    response_model=WriterDocumentRead,
)
async def get_writer_document(
    document_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterDocumentRead:
    try:
        doc = await svc.get_document(
            session=session, document_id=document_id, user_id=current_user.id
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return WriterDocumentRead.model_validate(doc)


@router.patch(
    "/writer/documents/{document_id}",
    response_model=WriterDocumentRead,
)
async def update_writer_document(
    document_id: str,
    body: WriterDocumentUpdate,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterDocumentRead:
    try:
        doc = await svc.update_document(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            title=body.title,
            thesis=body.thesis,
            preamble=body.preamble,
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return WriterDocumentRead.model_validate(doc)


@router.delete(
    "/writer/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_writer_document(
    document_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> None:
    try:
        await svc.delete_document(
            session=session, document_id=document_id, user_id=current_user.id
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None


@router.post(
    "/writer/documents/{document_id}/outline/propose",
    response_model=OutlineProposeResponse,
)
async def propose_outline(
    document_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> OutlineProposeResponse:
    guard = await require_credits(
        OUTLINE_PROPOSE_CREDITS,
        "writer_outline_propose",
        current_user=current_user,
        session=session,
    )
    try:
        outline = await svc.propose_outline(
            session=session, document_id=document_id, user_id=current_user.id
        )
    except (WriterDocumentNotFoundError, WriterDocumentPermissionError) as err:
        await guard.rollback()
        if isinstance(err, WriterDocumentNotFoundError):
            raise _not_found(str(err)) from err
        raise _forbidden() from None
    await guard.commit(reference_id=document_id)
    return OutlineProposeResponse(outline_by_section=outline)


@router.put(
    "/writer/documents/{document_id}/outline",
    response_model=WriterDocumentRead,
)
async def apply_outline(
    document_id: str,
    body: OutlineApplyRequest,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterDocumentRead:
    try:
        doc = await svc.apply_outline(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            outline_by_section=body.outline_by_section,
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return WriterDocumentRead.model_validate(doc)


@router.get(
    "/writer/documents/{document_id}/sections/{section_id}/questions",
)
async def get_section_questions(
    document_id: str,
    section_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> dict[str, object]:
    try:
        section, questions = await svc.get_section_questions(
            session=session, section_id=section_id, user_id=current_user.id
        )
    except WriterSectionNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return {"section_id": section.id, "questions": questions}


@router.put(
    "/writer/documents/{document_id}/sections/{section_id}/inputs",
    response_model=WriterSectionRead,
)
async def submit_section_inputs(
    document_id: str,
    section_id: str,
    body: SectionInputsUpdate,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterSectionRead:
    try:
        section = await svc.submit_section_inputs(
            session=session,
            section_id=section_id,
            user_id=current_user.id,
            answers=body.user_inputs,
        )
    except WriterSectionNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return WriterSectionRead.model_validate(section)


@router.post(
    "/writer/documents/{document_id}/sections/{section_id}/draft",
    response_model=WriterSectionDraftResponse,
)
async def draft_section(
    document_id: str,
    section_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterSectionDraftResponse:
    guard = await require_credits(
        SECTION_DRAFT_CREDITS,
        "writer_section_draft",
        current_user=current_user,
        session=session,
    )
    try:
        section, warnings = await svc.draft_section(
            session=session, section_id=section_id, user_id=current_user.id
        )
    except (WriterSectionNotFoundError, WriterDocumentPermissionError) as err:
        await guard.rollback()
        if isinstance(err, WriterSectionNotFoundError):
            raise _not_found(str(err)) from err
        raise _forbidden() from None
    except ValueError as err:
        await guard.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err)) from err
    await guard.commit(reference_id=section_id)
    return WriterSectionDraftResponse(section=WriterSectionRead.model_validate(section), warnings=warnings)


@router.patch(
    "/writer/documents/{document_id}/sections/{section_id}",
    response_model=WriterSectionRead,
)
async def save_section_edit(
    document_id: str,
    section_id: str,
    body: SectionManualEdit,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterSectionRead:
    try:
        section = await svc.save_section_edit(
            session=session,
            section_id=section_id,
            user_id=current_user.id,
            draft_latex=body.draft_latex,
        )
    except WriterSectionNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return WriterSectionRead.model_validate(section)


@router.get(
    "/writer/documents/{document_id}/sections/{section_id}/versions",
    response_model=list[SectionVersionRead],
)
async def get_section_versions(
    document_id: str,
    section_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> list[SectionVersionRead]:
    try:
        versions = await svc.get_section_versions(
            session=session, section_id=section_id, user_id=current_user.id
        )
    except WriterSectionNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return [SectionVersionRead.model_validate(v) for v in versions]


@router.post(
    "/writer/documents/{document_id}/sections/{section_id}/revert/{version_id}",
    response_model=WriterSectionRead,
)
async def revert_to_version(
    document_id: str,
    section_id: str,
    version_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterSectionRead:
    try:
        section = await svc.revert_to_version(
            session=session,
            section_id=section_id,
            version_id=version_id,
            user_id=current_user.id,
        )
    except (WriterSectionNotFoundError, WriterDocumentNotFoundError) as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return WriterSectionRead.model_validate(section)


@router.post(
    "/writer/documents/{document_id}/sources/suggest",
    response_model=SourceSuggestResponse,
)
async def suggest_sources(
    document_id: str,
    body: SourceSuggestRequest,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> SourceSuggestResponse:
    guard = await require_credits(
        SOURCE_SUGGEST_CREDITS,
        "writer_suggest_sources",
        current_user=current_user,
        session=session,
    )
    try:
        candidates_raw, warnings = await svc.suggest_sources(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            query=body.query,
            section_id=body.section_id,
        )
    except (
        WriterDocumentNotFoundError,
        WriterSectionNotFoundError,
        WriterDocumentPermissionError,
    ) as err:
        await guard.rollback()
        if isinstance(err, (WriterDocumentNotFoundError, WriterSectionNotFoundError)):
            raise _not_found(str(err)) from err
        raise _forbidden() from None
    await guard.commit(reference_id=document_id)
    candidates = [SourceCandidate(**c) for c in candidates_raw]
    return SourceSuggestResponse(candidates=candidates, warnings=warnings)


@router.post(
    "/writer/documents/{document_id}/sources/attach",
    response_model=SourceAttachResponse,
)
async def attach_source(
    document_id: str,
    body: SourceAttachRequest,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> SourceAttachResponse:
    try:
        paper_id, requires_upload, message = await svc.attach_source(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            candidate=body.candidate.model_dump(),
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return SourceAttachResponse(paper_id=paper_id, requires_upload=requires_upload, message=message)


@router.post(
    "/writer/documents/{document_id}/sources/attach-paper",
    response_model=SourceAttachResponse,
)
async def attach_paper_by_id(
    document_id: str,
    body: AttachPaperIdRequest,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> SourceAttachResponse:
    try:
        paper_id = await svc.attach_paper_id(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            paper_id=body.paper_id,
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return SourceAttachResponse(paper_id=paper_id, requires_upload=False, message="Paper attached.")


@router.delete(
    "/writer/documents/{document_id}/sources/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_source(
    document_id: str,
    paper_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> None:
    try:
        await svc.remove_source(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            paper_id=paper_id,
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None


@router.get(
    "/writer/documents/{document_id}/qa",
    response_model=QAReport,
)
async def get_qa_report(
    document_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> QAReport:
    try:
        doc = await svc.get_document(
            session=session, document_id=document_id, user_id=current_user.id
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    report = svc.get_qa_report(doc)
    return QAReport(**report)


@router.post(
    "/writer/documents/{document_id}/assemble",
    response_model=AssembleResponse,
)
async def assemble_document(
    document_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> AssembleResponse:
    try:
        result = await svc.assemble(
            session=session, document_id=document_id, user_id=current_user.id
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return AssembleResponse(
        tex=result.tex,
        bib=result.bib,
        unresolved_todo_count=result.unresolved_todo_count,
        warnings=result.warnings,
    )


@router.get("/writer/documents/{document_id}/export")
async def export_document(
    document_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> Response:
    try:
        zip_bytes = await svc.export_bundle(
            session=session, document_id=document_id, user_id=current_user.id
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=paper_{document_id[:8]}.zip"},
    )
