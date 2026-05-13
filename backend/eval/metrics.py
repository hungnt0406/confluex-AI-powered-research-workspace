"""Code-based evaluation metrics for literature-review agents and grounded chat.

All functions are pure and safe to run in CI without API keys. Regexes for paper-chat
leak detection are kept aligned with ``backend.services.paper_conversations``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from backend.services.deep_search import count_report_claim_sentences, verify_report_claims

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Aligned with backend.services.paper_conversations (chunk / score leakage).
_CHUNK_LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bChunk\s+\d+", re.IGNORECASE),
    re.compile(r"\[\s*Chunk\s+\d+\s*\]", re.IGNORECASE),
    re.compile(r"\bscore\s*[=:]\s*[0-9.]+", re.IGNORECASE),
    re.compile(r",\s*score\s*=\s*[0-9.]+", re.IGNORECASE),
)

_PAGE_MENTION_PATTERN = re.compile(
    r"\b(?:page|pages)\s+[0-9]+(?:\s*[-–]\s*[0-9]+)?\b",
    re.IGNORECASE,
)

_SUMMARY_TEXT_FIELDS = ("problem", "method", "result", "relevance_to_topic")


class _HasSeverity(Protocol):
    severity: str


def search_golden_hit(
    *,
    candidate_titles: Iterable[str],
    must_include_titles: Iterable[str],
) -> bool:
    """Return True if any golden title appears in the candidate set (case-insensitive)."""

    normalized = {title.strip().lower() for title in candidate_titles if title.strip()}
    return any(must.strip().lower() in normalized for must in must_include_titles if must.strip())


def mean_search_recall(hits: Sequence[bool]) -> float:
    """Fraction of golden cases that hit (same semantics as recall@k per topic)."""

    if not hits:
        return 0.0
    return sum(1 for hit in hits if hit) / len(hits)


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class ReaderSummaryMetrics:
    """Aggregate stats for ReaderAgent structured summaries."""

    n_records: int
    success_rate: float
    mean_field_coverage: float


def reader_summary_metrics(records: Sequence[Mapping[str, Any]]) -> ReaderSummaryMetrics:
    """Measure Reader structured-summary success and per-record field completeness."""

    if not records:
        return ReaderSummaryMetrics(n_records=0, success_rate=0.0, mean_field_coverage=0.0)

    successes = 0
    coverages: list[float] = []
    for record in records:
        if not record.get("has_error", False):
            successes += 1
        present = sum(1 for key in _SUMMARY_TEXT_FIELDS if _nonempty_str(record.get(key)))
        coverages.append(present / len(_SUMMARY_TEXT_FIELDS))

    return ReaderSummaryMetrics(
        n_records=len(records),
        success_rate=successes / len(records),
        mean_field_coverage=sum(coverages) / len(coverages),
    )


@dataclass(frozen=True)
class DeepSearchReportMetrics:
    """Citation hygiene signals from ``verify_report_claims``."""

    n_claim_sentences: int
    n_warnings: int
    citation_warning_rate: float


def aggregate_deep_search_report_metrics(
    report_body: str,
    source_summaries: list[dict[str, Any]],
) -> DeepSearchReportMetrics:
    """Count Deep Search verifier warnings per claim-like sentence."""

    flags = verify_report_claims(report_body, source_summaries)
    n_warnings = len(flags)
    n_claims = count_report_claim_sentences(report_body)
    rate = n_warnings / n_claims if n_claims else 0.0
    return DeepSearchReportMetrics(
        n_claim_sentences=n_claims,
        n_warnings=n_warnings,
        citation_warning_rate=rate,
    )


@dataclass(frozen=True)
class PaperChatAnswerMetrics:
    """Grounding and format checks for paper-scoped chat answers."""

    has_answer_heading: bool
    has_evidence_or_limits_heading: bool
    page_mention_count: int
    chunk_or_score_leak: bool
    format_score: float


def paper_chat_answer_metrics(answer: str) -> PaperChatAnswerMetrics:
    """Score markdown structure and detect internal retrieval label leakage."""

    text = answer.strip()
    lower = text.lower()
    has_answer = "## answer" in lower
    has_evidence = "## evidence" in lower or "## metadata" in lower
    has_limits = "## limits" in lower
    page_mentions = len(_PAGE_MENTION_PATTERN.findall(text))
    leak = any(pattern.search(text) for pattern in _CHUNK_LEAK_PATTERNS)

    format_parts = [
        has_answer,
        has_evidence or has_limits,
        has_limits,
    ]
    format_score = sum(1 for part in format_parts if part) / len(format_parts)

    return PaperChatAnswerMetrics(
        has_answer_heading=has_answer,
        has_evidence_or_limits_heading=has_evidence or has_limits,
        page_mention_count=page_mentions,
        chunk_or_score_leak=leak,
        format_score=format_score,
    )


def _token_set(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_PATTERN.finditer(text)}


def token_jaccard(answer: str, reference: str) -> float:
    """Lexical overlap between two strings (useful as a cheap grounding proxy)."""

    a, b = _token_set(answer), _token_set(reference)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def paper_chat_grounding_support(answer: str, evidence_texts: Sequence[str]) -> float:
    """Max Jaccard overlap between the answer and any evidence snippet (0..1)."""

    if not evidence_texts:
        return 0.0
    return max(token_jaccard(answer, snippet) for snippet in evidence_texts if snippet.strip())


def writer_qa_severity_counts(flags: Iterable[_HasSeverity]) -> dict[str, int]:
    """Tally Writer QA issues by severity (``error`` / ``warning`` / other)."""

    counts: dict[str, int] = {}
    for flag in flags:
        severity = getattr(flag, "severity", "unknown")
        if not isinstance(severity, str):
            severity = "unknown"
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def writer_qa_health_score(flags: Sequence[_HasSeverity]) -> float:
    """Map QA flags to [0, 1]; 1.0 means no errors and no warnings."""

    counts = writer_qa_severity_counts(flags)
    errors = counts.get("error", 0)
    warnings = counts.get("warning", 0)
    if errors:
        return 0.0
    if warnings == 0:
        return 1.0
    return max(0.0, 1.0 - min(1.0, 0.15 * warnings))
