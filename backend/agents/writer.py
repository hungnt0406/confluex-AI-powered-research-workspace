from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from backend.config import get_settings
from backend.services.llm import ClaudeStructuredOutputService, StructuredOutputError

WRITER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "body_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["text", "paper_ids"],
                "additionalProperties": False,
            },
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["body_blocks", "warnings"],
    "additionalProperties": False,
}

WRITER_SYSTEM_PROMPT = """
You are a grounded academic writing assistant.
You are given only the user-selected papers and must write only from those papers.
Rules:
- Use only the provided paper ids in body_blocks.paper_ids.
- Never invent authors, years, venues, findings, or citations.
- When the request is for references or BibTeX only, body_blocks may be empty.
- Each narrative body block must be supported by one or more provided paper ids.
- Do not include inline citation syntax in text. The application will render citations later.
- Put metadata caveats in warnings instead of fabricating missing details.
Return only JSON that matches the requested schema.
""".strip()

REFERENCE_ONLY_PATTERN = re.compile(r"\b(bibtex|bibliography|reference(?:s| section)?|thebibliography)\b")
NARRATIVE_PATTERN = re.compile(
    r"\b(write|draft|section|subsection|compare|comparison|background|related work|summary)\b"
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


class WriterGenerator(Protocol):
    """Protocol for structured writer generation."""

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 1_024,
        feature: str = "structured_output",
    ) -> dict[str, Any]:
        """Generate a structured JSON payload."""

    def is_configured(self) -> bool:
        """Return whether live generation is configured."""


@dataclass(frozen=True)
class WriterPaperContext:
    """Writer-ready paper context assembled from metadata, summaries, and chunk evidence."""

    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    abstract: str | None
    problem: str | None
    method: str | None
    result: str | None
    relevance_to_topic: str | None
    evidence_snippets: list[str]
    metadata_warnings: list[str]


@dataclass(frozen=True)
class WriterBodyBlock:
    """Narrative block plus the papers that support it."""

    text: str
    paper_ids: list[str]


@dataclass(frozen=True)
class WriterGenerationResult:
    """Structured writer output before citation rendering."""

    body_blocks: list[WriterBodyBlock]
    warnings: list[str]


class WriterBodyBlockPayload(BaseModel):
    """Validated LLM block payload."""

    text: str = Field(min_length=1, max_length=4_000)
    paper_ids: list[str] = Field(min_length=1, max_length=20)


class WriterGenerationPayload(BaseModel):
    """Validated LLM writer payload."""

    body_blocks: list[WriterBodyBlockPayload] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=50)


