"""Writer section agent — per-section IMRaD drafting with low-confidence tagging."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.agents.writer import GroundedWriterAgent, WriterBodyBlock, WriterPaperContext
from backend.services.llm import OpenRouterStructuredOutputService

IMRAD_SECTION_QUESTIONS: dict[str, list[str]] = {
    "abstract": [],
    "intro": [
        "What problem does this paper address?",
        "What is the research gap?",
        "What is your one-sentence contribution?",
        "Who is the target audience?",
    ],
    "related_work": [
        "Which 3-5 lines of prior work matter most?",
        "Any specific papers/authors to cover?",
        "What gap does your work fill that prior work doesn't?",
    ],
    "methods": [
        "What dataset(s) did you use?",
        "What model/algorithm/approach?",
        "What are the baselines?",
        "What is the evaluation metric?",
    ],
    "results": [
        "Paste your key numbers / table / main finding.",
        "What is the headline result?",
    ],
    "discussion": [
        "What is your interpretation?",
        "What are the limitations?",
        "Why does this matter?",
    ],
    "conclusion": [
        "One-sentence takeaway?",
        "Future work directions?",
    ],
}

DEFAULT_IMRAD_PREAMBLE = r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{hyperref}
\usepackage{natbib}
\usepackage[colorinlistoftodos,prependcaption,textsize=tiny]{todonotes}
\newcommand{\unsupported}[1]{\todo[color=red!30]{unsupported: #1}}
\title{PLACEHOLDER TITLE}
\author{PLACEHOLDER AUTHOR}
\date{\today}
\begin{document}
\maketitle
"""

IMRAD_SECTION_DEFAULTS: list[dict[str, Any]] = [
    {"section_type": "abstract", "order_index": 0, "title": "Abstract"},
    {"section_type": "intro", "order_index": 1, "title": "Introduction"},
    {"section_type": "related_work", "order_index": 2, "title": "Related Work"},
    {"section_type": "methods", "order_index": 3, "title": "Methods"},
    {"section_type": "results", "order_index": 4, "title": "Results"},
    {"section_type": "discussion", "order_index": 5, "title": "Discussion"},
    {"section_type": "conclusion", "order_index": 6, "title": "Conclusion"},
]

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
TODO_CITATION_TEMPLATE = r"\todo{{citation needed: {reason}}}"
MAX_SECTION_SOURCE_CONTEXTS = 7
GENERIC_FALLBACK_PREFIX = "Taken together, the selected papers form a focused evidence set"


@dataclass(frozen=True)
class LowConfidenceSpan:
    """A sentence flagged as having no supporting chunk evidence."""

    section_id: str
    text: str
    reason: str
    suggested_query: str
    char_offset: int


@dataclass(frozen=True)
class SectionDraftResult:
    """Rendered LaTeX draft for one section plus low-confidence metadata."""

    draft_latex: str
    low_confidence_spans: list[LowConfidenceSpan]
    cited_paper_ids: list[str]
    warnings: list[str]


def section_questions(section_type: str) -> list[str]:
    """Return the predetermined question list for a section type."""
    return IMRAD_SECTION_QUESTIONS.get(section_type, [])


