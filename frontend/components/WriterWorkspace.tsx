"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  WriterDocumentRead,
  WriterSectionRead,
  applyOutline,
  assembleDocument,
  exportDocument,
  proposeOutline,
  saveSectionEdit,
  updateWriterDocument,
} from "@/lib/api";
import { WriterOutlinePanel } from "@/components/WriterOutlinePanel";
import { WriterSourcesPanel } from "@/components/WriterSourcesPanel";
import { WriterQuestionsPanel } from "@/components/WriterQuestionsPanel";
import { WriterQAPanel } from "@/components/WriterQAPanel";

// Dynamic import Monaco to avoid SSR issues.
// If @monaco-editor/react is not installed, the import will fail and we fall back to a textarea.
const MonacoEditor = dynamic(
  () =>
    import("@monaco-editor/react")
      .then((mod) => mod.default)
      .catch(() => {
        // Return a React component that renders null — parent switches to textarea fallback
        const Fallback = () => null;
        Fallback.displayName = "MonacoFallback";
        return Fallback;
      }),
  { ssr: false },
);

type RightTab = "questions" | "sources" | "qa";

interface WriterWorkspaceProps {
  initialDocument: WriterDocumentRead;
  token: string;
}

function AssembleModal({
  result,
  onClose,
}: {
  result: { tex: string; bib: string; unresolved_todo_count: number; warnings: string[] };
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"tex" | "bib">("tex");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Assembled LaTeX output"
    >
      <div className="flex h-[80vh] w-[720px] max-w-[96vw] flex-col rounded-2xl border border-outline/20 bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-outline/20 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-on-surface">Assembled Document</h2>
            {result.unresolved_todo_count > 0 && (
              <p className="mt-0.5 text-[11px] text-amber-600">
                {result.unresolved_todo_count} unresolved \todo tags remain
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-primary/5 transition-colors"
            aria-label="Close"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>close</span>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-outline/20">
          {(["tex", "bib"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-xs font-semibold transition-colors ${
                tab === t
                  ? "border-b-2 border-primary text-primary"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
            >
              {t === "tex" ? "main.tex" : "references.bib"}
            </button>
          ))}
        </div>

        {/* Warnings */}
        {result.warnings.length > 0 && (
          <div className="shrink-0 mx-4 mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 space-y-0.5">
            {result.warnings.map((w, i) => (
              <p key={i} className="text-[11px] text-amber-700">{w}</p>
            ))}
          </div>
        )}

        {/* Content */}
        <pre className="flex-1 overflow-auto custom-scrollbar m-4 rounded-xl border border-outline/15 bg-stone-950 p-4 text-[11px] leading-relaxed text-green-300 font-mono whitespace-pre-wrap">
          {tab === "tex" ? result.tex : result.bib}
        </pre>
      </div>
    </div>
  );
}

function TextareaEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (val: string) => void;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-full w-full resize-none bg-stone-950 p-5 text-sm leading-relaxed text-green-200 font-mono outline-none"
      spellCheck={false}
      aria-label="LaTeX editor"
    />
  );
}

function LaTeXEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (val: string) => void;
}) {
  const [useTextarea, setUseTextarea] = useState(false);

  // If window is not available (SSR), show textarea
  if (typeof window === "undefined" || useTextarea) {
    return <TextareaEditor value={value} onChange={onChange} />;
  }

  return (
    <MonacoEditor
      height="100%"
      defaultLanguage="latex"
      value={value}
      onChange={(v) => {
        // If v is undefined Monaco may have failed to load; fall back to textarea
        if (v === undefined) { setUseTextarea(true); return; }
        onChange(v);
      }}
      theme="vs-dark"
      options={{
        fontSize: 13,
        lineHeight: 22,
        wordWrap: "on",
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        padding: { top: 20, bottom: 20 },
      }}
      onMount={(_editor, monaco) => {
        if (!monaco) { setUseTextarea(true); return; }
        const langs = monaco.languages.getLanguages();
        if (!langs.find((l: { id: string }) => l.id === "latex")) {
          monaco.languages.register({ id: "latex" });
        }
      }}
    />
  );
}

