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


def test_frontend_deep_search_requires_plan_approval_before_streaming() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()

    assert 'kind?: "text" | "status" | "summary" | "deep_search_plan" | "deep_search_thinking"' in chat_provider
    assert "DeepSearchPlanMessage" in chat_provider
    assert "pendingDeepSearchPlan" in chat_provider
    assert "createDeepSearchPlanMessage" in chat_provider
    assert "startDeepSearchPlan" in chat_provider
    assert "editDeepSearchPlan" in chat_provider
    assert "Here's a research plan for that topic." in chat_provider
    assert "if (chatMode === \"deep_search\")" in chat_provider
    assert "setPendingDeepSearchPlan(planMessage.deepSearchPlan);" in chat_provider
    assert "await streamDeepSearchTurn({" not in chat_provider[
        chat_provider.index("const submitMessage = useCallback") : chat_provider.index("const value = useMemo<ChatState>")
    ].split("if (chatMode === \"deep_search\")", 1)[1].split("return;", 1)[0]
    assert "DeepSearchPlanCard" in chat_workspace
    assert "Start research" in chat_workspace
    assert "Edit plan" in chat_workspace


def test_frontend_deep_search_thinking_panel_tracks_stream_events() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "DeepSearchThinkingState" in chat_provider
    assert "DEEP_SEARCH_THINKING_PHASES" in chat_provider
    assert "buildInitialDeepSearchThinkingSteps" in chat_provider
    assert "createDeepSearchThinkingMessage" in chat_provider
    assert "updateDeepSearchThinkingPhase" in chat_provider
    assert "appendDeepSearchThinkingSource" in chat_provider
    assert "applyDeepSearchThinkingActivity" in chat_provider
    assert "completeDeepSearchThinking" in chat_provider
    assert "DeepSearch: ${formatDeepSearchPhase(event.data.phase)}" not in chat_provider
    assert 'if (event.event === "activity")' in chat_provider
    assert "appendDeepSearchThinkingSource(thinkingMessageId, event.data);" in chat_provider
    assert "completeDeepSearchThinking(thinkingMessageId);" in chat_provider
    assert "DeepSearchThinkingPanel" in chat_workspace
    assert "Show thinking" in chat_workspace
    assert "Researching websites" in chat_provider
    assert "DeepSearchActivityEventData" in api_client
    assert '"stage_start" | "stage_update" | "source_found" | "stage_complete" | "finalizing"' in api_client
    assert '| { event: "activity"; data: DeepSearchActivityEventData }' in api_client


def test_frontend_deep_search_activity_accepts_compatibility_fields() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "type?: DeepSearchActivityEventType" in api_client
    assert "event_type?: DeepSearchActivityEventType" in api_client
    assert "message?: string" in api_client
    assert "detail?: string" in api_client
    assert "type?: DeepSearchActivityChipType" in api_client
    assert "source_type: string" in api_client
    assert "deepSearchActivityEventType(activity)" in chat_provider
    assert "deepSearchActivityMessage(activity)" in chat_provider
    assert "source.type ?? activitySourceTypeFromBackend(source.source_type)" in chat_provider
    assert "options.onEvent({ event: eventName, data } as DeepSearchStreamEvent);" in api_client


def test_frontend_deep_search_shows_full_thinking_plan_immediately() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()

    assert 'status: index === 0 ? "active" : "pending"' in chat_provider
    assert "steps: buildInitialDeepSearchThinkingSteps(question)" in chat_provider
    assert "project_evidence" in chat_provider
    assert "academic_search" in chat_provider
    assert "web_search" in chat_provider
    assert "summarizing_sources" in chat_provider
    assert "writing" in chat_provider
    assert "verifying" in chat_provider
    assert "text-on-surface-variant/55" in chat_workspace
    assert "bg-outline/50" in chat_workspace


def test_frontend_deep_search_avoids_empty_answer_placeholder() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    stream_turn = chat_provider[
        chat_provider.index("const streamDeepSearchTurn = useCallback")
        : chat_provider.index("const startDeepSearchPlan = useCallback")
    ]

    assert "ensureDeepSearchAnswerMessage" in chat_provider
    assert "setMessages((prev) => [...prev, thinkingMessage]);" in stream_turn
    assert "content: \"\"," not in stream_turn.split("await streamDeepSearchRun", 1)[0]
    assert "const targetMessageId = ensureDeepSearchAnswerMessage();" in stream_turn
    assert "const targetMessageId = ensureDeepSearchAnswerMessage(event.data.report_body);" in stream_turn


def test_frontend_deep_search_thinking_shows_live_activity_while_waiting() -> None:
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()
    globals_css = (REPO_ROOT / "frontend/app/globals.css").read_text()

    assert "setInterval" in chat_workspace
    assert "thinking.completed" in chat_workspace
    assert "Working for" in chat_workspace
    assert "animate-pulse" in chat_workspace
    assert "animate-[progress-shimmer" in chat_workspace
    assert "ThinkingSourceFavicon" in chat_workspace
    assert "https://www.google.com/s2/favicons" in chat_workspace
    assert "@keyframes progress-shimmer" in globals_css


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
    assert 'splitPanel ? "flex-[2_1_0%]" : "flex-1"' in context_panel
    assert 'splitPanel ? "flex-[1_1_0%]" : "flex-1"' in context_panel
    assert 'aria-hidden="true"' in context_panel
    assert "h-px flex-none bg-outline/20" in context_panel
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


def test_frontend_deep_search_accepts_heartbeat_stage_update_events() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "stage_update" in api_client
    assert "stage_start" in api_client
    assert "stage_complete" in api_client
    assert "source_found" in api_client
    assert "finalizing" in api_client

    assert "type?: DeepSearchActivityEventType" in api_client
    assert "event_type?: DeepSearchActivityEventType" in api_client
    assert "message?: string" in api_client
    assert "detail?: string" in api_client
    assert "sources?: DeepSearchActivitySource[]" in api_client

    assert "applyDeepSearchThinkingActivityToState" in chat_provider
    assert "deepSearchActivityEventType(activity)" in chat_provider
    assert "deepSearchActivityMessage(activity)" in chat_provider
    assert 'if (event.event === "activity")' in chat_provider
    assert "applyDeepSearchThinkingActivity(thinkingMessageId, event.data);" in chat_provider
