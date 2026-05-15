"""Writer chat agent — document-level natural-language change requests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from backend.agents.writer_editor import (
    TextSpan,
    _strip_unknown_citations,
    citation_keys,
)
from backend.services.llm import (
    ChatTurn,
    StructuredOutputClient,
    StructuredOutputError,
    StructuredOutputTransportError,
)


@dataclass(frozen=True)
class SectionRef:
    id: str
    title: str
    length: int
    position: int


@dataclass(frozen=True)
class SectionContent:
    id: str
    title: str
    draft_latex: str


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    summary_for_history: str = ""


@dataclass(frozen=True)
class SectionPatch:
    section_id: str
    section_title: str
    span: TextSpan
    original_text: str
    new_text: str
    rationale: str


@dataclass(frozen=True)
class ChatTurnResponse:
    reply: str
    summary_for_history: str = ""
    patches: list[SectionPatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


CHAT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "summary_for_history": {"type": "string"},
        "patches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_id": {"type": "string"},
                    "span": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "integer", "minimum": 0},
                            "end": {"type": "integer", "minimum": 0},
                        },
                        "required": ["start", "end"],
                    },
                    "original_text": {"type": "string"},
                    "new_text": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["section_id", "span", "original_text", "new_text", "rationale"],
            },
        },
    },
    "required": ["reply", "summary_for_history", "patches"],
}


SYSTEM_PROMPT = (
    "You are a careful LaTeX editor assisting an author on an academic paper. "
    "The author talks to you through a chat box and may ask for changes that span one or "
    "more sections of the current document. "
    "Return STRICT JSON only that matches the schema described in the user prompt. "
    "Rules:\n"
    "- Each patch must include `section_id`, a `span` of {start, end} character offsets, "
    "`original_text` that is EXACTLY equal to draft_latex[start:end] for that section, "
    "`new_text`, and a short `rationale`.\n"
    "- Preserve every existing \\cite{...} command and key. Never invent citation keys.\n"
    "- If you cannot find a clean span, return zero patches and ask a clarifying question "
    "in `reply`.\n"
    "- `summary_for_history` is a <=140 char one-line recap of this turn for future context."
)


def _format_outline(outline: list[SectionRef]) -> str:
    lines = [
        f"{ref.position}. id={ref.id} title={ref.title!r} length={ref.length}"
        for ref in outline
    ]
    return "\n".join(lines) if lines else "(no sections)"


def _format_included_sections(sections: list[SectionContent]) -> str:
    if not sections:
        return "(no section content was included this turn)"
    chunks: list[str] = []
    for sec in sections:
        chunks.append(
            f"### section_id={sec.id} title={sec.title!r}\n"
            f"```latex\n{sec.draft_latex}\n```"
        )
    return "\n\n".join(chunks)


def _format_history(messages: list[ChatMessage]) -> str:
    if not messages:
        return "(no prior turns)"
    return "\n".join(f"{m.role}: {m.content}" for m in messages)


_WS_RUN_RE = re.compile(r"\s+")

# LLMs commonly normalize punctuation when transcribing source text. Map common
# Unicode variants back to their ASCII equivalents so substring search still
# matches. Every entry must be a 1:1 character substitution so positions in the
# normalized string map directly back to positions in the original.
_PUNCT_NORMALIZATION: dict[int, str] = {
    ord("‘"): "'",   # left single quote
    ord("’"): "'",   # right single quote / apostrophe
    ord("‚"): "'",   # single low-9 quote
    ord("‛"): "'",   # single high-reversed-9 quote
    ord("“"): '"',   # left double quote
    ord("”"): '"',   # right double quote
    ord("„"): '"',   # double low-9 quote
    ord("‐"): "-",   # hyphen
    ord("‑"): "-",   # non-breaking hyphen
    ord("‒"): "-",   # figure dash
    ord("–"): "-",   # en dash
    ord("—"): "-",   # em dash
    ord("―"): "-",   # horizontal bar
    ord(" "): " ",   # non-breaking space
    ord(" "): " ",   # en space
    ord(" "): " ",   # em space
    ord(" "): " ",   # thin space
    ord("​"): "",    # zero-width space — note: not 1:1, handled below
    ord("…"): "...",  # horizontal ellipsis — not 1:1, handled below
}


def _normalize_for_match(s: str) -> str:
    """1:1 character substitutions for Unicode punctuation variants.

    Skips multi-char expansions (ellipsis, zero-width space) — those change
    string length and would break the position-preservation contract.
    """
    safe_map = {
        k: v
        for k, v in _PUNCT_NORMALIZATION.items()
        if len(v) == 1
    }
    return s.translate(safe_map)


def _locate_span(draft: str, needle: str, *, hint_start: int) -> tuple[int, int] | None:
    """Find `needle` in `draft`, tolerant of LLM whitespace, offset drift, and
    common Unicode punctuation substitutions.

    Why: LLMs cannot count characters reliably, so the `span` they return rarely
    matches `draft[start:end]` exactly. They also normalize quotes, dashes, and
    spaces when transcribing. The `original_text` field is much more reliable
    than `span` — anchor on it via tolerant substring search, then derive the
    true offsets in the original draft.
    """
    if not needle:
        return None

    # Exact match first.
    occurrences: list[int] = []
    cursor = 0
    while True:
        idx = draft.find(needle, cursor)
        if idx == -1:
            break
        occurrences.append(idx)
        cursor = idx + 1
    if occurrences:
        if hint_start >= 0:
            best = min(occurrences, key=lambda i: abs(i - hint_start))
        else:
            best = occurrences[0]
        return best, best + len(needle)

    # Punctuation-normalized match: replace Unicode quote/dash/space variants
    # in both strings, search there, map positions back (1:1, so positions are
    # preserved).
    norm_draft = _normalize_for_match(draft)
    norm_needle = _normalize_for_match(needle)
    if len(norm_draft) == len(draft) and len(norm_needle) == len(needle):
        norm_occurrences: list[int] = []
        cursor = 0
        while True:
            idx = norm_draft.find(norm_needle, cursor)
            if idx == -1:
                break
            norm_occurrences.append(idx)
            cursor = idx + 1
        if norm_occurrences:
            if hint_start >= 0:
                best = min(norm_occurrences, key=lambda i: abs(i - hint_start))
            else:
                best = norm_occurrences[0]
            return best, best + len(needle)

    # Whitespace-tolerant regex on normalized strings.
    trimmed = norm_needle.strip()
    if not trimmed:
        return None
    pattern_text = _WS_RUN_RE.sub(r"\\s+", re.escape(trimmed))
    match = None
    if hint_start >= 0:
        for m in re.finditer(pattern_text, norm_draft):
            if match is None or abs(m.start() - hint_start) < abs(match.start() - hint_start):
                match = m
    else:
        match = re.search(pattern_text, norm_draft)
    if match is None:
        return None
    return match.start(), match.end()


def _verify_patch(
    raw: dict[str, Any],
    sections_by_id: dict[str, SectionContent],
    allowed_keys: set[str],
) -> tuple[SectionPatch | None, str | None]:
    section_id = str(raw.get("section_id", "")).strip()
    section = sections_by_id.get(section_id)
    if section is None:
        return None, f"Dropped patch targeting unknown section {section_id!r}."

    span_data = raw.get("span") or {}
    try:
        hint_start = int(span_data.get("start", -1))
    except (TypeError, ValueError):
        hint_start = -1
    draft = section.draft_latex or ""
    original_text = str(raw.get("original_text", ""))

    # Insertion: empty original_text means "insert at hint_start".
    if original_text == "":
        if 0 <= hint_start <= len(draft):
            start, end = hint_start, hint_start
        else:
            return None, (
                f"Dropped patch in {section.title!r}: insertion offset out of bounds."
            )
    else:
        located = _locate_span(draft, original_text, hint_start=hint_start)
        if located is None:
            return None, (
                f"Dropped patch in {section.title!r}: original_text not found in the current draft."
            )
        start, end = located

    raw_new_text = str(raw.get("new_text", ""))
    introduced_raw = citation_keys(raw_new_text) - allowed_keys
    if introduced_raw:
        return None, (
            f"Dropped patch in {section.title!r}: introduced unknown citation key(s) "
            f"{sorted(introduced_raw)!r}."
        )
    new_text = _strip_unknown_citations(raw_new_text, allowed_keys)

    rationale = str(raw.get("rationale", "")).strip() or "Proposed change."
    return (
        SectionPatch(
            section_id=section.id,
            section_title=section.title,
            span=TextSpan(start=start, end=end),
            original_text=draft[start:end],
            new_text=new_text,
            rationale=rationale,
        ),
        None,
    )


class WriterChatAgent:
    """Run one chat turn for a writer document."""

    def __init__(self, *, client: StructuredOutputClient | None = None) -> None:
        if client is None:
            from backend.config import get_settings
            from backend.services.llm import get_structured_client

            settings = get_settings()
            client = get_structured_client(
                settings.writer_chat_provider,
                timeout_seconds=settings.writer_chat_request_timeout_seconds,
            )
        self.client = client

    async def respond(
        self,
        *,
        document_outline: list[SectionRef],
        included_sections: list[SectionContent],
        known_citation_keys: set[str],
        chat_history: list[ChatMessage],
        user_message: str,
        history_summary: str = "",
        max_tokens: int = 2_048,
    ) -> ChatTurnResponse:
        if not self.client.is_configured():
            return ChatTurnResponse(
                reply="Chat is offline; set XIAOMI_MIMO_API_KEY to enable.",
                summary_for_history="",
                patches=[],
            )

        sections_by_id = {sec.id: sec for sec in included_sections}
        allowed = set(known_citation_keys)
        for sec in included_sections:
            allowed.update(citation_keys(sec.draft_latex or ""))

        user_prompt = self._build_user_prompt(
            outline=document_outline,
            included_sections=included_sections,
            history=chat_history,
            history_summary=history_summary,
            user_message=user_message,
            strict=False,
        )
        try:
            payload, parse_error = await self._call(user_prompt, max_tokens=max_tokens)
        except StructuredOutputTransportError as transport_err:
            return ChatTurnResponse(
                reply=(
                    "The model took too long to respond. Try asking for changes in fewer "
                    "sections at a time, or try again in a moment."
                ),
                summary_for_history="",
                patches=[],
                warnings=[str(transport_err)],
            )
        warnings: list[str] = []
        if parse_error is not None:
            retry_prompt = self._build_user_prompt(
                outline=document_outline,
                included_sections=included_sections,
                history=chat_history,
                history_summary=history_summary,
                user_message=user_message,
                strict=True,
            )
            try:
                payload, parse_error = await self._call(retry_prompt, max_tokens=max_tokens)
            except StructuredOutputTransportError as transport_err:
                return ChatTurnResponse(
                    reply=(
                        "The model took too long to respond on retry. Try a smaller "
                        "request."
                    ),
                    summary_for_history="",
                    patches=[],
                    warnings=[str(transport_err)],
                )
            if parse_error is not None:
                return ChatTurnResponse(
                    reply=(
                        "I had trouble producing a valid response. Could you rephrase your request "
                        "or narrow it to one section?"
                    ),
                    summary_for_history="",
                    patches=[],
                    warnings=[parse_error],
                )

        reply = str(payload.get("reply", "")).strip()
        summary = str(payload.get("summary_for_history", "")).strip()[:280]
        raw_patches = payload.get("patches") or []
        if not isinstance(raw_patches, list):
            raw_patches = []

        verified: list[SectionPatch] = []
        for raw in raw_patches:
            if not isinstance(raw, dict):
                warnings.append("Dropped non-object patch entry.")
                continue
            patch, error = _verify_patch(raw, sections_by_id, allowed)
            if patch is None and error is not None:
                warnings.append(error)
                continue
            if patch is not None:
                verified.append(patch)

        if warnings:
            note = " " + " ".join(warnings)
            reply = (reply + note).strip()

        if not reply:
            reply = (
                "Here is what I came up with."
                if verified
                else "I could not find a clean change to propose."
            )

        return ChatTurnResponse(
            reply=reply,
            summary_for_history=summary,
            patches=verified,
            warnings=warnings,
        )

    def _build_user_prompt(
        self,
        *,
        outline: list[SectionRef],
        included_sections: list[SectionContent],
        history: list[ChatMessage],
        history_summary: str,
        user_message: str,
        strict: bool,
    ) -> str:
        retry_hint = (
            "\n\nIMPORTANT: a previous attempt returned malformed JSON. "
            "Return STRICT JSON only — no markdown, no commentary outside the JSON object."
            if strict
            else ""
        )
        return (
            "### Document outline\n"
            f"{_format_outline(outline)}\n\n"
            "### Section contents available for editing\n"
            f"{_format_included_sections(included_sections)}\n\n"
            "### Conversation summary (older turns)\n"
            f"{history_summary or '(none)'}\n\n"
            "### Recent conversation\n"
            f"{_format_history(history)}\n\n"
            "### New user message\n"
            f"{user_message}\n\n"
            "### Output schema\n"
            f"{json.dumps(CHAT_RESPONSE_SCHEMA)}"
            f"{retry_hint}"
        )

    async def _call(
        self, user_prompt: str, *, max_tokens: int
    ) -> tuple[dict[str, Any], str | None]:
        try:
            payload = await self.client.generate_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=CHAT_RESPONSE_SCHEMA,
                max_tokens=max_tokens,
                feature="writer_chat_turn",
                temperature=0.2,
            )
        except StructuredOutputTransportError:
            # Transport failures bubble up — a stricter prompt or chat-fallback
            # cannot help here, and retrying just doubles the wait.
            raise
        except StructuredOutputError as error:
            try:
                completion = await self.client.generate_chat(
                    messages=[
                        ChatTurn(role="system", content=SYSTEM_PROMPT),
                        ChatTurn(role="user", content=user_prompt),
                    ],
                    max_tokens=max_tokens,
                    temperature=0.2,
                    feature="writer_chat_turn",
                )
            except StructuredOutputTransportError:
                raise
            except StructuredOutputError:
                return {}, str(error)
            try:
                parsed = json.loads(completion.content)
            except json.JSONDecodeError as parse_err:
                return {}, f"Could not parse chat completion as JSON: {parse_err}"
            if not isinstance(parsed, dict):
                return {}, "Chat completion JSON was not an object."
            return parsed, None
        return payload, None
