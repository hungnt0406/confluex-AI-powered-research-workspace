import os

import pytest

from backend.agents.searcher import SearcherAgent
from backend.eval.metrics import mean_search_recall, search_golden_hit

GOLDEN = [
    {
        "topic": "transformers for machine translation",
        "year_start": 2017,
        "must_include_titles": ["Attention Is All You Need"],
    },
    {
        "topic": "graph convolutional networks for semi-supervised node classification",
        "year_start": 2017,
        "must_include_titles": ["Semi-Supervised Classification with Graph Convolutional Networks"],
    },
    {
        "topic": "vision transformers for image recognition",
        "year_start": 2020,
        "must_include_titles": [
            "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale"
        ],
    },
    {
        "topic": "contrastive language image pretraining",
        "year_start": 2021,
        "must_include_titles": ["Learning Transferable Visual Models From Natural Language Supervision"],
    },
    {
        "topic": "retrieval augmented generation for question answering",
        "year_start": 2020,
        "must_include_titles": ["Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"],
    },
]


@pytest.mark.eval
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_EVAL_TESTS") != "1",
    reason="Set RUN_EVAL_TESTS=1 to execute search-quality evals.",
)
async def test_search_quality_recall_at_10() -> None:
    searcher = SearcherAgent()
    hits: list[bool] = []

    for test_case in GOLDEN:
        _queries, papers, _errors = await searcher.collect_candidates(
            topic=test_case["topic"],
            year_start=test_case["year_start"],
            candidate_limit=10,
        )
        candidate_titles = [str(paper["title"]) for paper in papers[:10]]
        hits.append(
            search_golden_hit(
                candidate_titles=candidate_titles,
                must_include_titles=test_case["must_include_titles"],
            )
        )

    assert mean_search_recall(hits) >= 0.8
