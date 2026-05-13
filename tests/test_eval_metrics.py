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
from backend.services.deep_search import count_report_claim_sentences


def test_search_golden_hit_case_insensitive() -> None:
    candidates = {"attention is all you need", "other paper"}
    assert search_golden_hit(
        candidate_titles=candidates,
        must_include_titles=["Attention Is All You Need"],
    )
    assert not search_golden_hit(
        candidate_titles=candidates,
        must_include_titles=["Nonexistent Title"],
    )


def test_mean_search_recall() -> None:
    assert mean_search_recall([True, True, False, True]) == 0.75
    assert mean_search_recall([]) == 0.0


def test_reader_summary_metrics() -> None:
    records = [
        {
            "paper_id": "1",
            "problem": "p",
            "method": "m",
            "result": "r",
            "relevance_to_topic": "rel",
            "has_error": False,
        },
        {
            "paper_id": "2",
            "problem": "",
            "method": "m",
            "result": "r",
            "relevance_to_topic": "rel",
            "has_error": True,
        },
    ]
    m = reader_summary_metrics(records)
    assert m.n_records == 2
    assert m.success_rate == 0.5
    assert abs(m.mean_field_coverage - (1.0 + 0.75) / 2) < 1e-9


def test_deep_search_aggregate_metrics() -> None:
    body = "Transformers improve MT [Vaswani](https://arxiv.org/abs/1706.03762)."
    sources = [{"url": "https://arxiv.org/abs/1706.03762", "source_type": "paper"}]
    agg = aggregate_deep_search_report_metrics(body, sources)
    assert agg.n_warnings == 0
    assert agg.n_claim_sentences == count_report_claim_sentences(body)
    assert agg.citation_warning_rate == 0.0


def test_deep_search_metrics_uncited_claim() -> None:
    body = "Models get bigger every year without citations here."
    sources: list[dict] = [{"url": "https://example.com/a", "source_type": "web"}]
    agg = aggregate_deep_search_report_metrics(body, sources)
    assert agg.n_warnings >= 1
    assert 0.0 < agg.citation_warning_rate <= 1.0


def test_paper_chat_answer_metrics_good_shape() -> None:
    answer = (
        "## Answer\nGrounded.\n\n## Evidence\nSee (pages 3-4).\n\n## Limits\nNone.\n"
    )
    m = paper_chat_answer_metrics(answer)
    assert m.has_answer_heading
    assert m.has_evidence_or_limits_heading
    assert m.page_mention_count >= 1
    assert not m.chunk_or_score_leak
    assert m.format_score == 1.0


def test_paper_chat_answer_metrics_detects_leak() -> None:
    bad = "## Answer\nChunk 3, pages 1-2 had the detail.\n\n## Limits\nx"
    m = paper_chat_answer_metrics(bad)
    assert m.chunk_or_score_leak


def test_token_jaccard_and_grounding_support() -> None:
    assert token_jaccard("hello world", "hello there world") > 0.2
    assert paper_chat_grounding_support("the method uses attention", []) == 0.0
    support = paper_chat_grounding_support(
        "the method uses attention mechanisms",
        ["unrelated text about cooking", "attention mechanisms in neural networks"],
    )
    assert support > 0.1


def test_writer_qa_severity_counts_and_health() -> None:
    flags = [
        WriterQaFlag(issue="a", severity="warning", location="x"),
        WriterQaFlag(issue="b", severity="error", location="y"),
    ]
    assert writer_qa_severity_counts(flags) == {"warning": 1, "error": 1}
    assert writer_qa_health_score(flags) == 0.0

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
    clean_flags = qa.validate_output(
        body="Intro \\cite{vaswani2017attention}.",
        references=[],
        bibtex_entries=[],
        thebibliography=None,
        selected_papers=[paper],
        citation_mode="latex_cite",
        artifact_paper_ids=["p1"],
        citation_keys_by_paper_id={"p1": "vaswani2017attention"},
    )
    assert writer_qa_health_score(clean_flags) == 1.0
