import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, cast

import anyio
from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from backend.api.dependencies import (
    CurrentUser,
    DbSession,
    DeepSearchServiceDependency,
    PaperCitationServiceDependency,
    PaperConversationServiceDependency,
    PipelineServiceDependency,
    ProjectConversationServiceDependency,
    ReferenceFileServiceDependency,
    WriterOutputServiceDependency,
)
from backend.api.schemas.projects import (
    CitationGraphPaperRead,
    DeepSearchCreate,
    DeepSearchRunRead,
    DeepSearchRunSummaryRead,
    PaginationMeta,
    PaperCitationGraphRead,
    PaperConversationCreate,
    PaperConversationMessageCreate,
    PaperConversationRead,
    PaperConversationSummaryRead,
    ProjectConversationCreate,
    ProjectConversationMessageCreate,
    ProjectConversationRead,
    ProjectConversationSummaryRead,
    ProjectCreate,
    ProjectPaperListResponse,
    ProjectPaperRead,
    ProjectRead,
    ProjectTitleUpdate,
    ProjectTokenUsageRead,
    ReferenceFileRead,
    RunPipelineResponse,
    TokenUsageBreakdownRow,
    TokenUsageDailyRow,
    WriterGenerateRequest,
    WriterOutputRead,
)
from backend.db.models import (
    DeepSearchRun,
    Paper,
    PaperConversation,
    Project,
    ProjectConversation,
    ReferenceFile,
    WriterOutput,
)
from backend.services.ai_usage import (
    flush_usage_events,
    start_usage_collection,
    summarize_project_usage,
)
from backend.services.deep_search import DeepSearchStreamEvent, ensure_deep_search_allowed
from backend.services.paper_citations import (
    CitationNotFoundError,
    CitationProviderError,
    CitationResolutionError,
)
from backend.services.project_conversations import ProjectConversationStreamEvent
from backend.services.reference_files import (
    ReferenceFileDuplicateError,
    ReferenceFileValidationError,
)

router = APIRouter(prefix="/projects", tags=["projects"])


async def flush_project_usage_events(
    *,
    session: DbSession,
    current_user: CurrentUser,
    project: Project,
) -> None:
    """Persist usage events captured during a successful project request."""

    await flush_usage_events(session=session, user_id=current_user.id, project_id=project.id)


def encode_sse_event(event: str, data: Any) -> str:
    """Encode one server-sent event frame."""

    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def project_conversation_stream_payload(
    event: ProjectConversationStreamEvent,
) -> Any:
    """Serialize a project conversation stream event payload."""

    if event.event == "conversation":
        conversation = cast(ProjectConversation, event.data)
        return {
            "id": conversation.id,
            "project_id": conversation.project_id,
            "selected_paper_ids": list(conversation.selected_paper_ids_json),
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": [],
        }
    if event.event == "done":
        conversation = cast(ProjectConversation, event.data)
        return ProjectConversationRead.from_conversation(conversation).model_dump(mode="json")
    return event.data


def deep_search_stream_payload(event: DeepSearchStreamEvent) -> Any:
    """Serialize a deep search stream event payload."""

    if event.event == "run":
        run = cast(DeepSearchRun, event.data)
        return DeepSearchRunSummaryRead.from_run(run).model_dump(mode="json")
    if event.event == "done":
        run = cast(DeepSearchRun, event.data)
        return DeepSearchRunRead.from_run(run).model_dump(mode="json")
    return event.data


def sse_headers() -> dict[str, str]:
    """Headers that keep proxy and browser SSE handling unbuffered."""

    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def unlink_stored_file(storage_path: Path) -> None:
    """Delete a stored upload from disk if it still exists."""

    storage_path.unlink(missing_ok=True)


def unlink_stored_files(storage_paths: list[Path]) -> None:
    """Delete multiple stored uploads from disk, ignoring already-missing files."""

    for storage_path in storage_paths:
        storage_path.unlink(missing_ok=True)


async def get_owned_project_or_404(
    session: DbSession,
    user_id: str,
    project_id: str,
) -> Project:
    """Return a project owned by the authenticated user."""

    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


