from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import get_settings
from backend.main import create_app


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_default_cors_allows_local_frontend_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.chdir(tmp_path)

    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/healthz", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.asyncio
async def test_configured_cors_allows_deployed_frontend_origin(monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        " https://literature-review.vercel.app, https://admin-literature-review.vercel.app ,,",
    )

    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        allowed_response = await client.get(
            "/healthz",
            headers={"Origin": "https://literature-review.vercel.app"},
        )
        disallowed_response = await client.get(
            "/healthz",
            headers={"Origin": "http://localhost:3000"},
        )

    assert allowed_response.status_code == 200
    assert allowed_response.headers["access-control-allow-origin"] == (
        "https://literature-review.vercel.app"
    )
    assert "access-control-allow-origin" not in disallowed_response.headers
