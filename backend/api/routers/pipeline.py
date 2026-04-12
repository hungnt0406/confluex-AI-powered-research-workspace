from fastapi import APIRouter

from backend.agents.graph import PIPELINE_NODE_NAMES
from backend.api.schemas.projects import PipelineHealthResponse

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/health", response_model=PipelineHealthResponse)
async def get_pipeline_health() -> PipelineHealthResponse:
    """Return the phase-1 pipeline skeleton status."""

    return PipelineHealthResponse(status="ok", nodes=PIPELINE_NODE_NAMES)
