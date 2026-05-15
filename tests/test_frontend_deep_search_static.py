from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_chat_header_logo_has_no_dropdown_icon() -> None:
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()

    assert '<Logo size="sm" />' in chat_workspace
    assert '<Logo size="sm" />\n          <span className="material-symbols-outlined text-xs text-hint">expand_more</span>' not in chat_workspace


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
    assert 'if (chatMode === "deep_search" || chatMode === "deep_research_max")' in chat_provider
    assert "setPendingDeepSearchPlan(planMessage.deepSearchPlan);" in chat_provider
    assert "await streamDeepSearchTurn({" not in chat_provider[
        chat_provider.index("const submitMessage = useCallback") : chat_provider.index("const value = useMemo<ChatState>")
    ].split('if (chatMode === "deep_search" || chatMode === "deep_research_max")', 1)[1].split("return;", 1)[0]
    assert "DeepSearchPlanCard" in chat_workspace
    assert "Start research" in chat_workspace
    assert "Edit plan" in chat_workspace


def test_frontend_deep_search_plan_edit_offers_manual_or_llm_revision() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()

    assert "reviseDeepSearchPlan" in chat_provider
    assert "Revision request:" in chat_provider
    assert 'json: { question: revisedQuestion, mode: plan.mode }' in chat_provider
    assert "setPendingDeepSearchPlan((prev) =>" in chat_provider
    assert "Manual edit" in chat_workspace
    assert "Ask AI to edit" in chat_workspace
    assert "Generate revised plan" in chat_workspace
    assert "Preview the revised plan before starting Deep Search." in chat_workspace


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
    assert "appendDeepSearchThinkingSourceToState(message.thinking, event.data)" in chat_provider
    assert "completeDeepSearchThinkingState(message.thinking)" in chat_provider
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
    assert "updateDeepSearchMessages((prev) => [...prev, thinkingMessage]);" in stream_turn
    assert "content: \"\"," not in stream_turn.split("await streamDeepSearchRun", 1)[0]
    assert "const targetMessageId = ensureDeepSearchAnswerMessage();" in stream_turn
    assert "const targetMessageId = ensureDeepSearchAnswerMessage(event.data.report_body);" in stream_turn


def test_frontend_streaming_chat_does_not_force_scroll_when_user_reads_history() -> None:
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()

    assert "CHAT_SCROLL_BOTTOM_THRESHOLD" in chat_workspace
    assert "function isChatScrolledNearBottom" in chat_workspace
    assert "scrollHeight - scrollTop - clientHeight" in chat_workspace
    assert "const shouldAutoScrollRef = useRef(true);" in chat_workspace
    assert "const lastScrollIntentRef = useRef" in chat_workspace
    assert "const nearBottom = isChatScrolledNearBottom(node);" in chat_workspace
    assert "if (!shouldAutoScrollRef.current) return;" in chat_workspace
    assert "function handleChatWheel" in chat_workspace
    assert "event.deltaY < 0" in chat_workspace
    assert 'lastScrollIntentRef.current = "up";' in chat_workspace
    assert "function handleChatTouchMove" in chat_workspace
    assert "TOUCH_SCROLL_INTENT_THRESHOLD" in chat_workspace
    assert "onScroll={handleChatScroll}" in chat_workspace
    assert "onWheel={handleChatWheel}" in chat_workspace
    assert "onTouchMove={handleChatTouchMove}" in chat_workspace


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


def test_frontend_project_streams_are_scoped_to_project_snapshots() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    stream_turn = chat_provider[
        chat_provider.index("const streamProjectChatTurn = useCallback")
        : chat_provider.index("const streamDeepSearchTurn = useCallback")
    ]
    select_project = chat_provider[
        chat_provider.index("const selectProject = useCallback")
        : chat_provider.index("useEffect(() => {", chat_provider.index("const selectProject = useCallback"))
    ]
    submit_message = chat_provider[
        chat_provider.index("const submitMessage = useCallback")
        : chat_provider.index("const value = useMemo<ChatState>")
    ]

    assert "type ProjectChatSnapshot" in chat_provider
    assert "projectSnapshotsRef" in chat_provider
    assert "const cachedSnapshot = projectSnapshotsRef.current[projectId]" in select_project
    assert "applyProjectSnapshot(cachedSnapshot);" in select_project
    assert "updateProjectSnapshot(" in stream_turn
    assert "projectId," in stream_turn
    assert "setConversation(event.data);" not in stream_turn
    assert "setProjectBusy(targetProjectId, true);" in submit_message
    assert "setProjectBusy(targetProjectId, false);" in submit_message


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


