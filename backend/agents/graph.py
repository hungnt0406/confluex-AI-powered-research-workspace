from dataclasses import asdict
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.reader import ReaderAgent
from backend.agents.searcher import SearcherAgent
from backend.agents.state import AgentState
from backend.db.models import Project

PIPELINE_NODE_NAMES = [
    "searcher_node",
    "reader_node",
    "reader_warning_node",
]


class ProjectPipelineRunner:
    """Bind project-aware agent nodes into the LangGraph pipeline."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        project: Project,
        searcher_agent: SearcherAgent | None = None,
        reader_agent: ReaderAgent | None = None,
    ) -> None:
        self.session = session
        self.project = project
        self.searcher_agent = searcher_agent or SearcherAgent()
        self.reader_agent = reader_agent or ReaderAgent()

    async def searcher_node(self, state: AgentState) -> dict[str, Any]:
        print(f"[pipeline] searcher_node project_id={state.project_id} topic={state.topic}")
        return await self.searcher_agent.run(state, self.session, self.project)

    async def reader_node(self, state: AgentState) -> dict[str, Any]:
        print(f"[pipeline] reader_node project_id={state.project_id}")
        return await self.reader_agent.run(state, self.session, self.project)

    async def reader_warning_node(self, state: AgentState) -> dict[str, Any]:
        warning_message = (
            f"Only {len(state.ranked_papers)} ranked papers were available after filtering and ranking."
        )
        print(f"[pipeline] reader_warning_node project_id={state.project_id} warning={warning_message}")
        return {"qa_flags": [*state.qa_flags, warning_message]}

    def route_after_reader(self, state: AgentState) -> Literal["reader_warning_node", "__end__"]:
        if len(state.ranked_papers) < 5:
            return "reader_warning_node"
        return "__end__"

    def build_graph(self) -> Any:
        """Compile the phase-2 LangGraph pipeline."""

        builder = StateGraph(AgentState)
        builder.add_node("searcher_node", self.searcher_node)
        builder.add_node("reader_node", self.reader_node)
        builder.add_node("reader_warning_node", self.reader_warning_node)
        builder.add_edge(START, "searcher_node")
        builder.add_edge("searcher_node", "reader_node")
        builder.add_conditional_edges(
            "reader_node",
            self.route_after_reader,
            {
                "reader_warning_node": "reader_warning_node",
                "__end__": END,
            },
        )
        builder.add_edge("reader_warning_node", END)
        return builder.compile()

    async def run(self) -> AgentState:
        """Run the bound project pipeline graph."""

        graph = self.build_graph()
        initial_state = AgentState(
            project_id=self.project.id,
            topic=self.project.topic_description,
            year_start=self.project.year_start,
            candidate_limit=self.project.candidate_limit,
            summary_limit=self.project.summary_limit,
        )
        # LangGraph expects plain state updates at the graph boundary.
        result = await graph.ainvoke(asdict(initial_state))
        if isinstance(result, AgentState):
            return result

        return AgentState(**result)
