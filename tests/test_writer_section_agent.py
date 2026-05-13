"""Tests for the writer section agent (TDD)."""

from __future__ import annotations

from typing import Any

import pytest

from backend.agents.writer import GroundedWriterAgent, WriterPaperContext
from backend.agents.writer_section import (
    IMRAD_SECTION_DEFAULTS,
    WriterSectionAgent,
    section_questions,
)


class OfflineWriterGenerator:
    def is_configured(self) -> bool:
        return False

    async def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("offline fallback should not call the provider")


class MissingPaperIdsWriterGenerator:
    def is_configured(self) -> bool:
        return True

    async def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "body_blocks": [{"text": "Generated grounded text without source IDs."}],
            "warnings": [],
        }


def make_paper_context(
    paper_id: str = "p1",
    title: str = "Test Paper",
    *,
    method: str = "Test method.",
    result: str = "Test results.",
) -> WriterPaperContext:
    return WriterPaperContext(
        paper_id=paper_id,
        title=title,
        authors=["Author A"],
        year=2023,
        abstract="A test abstract.",
        problem="Testing problems.",
        method=method,
        result=result,
        relevance_to_topic="Relevant.",
        evidence_snippets=["Evidence snippet one.", "Evidence snippet two."],
        metadata_warnings=[],
    )


def make_offline_section_agent() -> WriterSectionAgent:
    return WriterSectionAgent(
        writer_agent=GroundedWriterAgent(writer_generator=OfflineWriterGenerator())
    )


class TestSectionQuestions:
    def test_methods_has_four_questions(self) -> None:
        qs = section_questions("methods")
        assert len(qs) == 4

    def test_abstract_has_no_questions(self) -> None:
        qs = section_questions("abstract")
        assert qs == []

    def test_intro_has_four_questions(self) -> None:
        qs = section_questions("intro")
        assert len(qs) == 4

    def test_related_work_has_three_questions(self) -> None:
        qs = section_questions("related_work")
        assert len(qs) == 3

    def test_results_has_two_questions(self) -> None:
        qs = section_questions("results")
        assert len(qs) == 2

    def test_discussion_has_three_questions(self) -> None:
        qs = section_questions("discussion")
        assert len(qs) == 3

    def test_conclusion_has_two_questions(self) -> None:
        qs = section_questions("conclusion")
        assert len(qs) == 2

    def test_unknown_section_type_returns_empty(self) -> None:
        qs = section_questions("unknown_section")
        assert qs == []


class TestIMRaDDefaults:
    def test_defaults_cover_all_seven_sections(self) -> None:
        section_types = [d["section_type"] for d in IMRAD_SECTION_DEFAULTS]
        assert set(section_types) == {
            "abstract",
            "intro",
            "related_work",
            "methods",
            "results",
            "discussion",
            "conclusion",
        }

    def test_defaults_order_indices_are_unique(self) -> None:
        order_indices = [d["order_index"] for d in IMRAD_SECTION_DEFAULTS]
        assert len(order_indices) == len(set(order_indices))

    def test_abstract_is_first(self) -> None:
        abstract = next(d for d in IMRAD_SECTION_DEFAULTS if d["section_type"] == "abstract")
        assert abstract["order_index"] == 0


def test_default_section_agent_uses_writer_generation_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.config import get_settings

    captured_kwargs: dict[str, Any] = {}

    class CapturingStructuredOutputService:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

        def is_configured(self) -> bool:
            return False

        async def generate_json(self, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("provider should not be called")

    monkeypatch.setenv("WRITER_GENERATION_TIMEOUT_SECONDS", "45")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "backend.agents.writer.ClaudeStructuredOutputService",
        CapturingStructuredOutputService,
    )

    try:
        agent = WriterSectionAgent()
        assert isinstance(agent.writer_agent, GroundedWriterAgent)
        assert captured_kwargs["timeout_seconds"] == 45.0
    finally:
        get_settings.cache_clear()


