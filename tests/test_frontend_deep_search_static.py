from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_deep_search_mode_wiring() -> None:
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "Standard" in chat_workspace
    assert "Deep Search" in chat_workspace
    assert "chatMode" in chat_workspace
    assert "setChatMode" in chat_workspace
    assert "streamDeepSearchRun" in chat_provider
    assert "/deep-search/stream" in chat_provider
    assert "paperIds: nextSelectedPaperIds" in chat_provider
    assert "DeepSearchStreamEvent" in api_client
    assert "source" in api_client


def test_frontend_deep_search_progress_is_cleared_after_completion() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()

    assert "deepSearchStatusMessageIds" in chat_provider
    assert "clearDeepSearchStatusMessages" in chat_provider
    assert "Deep Search run started." in chat_provider
    assert "!statusIds.has(message.id)" in chat_provider
    assert "clearDeepSearchStatusMessages();" in chat_provider


def test_frontend_restores_completed_deep_search_runs_after_refresh() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()

    assert "buildRestoredDeepSearchMessages" in chat_provider
    assert "sortRestoredChatMessages" in chat_provider
    assert "/deep-search-runs" in chat_provider
    assert "`/projects/${project.id}/deep-search-runs/${summary.id}`" in chat_provider
    assert "summary.status === \"completed\"" in chat_provider
    assert "omitEmptyPaperStatus" in chat_provider
    assert "createdAt: run.created_at" in chat_provider
    assert "...restoredConversationMessages" in chat_provider
    assert "...restoredDeepSearchMessages" in chat_provider
