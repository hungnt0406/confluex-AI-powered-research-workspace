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


def test_sidebar_writer_nav_shows_beta_badge() -> None:
    sidebar = (REPO_ROOT / "frontend/components/Sidebar.tsx").read_text()

    assert "<span>Writer</span>" in sidebar
    assert "Beta" in sidebar
    assert "aria-label=\"Writer beta\"" in sidebar
    assert "title=\"Writer beta\"" in sidebar


def test_sidebar_project_clicks_route_to_project_chat() -> None:
    sidebar = (REPO_ROOT / "frontend/components/Sidebar.tsx").read_text()

    assert "import { usePathname, useRouter } from \"next/navigation\";" in sidebar
    assert "const projectChatHref = `/chat?project=${projectId}`;" in sidebar
    assert "router.push(projectChatHref);" in sidebar
    assert "if (pathname !== \"/chat\")" in sidebar
    assert "onSelect={handleSelectProject}" in sidebar
