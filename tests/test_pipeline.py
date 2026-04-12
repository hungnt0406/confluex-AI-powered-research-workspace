import pytest


@pytest.mark.asyncio
async def test_pipeline_health_reports_dummy_nodes(client) -> None:
    response = await client.get("/pipeline/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["nodes"] == [
        "searcher_node",
        "reader_node",
        "reader_warning_node",
        "writer_node",
        "qa_node",
    ]
