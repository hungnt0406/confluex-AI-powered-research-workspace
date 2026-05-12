from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _submit_message_body() -> str:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    return chat_provider[
        chat_provider.index("const submitMessage = useCallback")
        : chat_provider.index("const value = useMemo<ChatState>")
    ]


def test_frontend_first_standard_message_uses_stream_project_pipeline() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()
    submit_message = _submit_message_body()
    first_project_flow = submit_message[
        submit_message.index("if (!activeProject)")
        : submit_message.index("const nextSelectedPaperIds = normalizeSelectedPaperIds")
    ]

    assert "ProjectPipelineStreamEvent" in api_client
    assert "streamProjectPipeline" in api_client
    assert 'Accept: "text/event-stream"' in api_client
    assert "streamProjectPipeline" in chat_provider
    assert "await streamProjectPipeline(project.id, {" in first_project_flow
    assert "api<RunPipelineResponse>(`/projects/${project.id}/run`" not in first_project_flow


def test_frontend_pipeline_papers_event_updates_related_papers_before_done() -> None:
    submit_message = _submit_message_body()
    first_project_flow = submit_message[
        submit_message.index("await streamProjectPipeline")
        : submit_message.index("await streamProjectChatTurn")
    ]

    assert first_project_flow.index('if (event.event === "papers")') < first_project_flow.index(
        'if (event.event === "done")',
    )
    assert "setPapers(event.data.papers);" in first_project_flow
    assert "setSelectedPaperIds([]);" in first_project_flow
    assert "Summarizing related papers" in first_project_flow
    assert "setRunSummary(event.data);" in first_project_flow


def test_frontend_pipeline_summary_event_patches_one_paper() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()
    submit_message = _submit_message_body()

    assert "function patchProjectPaper(papers: ProjectPaper[], updatedPaper: ProjectPaper)" in chat_provider
    assert "paper.id === updatedPaper.id ? updatedPaper : paper" in chat_provider
    assert 'if (event.event === "summary")' in submit_message
    assert "const updatedPaper = pipelineSummaryPaper(event.data);" in submit_message
    assert "setPapers((current) => patchProjectPaper(current, updatedPaper))" in submit_message


def test_frontend_standard_chat_starts_only_after_pipeline_done() -> None:
    submit_message = _submit_message_body()
    first_project_flow = submit_message[
        submit_message.index("await streamProjectPipeline")
        : submit_message.index("return;", submit_message.index("await streamProjectChatTurn"))
    ]

    assert first_project_flow.index("if (!completedRun)") < first_project_flow.index(
        "const nextPapers = await fetchProjectPapers(project.id);",
    )
    assert first_project_flow.index("const nextSelectedPaperIds: string[] = [];") < first_project_flow.index(
        "await streamProjectChatTurn",
    )
    assert "paperIds: nextSelectedPaperIds" in first_project_flow
    assert "setProjectBusy(targetProjectId, false);" in submit_message
    assert "setWorkspaceBusy(false);" in submit_message


def test_frontend_paper_cards_do_not_show_pending_summary_badge() -> None:
    context_panel = (REPO_ROOT / "frontend/components/ContextPanel.tsx").read_text()

    assert "showSummaryPending" not in context_panel
    assert "Summary pending" not in context_panel
    assert "const showSummaryToggle = paper.summary != null;" in context_panel
    assert "paper.summary.has_error" in context_panel
    assert "Summary unavailable" in context_panel