class WriterSectionAgent:
    """Thin adapter around GroundedWriterAgent for per-section IMRaD drafting."""

    def __init__(
        self,
        *,
        writer_agent: GroundedWriterAgent | None = None,
    ) -> None:
        self.writer_agent = writer_agent or GroundedWriterAgent(
            writer_generator=OpenRouterStructuredOutputService()
        )

    async def draft_section(
        self,
        *,
        section_id: str,
        section_type: str,
        title: str,
        outline_text: str | None,
        user_inputs: dict[str, str],
        paper_contexts: list[WriterPaperContext],
        citation_style: str = "ieee",
    ) -> SectionDraftResult:
        """Draft a single LaTeX section and tag unsupported sentences."""

        if not paper_contexts:
            return SectionDraftResult(
                draft_latex="",
                low_confidence_spans=[],
                cited_paper_ids=[],
                warnings=["No source papers attached — cannot draft grounded content."],
            )
        source_contexts = paper_contexts[:MAX_SECTION_SOURCE_CONTEXTS]

        instruction = self._build_instruction(
            section_type=section_type,
            title=title,
            outline_text=outline_text,
            user_inputs=user_inputs,
            paper_contexts=source_contexts,
        )

        result = await self.writer_agent.generate(
            paper_contexts=source_contexts,
            instruction=instruction,
            output_target="latex",
            citation_mode="latex_cite",
            reference_style=citation_style,
            include_references=False,
            max_words=None,
        )

        body_blocks = result.body_blocks
        warnings = list(result.warnings)
        if len(paper_contexts) > MAX_SECTION_SOURCE_CONTEXTS:
            warnings.append(
                f"Using the top {MAX_SECTION_SOURCE_CONTEXTS} source papers for this section draft."
            )

        # The generic writer fallback ignores IMRaD section type, which makes every section
        # read the same when the provider is unavailable. Replace it with a section-aware draft.
        if self._looks_like_generic_fallback(body_blocks, source_contexts):
            body_blocks = self._build_section_fallback_blocks(
                section_type=section_type,
                title=title,
                outline_text=outline_text,
                user_inputs=user_inputs,
                paper_contexts=source_contexts,
            )
            warnings.append(
                "LLM was unavailable or returned a generic fallback; using a section-specific fallback."
            )

        if not body_blocks and source_contexts:
            body_blocks = self._build_section_fallback_blocks(
                section_type=section_type,
                title=title,
                outline_text=outline_text,
                user_inputs=user_inputs,
                paper_contexts=source_contexts,
            )
            warnings.append("LLM returned no content — using a section-specific fallback.")

        latex_parts: list[str] = [f"\\section{{{title}}}"]
        low_confidence_spans: list[LowConfidenceSpan] = []
        cited_paper_ids: set[str] = set()
        char_offset = len(latex_parts[0]) + 1

        for block in body_blocks:
            if block.paper_ids:
                cited_paper_ids.update(block.paper_ids)
                cite_cmd = f"\\cite{{{','.join(block.paper_ids)}}}"
                text_with_cite = f"{block.text} {cite_cmd}"
                latex_parts.append(text_with_cite)
                char_offset += len(text_with_cite) + 1
            else:
                tagged = self._tag_unsupported_block(
                    block=block,
                    section_id=section_id,
                    char_offset=char_offset,
                    low_confidence_spans=low_confidence_spans,
                )
                latex_parts.append(tagged)
                char_offset += len(tagged) + 1

        draft_latex = "\n\n".join(latex_parts)

        return SectionDraftResult(
            draft_latex=draft_latex,
            low_confidence_spans=low_confidence_spans,
            cited_paper_ids=sorted(cited_paper_ids),
            warnings=warnings,
        )

    def _build_instruction(
        self,
        *,
        section_type: str,
        title: str,
        outline_text: str | None,
        user_inputs: dict[str, str],
        paper_contexts: list[WriterPaperContext],
    ) -> str:
        parts = [f"Write the '{title}' section (type: {section_type}) of an IMRaD LaTeX paper."]
        if outline_text:
            parts.append(f"Outline notes: {outline_text.strip()}")
        questions = section_questions(section_type)
        for question in questions:
            answer = user_inputs.get(question, "").strip()
            if answer:
                parts.append(f"{question}: {answer}")
        notes = user_inputs.get("__notes__", "").strip()
        if notes:
            parts.append(f"Additional researcher context / raw data:\n{notes}")
        if paper_contexts:
            cite_lines = [
                f'  {ctx.paper_id} — "{ctx.title}" ({ctx.year or "n.d."})'
                for ctx in paper_contexts
            ]
            parts.append(
                "Available paper IDs (reference only — do NOT write \\cite in text):\n"
                + "\n".join(cite_lines)
            )
        parts.append(
            "Produce LaTeX paragraph text only (no \\section command). "
            "Ground every claim in the provided papers. "
            "Do not invent citations or facts."
        )
        return "\n".join(parts)

    def _looks_like_generic_fallback(
        self,
        body_blocks: list[WriterBodyBlock],
        paper_contexts: list[WriterPaperContext],
    ) -> bool:
        if not body_blocks:
            return False
        if body_blocks[0].text.startswith(GENERIC_FALLBACK_PREFIX):
            return True
        if len(body_blocks) == 1 and "requested writing task" in body_blocks[0].text:
            return True

        context_by_id = {context.paper_id: context for context in paper_contexts}
        source_summary_blocks = 0
        for block in body_blocks:
            if len(block.paper_ids) != 1:
                continue
            context = context_by_id.get(block.paper_ids[0])
            if context is None:
                continue
            if block.text.startswith(self._clean_fallback_text(context.title)):
                source_summary_blocks += 1
        return source_summary_blocks == len(body_blocks)

    def _build_section_fallback_blocks(
        self,
        *,
        section_type: str,
        title: str,
        outline_text: str | None,
        user_inputs: dict[str, str],
        paper_contexts: list[WriterPaperContext],
    ) -> list[WriterBodyBlock]:
        if not paper_contexts:
            return []

        primary_contexts = paper_contexts[:3]
        secondary_contexts = paper_contexts[3:MAX_SECTION_SOURCE_CONTEXTS]
        topic_hint = self._fallback_topic_hint(
            title=title,
            outline_text=outline_text,
            user_inputs=user_inputs,
        )

        blocks: list[WriterBodyBlock] = []
        if section_type == "related_work":
            blocks.append(
                WriterBodyBlock(
                    text=(
                        f"Prior work for {topic_hint} is anchored by "
                        f"{self._join_context_labels(primary_contexts)}. These sources define the main "
                        "evidence base and make it possible to compare how earlier studies frame the "
                        "task, choose their modeling assumptions, and report tracking or analysis outcomes."
                    ),
                    paper_ids=[ctx.paper_id for ctx in primary_contexts],
                )
            )
            if secondary_contexts:
                blocks.append(
                    WriterBodyBlock(
                        text=(
                            f"Additional related studies, including "
                            f"{self._join_context_labels(secondary_contexts[:3])}, should be used to "
                            "separate recurring baselines from incremental extensions and to identify "
                            "where the current work can state a narrower contribution."
                        ),
                        paper_ids=[ctx.paper_id for ctx in secondary_contexts[:3]],
                    )
                )
            return blocks

        if section_type == "methods":
            method_text = self._join_evidence_segments(
                primary_contexts,
                field="method",
                fallback="the available methodological descriptions",
            )
            blocks.append(
                WriterBodyBlock(
                    text=(
                        f"Methodologically, this section uses {self._join_context_labels(primary_contexts)} "
                        f"to ground the design choices around {topic_hint}. The source evidence points to "
                        f"{method_text}, so the draft should describe the pipeline, assumptions, and "
                        "comparison setup before introducing implementation details."
                    ),
                    paper_ids=[ctx.paper_id for ctx in primary_contexts],
                )
            )
            return blocks

        if section_type == "results":
            result_text = self._join_evidence_segments(
                primary_contexts,
                field="result",
                fallback="the reported outcomes in the selected papers",
            )
            blocks.append(
                WriterBodyBlock(
                    text=(
                        f"The results section should report {result_text} while keeping each claim tied to "
                        f"{self._join_context_labels(primary_contexts)}. Quantitative values should be added "
                        "only where they are present in the attached source evidence."
                    ),
                    paper_ids=[ctx.paper_id for ctx in primary_contexts],
                )
            )
            return blocks

        if section_type in {"discussion", "conclusion"}:
            blocks.append(
                WriterBodyBlock(
                    text=(
                        f"This section uses {self._join_context_labels(primary_contexts)} to interpret the "
                        f"evidence for {topic_hint}. The draft should distinguish supported implications "
                        "from open limitations and avoid adding claims that are not present in the selected "
                        "source set."
                    ),
                    paper_ids=[ctx.paper_id for ctx in primary_contexts],
                )
            )
            return blocks

        problem_text = self._join_evidence_segments(
            primary_contexts,
            field="problem",
            fallback="the problem statements in the selected papers",
        )
        blocks.append(
            WriterBodyBlock(
                text=(
                    f"This section uses {self._join_context_labels(primary_contexts)} to frame {topic_hint}. "
                    f"The attached evidence emphasizes {problem_text}, which should motivate the section "
                    "without introducing unsupported background claims."
                ),
                paper_ids=[ctx.paper_id for ctx in primary_contexts],
            )
        )
        return blocks

    def _fallback_topic_hint(
        self,
        *,
        title: str,
        outline_text: str | None,
        user_inputs: dict[str, str],
    ) -> str:
        for value in [outline_text, *user_inputs.values(), title]:
            normalized = (value or "").strip()
            if normalized:
                return normalized.rstrip(".")
        return title

    def _join_context_labels(self, contexts: list[WriterPaperContext]) -> str:
        labels = [self._context_label(context) for context in contexts]
        if not labels:
            return "the selected sources"
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} and {labels[1]}"
        return f"{', '.join(labels[:-1])}, and {labels[-1]}"

    def _context_label(self, context: WriterPaperContext) -> str:
        title = self._clean_fallback_text(context.title).rstrip(".")
        if context.year:
            return f"{title} ({context.year})"
        return title

    def _join_evidence_segments(
        self,
        contexts: list[WriterPaperContext],
        *,
        field: str,
        fallback: str,
    ) -> str:
        segments: list[str] = []
        for context in contexts:
            raw_value = getattr(context, field)
            if not raw_value and context.abstract:
                raw_value = self._first_sentence(context.abstract)
            if not raw_value:
                continue
            segments.append(self._clean_fallback_text(raw_value).rstrip("."))
        if not segments:
            return fallback
        if len(segments) == 1:
            return self._lowercase_first(segments[0])
        return "; ".join(self._lowercase_first(segment) for segment in segments[:3])

    def _first_sentence(self, text: str) -> str:
        sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(text) if sentence.strip()]
        return sentences[0] if sentences else text.strip()

    def _clean_fallback_text(self, text: str) -> str:
        cleaned = re.sub(r"^\[PDF\]\s*", "", text.strip(), flags=re.IGNORECASE)
        cleaned = cleaned.replace("| Semantic Scholar", "").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned or "the selected source"

    def _lowercase_first(self, text: str) -> str:
        normalized = text.strip()
        if not normalized:
            return normalized
        return normalized[0].lower() + normalized[1:]

    def _tag_unsupported_block(
        self,
        *,
        block: WriterBodyBlock,
        section_id: str,
        char_offset: int,
        low_confidence_spans: list[LowConfidenceSpan],
    ) -> str:
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(block.text) if s.strip()]
        tagged_sentences: list[str] = []
        for sentence in sentences:
            reason = "no supporting chunk matched this claim"
            suggested_query = " ".join(sentence.split()[:8])
            low_confidence_spans.append(
                LowConfidenceSpan(
                    section_id=section_id,
                    text=sentence,
                    reason=reason,
                    suggested_query=suggested_query,
                    char_offset=char_offset,
                )
            )
            tag = TODO_CITATION_TEMPLATE.format(reason=reason)
            tagged_sentences.append(f"{sentence} {tag}")
            char_offset += len(sentence) + len(tag) + 2
        return " ".join(tagged_sentences)
