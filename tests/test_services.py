import os

import httpx
import pytest
import respx

from backend.services.arxiv import ARXIV_URL
from backend.services.arxiv import search_papers as search_arxiv_papers
from backend.services.semantic_scholar import (
    SEMANTIC_SCHOLAR_GRAPH_URL,
    SEMANTIC_SCHOLAR_URL,
    get_paper_citations,
    get_paper_details,
    get_paper_references,
)
from backend.services.semantic_scholar import (
    search_papers as search_semantic_scholar_papers,
)


@pytest.mark.asyncio
@respx.mock
async def test_semantic_scholar_search_returns_expected_fields() -> None:
    route = respx.get(SEMANTIC_SCHOLAR_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "paperId": "semantic-001",
                        "title": "Attention Is All You Need",
                        "authors": [{"name": "Ashish Vaswani"}],
                        "year": 2017,
                        "abstract": "Transformers replace recurrence with attention.",
                        "url": "https://www.semanticscholar.org/paper/semantic-001",
                        "openAccessPdf": {
                            "url": "https://pdf.example.com/attention-is-all-you-need.pdf"
                        },
                        "externalIds": {"DOI": "10.5555/3295222.3295349"},
                        "citationCount": 12345,
                        "referenceCount": 77,
                    }
                ]
            },
        )
    )

    papers = await search_semantic_scholar_papers("transformer", 2016, 5)

    assert route.called
    assert papers[0]["title"] == "Attention Is All You Need"
    assert papers[0]["authors"] == ["Ashish Vaswani"]
    assert papers[0]["doi"] == "10.5555/3295222.3295349"
    assert papers[0]["source_paper_id"] == "semantic-001"
    assert papers[0]["source_url"] == "https://www.semanticscholar.org/paper/semantic-001"
    assert papers[0]["pdf_url"] == "https://pdf.example.com/attention-is-all-you-need.pdf"
    assert papers[0]["citation_count"] == 12345
    assert papers[0]["reference_count"] == 77


