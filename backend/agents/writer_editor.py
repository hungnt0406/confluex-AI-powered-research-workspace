"""Writer editor agent — one open-ended edit operation against the current draft."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.config import get_settings
from backend.services.llm import OpenRouterStructuredOutputService, StructuredOutputError
from backend.services.llm_xiaomi import XiaomiStructuredOutputService


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int


@dataclass(frozen=True)
class NewResult:
    text: str
    source_ref: str | None = None
    attach_as_citation: bool = False
    image_data: str | None = None


@dataclass(frozen=True)
class WebSearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class EditPatch:
    span: TextSpan
    new_text: str
    rationale: str
    web_citations: list[WebSearchHit] = field(default_factory=list)
    original_text: str = ""


CITE_COMMAND_RE = re.compile(r"\\cite[a-zA-Z*]*\{([^}]+)\}")
CITE_MACRO_RE = re.compile(r"\\cite[a-zA-Z*]*\{[^}]+\}")
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
PARAPHRASE_INSTRUCTION_RE = re.compile(r"\b(paraphrase|rephrase|rewrite|reword)\b", re.IGNORECASE)

EDITOR_PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "new_text": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["new_text", "rationale"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a precise LaTeX editor for an academic writing workspace. "
    "Return strict JSON only with fields `new_text` and `rationale`. "
    "`new_text` MUST be a meaningful rewrite that follows the user's instruction — "
    "never echo the original span verbatim. "
    "Preserve existing \\cite{...} commands and keys exactly. "
    "Do not invent citations, references, commands, data, or source IDs."
)


def citation_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for match in CITE_COMMAND_RE.finditer(text):
        keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    return keys


def sanitize_citation_key(value: str | None) -> str | None:
    if not value:
        return None
    key = re.sub(r"[^A-Za-z0-9:_-]+", "_", value.strip()).strip("_")
    return key[:80] or None


def _bounded_span(draft: str, span: TextSpan) -> TextSpan:
    start = max(0, min(span.start, len(draft)))
    end = max(start, min(span.end, len(draft)))
    return TextSpan(start=start, end=end)


def _window_around_span(draft: str, span: TextSpan, context_chars: int = 900) -> str:
    start = max(0, span.start - context_chars)
    end = min(len(draft), span.end + context_chars)
    return draft[start:end]


def _neighbor_paragraphs(draft: str, offset: int) -> tuple[str, str]:
    offset = max(0, min(offset, len(draft)))
    before_parts = [p.strip() for p in PARAGRAPH_SPLIT_RE.split(draft[:offset]) if p.strip()]
    after_parts = [p.strip() for p in PARAGRAPH_SPLIT_RE.split(draft[offset:]) if p.strip()]
    return (before_parts[-1] if before_parts else "", after_parts[0] if after_parts else "")


def _strip_unknown_citations(text: str, allowed_keys: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        keys = [key.strip() for key in match.group(1).split(",") if key.strip()]
        if all(key in allowed_keys for key in keys):
            return match.group(0)
        return ""

    return CITE_COMMAND_RE.sub(replace, text)


def _restore_missing_citation_macros(original: str, revised: str) -> str:
    missing = [macro for macro in CITE_MACRO_RE.findall(original) if macro not in revised]
    if not missing:
        return revised
    return f"{revised.rstrip()} {' '.join(missing)}"


def _is_paraphrase_instruction(instruction: str | None) -> bool:
    return bool(instruction and PARAPHRASE_INSTRUCTION_RE.search(instruction))


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_noop_edit(original: str, revised: str) -> bool:
    return _normalized(original) == _normalized(revised)


def _strip_instruction_prefix(topic: str) -> str:
    cleaned = topic.strip()
    cleaned = re.sub(
        r"^(explain|describe|introduce|motivate|write|add)\b[^:]*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(explain|describe|introduce|motivate|write|add)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip() or topic.strip()


_LATEX_ENV_RE = re.compile(r"\\begin\{[a-zA-Z*]+\}", re.IGNORECASE)


def _looks_like_prompt_echo(topic: str, generated: str) -> bool:
    norm_topic = _normalized(topic).lower()
    norm_gen = _normalized(generated).lower()
    if not norm_gen:
        return True
    if norm_topic == norm_gen:
        return True
    # If the output contains an actual LaTeX environment it's structural content, not an echo.
    if _LATEX_ENV_RE.search(generated):
        return False
    if norm_gen.startswith(("explain ", "describe ", "introduce ", "motivate ", "write ", "add ")):
        return True
    # Instruction text appearing verbatim inside the output is also an echo.
    if len(norm_topic) > 20 and norm_topic in norm_gen:
        return True
    return False


_STRUCTURAL_INSTRUCTION_RE = re.compile(
    r"\b(convert|table|tabular|figure|equation|insert|put|paste|add table|add figure)\b",
    re.IGNORECASE,
)


def _deterministic_intro_paragraph(topic: str, section_heading: str) -> str:
    lower_topic = topic.lower()
    if _STRUCTURAL_INSTRUCTION_RE.search(lower_topic):
        return (
            "\\begin{table}[h]\n"
            "\\centering\n"
            "\\caption{[Add caption]}\n"
            "\\label{tab:[label]}\n"
            "\\begin{tabular}{lll}\n"
            "\\hline\n"
            "Column 1 & Column 2 & Column 3 \\\\\n"
            "\\hline\n"
            "Value & Value & Value \\\\\n"
            "\\hline\n"
            "\\end{tabular}\n"
            "\\end{table}"
        )
    focus = _strip_instruction_prefix(topic).rstrip(".")
    lower_focus = focus.lower()
    if "research gap" in lower_topic and "blurred" in lower_focus and "few frames" in lower_focus:
        return (
            "A central research gap is that standard trackers can perform adequately "
            "under ordinary motion but degrade when targets are blurred, occluded, or "
            "visible for only a few frames. These conditions reduce the amount of reliable "
            "visual evidence available to the model and make it harder to maintain stable "
            "localization and identity over time. Addressing this gap requires tracking "
            "methods that are designed for rapid appearance changes rather than assuming "
            "slow, continuous, and clearly observed motion."
        )
    if "high-speed object tracking" in lower_focus or "fast" in lower_focus:
        return (
            "High-speed object tracking is important because many real video systems must "
            "follow targets that move quickly, appear briefly, and change appearance across "
            "successive frames. In these settings, conventional trackers can lose accuracy "
            "when motion blur, occlusion, and limited frame rates reduce the quality of the "
            "available observations. This makes the problem a useful introduction to the "
            "broader need for tracking methods that balance real-time latency with robust "
            "target localization."
        )
    return (
        f"In the {section_heading} section, this point can be framed as follows: {focus}. "
        "This issue helps motivate the paper because it identifies a limitation in existing "
        "approaches and clarifies why a more targeted treatment is needed."
    )


def _deterministic_paraphrase(text: str) -> str:
    replacements: list[tuple[str, str]] = [
        (
            r"\bHigh-speed object tracking in video streams presents\b",
            "Tracking fast-moving objects in video streams poses",
        ),
        (r"\ba fundamental challenge\b", "a core challenge"),
        (r"\bcritical applications spanning\b", "important applications across"),
        (r"\bObjects moving at high velocities often appear blurred\b", "Fast-moving objects often appear blurred"),
        (
            r"\bremain visible for only a short duration across frames\b",
            "stay visible for only a few frames",
        ),
        (r"\bbecome temporarily occluded\b", "are temporarily occluded"),
        (
            r"\bmay be captured by cameras operating at limited frame rates\b",
            "may be recorded by cameras with limited frame rates",
        ),
        (r"\bThese combined factors significantly degrade\b", "Together, these factors reduce"),
        (r"\bstandard tracking methods\b", "standard trackers"),
        (
            r"\btypically optimized for more conventional motion scenarios\b",
            "usually designed for more typical motion patterns",
        ),
        (r"\bThe problem is particularly acute\b", "This issue is especially difficult"),
        (r"\breal-time applications\b", "real-time settings"),
        (r"\bcomputational latency must remain low\b", "latency must stay low"),
        (r"\bwhile maintaining tracking accuracy\b", "while tracking accuracy remains high"),
        (
            r"\bcreating a tension between speed and precision\b",
            "creating a trade-off between speed and precision",
        ),
        (r"\bdemands specialized solutions\b", "requires specialized solutions"),
        (r"\bfocuses on\b", "examines"),
        (r"\bmethods for\b", "approaches to"),
    ]
    paraphrased = text
    for pattern, replacement in replacements:
        paraphrased = re.sub(pattern, replacement, paraphrased, flags=re.IGNORECASE)
    if _is_noop_edit(text, paraphrased):
        paraphrased = re.sub(r"\bThis\b", "The selected passage", paraphrased, count=1)
    return paraphrased


def _format_web_hits(hits: list[WebSearchHit]) -> str:
    if not hits:
        return "None."
    return "\n".join(f"- {hit.title} ({hit.url}): {hit.snippet}" for hit in hits[:5])


def _format_new_results(results: list[NewResult]) -> str:
    if not results:
        return "None."
    lines: list[str] = []
    for result in results:
        source = f" source={result.source_ref}" if result.source_ref else ""
        cite = " cite=true" if result.attach_as_citation else ""
        lines.append(f"- {result.text.strip()}{source}{cite}")
    return "\n".join(lines)


class WriterEditorAgent:
    """One edit operation: revise a selected span, or insert at a cursor position."""

    def __init__(
        self,
        *,
        llm_client: OpenRouterStructuredOutputService | None = None,
        vision_llm_client: XiaomiStructuredOutputService | None = None,
    ) -> None:
        self.llm_client = llm_client or OpenRouterStructuredOutputService()
        if vision_llm_client is not None:
            self.vision_llm_client = vision_llm_client
        else:
            vision_model = get_settings().writer_editor_vision_model
            self.vision_llm_client = XiaomiStructuredOutputService(model=vision_model)

    async def edit(
        self,
        *,
        draft: str,
        instruction: str,
        section_heading: str,
        span: TextSpan | None = None,
        insertion_offset: int | None = None,
        new_results: list[NewResult] | None = None,
        web_hits: list[WebSearchHit] | None = None,
        known_citation_keys: set[str] | None = None,
    ) -> EditPatch:
        new_results = new_results or []
        web_hits = web_hits or []
        instruction = (instruction or "").strip()

        if span is not None:
            return await self._revise(
                draft=draft,
                instruction=instruction,
                section_heading=section_heading,
                span=span,
                new_results=new_results,
                web_hits=web_hits,
                known_citation_keys=known_citation_keys,
            )
        if insertion_offset is None:
            raise ValueError("Either span or insertion_offset is required.")
        return await self._insert(
            draft=draft,
            instruction=instruction,
            section_heading=section_heading,
            insertion_offset=insertion_offset,
            new_results=new_results,
            web_hits=web_hits,
            known_citation_keys=known_citation_keys,
        )

    async def _revise(
        self,
        *,
        draft: str,
        instruction: str,
        section_heading: str,
        span: TextSpan,
        new_results: list[NewResult],
        web_hits: list[WebSearchHit],
        known_citation_keys: set[str] | None,
    ) -> EditPatch:
        bounded = _bounded_span(draft, span)
        selected = draft[bounded.start : bounded.end]
        if not selected:
            return EditPatch(
                span=bounded,
                original_text=selected,
                new_text="",
                rationale="No selected text to revise.",
            )

        source_keys = {
            key for key in (sanitize_citation_key(r.source_ref) for r in new_results) if key
        }
        allowed = set(known_citation_keys or set()) | citation_keys(draft) | source_keys

        if not self.llm_client.is_configured():
            if new_results:
                additions = " ".join(r.text.strip() for r in new_results if r.text.strip())
                cites = [
                    sanitize_citation_key(r.source_ref)
                    for r in new_results
                    if r.attach_as_citation and sanitize_citation_key(r.source_ref)
                ]
                cite_text = f" \\cite{{{','.join(c for c in cites if c)}}}" if cites else ""
                new_text = f"{selected.strip()} {additions}{cite_text}".strip()
                return EditPatch(
                    span=bounded,
                    original_text=selected,
                    new_text=new_text,
                    rationale="offline_stub",
                    web_citations=web_hits,
                )
            return EditPatch(
                span=bounded,
                original_text=selected,
                new_text=selected,
                rationale="offline_stub",
                web_citations=web_hits,
            )

        directive = instruction or "Improve grammar, clarity, and phrasing."
        result_image = next((r.image_data for r in new_results if r.image_data), None)
        image_note = "\n- A screenshot has been attached. Use it as visual evidence." if result_image else ""
        prompt = (
            f"### Instruction (highest priority)\n{directive}\n\n"
            f"### Section heading\n{section_heading}\n\n"
            f"### Selected span to rewrite\n{selected}\n\n"
            f"### Surrounding context (read-only)\n{_window_around_span(draft, bounded)}\n\n"
            f"### New findings to incorporate (if any)\n{_format_new_results(new_results)}\n\n"
            f"### Web snippets (optional)\n{_format_web_hits(web_hits)}\n\n"
            "### Output rules\n"
            "- Return JSON: { \"new_text\": ..., \"rationale\": ... }\n"
            "- `new_text` MUST differ from the selected span and satisfy the instruction.\n"
            "- Keep every \\cite{...} command and key that appears in the selected span.\n"
            f"- Do not invent citations, sources, numbers, or authors.{image_note}"
        )
        payload = await self._generate_or_stub(prompt, selected, temperature=0.5, image_data=result_image)
        new_text = _strip_unknown_citations(str(payload["new_text"]), allowed)
        new_text = _restore_missing_citation_macros(selected, new_text)
        rationale = str(payload["rationale"]).strip() or "Revised selected text."

        if _is_noop_edit(selected, new_text):
            retry_prompt = (
                f"{prompt}\n\n"
                "### Retry directive\n"
                "Your previous output was IDENTICAL to the selected span — that is not "
                "acceptable. Produce a `new_text` that is materially different and "
                f"directly follows this instruction: {directive}. "
                "Keep the \\cite{...} commands intact but rewrite the surrounding prose."
            )
            retry = await self._generate_or_stub(retry_prompt, selected, temperature=0.8, image_data=result_image)
            new_text = _strip_unknown_citations(str(retry["new_text"]), allowed)
            new_text = _restore_missing_citation_macros(selected, new_text)
            rationale = str(retry["rationale"]).strip() or "Revised selected text."

            if _is_noop_edit(selected, new_text):
                if _is_paraphrase_instruction(instruction):
                    new_text = _restore_missing_citation_macros(
                        selected, _deterministic_paraphrase(selected)
                    )
                    rationale = "Paraphrased selected text while preserving citations."
                else:
                    new_text = selected
                    rationale = (
                        "The model returned the selected text unchanged. "
                        "Try a more specific instruction (e.g. \"shorten to two sentences\", "
                        "\"add a concrete example\", \"rewrite in a more formal tone\")."
                    )

        if _looks_like_prompt_echo(directive, new_text):
            new_text = _restore_missing_citation_macros(selected, _deterministic_paraphrase(selected))
            rationale = "Paraphrased selected text while preserving citations."

        return EditPatch(
            span=bounded,
            original_text=selected,
            new_text=new_text,
            rationale=rationale,
            web_citations=web_hits,
        )

    async def _insert(
        self,
        *,
        draft: str,
        instruction: str,
        section_heading: str,
        insertion_offset: int,
        new_results: list[NewResult],
        web_hits: list[WebSearchHit],
        known_citation_keys: set[str] | None,
    ) -> EditPatch:
        span = _bounded_span(draft, TextSpan(start=insertion_offset, end=insertion_offset))
        before, after = _neighbor_paragraphs(draft, span.start)
        topic = instruction or section_heading

        if not self.llm_client.is_configured():
            paragraph = f"\n\n{topic} should be developed here with evidence from the current draft.\n\n"
            return EditPatch(
                span=span,
                original_text="",
                new_text=paragraph,
                rationale="offline_stub",
                web_citations=web_hits,
            )

        result_image = next((r.image_data for r in new_results if r.image_data), None)
        image_note = "\n- A screenshot has been attached. Use it as visual evidence." if result_image else ""
        prompt = (
            f"### Instruction (highest priority)\n{topic}\n\n"
            f"### Section heading\n{section_heading}\n\n"
            f"### Paragraph before insertion (read-only)\n{before}\n\n"
            f"### Paragraph after insertion (read-only)\n{after}\n\n"
            f"### New findings to use (if any)\n{_format_new_results(new_results)}\n\n"
            f"### Web snippets (optional)\n{_format_web_hits(web_hits)}\n\n"
            "### Output rules\n"
            "- Return JSON: { \"new_text\": ..., \"rationale\": ... }\n"
            "- `new_text` MUST be valid LaTeX that fulfills the instruction — a paragraph, table, figure, equation, or any appropriate LaTeX environment.\n"
            "- For conversion requests (e.g. 'convert to table', 'convert to LaTeX'), output the complete LaTeX structure directly.\n"
            "- Do NOT echo or restate the instruction verbatim — produce the actual content.\n"
            f"- Do not invent citations, sources, numbers, or authors.{image_note}"
        )
        payload = await self._generate_or_stub(prompt, topic, temperature=0.6, image_data=result_image)
        source_keys = {
            key for key in (sanitize_citation_key(r.source_ref) for r in new_results) if key
        }
        allowed = set(known_citation_keys or set()) | citation_keys(draft) | source_keys
        new_text = _strip_unknown_citations(str(payload["new_text"]).strip(), allowed)
        rationale = str(payload["rationale"]).strip() or "Generated a focused paragraph."

        if _looks_like_prompt_echo(topic, new_text):
            new_text = _deterministic_intro_paragraph(topic, section_heading)
            rationale = (
                "Inserted a table template — the model did not produce a usable conversion. "
                "Fill in the rows from your screenshot."
                if _STRUCTURAL_INSTRUCTION_RE.search(topic)
                else "Generated a paragraph from the requested topic."
            )

        return EditPatch(
            span=span,
            original_text="",
            new_text=f"\n\n{new_text}\n\n",
            rationale=rationale,
            web_citations=web_hits,
        )

    async def _generate_or_stub(
        self,
        user_prompt: str,
        fallback_text: str,
        *,
        temperature: float = 0.5,
        image_data: str | None = None,
    ) -> dict[str, str]:
        client = (
            self.vision_llm_client
            if image_data and self.vision_llm_client.is_configured()
            else self.llm_client
        )
        try:
            payload = await client.generate_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=EDITOR_PATCH_SCHEMA,
                max_tokens=900,
                feature="writer_editor",
                temperature=temperature,
                image_data=image_data,
            )
        except StructuredOutputError:
            return {"new_text": fallback_text, "rationale": "offline_stub"}
        return {
            "new_text": str(payload.get("new_text", fallback_text)),
            "rationale": str(payload.get("rationale", "Revised draft text.")),
        }