async def get_project_reference_file_or_404(
    session: DbSession,
    *,
    project_id: str,
    reference_file_id: str,
) -> ReferenceFile:
    """Return a reference file belonging to a project."""

    result = await session.execute(
        select(ReferenceFile)
        .options(selectinload(ReferenceFile.paper))
        .where(
            ReferenceFile.project_id == project_id,
            ReferenceFile.id == reference_file_id,
        )
    )
    reference_file = result.scalar_one_or_none()
    if reference_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference file not found.",
        )
    return reference_file


async def get_project_paper_or_404(
    session: DbSession,
    *,
    project_id: str,
    paper_id: str,
) -> Paper:
    """Return a paper belonging to a project, including summary metadata for Q&A fallback."""

    result = await session.execute(
        select(Paper)
        .options(selectinload(Paper.summary))
        .where(
            Paper.project_id == project_id,
            Paper.id == paper_id,
        )
    )
    paper = result.scalar_one_or_none()
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found.",
        )
    return paper


async def get_project_papers_or_404(
    session: DbSession,
    *,
    project_id: str,
    paper_ids: list[str],
) -> list[Paper]:
    """Return ordered project papers for the provided ids."""

    unique_paper_ids = list(dict.fromkeys(paper_ids))
    result = await session.execute(
        select(Paper)
        .options(selectinload(Paper.summary))
        .where(
            Paper.project_id == project_id,
            Paper.id.in_(unique_paper_ids),
        )
    )
    papers_by_id = {paper.id: paper for paper in result.scalars().all()}
    missing_paper_ids = [paper_id for paper_id in unique_paper_ids if paper_id not in papers_by_id]
    if missing_paper_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more selected papers were not found in the project.",
        )

    return [papers_by_id[paper_id] for paper_id in unique_paper_ids]