class GroundedWriterAgent:
    """Generate grounded writing plans from selected papers."""

    def __init__(
        self,
        *,
        writer_generator: WriterGenerator | None = None,
        max_tokens: int | None = None,
    ) -> None:
        settings = get_settings()
        self.writer_generator = writer_generator or ClaudeStructuredOutputService(
            timeout_seconds=settings.writer_generation_timeout_seconds
        )
        self.max_tokens = max_tokens if max_tokens is not None else int(settings.external_api_timeout_seconds * 80)

    async def generate(
        self,
        *,
        paper_contexts: list[WriterPaperContext],
        instruction: str,
        output_target: str,
        citation_mode: str,
        reference_style: str,
        include_references: bool,
        max_words: int | None,
    ) -> WriterGenerationResult:
        if not paper_contexts:
            return WriterGenerationResult(body_blocks=[], warnings=["No papers were provided to the writer."])

        if not self.writer_generator.is_configured():
            return self._build_fallback_output(
                paper_contexts=paper_contexts,
                instruction=instruction,
                output_target=output_target,
                citation_mode=citation_mode,
                reference_style=reference_style,
                include_references=include_references,
                max_words=max_words,
            )

        for _attempt in range(2):
            try:
                payload = await self.writer_generator.generate_json(
                    system_prompt=WRITER_SYSTEM_PROMPT,
                    user_prompt=self._build_writer_prompt(
                        paper_contexts=paper_contexts,
                        instruction=instruction,
                        output_target=output_target,
                        citation_mode=citation_mode,
                        reference_style=reference_style,
                        include_references=include_references,
                        max_words=max_words,
                    ),
                    schema=WRITER_OUTPUT_SCHEMA,
                    max_tokens=self.max_tokens,
                    feature="writer_generation",
                )
                payload = self._repair_provider_payload(
                    payload=payload,
                    paper_contexts=paper_contexts,
                    instruction=instruction,
                    citation_mode=citation_mode,
                )
                parsed_payload = WriterGenerationPayload.model_validate(payload)
                return WriterGenerationResult(
                    body_blocks=[
                        WriterBodyBlock(text=block.text.strip(), paper_ids=list(block.paper_ids))
                        for block in parsed_payload.body_blocks
                        if block.text.strip()
                    ],
                    warnings=[warning.strip() for warning in parsed_payload.warnings if warning.strip()],
                )
            except (StructuredOutputError, ValidationError):
                continue

        return self._build_fallback_output(
            paper_contexts=paper_contexts,
            instruction=instruction,
            output_target=output_target,
            citation_mode=citation_mode,
            reference_style=reference_style,
            include_references=include_references,
            max_words=max_words,
        )

    def _repair_provider_payload(
        self,
        *,
        payload: dict[str, Any],
        paper_contexts: list[WriterPaperContext],
        instruction: str,
        citation_mode: str,
    ) -> dict[str, Any]:
        if citation_mode == "bibtex_only" or self._is_reference_only_request(instruction):
            return payload

        body_blocks = payload.get("body_blocks")
        if not isinstance(body_blocks, list):
            return payload

        fallback_paper_ids = [context.paper_id for context in paper_contexts[:20]]
        allowed_paper_ids = set(fallback_paper_ids)
        repaired_blocks: list[Any] = []
        omitted_id_count = 0
        unsupported_id_count = 0

        for block in body_blocks:
            if not isinstance(block, dict):
                repaired_blocks.append(block)
                continue

            raw_paper_ids = block.get("paper_ids")
            valid_paper_ids: list[str] = []
            if isinstance(raw_paper_ids, list):
                for raw_paper_id in raw_paper_ids:
                    if (
                        isinstance(raw_paper_id, str)
                        and raw_paper_id in allowed_paper_ids
                        and raw_paper_id not in valid_paper_ids
                    ):
                        valid_paper_ids.append(raw_paper_id)
                if len(valid_paper_ids) != len(raw_paper_ids):
                    unsupported_id_count += 1

            if not valid_paper_ids and isinstance(block.get("text"), str) and block["text"].strip():
                valid_paper_ids = list(fallback_paper_ids)
                omitted_id_count += 1

            if valid_paper_ids != raw_paper_ids:
                block = {**block, "paper_ids": valid_paper_ids}
            repaired_blocks.append(block)

        if omitted_id_count == 0 and unsupported_id_count == 0:
            return payload

        repaired_payload = {**payload, "body_blocks": repaired_blocks}
        warnings = [
            str(warning).strip()
            for warning in payload.get("warnings", [])
            if str(warning).strip()
        ] if isinstance(payload.get("warnings"), list) else []
        if omitted_id_count:
            warnings.append(
                "LLM omitted paper_ids for one or more body blocks; cited all selected papers for repaired blocks."
            )
        if unsupported_id_count:
            warnings.append("LLM returned unsupported paper_ids; removed unsupported citation IDs.")
        repaired_payload["warnings"] = self._dedupe_strings(warnings)
        return repaired_payload

    def _build_writer_prompt(
        self,
        *,
        paper_contexts: list[WriterPaperContext],
        instruction: str,
        output_target: str,
        citation_mode: str,
        reference_style: str,
        include_references: bool,
        max_words: int | None,
    ) -> str:
        context_sections: list[str] = []
        for context in paper_contexts:
            evidence_lines = "\n".join(f"- {snippet}" for snippet in context.evidence_snippets) or "- None"
            metadata_warnings = "\n".join(f"- {warning}" for warning in context.metadata_warnings) or "- None"
            context_sections.append(
                "\n".join(
                    [
                        f"Paper ID: {context.paper_id}",
                        f"Title: {context.title}",
                        f"Authors: {', '.join(context.authors) if context.authors else 'Missing'}",
                        f"Year: {context.year if context.year is not None else 'Missing'}",
                        f"Abstract: {(context.abstract or 'Missing').strip()}",
                        f"Problem: {(context.problem or 'Missing').strip()}",
                        f"Method: {(context.method or 'Missing').strip()}",
                        f"Result: {(context.result or 'Missing').strip()}",
                        f"Relevance: {(context.relevance_to_topic or 'Missing').strip()}",
                        "Evidence snippets:",
                        evidence_lines,
                        "Metadata warnings:",
                        metadata_warnings,
                    ]
                )
            )

        max_words_line = f"{max_words}" if max_words is not None else "No hard limit"
        return "\n\n".join(
            [
                f"Instruction: {instruction.strip()}",
                f"Output target: {output_target}",
                f"Citation mode: {citation_mode}",
                f"Reference style: {reference_style}",
                f"Include references: {include_references}",
                f"Max words: {max_words_line}",
                "Selected paper contexts:",
                *context_sections,
            ]
        )

    def _build_fallback_output(
        self,
        *,
        paper_contexts: list[WriterPaperContext],
        instruction: str,
        output_target: str,
        citation_mode: str,
        reference_style: str,
        include_references: bool,
        max_words: int | None,
    ) -> WriterGenerationResult:
        del output_target, reference_style, include_references

        deduped_warnings = self._dedupe_strings(
            [
                *[warning for context in paper_contexts for warning in context.metadata_warnings],
            ]
        )
        if citation_mode == "bibtex_only" or self._is_reference_only_request(instruction):
            return WriterGenerationResult(body_blocks=[], warnings=deduped_warnings)

        body_blocks: list[WriterBodyBlock] = []
        if len(paper_contexts) > 1:
            overview_text = (
                "Taken together, the selected papers form a focused evidence set for the requested writing task, "
                "with overlapping emphasis on the problem setting, methodological choices, and reported outcomes."
            )
            body_blocks.append(
                WriterBodyBlock(
                    text=overview_text,
                    paper_ids=[context.paper_id for context in paper_contexts],
                )
            )

        for context in paper_contexts:
            summary_text = self._compose_summary_sentence(context)
            if summary_text:
                body_blocks.append(WriterBodyBlock(text=summary_text, paper_ids=[context.paper_id]))

        truncated_blocks = self._apply_max_word_budget(body_blocks, max_words=max_words)
        return WriterGenerationResult(body_blocks=truncated_blocks, warnings=deduped_warnings)

    def _compose_summary_sentence(self, context: WriterPaperContext) -> str:
        summary_segments: list[str] = [f"{context.title}"]

        if context.problem:
            summary_segments.append(f"addresses {self._lowercase_first(context.problem)}")
        elif context.abstract:
            abstract_sentence = self._first_sentence(context.abstract)
            summary_segments.append(f"studies {self._lowercase_first(abstract_sentence)}")
        else:
            summary_segments.append("contributes evidence relevant to the selected writing task")

        if context.method:
            summary_segments.append(f"using {self._lowercase_first(context.method)}")

        summary_text = " ".join(summary_segments).strip()
        if context.result:
            result_sentence = self._lowercase_first(context.result)
            summary_text += f". It reports that {result_sentence}"

        return summary_text.rstrip(".") + "."

    def _apply_max_word_budget(
        self,
        body_blocks: list[WriterBodyBlock],
        *,
        max_words: int | None,
    ) -> list[WriterBodyBlock]:
        if max_words is None or max_words <= 0:
            return body_blocks

        remaining_words = max_words
        truncated_blocks: list[WriterBodyBlock] = []
        for block in body_blocks:
            block_words = block.text.split()
            if not block_words:
                continue
            if remaining_words <= 0:
                break
            if len(block_words) <= remaining_words:
                truncated_blocks.append(block)
                remaining_words -= len(block_words)
                continue

            truncated_text = " ".join(block_words[:remaining_words]).rstrip(",;:")
            if truncated_text:
                truncated_blocks.append(
                    WriterBodyBlock(text=f"{truncated_text}.", paper_ids=block.paper_ids)
                )
            break

        return truncated_blocks

    def _is_reference_only_request(self, instruction: str) -> bool:
        normalized_instruction = instruction.lower()
        return bool(REFERENCE_ONLY_PATTERN.search(normalized_instruction)) and not bool(
            NARRATIVE_PATTERN.search(normalized_instruction)
        )

    def _first_sentence(self, text: str) -> str:
        sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(text) if sentence.strip()]
        if not sentences:
            return text.strip()
        return sentences[0]

    def _lowercase_first(self, text: str) -> str:
        normalized_text = text.strip()
        if not normalized_text:
            return normalized_text
        return normalized_text[0].lower() + normalized_text[1:]

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        deduped_values: list[str] = []
        seen_values: set[str] = set()
        for value in values:
            normalized_value = value.strip()
            if not normalized_value or normalized_value in seen_values:
                continue
            seen_values.add(normalized_value)
            deduped_values.append(normalized_value)
        return deduped_values