@pytest.mark.asyncio
@respx.mock
async def test_arxiv_search_returns_expected_fields() -> None:
    xml_payload = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2401.12345v1</id>
        <link rel="alternate" type="text/html" href="http://arxiv.org/abs/2401.12345v1" />
        <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf" />
        <published>2024-01-15T00:00:00Z</published>
        <title>Graph Neural Networks for Literature Mining</title>
        <summary>We study graph methods for scientific retrieval.</summary>
        <author><name>Jane Doe</name></author>
        <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.1000/example</arxiv:doi>
      </entry>
    </feed>
    """
    route = respx.get(ARXIV_URL).mock(return_value=httpx.Response(200, text=xml_payload))

    papers = await search_arxiv_papers("graph neural network", 2020, 5)

    assert route.called
    assert papers[0]["title"] == "Graph Neural Networks for Literature Mining"
    assert papers[0]["authors"] == ["Jane Doe"]
    assert papers[0]["doi"] == "10.1000/example"
    assert papers[0]["source_paper_id"] == "2401.12345v1"
    assert papers[0]["source_url"] == "http://arxiv.org/abs/2401.12345v1"
    assert papers[0]["pdf_url"] == "http://arxiv.org/pdf/2401.12345v1"


@pytest.mark.asyncio
@respx.mock
async def test_semantic_scholar_get_paper_details_returns_expected_fields() -> None:
    route = respx.get(f"{SEMANTIC_SCHOLAR_GRAPH_URL}/paper/DOI%3A10.5555%2F3295222.3295349").mock(
        return_value=httpx.Response(
            200,
            json={
                "paperId": "semantic-001",
                "title": "Attention Is All You Need",
                "authors": [{"name": "Ashish Vaswani"}],
                "year": 2017,
                "abstract": "Transformers replace recurrence with attention.",
                "url": "https://www.semanticscholar.org/paper/semantic-001",
                "openAccessPdf": {
                    "url": "https://pdf.example.com/attention-is-all-you-need.pdf"
                },
                "externalIds": {"DOI": "10.5555/3295222.3295349"},
                "citationCount": 12345,
                "referenceCount": 77,
            },
        )
    )

    paper = await get_paper_details("DOI:10.5555/3295222.3295349")

    assert route.called
    assert paper.paper_id == "semantic-001"
    assert paper.title == "Attention Is All You Need"
    assert paper.authors == ["Ashish Vaswani"]
    assert paper.doi == "10.5555/3295222.3295349"
    assert paper.source_url == "https://www.semanticscholar.org/paper/semantic-001"
    assert paper.pdf_url == "https://pdf.example.com/attention-is-all-you-need.pdf"
    assert paper.citation_count == 12345
    assert paper.reference_count == 77


@pytest.mark.asyncio
@respx.mock
async def test_semantic_scholar_get_paper_citations_normalizes_nested_citing_paper() -> None:
    route = respx.get(f"{SEMANTIC_SCHOLAR_GRAPH_URL}/paper/semantic-001/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 1,
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "semantic-100",
                            "title": "Follow-up Transformer Paper",
                            "authors": [{"name": "Jane Doe"}],
                            "year": 2019,
                            "abstract": "Builds on the transformer architecture.",
                            "url": "https://www.semanticscholar.org/paper/semantic-100",
                            "openAccessPdf": {"url": "https://pdf.example.com/semantic-100.pdf"},
                            "externalIds": {"DOI": "10.1000/citing"},
                            "citationCount": 88,
                        }
                    }
                ],
            },
        )
    )

    papers = await get_paper_citations("semantic-001", limit=5)

    assert route.called
    assert papers == [
        {
            "title": "Follow-up Transformer Paper",
            "authors": ["Jane Doe"],
            "year": 2019,
            "abstract": "Builds on the transformer architecture.",
            "doi": "10.1000/citing",
            "source": "semantic_scholar",
            "source_paper_id": "semantic-100",
            "source_url": "https://www.semanticscholar.org/paper/semantic-100",
            "pdf_url": "https://pdf.example.com/semantic-100.pdf",
            "citation_count": 88,
        }
    ]


@pytest.mark.asyncio
@respx.mock
async def test_semantic_scholar_get_paper_references_normalizes_nested_cited_paper() -> None:
    route = respx.get(f"{SEMANTIC_SCHOLAR_GRAPH_URL}/paper/semantic-001/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 1,
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "semantic-200",
                            "title": "Sequence Modeling Baseline",
                            "authors": [{"name": "John Doe"}],
                            "year": 2015,
                            "abstract": "An earlier sequence model.",
                            "url": "https://www.semanticscholar.org/paper/semantic-200",
                            "openAccessPdf": {"url": "https://pdf.example.com/semantic-200.pdf"},
                            "externalIds": {"DOI": "10.1000/referenced"},
                            "citationCount": 1234,
                        }
                    }
                ],
            },
        )
    )

    papers = await get_paper_references("semantic-001", limit=5)

    assert route.called
    assert papers == [
        {
            "title": "Sequence Modeling Baseline",
            "authors": ["John Doe"],
            "year": 2015,
            "abstract": "An earlier sequence model.",
            "doi": "10.1000/referenced",
            "source": "semantic_scholar",
            "source_paper_id": "semantic-200",
            "source_url": "https://www.semanticscholar.org/paper/semantic-200",
            "pdf_url": "https://pdf.example.com/semantic-200.pdf",
            "citation_count": 1234,
        }
    ]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_API_TESTS") != "1",
    reason="Set RUN_LIVE_API_TESTS=1 to execute live external API checks.",
)
async def test_semantic_scholar_live_query_returns_known_title() -> None:
    papers = await search_semantic_scholar_papers("attention is all you need", 2017, 10)

    titles = {paper["title"].lower() for paper in papers}
    assert "attention is all you need" in titles


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_API_TESTS") != "1",
    reason="Set RUN_LIVE_API_TESTS=1 to execute live external API checks.",
)
async def test_arxiv_live_query_returns_results() -> None:
    papers = await search_arxiv_papers("graph neural networks", 2020, 5)

    assert papers
    assert all(paper["title"] for paper in papers)