async def get_project_paper_conversation_or_404(
    session: DbSession,
    *,
    paper_id: str,
    conversation_id: str,
) -> PaperConversation:
    """Return a conversation belonging to a paper."""

    result = await session.execute(
        select(PaperConversation)
        .options(selectinload(PaperConversation.messages))
        .where(
            PaperConversation.paper_id == paper_id,
            PaperConversation.id == conversation_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    return conversation


async def get_project_conversation_or_404(
    session: DbSession,
    *,
    project_id: str,
    conversation_id: str,
) -> ProjectConversation:
    """Return a project-scoped conversation belonging to a project."""

    result = await session.execute(
        select(ProjectConversation)
        .options(selectinload(ProjectConversation.messages))
        .where(
            ProjectConversation.project_id == project_id,
            ProjectConversation.id == conversation_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    return conversation


async def get_project_deep_search_run_or_404(
    session: DbSession,
    *,
    project_id: str,
    run_id: str,
) -> DeepSearchRun:
    """Return a deep search run belonging to a project."""

    result = await session.execute(
        select(DeepSearchRun)
        .options(selectinload(DeepSearchRun.sources))
        .where(
            DeepSearchRun.project_id == project_id,
            DeepSearchRun.id == run_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deep search run not found.",
        )
    return run


async def get_project_writer_output_or_404(
    session: DbSession,
    *,
    project_id: str,
    output_id: str,
) -> WriterOutput:
    """Return a persisted writer output belonging to a project."""

    result = await session.execute(
        select(WriterOutput).where(
            WriterOutput.project_id == project_id,
            WriterOutput.id == output_id,
        )
    )
    writer_output = result.scalar_one_or_none()
    if writer_output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writer output not found.",
        )
    return writer_output


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: DbSession,
    current_user: CurrentUser,
    response: Response,
) -> ProjectRead:
    """Create a project for the authenticated user."""

    project = Project(
        user_id=current_user.id,
        title=payload.title,
        topic_description=payload.topic_description,
        citation_format=payload.citation_format,
        year_start=payload.year_start,
        candidate_limit=payload.candidate_limit,
        summary_limit=payload.summary_limit,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    response.headers["Location"] = f"/projects/{project.id}"
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: DbSession, current_user: CurrentUser) -> list[ProjectRead]:
    """List projects owned by the authenticated user."""

    result = await session.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [ProjectRead.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> ProjectRead:
    """Fetch a single project for the authenticated user."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def rename_project(
    project_id: str,
    payload: ProjectTitleUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ProjectRead:
    """Rename an owned project."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    project.title = payload.title
    await session.commit()
    await session.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> Response:
    """Delete an owned project and clean up any stored reference files."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    storage_paths_result = await session.execute(
        select(ReferenceFile.storage_path).where(ReferenceFile.project_id == project.id)
    )
    storage_paths = [
        Path(storage_path)
        for storage_path in dict.fromkeys(storage_paths_result.scalars().all())
        if storage_path
    ]

    await session.delete(project)
    await session.commit()

    try:
        await anyio.to_thread.run_sync(unlink_stored_files, storage_paths)
    except OSError:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/run",
    response_model=RunPipelineResponse,
    status_code=status.HTTP_200_OK,
)
async def queue_project_pipeline(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
    pipeline_service: PipelineServiceDependency,
) -> RunPipelineResponse:
    """Run the project pipeline and return the phase-2 result summary."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    start_usage_collection()
    state = await pipeline_service.run_project(session=session, project=project)
    await flush_project_usage_events(session=session, current_user=current_user, project=project)
    return RunPipelineResponse(
        status="completed",
        project_id=project.id,
        queries=state.queries,
        candidate_count=len(state.raw_papers),
        ranked_count=len(state.ranked_papers),
        summary_count=len(state.summaries),
        qa_flags=state.qa_flags,
        errors=state.errors,
    )


@router.get("/{project_id}/token-usage", response_model=ProjectTokenUsageRead)
async def get_project_token_usage(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> ProjectTokenUsageRead:
    """Return project-scoped provider-reported token usage aggregates."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    summary = await summarize_project_usage(session=session, project_id=project.id)
    return ProjectTokenUsageRead(
        project_id=project.id,
        total_tokens=summary.total_tokens,
        prompt_tokens=summary.prompt_tokens,
        completion_tokens=summary.completion_tokens,
        reasoning_tokens=summary.reasoning_tokens,
        cached_tokens=summary.cached_tokens,
        cost_credits=summary.cost_credits,
        request_count=summary.request_count,
        by_feature=[
            TokenUsageBreakdownRow(
                key=row.key,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_feature
        ],
        by_model=[
            TokenUsageBreakdownRow(
                key=row.key,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_model
        ],
        by_day=[
            TokenUsageDailyRow(
                day=row.day,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_day
        ],
    )


@router.post(
    "/{project_id}/reference-files",
    response_model=ReferenceFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_reference_file(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
    reference_file_service: ReferenceFileServiceDependency,
    response: Response,
    file: Annotated[UploadFile, File(...)],
) -> ReferenceFileRead:
    """Upload a PDF reference file for a project."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    content = await file.read()
    start_usage_collection()

    try:
        reference_file = await reference_file_service.create_reference_file(
            session=session,
            project=project,
            filename=file.filename or "reference.pdf",
            content_type=file.content_type,
            content=content,
        )
    except ReferenceFileValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except ReferenceFileDuplicateError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    loaded_reference_file = await get_project_reference_file_or_404(
        session,
        project_id=project.id,
        reference_file_id=reference_file.id,
    )
    await flush_project_usage_events(session=session, current_user=current_user, project=project)
    response.headers["Location"] = f"/projects/{project.id}/reference-files/{reference_file.id}"
    return ReferenceFileRead.from_reference(loaded_reference_file)


@router.get("/{project_id}/reference-files", response_model=list[ReferenceFileRead])
async def list_project_reference_files(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> list[ReferenceFileRead]:
    """List reference files for the authenticated user's project."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    result = await session.execute(
        select(ReferenceFile)
        .options(selectinload(ReferenceFile.paper))
        .where(ReferenceFile.project_id == project.id)
        .order_by(ReferenceFile.created_at.desc())
    )
    reference_files = result.scalars().all()
    return [ReferenceFileRead.from_reference(reference_file) for reference_file in reference_files]


@router.delete("/{project_id}/reference-files/{reference_file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_reference_file(
    project_id: str,
    reference_file_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> Response:
    """Delete a project reference file and its linked paper."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    reference_file = await get_project_reference_file_or_404(
        session,
        project_id=project.id,
        reference_file_id=reference_file_id,
    )
    storage_path = Path(reference_file.storage_path)

    if reference_file.paper is not None:
        await session.delete(reference_file.paper)
    await session.delete(reference_file)
    await session.commit()

    try:
        await anyio.to_thread.run_sync(unlink_stored_file, storage_path)
    except OSError:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def apply_paper_filters(
    statement: Select[Any],
    *,
    project_id: str,
    status_filter: str | None,
    minimum_relevance: float | None,
) -> Select[Any]:
    """Apply project-specific paper filters to a SQLAlchemy statement."""

    statement = statement.where(Paper.project_id == project_id)
    if status_filter is not None:
        statement = statement.where(Paper.status == status_filter)
    if minimum_relevance is not None:
        statement = statement.where(Paper.relevance_score >= minimum_relevance)
    return statement


@router.get("/{project_id}/papers", response_model=ProjectPaperListResponse)
async def list_project_papers(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    minimum_relevance: float | None = Query(default=None, ge=0.0, le=100.0, alias="min_relevance"),
) -> ProjectPaperListResponse:
    """List papers for the authenticated user's project with pagination and filters."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)

    filtered_count_statement = apply_paper_filters(
        select(func.count()).select_from(Paper),
        project_id=project.id,
        status_filter=status_filter,
        minimum_relevance=minimum_relevance,
    )
    total = int((await session.execute(filtered_count_statement)).scalar_one())

    statement = apply_paper_filters(
        select(Paper).options(selectinload(Paper.summary)),
        project_id=project.id,
        status_filter=status_filter,
        minimum_relevance=minimum_relevance,
    ).order_by(Paper.relevance_score.desc(), Paper.year.desc(), Paper.title.asc())

    offset = (page - 1) * per_page
    result = await session.execute(statement.offset(offset).limit(per_page))
    papers = result.scalars().all()

    return ProjectPaperListResponse(
        data=[ProjectPaperRead.model_validate(paper) for paper in papers],
        meta=PaginationMeta.from_totals(total=total, page=page, per_page=per_page),
    )


@router.get(
    "/{project_id}/papers/{paper_id}/citation-graph",
    response_model=PaperCitationGraphRead,
)
async def get_project_paper_citation_graph(
    project_id: str,
    paper_id: str,
    session: DbSession,
    current_user: CurrentUser,
    paper_citation_service: PaperCitationServiceDependency,
    limit: int = Query(default=20, ge=1, le=100),
) -> PaperCitationGraphRead:
    """Return both cited-by and reference lists for one project paper."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    paper = await get_project_paper_or_404(
        session,
        project_id=project.id,
        paper_id=paper_id,
    )

    try:
        citation_graph = await paper_citation_service.get_citation_graph(
            session=session,
            paper=paper,
            limit=limit,
        )
    except CitationResolutionError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except CitationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CitationProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    return PaperCitationGraphRead(
        paper_id=citation_graph.paper_id,
        resolved_by=citation_graph.resolved_by,
        resolved_source_paper_id=citation_graph.resolved_source_paper_id,
        citation_count=citation_graph.citation_count,
        reference_count=citation_graph.reference_count,
        cited_by=[
            CitationGraphPaperRead.model_validate(related_paper)
            for related_paper in citation_graph.cited_by
        ],
        references=[
            CitationGraphPaperRead.model_validate(related_paper)
            for related_paper in citation_graph.references
        ],
    )


@router.post(
    "/{project_id}/papers/{paper_id}/conversations",
    response_model=PaperConversationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_paper_conversation(
    project_id: str,
    paper_id: str,
    payload: PaperConversationCreate,
    session: DbSession,
    current_user: CurrentUser,
    conversation_service: PaperConversationServiceDependency,
    response: Response,
) -> PaperConversationRead:
    """Start a grounded conversation for a project paper."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    paper = await get_project_paper_or_404(
        session,
        project_id=project.id,
        paper_id=paper_id,
    )
    start_usage_collection()
    result = await conversation_service.create_conversation(
        session=session,
        paper=paper,
        question=payload.question,
    )
    await flush_project_usage_events(session=session, current_user=current_user, project=project)
    response.headers["Location"] = (
        f"/projects/{project.id}/papers/{paper.id}/conversations/{result.conversation.id}"
    )
    return PaperConversationRead.model_validate(result.conversation)


@router.post(
    "/{project_id}/papers/{paper_id}/conversations/{conversation_id}/messages",
    response_model=PaperConversationRead,
    status_code=status.HTTP_200_OK,
)
async def create_paper_conversation_message(
    project_id: str,
    paper_id: str,
    conversation_id: str,
    payload: PaperConversationMessageCreate,
    session: DbSession,
    current_user: CurrentUser,
    conversation_service: PaperConversationServiceDependency,
) -> PaperConversationRead:
    """Persist a follow-up grounded turn for a paper conversation."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    paper = await get_project_paper_or_404(
        session,
        project_id=project.id,
        paper_id=paper_id,
    )
    conversation = await get_project_paper_conversation_or_404(
        session,
        paper_id=paper.id,
        conversation_id=conversation_id,
    )
    start_usage_collection()
    result = await conversation_service.continue_conversation(
        session=session,
        paper=paper,
        conversation=conversation,
        question=payload.question,
    )
    await flush_project_usage_events(session=session, current_user=current_user, project=project)
    return PaperConversationRead.model_validate(result.conversation)


@router.get(
    "/{project_id}/papers/{paper_id}/conversations",
    response_model=list[PaperConversationSummaryRead],
)
async def list_paper_conversations(
    project_id: str,
    paper_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> list[PaperConversationSummaryRead]:
    """List grounded conversations for a project paper."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    paper = await get_project_paper_or_404(
        session,
        project_id=project.id,
        paper_id=paper_id,
    )
    result = await session.execute(
        select(PaperConversation)
        .options(selectinload(PaperConversation.messages))
        .where(PaperConversation.paper_id == paper.id)
        .order_by(PaperConversation.updated_at.desc(), PaperConversation.created_at.desc())
    )
    conversations = result.scalars().all()
    return [
        PaperConversationSummaryRead.from_conversation(conversation)
        for conversation in conversations
    ]


@router.get(
    "/{project_id}/papers/{paper_id}/conversations/{conversation_id}",
    response_model=PaperConversationRead,
)
async def get_paper_conversation(
    project_id: str,
    paper_id: str,
    conversation_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> PaperConversationRead:
    """Fetch one grounded conversation for a project paper."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    paper = await get_project_paper_or_404(
        session,
        project_id=project.id,
        paper_id=paper_id,
    )
    conversation = await get_project_paper_conversation_or_404(
        session,
        paper_id=paper.id,
        conversation_id=conversation_id,
    )
    return PaperConversationRead.model_validate(conversation)


@router.post(
    "/{project_id}/conversations",
    response_model=ProjectConversationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_conversation(
    project_id: str,
    payload: ProjectConversationCreate,
    session: DbSession,
    current_user: CurrentUser,
    conversation_service: ProjectConversationServiceDependency,
    response: Response,
) -> ProjectConversationRead:
    """Start a grounded multi-paper conversation for a project."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    selected_papers = await get_project_papers_or_404(
        session,
        project_id=project.id,
        paper_ids=payload.paper_ids,
    )
    start_usage_collection()
    result = await conversation_service.create_conversation(
        session=session,
        project_id=project.id,
        selected_papers=selected_papers,
        question=payload.question,
    )
    await flush_project_usage_events(session=session, current_user=current_user, project=project)
    response.headers["Location"] = f"/projects/{project.id}/conversations/{result.conversation.id}"
    return ProjectConversationRead.from_conversation(result.conversation)


@router.post(
    "/{project_id}/conversations/stream",
    status_code=status.HTTP_201_CREATED,
)
async def stream_project_conversation(
    project_id: str,
    payload: ProjectConversationCreate,
    session: DbSession,
    current_user: CurrentUser,
    conversation_service: ProjectConversationServiceDependency,
) -> StreamingResponse:
    """Stream a first project-scoped multi-paper conversation turn as SSE."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    selected_papers = await get_project_papers_or_404(
        session,
        project_id=project.id,
        paper_ids=payload.paper_ids,
    )
    start_usage_collection()

    async def events() -> AsyncIterator[str]:
        try:
            async for event in conversation_service.stream_create_conversation(
                session=session,
                project_id=project.id,
                selected_papers=selected_papers,
                question=payload.question,
            ):
                if event.event == "done":
                    await flush_project_usage_events(
                        session=session,
                        current_user=current_user,
                        project=project,
                    )
                yield encode_sse_event(event.event, project_conversation_stream_payload(event))
        except Exception as error:
            await session.rollback()
            yield encode_sse_event("error", {"detail": str(error)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        status_code=status.HTTP_201_CREATED,
        headers=sse_headers(),
    )


@router.post(
    "/{project_id}/conversations/{conversation_id}/messages",
    response_model=ProjectConversationRead,
)
async def create_project_conversation_message(
    project_id: str,
    conversation_id: str,
    payload: ProjectConversationMessageCreate,
    session: DbSession,
    current_user: CurrentUser,
    conversation_service: ProjectConversationServiceDependency,
) -> ProjectConversationRead:
    """Persist a follow-up turn for a project-scoped multi-paper conversation."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    conversation = await get_project_conversation_or_404(
        session,
        project_id=project.id,
        conversation_id=conversation_id,
    )
    selected_papers = await get_project_papers_or_404(
        session,
        project_id=project.id,
        paper_ids=payload.paper_ids,
    )
    start_usage_collection()
    result = await conversation_service.continue_conversation(
        session=session,
        conversation=conversation,
        selected_papers=selected_papers,
        question=payload.question,
    )
    await flush_project_usage_events(session=session, current_user=current_user, project=project)
    return ProjectConversationRead.from_conversation(result.conversation)


@router.post(
    "/{project_id}/conversations/{conversation_id}/messages/stream",
)
async def stream_project_conversation_message(
    project_id: str,
    conversation_id: str,
    payload: ProjectConversationMessageCreate,
    session: DbSession,
    current_user: CurrentUser,
    conversation_service: ProjectConversationServiceDependency,
) -> StreamingResponse:
    """Stream a follow-up project-scoped multi-paper conversation turn as SSE."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    conversation = await get_project_conversation_or_404(
        session,
        project_id=project.id,
        conversation_id=conversation_id,
    )
    selected_papers = await get_project_papers_or_404(
        session,
        project_id=project.id,
        paper_ids=payload.paper_ids,
    )
    start_usage_collection()

    async def events() -> AsyncIterator[str]:
        try:
            async for event in conversation_service.stream_continue_conversation(
                session=session,
                conversation=conversation,
                selected_papers=selected_papers,
                question=payload.question,
            ):
                if event.event == "done":
                    await flush_project_usage_events(
                        session=session,
                        current_user=current_user,
                        project=project,
                    )
                yield encode_sse_event(event.event, project_conversation_stream_payload(event))
        except Exception as error:
            await session.rollback()
            yield encode_sse_event("error", {"detail": str(error)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


@router.get(
    "/{project_id}/conversations",
    response_model=list[ProjectConversationSummaryRead],
)
async def list_project_conversations(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> list[ProjectConversationSummaryRead]:
    """List project-scoped grounded conversations."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    result = await session.execute(
        select(ProjectConversation)
        .options(selectinload(ProjectConversation.messages))
        .where(ProjectConversation.project_id == project.id)
        .order_by(ProjectConversation.updated_at.desc(), ProjectConversation.created_at.desc())
    )
    conversations = result.scalars().all()
    return [
        ProjectConversationSummaryRead.from_conversation(conversation)
        for conversation in conversations
    ]


@router.get(
    "/{project_id}/conversations/{conversation_id}",
    response_model=ProjectConversationRead,
)
async def get_project_conversation(
    project_id: str,
    conversation_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> ProjectConversationRead:
    """Fetch one project-scoped grounded conversation."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    conversation = await get_project_conversation_or_404(
        session,
        project_id=project.id,
        conversation_id=conversation_id,
    )
    return ProjectConversationRead.from_conversation(conversation)


@router.post(
    "/{project_id}/deep-search/stream",
    status_code=status.HTTP_201_CREATED,
)
async def stream_deep_search(
    project_id: str,
    payload: DeepSearchCreate,
    session: DbSession,
    current_user: CurrentUser,
    deep_search_service: DeepSearchServiceDependency,
) -> StreamingResponse:
    """Stream a project-scoped deep search run as SSE."""

    ensure_deep_search_allowed(current_user)
    project = await get_owned_project_or_404(session, current_user.id, project_id)
    selected_papers = await get_project_papers_or_404(
        session,
        project_id=project.id,
        paper_ids=payload.paper_ids,
    )
    start_usage_collection()

    async def events() -> AsyncIterator[str]:
        try:
            async for event in deep_search_service.stream_run(
                session=session,
                project=project,
                question=payload.question,
                selected_papers=selected_papers,
            ):
                if event.event == "done":
                    await flush_project_usage_events(
                        session=session,
                        current_user=current_user,
                        project=project,
                    )
                yield encode_sse_event(event.event, deep_search_stream_payload(event))
        except Exception as error:
            await session.rollback()
            yield encode_sse_event("error", {"detail": str(error)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        status_code=status.HTTP_201_CREATED,
        headers=sse_headers(),
    )


@router.get(
    "/{project_id}/deep-search-runs",
    response_model=list[DeepSearchRunSummaryRead],
)
async def list_deep_search_runs(
    project_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> list[DeepSearchRunSummaryRead]:
    """List persisted deep search runs for an owned project."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    result = await session.execute(
        select(DeepSearchRun)
        .options(selectinload(DeepSearchRun.sources))
        .where(DeepSearchRun.project_id == project.id)
        .order_by(DeepSearchRun.created_at.desc())
    )
    runs = result.scalars().all()
    return [DeepSearchRunSummaryRead.from_run(run) for run in runs]


@router.get(
    "/{project_id}/deep-search-runs/{run_id}",
    response_model=DeepSearchRunRead,
)
async def get_deep_search_run(
    project_id: str,
    run_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> DeepSearchRunRead:
    """Fetch one persisted deep search run for an owned project."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    run = await get_project_deep_search_run_or_404(
        session,
        project_id=project.id,
        run_id=run_id,
    )
    return DeepSearchRunRead.from_run(run)


@router.post(
    "/{project_id}/writer/generate",
    response_model=WriterOutputRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_writer_output(
    project_id: str,
    payload: WriterGenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
    writer_output_service: WriterOutputServiceDependency,
    response: Response,
) -> WriterOutputRead:
    """Generate, QA, and persist a grounded writer artifact for selected project papers."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    start_usage_collection()
    try:
        writer_output = await writer_output_service.generate_output(
            session=session,
            project=project,
            paper_ids=payload.paper_ids,
            instruction=payload.instruction,
            output_target=payload.output_target,
            citation_mode=payload.citation_mode,
            reference_style=payload.reference_style,
            include_references=payload.include_references,
            max_words=payload.max_words,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    await flush_project_usage_events(session=session, current_user=current_user, project=project)
    response.headers["Location"] = f"/projects/{project.id}/writer/outputs/{writer_output.id}"
    return WriterOutputRead.from_writer_output(writer_output)


@router.get(
    "/{project_id}/writer/outputs/{output_id}",
    response_model=WriterOutputRead,
)
async def get_writer_output(
    project_id: str,
    output_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> WriterOutputRead:
    """Fetch one persisted writer output for the authenticated user's project."""

    project = await get_owned_project_or_404(session, current_user.id, project_id)
    writer_output = await get_project_writer_output_or_404(
        session,
        project_id=project.id,
        output_id=output_id,
    )
    return WriterOutputRead.from_writer_output(writer_output)