def test_frontend_chat_markdown_renders_citation_hover_previews_without_html_cards() -> None:
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "const markdownLinkPattern" in chat_workspace
    assert "CitationCluster" in chat_workspace
    assert "createPortal" in chat_workspace
    assert "document.body" in chat_workspace
    assert "CitationPreview" in chat_workspace
    assert "fixed z-[1000]" in chat_workspace
    assert "getBoundingClientRect" in chat_workspace
    assert "pointer-events-auto fixed z-[1000]" in chat_workspace
    assert "closeTimeoutRef" in chat_workspace
    assert "window.setTimeout" in chat_workspace
    assert 'className="mb-2 block rounded-xl px-3 py-2 transition-colors hover:bg-surface-container-low focus:bg-surface-container-low focus:outline-none last:mb-0"' in chat_workspace
    assert "SourcePreviewFavicon" in chat_workspace
    assert "extractSourceReferences" in chat_workspace
    assert "sourceReferencesFromDeepSearchSources" in chat_workspace
    assert "<MarkdownContent text={message.content} sources={message.sources ?? []}" in chat_workspace
    assert "note?: string" in chat_provider
    assert "note: source.note" in chat_provider
    assert "note: source.note ??" in chat_provider
    assert "note: string;" in api_client
    assert "+{overflowCount}" in chat_workspace
    assert "renderBareUrls" in chat_workspace
    assert "data-source-id" not in chat_workspace
    assert "source-card" not in chat_workspace


def test_frontend_chat_markdown_renders_latex_math() -> None:
    chat_workspace = (REPO_ROOT / "frontend/components/ChatWorkspace.tsx").read_text()
    app_layout = (REPO_ROOT / "frontend/app/layout.tsx").read_text()
    package_json = (REPO_ROOT / "frontend/package.json").read_text()

    assert "import katex from \"katex\"" in chat_workspace
    assert "katex.renderToString" in chat_workspace
    assert "MathExpression" in chat_workspace
    assert "displayMode" in chat_workspace
    assert "trimmed.startsWith(\"$$\")" in chat_workspace
    assert "renderInlineMarkdown" in chat_workspace
    assert "katex/dist/katex.min.css" in app_layout
    assert '"katex"' in package_json


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
    assert "applyDeepSearchThinkingActivityToState(message.thinking, event.data)" in chat_provider


def test_frontend_citation_graph_caches_previews_and_imports() -> None:
    citation_graph = (REPO_ROOT / "frontend/components/CitationGraph.tsx").read_text()
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "citationGraphCache" in chat_provider
    assert "citationGraphRequestRefs" in chat_provider
    assert "getCitationGraph" in chat_provider
    assert "prefetchCitationGraphs" in chat_provider
    assert "addCitationGraphPaperToProject" in chat_provider
    assert "fetchPaperCitationGraph" in chat_provider
    assert "importCitationGraphPaper" in api_client
    assert "/papers/import-citation" in api_client

    assert "NodePreviewCard" in citation_graph
    assert "setSelectedNode(rawNode as GraphNode)" in citation_graph
    assert "window.open" not in citation_graph
    assert "Add to project" in citation_graph
    assert "In project" in citation_graph
    assert "PROJECT_NODE_STROKE" in citation_graph
    assert "CitationGraphList" in citation_graph
    assert "Seed Paper" in citation_graph
    assert "References" in citation_graph
    assert "Cited By" in citation_graph
    assert "Resolving seed paper..." in citation_graph
    assert "Fetching citation neighborhood..." in citation_graph
    assert "Preparing graph layout..." in citation_graph
