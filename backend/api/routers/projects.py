from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from backend.api.dependencies import CurrentUser, DbSession, PipelineServiceDependency
from backend.api.schemas.projects import (
    PaginationMeta,
    ProjectCreate,
    ProjectPaperListResponse,
    ProjectPaperRead,
    ProjectRead,
    RunPipelineResponse,
)
from backend.db.models import Paper, Project

router = APIRouter(prefix="/projects", tags=["projects"])


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
    state = await pipeline_service.run_project(session=session, project=project)
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