export function WriterWorkspace({ initialDocument, token }: WriterWorkspaceProps) {
  const [document, setDocument] = useState<WriterDocumentRead>(initialDocument);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(
    initialDocument.sections[0]?.id ?? null,
  );
  const [rightTab, setRightTab] = useState<RightTab>("questions");
  const [editorContent, setEditorContent] = useState<string>("");
  const [proposingOutline, setProposingOutline] = useState(false);
  const [savingOutline, setSavingOutline] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [assembleResult, setAssembleResult] = useState<{
    tex: string;
    bib: string;
    unresolved_todo_count: number;
    warnings: string[];
  } | null>(null);
  const [titleDraft, setTitleDraft] = useState(initialDocument.title);
  const [editingTitle, setEditingTitle] = useState(false);
  const [savingTitle, setSavingTitle] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedContentRef = useRef<string>("");
  const titleInputRef = useRef<HTMLInputElement | null>(null);

  const activeSection = document.sections.find((s) => s.id === activeSectionId) ?? null;
  const chatHref = `/chat?project=${document.project_id}`;

  // Sync editor content when active section changes
  useEffect(() => {
    const content = activeSection?.draft_latex ?? "";
    setEditorContent(content);
    lastSavedContentRef.current = content;
  }, [activeSectionId]); // intentional: only reset on section switch

  // Focus title input when editing
  useEffect(() => {
    if (editingTitle) {
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }
  }, [editingTitle]);

  // Auto-save debounced
  const handleEditorChange = useCallback(
    (value: string) => {
      setEditorContent(value);

      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);

      saveTimerRef.current = setTimeout(async () => {
        if (!activeSection || value === lastSavedContentRef.current) return;
        try {
          const updated = await saveSectionEdit(document.id, activeSection.id, value, token);
          lastSavedContentRef.current = value;
          setDocument((prev) => ({
            ...prev,
            sections: prev.sections.map((s) => (s.id === updated.id ? updated : s)),
          }));
        } catch {
          // Silent auto-save failure — user can retry manually
        }
      }, 1000);
    },
    [activeSection, document.id, token],
  );

  // Cleanup timer
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  const handleSectionUpdate = useCallback((section: WriterSectionRead) => {
    setDocument((prev) => ({
      ...prev,
      sections: prev.sections.map((s) => (s.id === section.id ? section : s)),
    }));
    // Sync editor if this is the active section
    if (section.id === activeSectionId) {
      const newContent = section.draft_latex ?? "";
      setEditorContent(newContent);
      lastSavedContentRef.current = newContent;
    }
  }, [activeSectionId]);

  const handleProposeOutline = useCallback(async () => {
    setProposingOutline(true);
    setError(null);
    try {
      const { outline_by_section } = await proposeOutline(document.id, token);
      // Auto-apply the proposed outline
      const updated = await applyOutline(document.id, outline_by_section, token);
      setDocument(updated);
      if (!activeSectionId && updated.sections.length > 0) {
        setActiveSectionId(updated.sections[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to propose outline.");
    } finally {
      setProposingOutline(false);
    }
  }, [document.id, token, activeSectionId]);

  const handleSaveOutline = useCallback(async () => {
    setSavingOutline(true);
    setError(null);
    try {
      const outline_by_section: Record<string, string> = {};
      for (const s of document.sections) {
        outline_by_section[s.id] = s.outline_text ?? "";
      }
      const updated = await applyOutline(document.id, outline_by_section, token);
      setDocument(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save outline.");
    } finally {
      setSavingOutline(false);
    }
  }, [document, token]);

  const handleAssemble = useCallback(async () => {
    setAssembling(true);
    setError(null);
    try {
      const result = await assembleDocument(document.id, token);
      setAssembleResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assembly failed.");
    } finally {
      setAssembling(false);
    }
  }, [document.id, token]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    setError(null);
    try {
      const blob = await exportDocument(document.id, token);
      const url = URL.createObjectURL(blob);
      const a = window.document.createElement("a");
      a.href = url;
      a.download = `${document.title.replace(/\s+/g, "_")}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  }, [document.id, document.title, token]);

  const handleTitleSave = useCallback(async () => {
    const next = titleDraft.trim();
    if (!next || next === document.title) {
      setEditingTitle(false);
      setTitleDraft(document.title);
      return;
    }
    setSavingTitle(true);
    try {
      const updated = await updateWriterDocument(document.id, { title: next }, token);
      setDocument(updated);
      setTitleDraft(updated.title);
      setEditingTitle(false);
    } catch {
      // keep editing
    } finally {
      setSavingTitle(false);
    }
  }, [document.id, document.title, titleDraft, token]);

  const RIGHT_TABS: { id: RightTab; label: string; icon: string }[] = [
    { id: "questions", label: "Questions", icon: "quiz" },
    { id: "sources", label: "Sources", icon: "book_2" },
    { id: "qa", label: "QA", icon: "fact_check" },
  ];

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background font-ui text-on-surface">
      {/* Top bar */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-outline/20 bg-surface-container px-4">
        {/* Editable title */}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Link
            href={chatHref}
            aria-label="Back to chat workspace"
            title="Back to chat workspace"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-primary hover:bg-primary/10 transition-colors"
          >
            <svg
              viewBox="0 0 62 60"
              width={24}
              height={24}
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              {[
                "M 4,50 C 8,35 18,15 32,6",
                "M 9,52 C 13,36 24,16 39,7",
                "M 14,53 C 19,37 30,17 45,8",
                "M 19,54 C 25,38 36,18 51,9",
                "M 24,55 C 30,39 42,19 56,10",
                "M 29,55 C 36,40 47,21 58,14",
                "M 33,54 C 40,41 51,24 58,20",
                "M 37,53 C 43,42 53,27 57,26",
                "M 40,52 C 45,43 53,31 56,32",
              ].map((d, i) => (
                <path key={i} d={d} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none" />
              ))}
            </svg>
          </Link>
          {editingTitle ? (
            <form
              className="flex min-w-0 flex-1 items-center gap-1.5"
              onSubmit={(e) => { e.preventDefault(); void handleTitleSave(); }}
            >
              <input
                ref={titleInputRef}
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                disabled={savingTitle}
                maxLength={255}
                className="h-7 min-w-0 flex-1 rounded-md border border-primary/40 bg-background px-2.5 text-sm font-semibold text-on-surface outline-none focus:border-primary/70 transition-colors"
                aria-label="Document title"
              />
              <button
                type="submit"
                disabled={savingTitle}
                className="flex h-7 w-7 items-center justify-center rounded-md text-on-surface-variant hover:bg-primary/10 transition-colors disabled:opacity-40"
                aria-label="Save title"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>check</span>
              </button>
              <button
                type="button"
                disabled={savingTitle}
                onClick={() => { setEditingTitle(false); setTitleDraft(document.title); }}
                className="flex h-7 w-7 items-center justify-center rounded-md text-on-surface-variant hover:bg-primary/10 transition-colors disabled:opacity-40"
                aria-label="Cancel title edit"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>close</span>
              </button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setEditingTitle(true)}
              className="group flex min-w-0 items-center gap-1.5 rounded-md px-1.5 py-0.5 hover:bg-primary/5 transition-colors"
              aria-label={`Edit title: ${document.title}`}
            >
              <span className="truncate text-sm font-semibold text-on-surface">{document.title}</span>
              <span
                className="material-symbols-outlined shrink-0 text-hint opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ fontSize: "14px" }}
              >
                edit
              </span>
            </button>
          )}
        </div>

        {/* Document meta */}
        <div className="hidden items-center gap-2 sm:flex">
          <span className="rounded-full border border-outline/20 bg-surface-container-low px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">
            {document.paper_type}
          </span>
          <span className="rounded-full border border-outline/20 bg-surface-container-low px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">
            {document.citation_style}
          </span>
        </div>

        {/* Error inline */}
        {error && (
          <div className="hidden max-w-xs truncate rounded-lg border border-rose-500/20 bg-rose-50 px-3 py-1 text-[11px] text-rose-700 md:block">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleAssemble()}
            disabled={assembling || exporting}
            className="flex h-8 items-center gap-1.5 rounded-full border border-outline/25 bg-surface-container-lowest px-3 text-xs font-semibold text-on-surface hover:bg-primary/5 hover:border-primary/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {assembling ? (
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>code</span>
            )}
            {assembling ? "Assembling…" : "Assemble"}
          </button>
          <button
            type="button"
            onClick={() => void handleExport()}
            disabled={assembling || exporting}
            className="flex h-8 items-center gap-1.5 rounded-full bg-primary px-3 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {exporting ? (
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>download</span>
            )}
            {exporting ? "Exporting…" : "Export"}
          </button>
        </div>
      </header>

      {/* Error banner (mobile fallback) */}
      {error && (
        <div className="shrink-0 border-b border-rose-500/20 bg-rose-50 px-4 py-2 text-[11px] text-rose-700 md:hidden">
          {error}
          <button type="button" onClick={() => setError(null)} className="ml-2 text-rose-500 hover:text-rose-700">
            <span className="material-symbols-outlined" style={{ fontSize: "12px" }}>close</span>
          </button>
        </div>
      )}

      {/* 3-column workspace */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Outline (20%) */}
        <div className="w-[220px] shrink-0">
          <WriterOutlinePanel
            document={document}
            activeSectionId={activeSectionId}
            onSectionClick={setActiveSectionId}
            onProposeOutline={handleProposeOutline}
            onSaveOutline={handleSaveOutline}
            proposingOutline={proposingOutline}
            savingOutline={savingOutline}
          />
        </div>

        {/* Center: Monaco Editor (flex-1) */}
        <div className="flex flex-1 flex-col overflow-hidden bg-stone-950">
          {/* Section header bar */}
          {activeSection ? (
            <div className="flex h-9 shrink-0 items-center gap-2 border-b border-stone-800 px-4">
              <span
                className="material-symbols-outlined text-stone-400"
                style={{ fontSize: "14px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
                aria-hidden="true"
              >
                article
              </span>
              <span className="text-xs font-medium text-stone-300">{activeSection.title}</span>
              <span className={`ml-auto rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${
                activeSection.status === "user_edited"
                  ? "bg-emerald-900 text-emerald-300"
                  : activeSection.status === "drafted"
                  ? "bg-sky-900 text-sky-300"
                  : activeSection.status === "awaiting_input"
                  ? "bg-amber-900 text-amber-300"
                  : "bg-stone-700 text-stone-400"
              }`}>
                {activeSection.status.replace(/_/g, " ")}
              </span>
            </div>
          ) : (
            <div className="flex h-9 shrink-0 items-center gap-2 border-b border-stone-800 px-4">
              <span className="text-xs text-stone-500">No section selected</span>
            </div>
          )}

          {/* Editor */}
          <div className="flex-1 overflow-hidden">
            {activeSection ? (
              <LaTeXEditor value={editorContent} onChange={handleEditorChange} />
            ) : (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <span
                    className="material-symbols-outlined text-stone-600"
                    style={{ fontSize: "40px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 40" }}
                    aria-hidden="true"
                  >
                    article
                  </span>
                  <p className="mt-3 text-sm text-stone-500">Select a section to start editing</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Tabbed Panel (300px) */}
        <div className="flex w-[300px] shrink-0 flex-col overflow-hidden border-l border-outline/20">
          {/* Tab bar */}
          <div className="flex h-9 shrink-0 items-stretch border-b border-outline/20 bg-surface-container">
            {RIGHT_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setRightTab(tab.id)}
                className={`flex flex-1 items-center justify-center gap-1 text-[11px] font-semibold transition-colors ${
                  rightTab === tab.id
                    ? "border-b-2 border-primary text-primary bg-primary/5"
                    : "text-on-surface-variant hover:text-on-surface hover:bg-primary/5"
                }`}
                aria-selected={rightTab === tab.id}
                role="tab"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
                  {tab.icon}
                </span>
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden" role="tabpanel">
            {rightTab === "questions" && (
              <WriterQuestionsPanel
                documentId={document.id}
                activeSection={activeSection}
                token={token}
                onSectionUpdate={handleSectionUpdate}
              />
            )}
            {rightTab === "sources" && (
              <WriterSourcesPanel
                document={document}
                token={token}
                onDocumentUpdate={setDocument}
              />
            )}
            {rightTab === "qa" && (
              <WriterQAPanel documentId={document.id} token={token} />
            )}
          </div>
        </div>
      </div>

      {/* Assemble modal */}
      {assembleResult && (
        <AssembleModal result={assembleResult} onClose={() => setAssembleResult(null)} />
      )}
    </div>
  );
}
