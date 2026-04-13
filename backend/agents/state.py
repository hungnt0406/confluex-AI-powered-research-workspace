from dataclasses import dataclass, field


@dataclass
class AgentState:
    """Shared state that flows through the LangGraph pipeline."""

    project_id: str
    topic: str
    year_start: int = 2018
    candidate_limit: int = 60
    summary_limit: int = 30
    queries: list[str] = field(default_factory=list)
    raw_papers: list[dict[str, object]] = field(default_factory=list)
    ranked_papers: list[dict[str, object]] = field(default_factory=list)
    summaries: list[dict[str, object]] = field(default_factory=list)
    draft: str = ""
    qa_flags: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
