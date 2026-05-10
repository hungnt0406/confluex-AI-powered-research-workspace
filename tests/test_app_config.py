from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import get_settings
from backend.main import create_app
from backend.services.llm import OpenRouterStructuredOutputService
from backend.services.paper_conversations import PaperConversationService
from backend.services.project_conversations import ProjectConversationService


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


def test_mimo_models_use_xiaomi_url_without_openrouter_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-live-key")
    monkeypatch.delenv("XIAOMI_MIMO_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", "mimo-v2.5-pro")
    monkeypatch.setenv("XIAOMI_MIMO_BASE_URL", "https://xiaomi.example/v1")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.llm_api_key_for_model("mimo-v2.5-pro") is None
    assert settings.llm_base_url_for_model("mimo-v2.5-pro") == "https://xiaomi.example/v1"

    project_chat = ProjectConversationService()
    paper_chat = PaperConversationService()
    structured_output = OpenRouterStructuredOutputService()

    assert project_chat.api_key is None
    assert paper_chat.api_key is None
    assert structured_output.api_key is None
    assert project_chat.base_url == "https://xiaomi.example/v1"
    assert paper_chat.base_url == "https://xiaomi.example/v1"
    assert structured_output.base_url == "https://xiaomi.example/v1"
    assert not project_chat.is_configured()
    assert not paper_chat.is_configured()
    assert not structured_output.is_configured()


def test_mimo_models_use_xiaomi_key_when_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-live-key")
    monkeypatch.setenv("XIAOMI_MIMO_API_KEY", "xm-live-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "MiMo-V2.5-Pro")
    monkeypatch.setenv("XIAOMI_MIMO_BASE_URL", "https://xiaomi.example/v1")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.llm_api_key_for_model("MiMo-V2.5-Pro") == "xm-live-key"
    assert settings.llm_base_url_for_model("MiMo-V2.5-Pro") == "https://xiaomi.example/v1"

    project_chat = ProjectConversationService()
    paper_chat = PaperConversationService()
    structured_output = OpenRouterStructuredOutputService()

    assert project_chat.api_key == "xm-live-key"
    assert paper_chat.api_key == "xm-live-key"
    assert structured_output.api_key == "xm-live-key"
    assert project_chat.base_url == "https://xiaomi.example/v1"
    assert paper_chat.base_url == "https://xiaomi.example/v1"
    assert structured_output.base_url == "https://xiaomi.example/v1"
