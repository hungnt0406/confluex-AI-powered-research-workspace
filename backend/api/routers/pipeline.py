from fastapi import APIRouter
from pydantic import BaseModel

from backend.agents.graph import PIPELINE_NODE_NAMES
from backend.api.dependencies import CurrentUser
from backend.api.schemas.projects import PipelineHealthResponse
from backend.services.llm import OpenRouterStructuredOutputService, StructuredOutputError

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "items"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["steps"],
    "additionalProperties": False,
}

_PLAN_SYSTEM_PROMPT = """You generate concise, topic-specific research plans.
Given a user's research question, produce exactly 3 steps in this order:
1. "Research Websites" — 3 bullet-point actions for gathering sources on the specific topic
2. "Analyze Results" — 2 bullet-point actions for synthesizing the gathered sources
3. "Create Report" — 2 bullet-point actions for writing and finalizing the report

Rules:
- Use the exact step titles above.
- Tailor every bullet point to the user's specific topic; avoid generic filler.
- Each bullet point is a single, actionable sentence (max 20 words).
- Return valid JSON conforming to the provided schema."""


def _fallback_steps(question: str) -> list[dict]:
    compact = question.strip()[:120]
    return [
        {
            "title": "Research Websites",
            "items": [
                f'Define the research question around "{compact}".',
                "Search scholarly indexes, project papers, and current web sources for supporting evidence.",
                "Collect source notes that can be cited directly in the final report.",
            ],
        },
        {
            "title": "Analyze Results",
            "items": [
                "Compare evidence quality across papers, web results, and selected project context.",
                "Extract points of agreement, disagreement, limitations, and recent developments.",
            ],
        },
        {
            "title": "Create Report",
            "items": [
                "Write a concise synthesis with named source links for factual claims.",
                "Run citation checks and preserve the final sources in the context panel.",
            ],
        },
    ]


class DeepSearchPlanRequest(BaseModel):
    question: str


class DeepSearchPlanStep(BaseModel):
    title: str
    items: list[str]


class DeepSearchPlanResponse(BaseModel):
    steps: list[DeepSearchPlanStep]


@router.get("/health", response_model=PipelineHealthResponse)
async def get_pipeline_health() -> PipelineHealthResponse:
    """Return the phase-1 pipeline skeleton status."""

    return PipelineHealthResponse(status="ok", nodes=PIPELINE_NODE_NAMES)


@router.post("/deep-search/plan", response_model=DeepSearchPlanResponse)
async def generate_deep_search_plan(
    body: DeepSearchPlanRequest,
    _current_user: CurrentUser,
) -> DeepSearchPlanResponse:
    """Generate a topic-specific research plan using the LLM."""

    llm = OpenRouterStructuredOutputService()
    if not llm.is_configured():
        return DeepSearchPlanResponse(steps=[DeepSearchPlanStep(**s) for s in _fallback_steps(body.question)])

    try:
        result = await llm.generate_json(
            system_prompt=_PLAN_SYSTEM_PROMPT,
            user_prompt=f"Research question: {body.question}",
            schema=_PLAN_SCHEMA,
            max_tokens=512,
            feature="deep_search_plan",
        )
        raw_steps = result.get("steps", [])
        if not isinstance(raw_steps, list) or len(raw_steps) != 3:
            raise StructuredOutputError("Unexpected plan structure from LLM.")
        steps = [DeepSearchPlanStep(**s) for s in raw_steps]
    except (StructuredOutputError, Exception):
        steps = [DeepSearchPlanStep(**s) for s in _fallback_steps(body.question)]

    return DeepSearchPlanResponse(steps=steps)
