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
        "questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "seed_queries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {"type": "string", "maxLength": 80},
        },
    },
    "required": ["questions", "seed_queries"],
    "additionalProperties": False,
}

_PLAN_SYSTEM_PROMPT = (
    "You are a deep research strategist. Given a research question, identify the core claims "
    "worth verifying, the key debates or open problems in the field, likely knowledge gaps, "
    "and counterintuitive angles that would make the answer genuinely useful. "
    "Then produce 3 to 5 specific, investigable research sub-questions that best illuminate "
    "the topic. Do not produce generic process steps — produce real questions about the subject. "
    "Also produce 1-2 short keyword search queries (seed_queries) suitable for academic APIs — "
    "these must be concise keyword strings (under 8 words each), NOT full sentences."
)


def _fallback_questions(question: str) -> list[str]:
    compact = question.strip()[:200]
    return [
        compact,
        f"What recent academic evidence addresses: {compact}?",
        f"What are the key debates, limitations, or open problems related to: {compact}?",
        f"What implementation context or real-world examples are relevant to: {compact}?",
    ]


def _fallback_seed_queries(question: str) -> list[str]:
    words = question.strip().split()
    return [" ".join(words[:6])]


class DeepSearchPlanRequest(BaseModel):
    question: str


class DeepSearchPlanResponse(BaseModel):
    questions: list[str]
    seed_queries: list[str] = []


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
        return DeepSearchPlanResponse(
            questions=_fallback_questions(body.question),
            seed_queries=_fallback_seed_queries(body.question),
        )

    try:
        result = await llm.generate_json(
            system_prompt=_PLAN_SYSTEM_PROMPT,
            user_prompt=f"Research question: {body.question}",
            schema=_PLAN_SCHEMA,
            max_tokens=512,
            feature="deep_search_plan",
        )
        raw_questions = result.get("questions", [])
        raw_seed_queries = result.get("seed_queries", [])
        if not isinstance(raw_questions, list) or not raw_questions:
            raise StructuredOutputError("Unexpected plan structure from LLM.")
        questions = [str(q).strip() for q in raw_questions if str(q).strip()]
        seed_queries = [str(q).strip() for q in raw_seed_queries if str(q).strip()]
        if not seed_queries:
            seed_queries = _fallback_seed_queries(body.question)
    except (StructuredOutputError, Exception):
        questions = _fallback_questions(body.question)
        seed_queries = _fallback_seed_queries(body.question)

    return DeepSearchPlanResponse(questions=questions, seed_queries=seed_queries)
