import os

import httpx
import pytest
import respx

from backend.services.arxiv import ARXIV_URL
from backend.services.arxiv import search_papers as search_arxiv_papers
from backend.services.semantic_scholar import (
    SEMANTIC_SCHOLAR_URL,
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
                        "title": "Attention Is All You Need",
                        "authors": [{"name": "Ashish Vaswani"}],
                        "year": 2017,
                        "abstract": "Transformers replace recurrence with attention.",
                        "externalIds": {"DOI": "10.5555/3295222.3295349"},
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


@pytest.mark.asyncio
@respx.mock
async def test_arxiv_search_returns_expected_fields() -> None:
    xml_payload = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2401.12345v1</id>
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
