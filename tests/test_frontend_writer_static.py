import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_writer_source_attach_wraps_candidate_payload() -> None:
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "`/writer/documents/${documentId}/sources/attach`" in api_client
    assert "{ method: \"POST\", token, json: { candidate } }" in api_client


def test_writer_sources_panel_tracks_backend_paper_ids_for_attached_candidates() -> None:
    sources_panel = (REPO_ROOT / "frontend/components/WriterSourcesPanel.tsx").read_text()

    assert "const [attachedCandidateIds" in sources_panel
    assert "if (result.paper_id)" in sources_panel
    assert "const paperId = result.paper_id" in sources_panel
    assert "setAttachedCandidateIds((prev) => ({ ...prev, [key]: paperId }))" in sources_panel
    assert "result.paper_id ?? key" not in sources_panel
    assert "isAttached={attachedIds.has(key) || Boolean(attachedCandidateIds[key])}" in sources_panel


def test_writer_sources_panel_supports_pdf_upload_attach_by_paper_id() -> None:
    sources_panel = (REPO_ROOT / "frontend/components/WriterSourcesPanel.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "uploadWriterDocumentSource(document.id, file, token)" in sources_panel
    assert "attachPaperById(document.id, result.linked_paper_id, token)" not in sources_panel
    assert "`/writer/documents/${documentId}/sources/upload`" in api_client


def test_writer_sources_panel_renders_attached_source_labels() -> None:
    sources_panel = (REPO_ROOT / "frontend/components/WriterSourcesPanel.tsx").read_text()
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "export interface WriterSourcePaper" in api_client
    assert "source_papers: WriterSourcePaper[];" in api_client
    assert "function sourceLabel(source: WriterSourcePaper | null, paperId: string)" in sources_panel
    assert "const attachedSourceById = new Map(document.source_papers.map((source) => [source.id, source]));" in sources_panel
    assert "const label = sourceLabel(source, paperId);" in sources_panel
    assert "{label}" in sources_panel
    assert "font-mono\">{paperId}" not in sources_panel


def test_writer_page_loads_documents_without_active_project() -> None:
    writer_page = (REPO_ROOT / "frontend/app/writer/page.tsx").read_text()

    assert "if (!token) {" in writer_page
    assert "if (!token || !activeProject)" not in writer_page
    assert "const docs = await listWriterDocuments(token);" in writer_page
    assert "const showProjectPickerState" not in writer_page
    assert "disabled={!activeProject}" not in writer_page


def test_writer_project_route_param_drives_active_project_restore() -> None:
    chat_provider = (REPO_ROOT / "frontend/components/ChatProvider.tsx").read_text()

    assert "function loadRouteProjectId()" in chat_provider
    assert "const routeProjectId = loadRouteProjectId();" in chat_provider
    assert "const savedProjectId = routeProjectId ?? loadSavedActiveProjectId(user?.id);" in chat_provider
    assert "if (!routeProjectId) persistActiveProjectId(user?.id, null);" in chat_provider
    assert "if (!activeProject && !restoreAttemptedRef.current) return;" in chat_provider


def test_writer_page_has_back_to_chat_workspace_action() -> None:
    writer_page = (REPO_ROOT / "frontend/app/writer/page.tsx").read_text()

    assert "const chatHref = activeProject ? `/chat?project=${activeProject.id}` : \"/chat\";" in writer_page
    assert "href={chatHref}" in writer_page
    assert "Back to Chat" in writer_page


def test_writer_new_document_submit_button_keeps_loading_dom_stable() -> None:
    writer_page = (REPO_ROOT / "frontend/app/writer/page.tsx").read_text()
    modal_match = re.search(
        r"function NewDocumentModal\(.*?\nfunction DocumentCard",
        writer_page,
        flags=re.DOTALL,
    )

    assert modal_match is not None
    modal = modal_match.group(0)
    assert "{submitting && (" not in modal
    assert "hidden={!submitting}" in modal
    assert "hidden={submitting}" in modal
    assert 'aria-live="polite"' in modal


def test_writer_workspace_logo_links_back_to_project_chat() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "import Link from \"next/link\";" in workspace
    assert "const chatHref = document.project_id ? `/chat?project=${document.project_id}` : \"/writer\";" in workspace
    assert "href={chatHref}" in workspace
    assert "aria-label={document.project_id ? \"Back to chat workspace\" : \"Back to writer documents\"}" in workspace


def test_writer_api_supports_standalone_documents_and_project_import() -> None:
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert '"/writer/documents"' in api_client
    assert "projectId?: string | null" in api_client
    assert "`/writer/documents/${documentId}/sources/import-project`" in api_client
    assert "export async function importProjectSources" in api_client


def test_writer_question_warnings_render_after_delay() -> None:
    questions_panel = (REPO_ROOT / "frontend/components/WriterQuestionsPanel.tsx").read_text()

    assert "const warningDelayTimerRef = useRef<number | null>(null);" in questions_panel
    assert "warningDelayTimerRef.current = window.setTimeout(() => {" in questions_panel
    assert "setWarnings(ws);" in questions_panel
    assert "}, 2000);" in questions_panel
    assert "window.clearTimeout(warningDelayTimerRef.current);" in questions_panel


def test_writer_api_supports_section_outline_approval() -> None:
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "export async function proposeSectionOutline" in api_client
    assert "export async function approveSectionOutline" in api_client
    assert "`/writer/documents/${documentId}/sections/${sectionId}/outline/propose`" in api_client
    assert "`/writer/documents/${documentId}/sections/${sectionId}/outline`" in api_client
    assert "json: { outline_text }" in api_client


def test_writer_questions_panel_gates_drafting_on_approved_outline() -> None:
    questions_panel = (REPO_ROOT / "frontend/components/WriterQuestionsPanel.tsx").read_text()
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "proposeSectionOutline" in questions_panel
    assert "approveSectionOutline" in questions_panel
    assert "documentPaperType={document.paper_type}" in workspace
    assert "function isApprovedSectionOutline" in questions_panel
    assert "documentPaperType === \"survey\"" in questions_panel
    assert "sectionType === \"results\"" in questions_panel
    assert "outline.includes(\"\\\\subsection{\")" in questions_panel
    assert "Generate section outline" in questions_panel
    assert "Approve outline" in questions_panel
    assert "disabled={submitting || drafting || !hasApprovedOutline}" in questions_panel
    assert "if (!activeSection || !hasApprovedOutline) return;" in questions_panel


def test_writer_outline_panel_removes_full_document_outline_actions() -> None:
    outline_panel = (REPO_ROOT / "frontend/components/WriterOutlinePanel.tsx").read_text()
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "onProposeOutline" not in outline_panel
    assert "onSaveOutline" not in outline_panel
    assert "outlineActionMessage" not in outline_panel
    assert "Propose Outline" not in outline_panel
    assert "Generate Outline" not in outline_panel
    assert "Save Outline" not in outline_panel
    assert "Propose an outline to get started." not in outline_panel
    assert "handleProposeOutline" not in workspace
    assert "handleSaveOutline" not in workspace
    assert "outlineActionMessage" not in workspace


def test_writer_right_panel_is_resizable_from_forty_percent_default() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()
    loading_page = (REPO_ROOT / "frontend/app/writer/[documentId]/page.tsx").read_text()

    assert "const [rightPanelWidth, setRightPanelWidth] = useState<number>(480);" in workspace
    assert "window.innerWidth * 0.4" in workspace
    assert "handleRightPanelMouseDown" in workspace
    assert "handleRightPanelKeyDown" in workspace
    assert "Resize writer side panel" in workspace
    assert "cursor-col-resize" in workspace
    assert "style={{ width: `${rightPanelWidth}px` }}" in workspace
    assert "w-[40vw] min-w-[360px] max-w-[640px]" in loading_page
    assert "w-[40vw] min-w-[360px] max-w-[640px]" not in workspace
    assert "w-[300px] shrink-0 flex-col" not in workspace
    assert "w-[300px] shrink-0 border-l" not in loading_page


def test_writer_editor_overlay_is_mounted_in_workspace() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "WriterEditorOverlay" in workspace
    assert "setMonacoEditor" in workspace
    assert "onPendingChange={setHasPendingEditorPatch}" in workspace
    assert "if (hasPendingEditorPatch) return;" in workspace


def test_writer_editor_api_exports_preview_and_apply() -> None:
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "export interface EditRequest" in api_client
    assert "export interface EditPatchResponse" in api_client
    assert "original_text: string;" in api_client
    assert "export async function previewWriterEdit" in api_client
    assert "export async function applyWriterEdit" in api_client
    assert "`/writer/documents/${documentId}/sections/${sectionId}/edit`" in api_client
    assert "`/writer/documents/${documentId}/sections/${sectionId}/edit/apply`" in api_client


def test_writer_editor_overlay_renders_diff_preview_controls() -> None:
    overlay = (REPO_ROOT / "frontend/components/WriterEditorOverlay.tsx").read_text()

    assert "bg-emerald-50" in overlay
    assert "line-through" in overlay
    assert "createPortal(" in overlay
    assert "getDomNode" in overlay
    assert "getBoundingClientRect()" in overlay
    assert "fixed inset-0 z-[70]" in overlay
    assert "function previewText(text: string)" in overlay
    assert "{previewText(pendingPatch.new_text)}" in overlay
    assert "maxHeight: `${patchPlacement.maxHeight}px`" in overlay
    assert "overflow-y-auto" in overlay
    assert "whitespace-pre-wrap break-words" in overlay
    assert "shrink-0 flex-wrap" in overlay
    assert "Accept" in overlay
    assert "Regenerate" in overlay
    assert "Refine" in overlay
    assert "Discard" in overlay
    assert "Add findings (optional)" in overlay
    assert "Web search" in overlay


def test_writer_editor_overlay_uses_single_edit_action() -> None:
    overlay = (REPO_ROOT / "frontend/components/WriterEditorOverlay.tsx").read_text()

    assert "Fix grammar, clarity, and phrasing." not in overlay
    assert "intent: \"fix_error\"" not in overlay
    assert "intent: \"generate_paragraph\"" not in overlay
    assert "intent: \"incorporate_results\"" not in overlay
    assert "auto_awesome" in overlay
    assert "Edit selection" in overlay
    assert "Write new paragraph" in overlay
    assert "Add findings (optional)" in overlay


def test_writer_workspace_offers_visual_source_toggle() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "import { WriterProseEditor } from \"@/components/WriterProseEditor\";" in workspace
    assert "type EditorViewMode = \"visual\" | \"source\";" in workspace
    assert "const [viewMode, setViewMode] = useState<EditorViewMode>(\"visual\");" in workspace
    assert "aria-label=\"Editor view mode\"" in workspace
    assert "viewMode === \"visual\" ? (" in workspace
    assert "editorKey={`${activeSection.id}:${proseRefreshToken}`}" in workspace


def test_writer_workspace_renders_section_metadata_from_live_draft() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()
    time_util = (REPO_ROOT / "frontend/lib/time.ts").read_text()

    assert "import { formatRelativeTime } from \"@/lib/time\";" in workspace
    assert "const activeSectionWordCount = useMemo(" in workspace
    assert "editorContent.trim().split(/\\s+/).filter(Boolean).length" in workspace
    assert "1 word" in workspace
    assert "words" in workspace
    assert "Edited {formatRelativeTime(activeSection.updated_at)}" in workspace
    assert "justify-end" in workspace
    assert "border" not in re.search(
        r"<div className=\"flex shrink-0 items-center justify-end[^\"]+\".*?</div>",
        workspace,
        flags=re.DOTALL,
    ).group(0)

    assert "export function formatRelativeTime(iso: string)" in time_util
    assert "new Date(iso).getTime()" in time_util
    assert "Intl.DateTimeFormat" not in time_util


def test_writer_workspace_has_undo_redo_buttons() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "const [historyBySection, setHistoryBySection] = useState<" in workspace
    assert "const pushHistory = useCallback((sectionId: string, content: string)" in workspace
    assert "pushHistory(activeSection.id, value);" in workspace
    assert "pushHistory(section.id, newContent);" in workspace
    assert "const handleUndo = useCallback(" in workspace
    assert "const handleRedo = useCallback(" in workspace
    assert "const canUndo = (activeHistory?.past.length ?? 0) > 0;" in workspace
    assert "const canRedo = (activeHistory?.future.length ?? 0) > 0;" in workspace
    assert "aria-label=\"Undo\"" in workspace
    assert "aria-label=\"Redo\"" in workspace
    assert "disabled={!canUndo}" in workspace
    assert "disabled={!canRedo}" in workspace
    assert "const applyHistoricalContent = useCallback(" in workspace


def test_writer_visual_mode_mounts_ai_edit_overlay() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()
    adapter = (REPO_ROOT / "frontend/lib/prose-editor-adapter.ts").read_text()
    domMap = (REPO_ROOT / "frontend/lib/dom-latex-map.ts").read_text()

    assert "import { createProseEditorAdapter } from \"@/lib/prose-editor-adapter\";" in workspace
    assert "const proseAdapter = useMemo<MonacoEditorLike | null>" in workspace
    assert "createProseEditorAdapter(proseEditorEl" in workspace
    assert "editor={proseAdapter}" in workspace
    assert "onMount={setProseEditorEl}" in workspace
    assert "setProseRefreshToken((n) => n + 1);" in workspace

    assert "export function createProseEditorAdapter" in adapter
    assert "domPositionToLatexOffset" in adapter
    assert "latexOffsetToDomPosition" in adapter
    assert "getScrolledVisiblePosition" in adapter

    assert "export function domPositionToLatexOffset" in domMap
    assert "export function latexOffsetToDomPosition" in domMap


def test_writer_prose_editor_renders_latex_macros() -> None:
    editor = (REPO_ROOT / "frontend/components/WriterProseEditor.tsx").read_text()
    converter = (REPO_ROOT / "frontend/lib/latex-prose.ts").read_text()

    assert "contentEditable" in editor
    assert "suppressContentEditableWarning" in editor
    assert "containerRef.current.innerHTML = renderBlocksToHtml(" in editor
    assert "wp-cite" in editor
    assert "wp-todo" in editor
    assert "parseLatexToBlocks" in editor
    assert "serializeBlocksToLatex" in editor

    assert "export function parseLatexToBlocks" in converter
    assert "export function serializeBlocksToLatex" in converter
    assert "\\\\(textbf|emph|textit|cite|todo)" in converter
    assert "subsubsection" in converter


def test_sidebar_writer_nav_shows_beta_badge() -> None:
    sidebar = (REPO_ROOT / "frontend/components/Sidebar.tsx").read_text()

    assert "<span>Writer Workspace</span>" in sidebar
    assert "Beta" in sidebar
    assert "aria-label=\"Writer Workspace beta\"" in sidebar
    assert "title=\"Writer Workspace beta\"" in sidebar


def test_writer_chat_api_exports_client_functions() -> None:
    api_client = (REPO_ROOT / "frontend/lib/api.ts").read_text()

    assert "export async function createWriterChat" in api_client
    assert "export async function listWriterChats" in api_client
    assert "export async function getWriterChat" in api_client
    assert "export async function sendWriterChatMessage" in api_client
    assert "export async function acceptWriterChatPatch" in api_client
    assert "export async function rejectWriterChatPatch" in api_client
    assert "export async function undoWriterChatPatch" in api_client
    assert "export interface ChatSectionPatch" in api_client
    assert "export interface ChatMessage" in api_client
    assert "export interface ChatRead" in api_client
    assert "export interface ChatTurnRead" in api_client
    assert "`/writer/documents/${documentId}/chat`" in api_client
    assert "/message/${messageId}/patch/${patchIndex}/accept`" in api_client
    assert "/message/${messageId}/patch/${patchIndex}/reject`" in api_client
    assert "/message/${messageId}/patch/${patchIndex}/undo`" in api_client


def test_writer_chat_panel_is_mounted_in_workspace() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "WriterChatPanel" in workspace
    assert '"@/components/WriterChatPanel"' in workspace
    assert "<WriterChatPanel" in workspace
    assert "onScrollToInlineDiff={scrollToInlineDiff}" in workspace
    assert "onAfterPatchApplied={refreshDocument}" in workspace
    assert "onChatBusyChange={setChatApplyInFlight}" in workspace
    assert "onPatchesAvailable={handlePatchesAvailable}" in workspace
    assert "chatApplyInFlight" in workspace


def test_writer_chat_panel_renders_compact_rows_without_bulk_actions() -> None:
    panel = (REPO_ROOT / "frontend/components/WriterChatPanel.tsx").read_text()

    # Inline-diff blocks must no longer live in the chat panel — they moved to
    # WriterChatInlineDiff. The chat panel keeps rose-bg only for the credits
    # banner and emerald only in the compact "edits ready" pill.
    assert "line-through" not in panel
    assert "Accept all" not in panel
    assert "Reject all" not in panel
    assert "writer-chat-panel:" in panel
    assert "writer-chat-id:" in panel
    assert "text-rose-" in panel
    assert "createWriterChat" in panel
    assert "sendWriterChatMessage" in panel
    assert "acceptWriterChatPatch" in panel
    assert "rejectWriterChatPatch" in panel
    assert "undoWriterChatPatch" in panel
    assert "isInsufficientCreditsError" in panel
    assert "3 credits per turn" in panel
    # Compact row indicator text.
    assert "edits ready in editor" in panel
    assert "in editor" in panel


def test_writer_chat_panel_does_not_render_inline_diff_blocks() -> None:
    panel = (REPO_ROOT / "frontend/components/WriterChatPanel.tsx").read_text()
    inline = (REPO_ROOT / "frontend/components/WriterChatInlineDiff.tsx").read_text()

    # The old diff card classes for the original/strikethrough block must
    # not appear in the chat panel any more — they belong to the inline
    # overlay's CSS.
    assert "bg-rose-50 dark:bg-rose-950/30" not in panel
    # But the inline component owns the strikethrough class string and
    # uses Monaco APIs for decorations / view zones / content widgets.
    assert "writer-chat-removed" in inline
    assert "writer-chat-zone-block" in inline
    assert "writer-chat-accept-toolbar" in inline
    assert "writer-chat-flash" in inline


def test_writer_chat_inline_diff_uses_monaco_apis() -> None:
    inline = (REPO_ROOT / "frontend/components/WriterChatInlineDiff.tsx").read_text()

    assert "changeViewZones" in inline
    assert "addContentWidget" in inline
    assert "deltaDecorations" in inline
    assert "createPortal" in inline
    assert "acceptWriterChatPatch" in inline
    assert "rejectWriterChatPatch" in inline
    # Stale guard: 409 from accept flips the patch to a "draft changed" pill.
    assert "err.status === 409" in inline
    assert "Draft changed" in inline


def test_writer_workspace_mounts_inline_diff_and_prose_banner() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "WriterChatInlineDiff" in workspace
    assert "pendingChatPatches" in workspace
    assert "handlePatchesAvailable" in workspace
    assert "handleInlinePatchResolved" in workspace
    assert "scrollToInlineDiff" in workspace
    # Visual mode now mounts a working inline-diff overlay built on
    # latexOffsetToDomPosition + Range.getClientRects(). The previous
    # "Switch to source" pill has been replaced.
    assert "WriterChatInlineDiffProse" in workspace
    assert "switch to\n            source view to review." not in workspace
    assert ">Switch to source<" not in workspace


def test_writer_chat_inline_diff_prose_uses_dom_latex_map() -> None:
    prose = (REPO_ROOT / "frontend/components/WriterChatInlineDiffProse.tsx").read_text()

    # Must use the proper repo primitive (NOT DOM text search).
    assert "from \"@/lib/dom-latex-map\"" in prose
    assert "latexOffsetToDomPosition" in prose
    # Renders prose, not raw latex.
    assert "from \"@/lib/latex-prose\"" in prose
    assert "parseLatexToBlocks" in prose
    # Negative assertions: must not regress to text-based search of the DOM.
    assert ".indexOf(" not in prose
    assert ".findIndex(" not in prose
    # Negative assertions: must not import Monaco-only APIs.
    assert "deltaDecorations" not in prose
    assert "changeViewZones" not in prose
    assert "addContentWidget" not in prose
    # Reposition primitives must be wired.
    assert "MutationObserver" in prose
    assert "requestAnimationFrame" in prose
    assert "ResizeObserver" in prose
    # Range-based geometry.
    assert "getClientRects" in prose
    # Accept/reject + stale guard duplicated from source mode.
    assert "acceptWriterChatPatch" in prose
    assert "rejectWriterChatPatch" in prose
    assert "err.status === 409" in prose
    assert "Draft changed" in prose


def test_writer_workspace_mounts_prose_inline_diff_in_visual_mode() -> None:
    workspace = (REPO_ROOT / "frontend/components/WriterWorkspace.tsx").read_text()

    assert "import { WriterChatInlineDiffProse }" in workspace
    assert "<WriterChatInlineDiffProse" in workspace
    assert "proseAdapter={proseAdapter}" in workspace
    assert "onRequestSourceView={() => setViewMode(\"source\")}" in workspace


def test_sidebar_project_clicks_route_to_project_chat() -> None:
    sidebar = (REPO_ROOT / "frontend/components/Sidebar.tsx").read_text()

    assert "import { usePathname, useRouter } from \"next/navigation\";" in sidebar
    assert "const projectChatHref = `/chat?project=${projectId}`;" in sidebar
    assert "router.push(projectChatHref);" in sidebar
    assert "if (pathname !== \"/chat\")" in sidebar
    assert "onSelect={handleSelectProject}" in sidebar
