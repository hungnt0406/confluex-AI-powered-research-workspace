"""Writer workspace router — IMRaD document creation and drafting."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.writer_editor import (
    EditPatch,
    NewResult,
    TextSpan,
    WebSearchHit,
)
from backend.api.dependencies import (
    CurrentUser,
    DbSession,
    require_credits,
)
from backend.api.schemas.projects import ReferenceFileRead
from backend.api.schemas.writer_documents import (
    AssembleResponse,
    AttachPaperIdRequest,
    EditPatchResponse,
    EditRequest,
    OutlineApplyRequest,
    OutlineProposeResponse,
    ProjectSourceImportRequest,
    ProjectSourceImportResponse,
    QAReport,
    SectionInputsUpdate,
    SectionManualEdit,
    SectionOutlineApplyRequest,
    SectionOutlineProposeResponse,
    SectionVersionRead,
    SourceAttachRequest,
    SourceAttachResponse,
    SourceCandidate,
    SourceSuggestRequest,
    SourceSuggestResponse,
    TextSpanSchema,
    WebCitationSchema,
    WriterDocumentCreate,
    WriterDocumentRead,
    WriterDocumentSummaryRead,
    WriterDocumentUpdate,
    WriterSectionDraftResponse,
    WriterSectionRead,
    WriterSourcePaperRead,
)
from backend.config import get_settings
from backend.db.models import Paper, WriterDocument, WriterDocumentSource
from backend.services.ai_usage import start_usage_collection
from backend.services.reference_files import (
    ReferenceFileDuplicateError,
    ReferenceFileValidationError,
)
from backend.services.writer_documents import (
    WriterDocumentNotFoundError,
    WriterDocumentPermissionError,
    WriterDocumentService,
    WriterSectionNotFoundError,
)
from backend.services.writer_editor import WriterEditConflictError, WriterEditorService

router = APIRouter(tags=["writer-documents"])

OUTLINE_PROPOSE_CREDITS = 2
SECTION_DRAFT_CREDITS = 5
SOURCE_SUGGEST_CREDITS = 1
WRITER_EDITOR_CREDITS = 2
WRITER_EDITOR_WEB_CREDITS = 4


def get_writer_document_service() -> WriterDocumentService:
    return WriterDocumentService()


def get_writer_editor_service() -> WriterEditorService:
    return WriterEditorService()


WriterDocumentServiceDependency = Annotated[
    WriterDocumentService, Depends(get_writer_document_service)
]
WriterEditorServiceDependency = Annotated[
    WriterEditorService, Depends(get_writer_editor_service)
]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


def _writer_editor_cost(body: EditRequest) -> tuple[int, str]:
    if body.web_search:
        return WRITER_EDITOR_WEB_CREDITS, "writer_editor_edit_web"
    return WRITER_EDITOR_CREDITS, "writer_editor_edit"


def _patch_response(patch: EditPatch) -> EditPatchResponse:
    return EditPatchResponse(
        span=TextSpanSchema(start=patch.span.start, end=patch.span.end),
        new_text=patch.new_text,
        rationale=patch.rationale,
        original_text=patch.original_text,
        web_citations=[
            WebCitationSchema(title=hit.title, url=hit.url, snippet=hit.snippet)
            for hit in patch.web_citations
        ],
    )


def _patch_from_schema(body: EditPatchResponse) -> EditPatch:
    return EditPatch(
        span=TextSpan(start=body.span.start, end=body.span.end),
        new_text=body.new_text,
        rationale=body.rationale,
        original_text=body.original_text,
        web_citations=[
            WebSearchHit(title=hit.title, url=hit.url, snippet=hit.snippet)
            for hit in body.web_citations
        ],
    )


async def _serialize_writer_document(
    session: AsyncSession,
    doc: WriterDocument,
) -> WriterDocumentRead:
    payload = WriterDocumentRead.model_validate(doc)
    result = await session.execute(
        select(WriterDocumentSource)
        .where(
            WriterDocumentSource.writer_document_id == doc.id,
            WriterDocumentSource.paper_id.is_not(None),
        )
        .order_by(WriterDocumentSource.order_index.asc())
    )
    source_paper_ids = [row.paper_id for row in result.scalars().all() if row.paper_id]
    if not source_paper_ids:
        source_paper_ids = list(doc.source_paper_ids_json or [])
    payload.source_paper_ids_json = list(source_paper_ids)
    if not source_paper_ids:
        return payload

    papers_result = await session.execute(select(Paper).where(Paper.id.in_(source_paper_ids)))
    papers_by_id = {paper.id: paper for paper in papers_result.scalars().all()}
    payload.source_papers = [
        WriterSourcePaperRead.model_validate(papers_by_id[paper_id])
        for paper_id in source_paper_ids
        if paper_id in papers_by_id
    ]
    return payload


@router.post(
    "/writer/documents",
    response_model=WriterDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_standalone_writer_document(
    body: WriterDocumentCreate,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterDocumentRead:
    doc = await svc.create_document(
        session=session,
        user_id=current_user.id,
        project_id=None,
        title=body.title,
        topic=body.topic,
        thesis=body.thesis,
        paper_type=body.paper_type,
        citation_style=body.citation_style,
    )
    return await _serialize_writer_document(session, doc)


@router.get(
    "/writer/documents",
    response_model=list[WriterDocumentSummaryRead],
)
async def list_standalone_writer_documents(
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> list[WriterDocumentSummaryRead]:
    docs = await svc.list_documents(session=session, user_id=current_user.id)
    return [WriterDocumentSummaryRead.model_validate(d) for d in docs]


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
    try:
        doc = await svc.create_document(
            session=session,
            user_id=current_user.id,
            project_id=project_id,
            title=body.title,
            topic=body.topic,
            thesis=body.thesis,
            paper_type=body.paper_type,
            citation_style=body.citation_style,
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return await _serialize_writer_document(session, doc)


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
    try:
        docs = await svc.list_documents(
            session=session,
            user_id=current_user.id,
            project_id=project_id,
        )
    except WriterDocumentNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
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
    return await _serialize_writer_document(session, doc)


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
    return await _serialize_writer_document(session, doc)


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
    return await _serialize_writer_document(session, doc)


@router.post(
    "/writer/documents/{document_id}/sections/{section_id}/outline/propose",
    response_model=SectionOutlineProposeResponse,
)
async def propose_section_outline(
    document_id: str,
    section_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> SectionOutlineProposeResponse:
    guard = await require_credits(
        OUTLINE_PROPOSE_CREDITS,
        "writer_section_outline_propose",
        current_user=current_user,
        session=session,
    )
    try:
        section, outline = await svc.propose_section_outline(
            session=session,
            section_id=section_id,
            user_id=current_user.id,
        )
    except (WriterSectionNotFoundError, WriterDocumentPermissionError) as err:
        await guard.rollback()
        if isinstance(err, WriterSectionNotFoundError):
            raise _not_found(str(err)) from err
        raise _forbidden() from None
    await guard.commit(reference_id=section_id)
    return SectionOutlineProposeResponse(section_id=section.id, outline_text=outline)


@router.put(
    "/writer/documents/{document_id}/sections/{section_id}/outline",
    response_model=WriterSectionRead,
)
async def approve_section_outline(
    document_id: str,
    section_id: str,
    body: SectionOutlineApplyRequest,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> WriterSectionRead:
    try:
        section = await svc.approve_section_outline(
            session=session,
            section_id=section_id,
            user_id=current_user.id,
            outline_text=body.outline_text,
        )
    except WriterSectionNotFoundError as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err)) from err
    return WriterSectionRead.model_validate(section)


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


@router.post(
    "/writer/documents/{document_id}/sections/{section_id}/edit",
    response_model=EditPatchResponse,
)
async def preview_section_edit(
    document_id: str,
    section_id: str,
    body: EditRequest,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterEditorServiceDependency,
) -> EditPatchResponse:
    credit_cost, feature = _writer_editor_cost(body)
    guard = await require_credits(
        credit_cost,
        feature,
        current_user=current_user,
        session=session,
    )
    try:
        patch = await svc.preview(
            session=session,
            document_id=document_id,
            section_id=section_id,
            user_id=current_user.id,
            instruction=body.instruction,
            span=(
                TextSpan(start=body.span.start, end=body.span.end)
                if body.span is not None
                else None
            ),
            insertion_offset=body.insertion_offset,
            new_results=[
                NewResult(
                    text=result.text,
                    source_ref=result.source_ref,
                    attach_as_citation=result.attach_as_citation,
                )
                for result in body.new_results
            ],
            web_search=body.web_search,
            web_query=body.web_query,
        )
    except (WriterSectionNotFoundError, WriterDocumentNotFoundError, WriterDocumentPermissionError) as err:
        await guard.rollback()
        if isinstance(err, (WriterSectionNotFoundError, WriterDocumentNotFoundError)):
            raise _not_found(str(err)) from err
        raise _forbidden() from None
    except ValueError as err:
        await guard.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err)) from err
    except Exception:
        await guard.rollback()
        raise
    await guard.commit(reference_id=section_id)
    return _patch_response(patch)


@router.post(
    "/writer/documents/{document_id}/sections/{section_id}/edit/apply",
    response_model=WriterSectionRead,
)
async def apply_section_edit(
    document_id: str,
    section_id: str,
    body: EditPatchResponse,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterEditorServiceDependency,
) -> WriterSectionRead:
    try:
        section = await svc.apply(
            session=session,
            document_id=document_id,
            section_id=section_id,
            user_id=current_user.id,
            patch=_patch_from_schema(body),
        )
    except (WriterSectionNotFoundError, WriterDocumentNotFoundError) as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    except WriterEditConflictError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
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


@router.post(
    "/writer/documents/{document_id}/sources/import-project",
    response_model=ProjectSourceImportResponse,
)
async def import_project_sources(
    document_id: str,
    body: ProjectSourceImportRequest,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
) -> ProjectSourceImportResponse:
    try:
        paper_ids = await svc.import_project_sources(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            project_id=body.project_id,
            paper_ids=body.paper_ids,
        )
    except (WriterDocumentNotFoundError, WriterSectionNotFoundError) as err:
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        raise _forbidden() from None
    return ProjectSourceImportResponse(paper_ids=paper_ids, imported_count=len(paper_ids))


@router.post(
    "/writer/documents/{document_id}/sources/upload",
    response_model=ReferenceFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_writer_document_source(
    document_id: str,
    session: DbSession,
    current_user: CurrentUser,
    svc: WriterDocumentServiceDependency,
    file: Annotated[UploadFile, File(...)],
) -> ReferenceFileRead:
    content = await file.read()
    guard = await require_credits(
        get_settings().credit_cost_pdf_upload,
        feature="writer_pdf_upload",
        current_user=current_user,
        session=session,
    )
    start_usage_collection()
    try:
        reference_file = await svc.upload_source_pdf(
            session=session,
            document_id=document_id,
            user_id=current_user.id,
            filename=file.filename or "reference.pdf",
            content_type=file.content_type,
            content=content,
        )
    except WriterDocumentNotFoundError as err:
        await guard.rollback()
        raise _not_found(str(err)) from err
    except WriterDocumentPermissionError:
        await guard.rollback()
        raise _forbidden() from None
    except ReferenceFileValidationError as err:
        await guard.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
    except ReferenceFileDuplicateError as err:
        await guard.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    except Exception:
        await guard.rollback()
        raise
    await guard.commit(reference_id=reference_file.id)
    return ReferenceFileRead.from_reference(reference_file)


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