class TestGroundedWriterAgentProviderNormalization:
    async def test_missing_provider_paper_ids_are_repaired_for_narrative_blocks(self) -> None:
        agent = GroundedWriterAgent(writer_generator=MissingPaperIdsWriterGenerator())

        result = await agent.generate(
            paper_contexts=[make_paper_context("p1"), make_paper_context("p2")],
            instruction="Write the introduction section.",
            output_target="latex",
            citation_mode="latex_cite",
            reference_style="ieee",
            include_references=False,
            max_words=None,
        )

        assert result.body_blocks[0].text == "Generated grounded text without source IDs."
        assert result.body_blocks[0].paper_ids == ["p1", "p2"]
        assert "omitted paper_ids" in " ".join(result.warnings)


class TestWriterSectionAgentOffline:
    """Tests that run without an LLM key via the offline fallback path."""

    async def test_draft_section_with_papers_returns_draft(self) -> None:
        agent = make_offline_section_agent()
        result = await agent.draft_section(
            section_id="sec-1",
            section_type="methods",
            title="Methods",
            outline_text="Describe the method in detail.",
            user_inputs={
                "What dataset(s) did you use?": "CIFAR-10",
                "What model/algorithm/approach?": "ResNet-50",
            },
            paper_contexts=[make_paper_context("p1")],
            citation_style="ieee",
        )
        assert isinstance(result.draft_latex, str)
        assert len(result.draft_latex) > 0
        assert r"\section{Methods}" in result.draft_latex
        assert "Methodologically" in result.draft_latex
        assert "Taken together" not in result.draft_latex

    async def test_draft_section_no_papers_returns_warning(self) -> None:
        agent = make_offline_section_agent()
        result = await agent.draft_section(
            section_id="sec-2",
            section_type="intro",
            title="Introduction",
            outline_text=None,
            user_inputs={},
            paper_contexts=[],
            citation_style="ieee",
        )
        assert result.draft_latex == ""
        assert len(result.warnings) > 0
        assert "No source papers" in result.warnings[0]

    async def test_unsupported_blocks_tagged_with_todo(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from backend.agents.writer import WriterBodyBlock, WriterGenerationResult

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(
            return_value=WriterGenerationResult(
                body_blocks=[
                    WriterBodyBlock(text="This claim has no support.", paper_ids=[]),
                    WriterBodyBlock(text="This claim is supported.", paper_ids=["p1"]),
                ],
                warnings=[],
            )
        )
        agent = WriterSectionAgent(writer_agent=mock_agent)
        result = await agent.draft_section(
            section_id="sec-3",
            section_type="results",
            title="Results",
            outline_text=None,
            user_inputs={},
            paper_contexts=[make_paper_context("p1")],
            citation_style="ieee",
        )
        assert r"\todo{citation needed:" in result.draft_latex
        assert len(result.low_confidence_spans) >= 1
        assert result.low_confidence_spans[0].text == "This claim has no support."

    async def test_supported_blocks_appear_untagged(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from backend.agents.writer import WriterBodyBlock, WriterGenerationResult

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(
            return_value=WriterGenerationResult(
                body_blocks=[
                    WriterBodyBlock(text="Fully supported claim.", paper_ids=["p1"]),
                ],
                warnings=[],
            )
        )
        agent = WriterSectionAgent(writer_agent=mock_agent)
        result = await agent.draft_section(
            section_id="sec-4",
            section_type="results",
            title="Results",
            outline_text=None,
            user_inputs={},
            paper_contexts=[make_paper_context("p1")],
            citation_style="ieee",
        )
        assert r"\todo{" not in result.draft_latex
        assert r"\cite{p1}" in result.draft_latex
        assert result.low_confidence_spans == []

    async def test_empty_llm_body_uses_section_specific_fallback(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from backend.agents.writer import WriterGenerationResult

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(
            return_value=WriterGenerationResult(body_blocks=[], warnings=["LLM warning"])
        )
        agent = WriterSectionAgent(writer_agent=mock_agent)
        result = await agent.draft_section(
            section_id="sec-stub",
            section_type="intro",
            title="Introduction",
            outline_text=None,
            user_inputs={},
            paper_contexts=[make_paper_context("paper-stub", title="Stub Paper")],
            citation_style="ieee",
        )
        assert "This section uses Stub Paper (2023)" in result.draft_latex
        assert r"\cite{paper-stub}" in result.draft_latex
        assert "section-specific fallback" in " ".join(result.warnings)

    def test_instruction_includes_notes_without_inline_cite_demand(self) -> None:
        agent = WriterSectionAgent()
        instruction = agent._build_instruction(
            paper_type="research",
            section_type="intro",
            title="Introduction",
            outline_text="Motivate the gap.",
            user_inputs={
                "What problem does this paper address?": "Long-context clinical QA.",
                "__notes__": "Dataset: 1,240 annotated cases.",
            },
            paper_contexts=[make_paper_context("p1")],
        )
        assert "Dataset: 1,240 annotated cases." in instruction
        assert "do NOT write \\cite in text" in instruction
        assert "reference only" not in instruction.lower()
        assert "Cite every factual claim" not in instruction

    def test_research_methods_instruction_requires_approved_outline(self) -> None:
        agent = WriterSectionAgent()
        instruction = agent._build_instruction(
            paper_type="research",
            section_type="methods",
            title="Methods",
            outline_text=(
                r"\subsection{Study Design and Experimental Setup}"
                "\n"
                r"\subsection{Proposed Method}"
            ),
            user_inputs={
                "What dataset(s) did you use?": "TrackingNet",
                "What model/algorithm/approach?": "Transformer tracker",
            },
            paper_contexts=[make_paper_context("p1")],
        )

        assert "The approved outline is mandatory" in instruction
        assert r"\subsection{Study Design and Experimental Setup}" in instruction
        assert "Use the approved LaTeX subsection headings" in instruction

    async def test_research_methods_fallback_preserves_approved_subsections(self) -> None:
        agent = make_offline_section_agent()
        result = await agent.draft_section(
            section_id="sec-research-methods",
            paper_type="research",
            section_type="methods",
            title="Methods",
            outline_text=(
                r"\subsection{Study Design and Experimental Setup}"
                "\n"
                r"\subsection{Proposed Method}"
                "\n"
                r"\subsection{Evaluation Metrics}"
            ),
            user_inputs={
                "What dataset(s) did you use?": "TrackingNet",
                "What model/algorithm/approach?": "Transformer tracker",
                "What is the evaluation metric?": "Success and precision",
            },
            paper_contexts=[
                make_paper_context("p1", title="Transformer Tracking"),
                make_paper_context("p2", title="Tracking Benchmarks"),
            ],
            citation_style="ieee",
        )

        assert r"\section{Methods}" in result.draft_latex
        assert r"\subsection{Study Design and Experimental Setup}" in result.draft_latex
        assert r"\subsection{Proposed Method}" in result.draft_latex
        assert r"\subsection{Evaluation Metrics}" in result.draft_latex
        assert r"\cite{p1,p2}" in result.draft_latex

    async def test_survey_results_fallback_preserves_approved_subsections(self) -> None:
        agent = make_offline_section_agent()
        result = await agent.draft_section(
            section_id="sec-survey-results",
            paper_type="survey",
            section_type="results",
            title="Results",
            outline_text=(
                r"\subsection{Comparative Findings by Method Family}"
                "\n"
                r"\subsection{Performance Under High-Speed Conditions}"
                "\n"
                r"\subsection{Accuracy, Robustness, and Latency Trade-offs}"
            ),
            user_inputs={
                "Paste your key numbers / table / main finding.": "Transformer trackers improve robustness but increase latency.",
                "What is the headline result?": "No single tracker dominates every high-speed condition.",
            },
            paper_contexts=[
                make_paper_context("p1", title="Fast Object Tracking", result="Siamese trackers improve accuracy."),
                make_paper_context("p2", title="Robust Tracking Survey", result="Kalman-only tracking drifts under non-linear motion."),
            ],
            citation_style="ieee",
        )

        assert r"\section{Results}" in result.draft_latex
        assert r"\subsection{Comparative Findings by Method Family}" in result.draft_latex
        assert r"\subsection{Performance Under High-Speed Conditions}" in result.draft_latex
        assert r"\subsection{Accuracy, Robustness, and Latency Trade-offs}" in result.draft_latex
        assert r"\cite{p1,p2}" in result.draft_latex

    async def test_offline_fallback_is_section_specific_not_reused_generic_text(self) -> None:
        contexts = [
            make_paper_context(
                f"p{i}",
                title=f"TrackNet Variant {i}",
                method=f"tracking method {i}",
                result=f"tracking result {i}",
            )
            for i in range(1, 5)
        ]
        agent = make_offline_section_agent()

        related = await agent.draft_section(
            section_id="related",
            section_type="related_work",
            title="Related Work",
            outline_text="Compare shuttlecock tracking methods.",
            user_inputs={},
            paper_contexts=contexts,
            citation_style="ieee",
        )
        methods = await agent.draft_section(
            section_id="methods",
            section_type="methods",
            title="Methods",
            outline_text="Describe the proposed tracking pipeline.",
            user_inputs={},
            paper_contexts=contexts,
            citation_style="ieee",
        )

        assert "Prior work" in related.draft_latex
        assert "Methodologically" in methods.draft_latex
        assert "Taken together" not in related.draft_latex
        assert related.draft_latex != methods.draft_latex

    async def test_offline_fallback_limits_section_sources_to_seven(self) -> None:
        contexts = [make_paper_context(f"p{i}", title=f"Paper {i}") for i in range(1, 11)]
        agent = make_offline_section_agent()

        result = await agent.draft_section(
            section_id="sec-related",
            section_type="related_work",
            title="Related Work",
            outline_text="Compare source families.",
            user_inputs={},
            paper_contexts=contexts,
            citation_style="ieee",
        )

        assert r"\cite{p1,p2,p3}" in result.draft_latex
        assert "p8" not in result.draft_latex
        assert "Using the top 7 source papers" in " ".join(result.warnings)

    async def test_multi_paper_blocks_use_one_grouped_cite_command(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from backend.agents.writer import WriterBodyBlock, WriterGenerationResult

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(
            return_value=WriterGenerationResult(
                body_blocks=[
                    WriterBodyBlock(text="Shared supported claim.", paper_ids=["p1", "p2"]),
                ],
                warnings=[],
            )
        )
        agent = WriterSectionAgent(writer_agent=mock_agent)
        result = await agent.draft_section(
            section_id="sec-grouped",
            section_type="related_work",
            title="Related Work",
            outline_text=None,
            user_inputs={},
            paper_contexts=[make_paper_context("p1"), make_paper_context("p2")],
            citation_style="ieee",
        )

        assert r"\cite{p1,p2}" in result.draft_latex
        assert r"\cite{p1} \cite{p2}" not in result.draft_latex

    async def test_cited_paper_ids_collected_from_blocks(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from backend.agents.writer import WriterBodyBlock, WriterGenerationResult

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(
            return_value=WriterGenerationResult(
                body_blocks=[
                    WriterBodyBlock(text="Block one.", paper_ids=["p1", "p2"]),
                    WriterBodyBlock(text="Block two.", paper_ids=["p3"]),
                ],
                warnings=[],
            )
        )
        agent = WriterSectionAgent(writer_agent=mock_agent)
        result = await agent.draft_section(
            section_id="sec-5",
            section_type="methods",
            title="Methods",
            outline_text=None,
            user_inputs={},
            paper_contexts=[
                make_paper_context("p1"),
                make_paper_context("p2"),
                make_paper_context("p3"),
            ],
            citation_style="ieee",
        )
        assert set(result.cited_paper_ids) == {"p1", "p2", "p3"}
