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


def test_frontend_restored_chat_sort_handles_invalid_timestamps() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()

    assert "restoredChatSortKey" in chat_provider
    assert "Number.isFinite(parsed)" in chat_provider
    assert "Number.POSITIVE_INFINITY" in chat_provider
    assert "left.sortKey < right.sortKey" in chat_provider
    assert "left.index - right.index" in chat_provider


def test_frontend_deep_search_sources_render_in_context_panel() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()
    context_panel = (REPO_ROOT / "frontend/components/ContextPanel.tsx").read_text()

    assert "deepSearchSources" in chat_provider
    assert "DeepSearchSourceCard" in context_panel
    assert "SourceFavicon" in context_panel
    assert "getFaviconUrl" in context_panel
    assert "https://www.google.com/s2/favicons" in context_panel
    assert "h-5 w-5" in context_panel
    assert "h-3.5 w-3.5" in context_panel
    assert "onError={() => setFailed(true)}" in context_panel
    assert "Deep Search Sources" in context_panel
    assert "open = papers.length > 0 || deepSearchSources.length > 0" in context_panel
    assert "sources={message.sources}" not in chat_workspace
    assert context_panel.index("Related Papers") < context_panel.index("Deep Search Sources")
    assert "const splitPanel = papers.length > 0 && deepSearchSources.length > 0" in context_panel
    assert 'splitPanel ? "flex-1 basis-0" : "flex-1"' in context_panel
    assert "overflow-y-auto pr-1 custom-scrollbar" in context_panel
    assert context_panel.count("overflow-y-auto pr-1 custom-scrollbar") >= 2


def test_frontend_deep_search_primes_related_papers() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()

    assert "hasDiscoveredProjectPapers" in chat_provider
    assert "ensureDeepSearchRelatedPapers" in chat_provider
    assert "Finding related papers for the sidebar..." in chat_provider
    assert "`/projects/${projectId}/run`" in chat_provider
    assert "await ensureDeepSearchRelatedPapers({" in chat_provider
    assert "shouldRunDiscovery: !hasDiscoveredProjectPapers(papers)" in chat_provider
