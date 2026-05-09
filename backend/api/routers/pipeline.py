import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from backend.agents.graph import PIPELINE_NODE_NAMES
from backend.api.dependencies import CurrentUser
from backend.api.schemas.projects import PipelineHealthResponse
from backend.services.llm import OpenRouterStructuredOutputService, StructuredOutputError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_STANDARD_PLAN_PROMPT = (
    "You are a deep research strategist. Given a research question, identify the core claims "
    "worth verifying, the key debates or open problems in the field, likely knowledge gaps, "
    "and counterintuitive angles that would make the answer genuinely useful. "
    "Produce 3 to 5 specific research sub-questions that illuminate the topic — name specific "
    "methods, models, or phenomena, not generic process steps. "
    "Also produce 1-2 short keyword search queries (seed_queries) for academic APIs — "
    "concise keyword strings under 8 words each, NOT full sentences. "
    'Respond with JSON: {"questions": ["...", ...], "seed_queries": ["...", ...]}'
)

_MAX_PLAN_PROMPT = (
    "You are a systematic research architect. Decompose the research question into 5 to 8 "
    "distinct research dimensions — one question per dimension, covering: the primary "
    "architecture or method, specific challenges it addresses, competing approaches, empirical "
    "benchmarks (Precision, Recall, F1, FPS, mAP), output representation differences "
    "(e.g. heatmap vs bounding box), training data and dataset requirements, and trade-off "
    "synthesis. Each question must name SPECIFIC things (model names, metric names, dataset "
    "names) — never generic phrases like 'recent evidence' or 'real-world examples'. "
    "Do not restate the original question verbatim. "
    "Also produce 2-3 short keyword search queries (seed_queries) for academic APIs — "
    "keyword-style under 8 words each, NOT full sentences. "
    'Respond with JSON: {"questions": ["...", ...], "seed_queries": ["...", ...]}'
)


def _fallback_questions(question: str, mode: str = "standard") -> list[str]:
    compact = question.strip()[:200]
    if mode == "max":
        return [
            "What is the architecture and technical design of the primary method?",
            "What specific challenges or conditions does this approach address?",
            "What competing or alternative approaches exist for the same task?",
            "How does this method compare empirically on precision, recall, F1, and speed?",
            "What datasets and training procedures are required?",
        ]
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
    mode: Literal["standard", "max"] = "standard"


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
            questions=_fallback_questions(body.question, body.mode),
            seed_queries=_fallback_seed_queries(body.question),
        )

    is_max = body.mode == "max"
    schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 3,
                "maxItems": 8 if is_max else 5,
                "items": {"type": "string"},
            },
            "seed_queries": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3 if is_max else 2,
                "items": {"type": "string", "maxLength": 80},
            },
        },
        "required": ["questions", "seed_queries"],
        "additionalProperties": False,
    }

    try:
        result = await llm.generate_json(
            system_prompt=_MAX_PLAN_PROMPT if is_max else _STANDARD_PLAN_PROMPT,
            user_prompt=f"Research question: {body.question}",
            schema=schema,
            max_tokens=900 if is_max else 512,
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
    except (StructuredOutputError, Exception) as exc:
        logger.warning("deep-search/plan fell back to local questions: %s", exc)
        questions = _fallback_questions(body.question, body.mode)
        seed_queries = _fallback_seed_queries(body.question)

    return DeepSearchPlanResponse(questions=questions, seed_queries=seed_queries)
