#!/usr/bin/env python3
"""Print sample outputs for all ``backend.eval`` metrics (no DB, no API keys).

These metrics score structured data or text — they are not an LLM endpoint.
Run from the repository root:

    uv run python scripts/run_eval_metric_samples.py
"""

from __future__ import annotations

import json
from dataclasses import asdict

from backend.agents.qa import WriterQAAgent, WriterQaFlag
from backend.db.models import Paper
from backend.eval.metrics import (
    aggregate_deep_search_report_metrics,
    mean_search_recall,
    paper_chat_answer_metrics,
    paper_chat_grounding_support,
    reader_summary_metrics,
    search_golden_hit,
    token_jaccard,
    writer_qa_health_score,
    writer_qa_severity_counts,
)


def _print(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(json.dumps(asdict(payload), indent=2, default=str))  # type: ignore[arg-type]


def main() -> None:
    print("Sample outputs for backend.eval metrics (deterministic; no live models).")

    candidates = ["Attention Is All You Need", "Some Other Paper"]
    golden = ["attention is all you need"]
    hit = search_golden_hit(candidate_titles=candidates, must_include_titles=golden)
    recall = mean_search_recall([hit, True, False])
    _print(
        "Searcher: search_golden_hit + mean_search_recall",
        {"search_golden_hit": hit, "mean_search_recall_over_3_fake_topics": recall},
    )

    reader_records = [
        {
            "paper_id": "a",
            "problem": "p",
            "method": "m",
            "result": "r",
            "relevance_to_topic": "rel",
            "has_error": False,
        },
        {
            "paper_id": "b",
            "problem": "",
            "method": "m",
            "result": "r",
            "relevance_to_topic": "rel",
            "has_error": True,
        },
    ]
    _print("Reader: reader_summary_metrics", reader_summary_metrics(reader_records))

    report = (
        "Transformers improve MT [Vaswani et al.]"
        "(https://arxiv.org/abs/1706.03762). "
        "Models grow every year without a citation in this sentence."
    )
    sources = [
        {"url": "https://arxiv.org/abs/1706.03762", "source_type": "paper"},
        {"url": "https://example.com/web", "source_type": "web"},
    ]
    _print(
        "Deep Search: aggregate_deep_search_report_metrics",
        aggregate_deep_search_report_metrics(report, sources),
    )

    good_chat = (
        "## Answer\nThe model uses self-attention.\n\n"
        "## Evidence\nSee discussion on (pages 3-4).\n\n"
        "## Limits\nOffline sample.\n"
    )
    bad_chat = "## Answer\nChunk 3, pages 1-2 describe it.\n\n## Limits\nx\n"
    _print("Paper chat: paper_chat_answer_metrics (good)", paper_chat_answer_metrics(good_chat))
    _print("Paper chat: paper_chat_answer_metrics (leak)", paper_chat_answer_metrics(bad_chat))

    answer = "the method relies on attention mechanisms"
    evidence = [
        "cooking recipes for pasta",
        "attention mechanisms in transformer blocks",
    ]
    _print(
        "Paper chat: token_jaccard + paper_chat_grounding_support",
        {
            "token_jaccard_answer_vs_second_snippet": round(token_jaccard(answer, evidence[1]), 4),
            "paper_chat_grounding_support": round(paper_chat_grounding_support(answer, evidence), 4),
        },
    )

    flags_mixed = [
        WriterQaFlag(issue="w", severity="warning", location="body"),
        WriterQaFlag(issue="e", severity="error", location="body"),
    ]
    _print(
        "Writer QA: severity counts + health (synthetic flags)",
        {
            "writer_qa_severity_counts": writer_qa_severity_counts(flags_mixed),
            "writer_qa_health_score": writer_qa_health_score(flags_mixed),
        },
    )

    paper = Paper(
        id="p1",
        project_id="proj",
        title="Attention Is All You Need",
        year=2017,
        authors=["A Vaswani"],
        abstract="abstract " * 30,
        source="semantic_scholar",
        source_url="https://arxiv.org/abs/1706.03762",
    )
    qa = WriterQAAgent()
    clean = qa.validate_output(
        body="Intro \\cite{vaswani2017attention}.",
        references=[],
        bibtex_entries=[],
        thebibliography=None,
        selected_papers=[paper],
        citation_mode="latex_cite",
        artifact_paper_ids=["p1"],
        citation_keys_by_paper_id={"p1": "vaswani2017attention"},
    )
    _print(
        "Writer QA: health on minimal valid latex_cite body",
        {
            "flags": [asdict(f) for f in clean],
            "writer_qa_severity_counts": writer_qa_severity_counts(clean),
            "writer_qa_health_score": writer_qa_health_score(clean),
        },
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
