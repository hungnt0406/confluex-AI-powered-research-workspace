"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  ChatSectionPatch,
  TextSpan,
  WriterDocumentRead,
  WriterSectionRead,
  assembleDocument,
  exportDocument,
  getWriterDocument,
  loadUser,
  saveSectionEdit,
  updateWriterDocument,
} from "@/lib/api";
import { WriterOutlinePanel } from "@/components/WriterOutlinePanel";
import { MonacoEditorLike, WriterEditorOverlay } from "@/components/WriterEditorOverlay";
import { WriterProseEditor } from "@/components/WriterProseEditor";
import { createProseEditorAdapter } from "@/lib/prose-editor-adapter";
import { WriterSourcesPanel } from "@/components/WriterSourcesPanel";
import { WriterQuestionsPanel } from "@/components/WriterQuestionsPanel";
import { WriterQAPanel } from "@/components/WriterQAPanel";
import {
  ChatPatchStatusUpdate,
  WriterChatPanel,
} from "@/components/WriterChatPanel";
import {
  PendingChatPatch,
  WriterChatInlineDiff,
} from "@/components/WriterChatInlineDiff";
import { WriterChatInlineDiffProse } from "@/components/WriterChatInlineDiffProse";
import { formatRelativeTime } from "@/lib/time";
import {
  WriterShortcutsModal,
  type WriterShortcutOverlayHandle,
  useWriterShortcuts,
} from "@/hooks/useWriterShortcuts";

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
type EditorViewMode = "visual" | "source";
type SaveStatus = "idle" | "saving" | "saved" | "error";

const WRITER_OUTLINE_PANEL_WIDTH = 220;
const WRITER_EDITOR_MIN_WIDTH = 280;
const WRITER_RIGHT_PANEL_MIN_WIDTH = 360;
const WRITER_RIGHT_PANEL_MAX_WIDTH = 720;

interface WriterWorkspaceProps {
  initialDocument: WriterDocumentRead;
  token: string;
}

function SaveStatusPill({
  status,
  lastSavedAt,
  error,
  onRetry,
}: {
  status: SaveStatus;
  lastSavedAt: number | null;
  error: string | null;
  onRetry: () => void;
}) {
  if (status === "idle") return null;

  if (status === "saving") {
    return (
      <span
        aria-live="polite"
        className="inline-flex items-center gap-1 text-stone-500"
      >
        <span
          className="material-symbols-outlined animate-spin"
          style={{ fontSize: "13px" }}
          aria-hidden="true"
        >
          progress_activity
        </span>
        Saving…
      </span>
    );
  }

  if (status === "saved") {
    return (
      <span
        aria-live="polite"
        className="inline-flex items-center gap-1 text-emerald-600"
      >
        <span
          className="material-symbols-outlined"
          style={{ fontSize: "13px" }}
          aria-hidden="true"
        >
          check_circle
        </span>
        Saved {lastSavedAt ? formatRelativeTime(new Date(lastSavedAt).toISOString()) : "just now"}
      </span>
    );
  }

  return (
    <span
      aria-live="polite"
      className="inline-flex items-center gap-1.5 text-red-600"
      title={error ?? "Save failed"}
    >
      <span
        className="material-symbols-outlined"
        style={{ fontSize: "13px" }}
        aria-hidden="true"
      >
        warning
      </span>
      Save failed
      <button
        type="button"
        onClick={onRetry}
        aria-label="Retry saving section"
        className="rounded-full border border-red-200 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 hover:bg-red-50"
      >
        Retry
      </button>
    </span>
  );
}

function findScrollAncestor(el: HTMLElement | null): HTMLElement | null {
  if (!el || typeof window === "undefined") return null;
  let cur: HTMLElement | null = el.parentElement;
  while (cur) {
    const overflowY = window.getComputedStyle(cur).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") return cur;
    cur = cur.parentElement;
  }
  return null;
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
            <span className="material-symbols-outlined" style={{ fontSize: "18px" }} aria-hidden="true">close</span>
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
  onMountEditor,
}: {
  value: string;
  onChange: (val: string) => void;
  onMountEditor: (editor: MonacoEditorLike | null) => void;
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
      onMount={(editor, monaco) => {
        if (!monaco) { setUseTextarea(true); return; }
        const langs = monaco.languages.getLanguages();
        if (!langs.find((l: { id: string }) => l.id === "latex")) {
          monaco.languages.register({ id: "latex" });
        }
        onMountEditor(editor as MonacoEditorLike);
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
  const [rightPanelWidth, setRightPanelWidth] = useState<number>(480);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState<boolean>(true);
  const [editorContent, setEditorContent] = useState<string>("");
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
  const [monacoEditor, setMonacoEditor] = useState<MonacoEditorLike | null>(null);
  const [hasPendingEditorPatch, setHasPendingEditorPatch] = useState(false);
  const [chatApplyInFlight, setChatApplyInFlight] = useState(false);
  const [viewMode, setViewMode] = useState<EditorViewMode>("visual");
  const [proseEditorEl, setProseEditorEl] = useState<HTMLElement | null>(null);
  const [proseRefreshToken, setProseRefreshToken] = useState(0);
  const editorContentRef = useRef<string>("");
  const [historyBySection, setHistoryBySection] = useState<
    Record<string, { past: string[]; present: string; future: string[] }>
  >({});
  const [pendingChatPatches, setPendingChatPatches] = useState<PendingChatPatch[]>([]);
  const [chatPatchStatusUpdates, setChatPatchStatusUpdates] = useState<
    ChatPatchStatusUpdate[]
  >([]);
  const [inlineFlashKey, setInlineFlashKey] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatButtonY, setChatButtonY] = useState<number | null>(null);
  const chatButtonDragRef = useRef<{ startY: number; startOffsetY: number; didDrag: boolean } | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedContentRef = useRef<string>("");
  const saveGenerationRef = useRef(0);
  const activeSectionIdRef = useRef<string | null>(activeSectionId);
  const editorRootRef = useRef<HTMLDivElement | null>(null);
  const editorOverlayRef = useRef<WriterShortcutOverlayHandle | null>(null);
  const titleInputRef = useRef<HTMLInputElement | null>(null);
  const rightPanelDraggingRef = useRef(false);
  const rightPanelStartXRef = useRef(0);
  const rightPanelStartWidthRef = useRef(0);

  const activeSection = document.sections.find((s) => s.id === activeSectionId) ?? null;
  activeSectionIdRef.current = activeSectionId;
  const chatHref = document.project_id ? `/chat?project=${document.project_id}` : "/writer";
  const writerChatUserId = useMemo(() => loadUser()?.id ?? "anon", []);
  const shortcuts = useWriterShortcuts({
    overlayRef: editorOverlayRef,
    editorRootRef,
  });

  const clampRightPanelWidth = useCallback((width: number) => {
    const viewportMax =
      window.innerWidth - WRITER_OUTLINE_PANEL_WIDTH - WRITER_EDITOR_MIN_WIDTH;
    const maxWidth = Math.max(
      WRITER_RIGHT_PANEL_MIN_WIDTH,
      Math.min(WRITER_RIGHT_PANEL_MAX_WIDTH, viewportMax),
    );
    return Math.round(Math.min(Math.max(width, WRITER_RIGHT_PANEL_MIN_WIDTH), maxWidth));
  }, []);

  const handleRightPanelMouseMove = useCallback(
    (event: MouseEvent) => {
      if (!rightPanelDraggingRef.current) return;
      const delta = rightPanelStartXRef.current - event.clientX;
      setRightPanelWidth(clampRightPanelWidth(rightPanelStartWidthRef.current + delta));
    },
    [clampRightPanelWidth],
  );

  const handleRightPanelMouseUp = useCallback(() => {
    if (!rightPanelDraggingRef.current) return;
    rightPanelDraggingRef.current = false;
    window.document.body.style.userSelect = "";
    window.document.body.style.cursor = "";
    window.removeEventListener("mousemove", handleRightPanelMouseMove);
    window.removeEventListener("mouseup", handleRightPanelMouseUp);
  }, [handleRightPanelMouseMove]);

  const handleRightPanelMouseDown = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      event.preventDefault();
      rightPanelDraggingRef.current = true;
      rightPanelStartXRef.current = event.clientX;
      rightPanelStartWidthRef.current = rightPanelWidth;
      window.document.body.style.userSelect = "none";
      window.document.body.style.cursor = "col-resize";
      window.addEventListener("mousemove", handleRightPanelMouseMove);
      window.addEventListener("mouseup", handleRightPanelMouseUp);
    },
    [handleRightPanelMouseMove, handleRightPanelMouseUp, rightPanelWidth],
  );

  const handleRightPanelKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setRightPanelWidth((width) => clampRightPanelWidth(width + 32));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setRightPanelWidth((width) => clampRightPanelWidth(width - 32));
      }
    },
    [clampRightPanelWidth],
  );

  useEffect(() => {
    setRightPanelWidth(clampRightPanelWidth(window.innerWidth * 0.4));
    const handleResize = () => {
      setRightPanelWidth((width) => clampRightPanelWidth(width));
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [clampRightPanelWidth]);

  useEffect(() => {
    return () => {
      window.removeEventListener("mousemove", handleRightPanelMouseMove);
      window.removeEventListener("mouseup", handleRightPanelMouseUp);
      if (rightPanelDraggingRef.current) {
        window.document.body.style.userSelect = "";
        window.document.body.style.cursor = "";
      }
    };
  }, [handleRightPanelMouseMove, handleRightPanelMouseUp]);

  // Sync editor content when active section changes
  useEffect(() => {
    const content = activeSection?.draft_latex ?? "";
    setEditorContent(content);
    editorContentRef.current = content;
    lastSavedContentRef.current = content;
    saveGenerationRef.current += 1;
    setSaveStatus("idle");
    setLastSavedAt(null);
    setSaveError(null);
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (activeSectionId) {
      setHistoryBySection((prev) => {
        if (prev[activeSectionId]) return prev;
        return { ...prev, [activeSectionId]: { past: [], present: content, future: [] } };
      });
    }
  }, [activeSectionId]); // intentional: only reset on section switch

  // Keep the ref in sync so the prose-editor adapter sees the latest LaTeX.
  editorContentRef.current = editorContent;

  const proseAdapter = useMemo<MonacoEditorLike | null>(() => {
    if (!proseEditorEl) return null;
    return createProseEditorAdapter(proseEditorEl, () => editorContentRef.current);
  }, [proseEditorEl]);

  const HISTORY_LIMIT = 50;

  const pushHistory = useCallback((sectionId: string, content: string) => {
    setHistoryBySection((prev) => {
      const entry = prev[sectionId];
      if (!entry) {
        return { ...prev, [sectionId]: { past: [], present: content, future: [] } };
      }
      if (entry.present === content) return prev;
      const past = [...entry.past, entry.present].slice(-HISTORY_LIMIT);
      return { ...prev, [sectionId]: { past, present: content, future: [] } };
    });
  }, []);

  const activeHistory = activeSectionId ? historyBySection[activeSectionId] : undefined;
  const canUndo = (activeHistory?.past.length ?? 0) > 0;
  const canRedo = (activeHistory?.future.length ?? 0) > 0;
  const editorMetrics = useMemo(() => {
    const trimmed = editorContent.trim();
    const words = trimmed ? trimmed.split(/\s+/).length : 0;
    const paragraphs = trimmed ? trimmed.split(/\n\s*\n/).filter(Boolean).length : 0;
    const minutes = Math.max(1, Math.round(words / 200));
    return { words, paragraphs, minutes };
  }, [editorContent]);
  const editorMetricsLabel =
    editorMetrics.words === 0
      ? "Empty section"
      : `${editorMetrics.words} ${editorMetrics.words === 1 ? "word" : "words"} · ${
          editorMetrics.paragraphs
        } ¶ · ~${editorMetrics.minutes} ${
          editorMetrics.minutes === 1 ? "min" : "mins"
        }`;

  // Focus title input when editing
  useEffect(() => {
    if (editingTitle) {
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }
  }, [editingTitle]);

  const persistSectionContent = useCallback(
    async (sectionId: string, value: string, generation: number) => {
      const isCurrentSection = () =>
        activeSectionIdRef.current === sectionId && saveGenerationRef.current === generation;

      if (isCurrentSection()) {
        setSaveStatus("saving");
      }

      try {
        const updated = await saveSectionEdit(document.id, sectionId, value, token);
        if (isCurrentSection()) {
          lastSavedContentRef.current = value;
          setLastSavedAt(Date.now());
          setSaveStatus("saved");
          setSaveError(null);
        }
        setDocument((prev) => ({
          ...prev,
          sections: prev.sections.map((s) => (s.id === updated.id ? updated : s)),
        }));
        pushHistory(sectionId, value);
      } catch (err) {
        if (isCurrentSection()) {
          setSaveStatus("error");
          setSaveError(err instanceof Error ? err.message : "Save failed");
        }
      }
    },
    [document.id, pushHistory, token],
  );

  // Auto-save debounced
  const handleEditorChange = useCallback(
    (value: string) => {
      setEditorContent(value);

      if (hasPendingEditorPatch) return;
      if (chatApplyInFlight) return;

      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);

      const sectionId = activeSection?.id;
      saveGenerationRef.current += 1;
      const generation = saveGenerationRef.current;
      saveTimerRef.current = setTimeout(() => {
        saveTimerRef.current = null;
        if (!sectionId) return;
        if (value === lastSavedContentRef.current) {
          setSaveStatus("idle");
          return;
        }
        void persistSectionContent(sectionId, value, generation);
      }, 1000);
    },
    [
      activeSection?.id,
      chatApplyInFlight,
      hasPendingEditorPatch,
      persistSectionContent,
    ],
  );

  const retrySave = useCallback(() => {
    if (!activeSection) return;
    void persistSectionContent(
      activeSection.id,
      editorContentRef.current,
      saveGenerationRef.current,
    );
  }, [activeSection, persistSectionContent]);

  // Refresh the document from the server (called after a chat-driven patch is applied).
  const refreshDocument = useCallback(async () => {
    try {
      const fresh = await getWriterDocument(document.id, token);
      setDocument(fresh);
      const activeFresh = fresh.sections.find((s) => s.id === activeSectionId);
      if (activeFresh) {
        // Bumping proseRefreshToken re-mounts WriterProseEditor (uncontrolled
        // contenteditable). The remount resets scrollTop on whichever
        // ancestor of the editor element scrolls — so the user gets snapped
        // to the top of the document the moment they Accept a chat patch.
        // Snapshot scroll position before the remount and restore it on the
        // next two animation frames (one for React commit, one for paint).
        const scrollEl = findScrollAncestor(proseEditorEl);
        const savedScrollTop = scrollEl?.scrollTop ?? 0;
        const next = activeFresh.draft_latex ?? "";
        setEditorContent(next);
        editorContentRef.current = next;
        lastSavedContentRef.current = next;
        setProseRefreshToken((n) => n + 1);
        if (scrollEl && typeof window !== "undefined") {
          window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
              scrollEl.scrollTop = savedScrollTop;
            });
          });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh document.");
    }
  }, [activeSectionId, document.id, proseEditorEl, token]);

  const flashSpan = useCallback(
    (span: TextSpan) => {
      const editor =
        viewMode === "visual" ? proseAdapter : (monacoEditor as MonacoEditorLike | null);
      const model = editor?.getModel?.() ?? null;
      if (!editor || !model) return;
      try {
        const startPos = model.getPositionAt(Math.max(0, span.start));
        const dom = editor.getDomNode?.();
        const visible = editor.getScrolledVisiblePosition(startPos);
        if (dom && visible) {
          const rect = dom.getBoundingClientRect();
          const indicator = window.document.createElement("div");
          indicator.style.position = "fixed";
          indicator.style.left = `${rect.left + visible.left - 4}px`;
          indicator.style.top = `${rect.top + visible.top - 2}px`;
          indicator.style.height = `${Math.max(visible.height, 18)}px`;
          indicator.style.width = "4px";
          indicator.style.background = "rgba(16, 185, 129, 0.75)";
          indicator.style.borderRadius = "2px";
          indicator.style.transition = "opacity 0.6s ease-out";
          indicator.style.zIndex = "9999";
          indicator.style.pointerEvents = "none";
          window.document.body.appendChild(indicator);
          window.setTimeout(() => {
            indicator.style.opacity = "0";
          }, 600);
          window.setTimeout(() => indicator.remove(), 1200);
        }
      } catch {
        /* ignore */
      }
    },
    [monacoEditor, proseAdapter, viewMode],
  );

  // Scroll Monaco (or the prose adapter) to a span in a section and flash it.
  const scrollToSection = useCallback(
    (sectionId: string, span: TextSpan) => {
      if (sectionId !== activeSectionId) {
        setActiveSectionId(sectionId);
        // Defer the scroll-and-flash until the next paint when the section content swaps in.
        window.setTimeout(() => flashSpan(span), 80);
        return;
      }
      flashSpan(span);
    },
    [activeSectionId, flashSpan],
  );

  // ----- Chat inline diff plumbing -----
  const handlePatchesAvailable = useCallback(
    (chatId: string, messageId: string, patches: ChatSectionPatch[]) => {
      setPendingChatPatches((prev) => {
        const seen = new Set(prev.map((p) => p.key));
        const additions: PendingChatPatch[] = [];
        patches.forEach((patch, idx) => {
          if (patch.status !== "pending") return;
          const key = `${chatId}:${messageId}:${idx}`;
          if (seen.has(key)) return;
          additions.push({
            key,
            chatId,
            messageId,
            patchIndex: idx,
            patch,
          });
        });
        if (additions.length === 0) return prev;
        return [...prev, ...additions];
      });
    },
    [],
  );

  const handleInlinePatchResolved = useCallback(
    (patchKey: string, status: "applied" | "rejected" | "stale") => {
      let resolved: PendingChatPatch | null = null;
      setPendingChatPatches((prev) => {
        const next: PendingChatPatch[] = [];
        for (const entry of prev) {
          if (entry.key === patchKey) {
            resolved = entry;
            continue;
          }
          next.push(entry);
        }
        return next;
      });
      if (resolved) {
        const r = resolved as PendingChatPatch;
        setChatPatchStatusUpdates((prev) => [
          ...prev,
          { messageId: r.messageId, patchIndex: r.patchIndex, status },
        ]);
      }
    },
    [],
  );

  const scrollToInlineDiff = useCallback(
    (messageId: string, patchIndex: number) => {
      const entry = pendingChatPatches.find(
        (p) => p.messageId === messageId && p.patchIndex === patchIndex,
      );
      if (!entry) return;
      // If the patch targets a different section, switch first.
      if (entry.patch.section_id !== activeSectionId) {
        setActiveSectionId(entry.patch.section_id);
        window.setTimeout(() => {
          setInlineFlashKey(entry.key);
          flashSpan(entry.patch.span);
          window.setTimeout(() => setInlineFlashKey(null), 1400);
        }, 120);
        return;
      }
      setInlineFlashKey(entry.key);
      flashSpan(entry.patch.span);
      window.setTimeout(() => setInlineFlashKey(null), 1400);
    },
    [activeSectionId, flashSpan, pendingChatPatches],
  );

  const closeChatPanel = useCallback(() => {
    setChatOpen(false);
  }, []);

  const requestSourceView = useCallback(() => {
    setViewMode("source");
  }, []);

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
      editorContentRef.current = newContent;
      lastSavedContentRef.current = newContent;
      pushHistory(section.id, newContent);
      // Force a remount of the uncontrolled prose editor so AI patches show.
      setProseRefreshToken((n) => n + 1);
    }
  }, [activeSectionId, pushHistory]);

  const applyHistoricalContent = useCallback(
    async (sectionId: string, content: string) => {
      setEditorContent(content);
      editorContentRef.current = content;
      lastSavedContentRef.current = content;
      // Force the uncontrolled prose editor to remount with the historical text.
      setProseRefreshToken((n) => n + 1);
      // Cancel any pending autosave so it doesn't overwrite the restored state.
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
      try {
        const updated = await saveSectionEdit(document.id, sectionId, content, token);
        setDocument((prev) => ({
          ...prev,
          sections: prev.sections.map((s) => (s.id === updated.id ? updated : s)),
        }));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to persist undo/redo.");
      }
    },
    [document.id, token],
  );

  const handleUndo = useCallback(() => {
    if (!activeSectionId) return;
    setHistoryBySection((prev) => {
      const entry = prev[activeSectionId];
      if (!entry || entry.past.length === 0) return prev;
      const newPresent = entry.past[entry.past.length - 1];
      const newPast = entry.past.slice(0, -1);
      const newFuture = [entry.present, ...entry.future].slice(0, HISTORY_LIMIT);
      void applyHistoricalContent(activeSectionId, newPresent);
      return {
        ...prev,
        [activeSectionId]: { past: newPast, present: newPresent, future: newFuture },
      };
    });
  }, [activeSectionId, applyHistoricalContent]);

  const handleRedo = useCallback(() => {
    if (!activeSectionId) return;
    setHistoryBySection((prev) => {
      const entry = prev[activeSectionId];
      if (!entry || entry.future.length === 0) return prev;
      const newPresent = entry.future[0];
      const newFuture = entry.future.slice(1);
      const newPast = [...entry.past, entry.present].slice(-HISTORY_LIMIT);
      void applyHistoricalContent(activeSectionId, newPresent);
      return {
        ...prev,
        [activeSectionId]: { past: newPast, present: newPresent, future: newFuture },
      };
    });
  }, [activeSectionId, applyHistoricalContent]);

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
      <a
        href="#writer-editor"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-xs focus:font-semibold focus:text-white"
      >
        Skip to editor
      </a>
      {/* Top bar */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-outline/20 bg-surface-container px-4">
        {/* Editable title */}
        <div id="ob-titlebox" className="flex min-w-0 flex-1 items-center gap-2">
          <Link
            href={chatHref}
            aria-label={document.project_id ? "Back to chat workspace" : "Back to writer documents"}
            title={document.project_id ? "Back to chat workspace" : "Back to writer documents"}
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
                <span className="material-symbols-outlined" style={{ fontSize: "14px" }} aria-hidden="true">check</span>
              </button>
              <button
                type="button"
                disabled={savingTitle}
                onClick={() => { setEditingTitle(false); setTitleDraft(document.title); }}
                className="flex h-7 w-7 items-center justify-center rounded-md text-on-surface-variant hover:bg-primary/10 transition-colors disabled:opacity-40"
                aria-label="Cancel title edit"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "14px" }} aria-hidden="true">close</span>
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
                aria-hidden="true"
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
        <div id="ob-export" className="flex items-center gap-2">
          <div className="flex items-center gap-0.5 rounded-full border border-outline/20 bg-surface-container-lowest p-0.5">
            <button
              type="button"
              onClick={handleUndo}
              disabled={!canUndo}
              aria-label="Undo"
              title="Undo"
              className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface hover:bg-primary/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }} aria-hidden="true">undo</span>
            </button>
            <button
              type="button"
              onClick={handleRedo}
              disabled={!canRedo}
              aria-label="Redo"
              title="Redo"
              className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface hover:bg-primary/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }} aria-hidden="true">redo</span>
            </button>
          </div>
          <button
            type="button"
            onClick={() => void handleAssemble()}
            disabled={assembling || exporting}
            className="flex h-8 items-center gap-1.5 rounded-full border border-outline/25 bg-surface-container-lowest px-3 text-xs font-semibold text-on-surface hover:bg-primary/5 hover:border-primary/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {assembling ? (
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }} aria-hidden="true">
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }} aria-hidden="true">code</span>
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
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }} aria-hidden="true">
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }} aria-hidden="true">download</span>
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
            <span className="material-symbols-outlined" style={{ fontSize: "12px" }} aria-hidden="true">close</span>
          </button>
        </div>
      )}

      {/* 3-column workspace */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Outline (20%) */}
        <div id="ob-outline" className="w-[220px] shrink-0">
          <WriterOutlinePanel
            document={document}
            activeSectionId={activeSectionId}
            onSectionClick={setActiveSectionId}
          />
        </div>

        {/* Center: Editor (flex-1) */}
        <div
          id="ob-editor"
          ref={editorRootRef}
          className={`flex flex-1 flex-col overflow-hidden ${viewMode === "source" ? "bg-stone-950" : "bg-stone-50"}`}
        >
          {/* Section header bar */}
          {activeSection ? (
            <div className={`flex h-9 shrink-0 items-center gap-2 border-b px-4 ${viewMode === "source" ? "border-stone-800" : "border-stone-200"}`}>
              <span
                className={`material-symbols-outlined ${viewMode === "source" ? "text-stone-400" : "text-stone-500"}`}
                style={{ fontSize: "14px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
                aria-hidden="true"
              >
                article
              </span>
              <span className={`text-xs font-medium ${viewMode === "source" ? "text-stone-300" : "text-stone-700"}`}>
                {activeSection.title}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${
                viewMode === "source"
                  ? activeSection.status === "user_edited"
                    ? "bg-emerald-900 text-emerald-300"
                    : activeSection.status === "drafted"
                    ? "bg-sky-900 text-sky-300"
                    : activeSection.status === "awaiting_input"
                    ? "bg-amber-900 text-amber-300"
                    : "bg-stone-700 text-stone-400"
                  : activeSection.status === "user_edited"
                    ? "bg-emerald-100 text-emerald-700"
                    : activeSection.status === "drafted"
                    ? "bg-sky-100 text-sky-700"
                    : activeSection.status === "awaiting_input"
                    ? "bg-amber-100 text-amber-700"
                    : "bg-stone-200 text-stone-600"
              }`}>
                {activeSection.status.replace(/_/g, " ")}
              </span>
              <div
                role="tablist"
                aria-label="Editor view mode"
                className={`ml-auto flex items-center rounded-full p-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  viewMode === "source" ? "bg-stone-800" : "bg-stone-200"
                }`}
              >
                {(["visual", "source"] as const).map((mode) => {
                  const active = viewMode === mode;
                  return (
                    <button
                      key={mode}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      onClick={() => setViewMode(mode)}
                      className={`flex h-5 items-center gap-1 rounded-full px-2 transition-colors ${
                        active
                          ? viewMode === "source"
                            ? "bg-stone-700 text-white"
                            : "bg-white text-stone-800 shadow-sm"
                          : viewMode === "source"
                            ? "text-stone-400 hover:text-stone-200"
                            : "text-stone-500 hover:text-stone-800"
                      }`}
                      title={mode === "visual" ? "Visual prose editor" : "LaTeX source editor"}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "12px" }} aria-hidden="true">
                        {mode === "visual" ? "edit_note" : "code"}
                      </span>
                      {mode}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className={`flex h-9 shrink-0 items-center gap-2 border-b px-4 ${viewMode === "source" ? "border-stone-800" : "border-stone-200"}`}>
              <span className={`text-xs ${viewMode === "source" ? "text-stone-500" : "text-stone-500"}`}>
                No section selected
              </span>
            </div>
          )}

          {/* Prose-mode chat-patch inline diff renders absolute overlays inside
              the prose editor's root — no banner needed. */}

          {/* Editor */}
          <div
            id="writer-editor"
            tabIndex={0}
            className="relative flex-1 overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-primary/45 focus-visible:ring-inset"
          >
            {!chatOpen && (
              <button
                type="button"
                onClick={() => {
                  if (!chatButtonDragRef.current?.didDrag) setChatOpen(true);
                  chatButtonDragRef.current = null;
                }}
                onMouseDown={(e) => {
                  const rect = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect();
                  const btnRect = e.currentTarget.getBoundingClientRect();
                  chatButtonDragRef.current = {
                    startY: e.clientY,
                    startOffsetY: btnRect.top - rect.top + btnRect.height / 2,
                    didDrag: false,
                  };
                  const DRAG_THRESHOLD_PX = 4;
                  const onMove = (me: MouseEvent) => {
                    if (!chatButtonDragRef.current) return;
                    const delta = me.clientY - chatButtonDragRef.current.startY;
                    if (!chatButtonDragRef.current.didDrag && Math.abs(delta) < DRAG_THRESHOLD_PX) return;
                    chatButtonDragRef.current.didDrag = true;
                    const newY = chatButtonDragRef.current.startOffsetY + delta;
                    const clampedY = Math.max(20, Math.min(rect.height - 20, newY));
                    setChatButtonY(clampedY);
                  };
                  const onUp = () => {
                    window.removeEventListener("mousemove", onMove);
                    window.removeEventListener("mouseup", onUp);
                  };
                  window.addEventListener("mousemove", onMove);
                  window.addEventListener("mouseup", onUp);
                }}
                aria-label="Open document chat"
                style={chatButtonY !== null ? { top: chatButtonY, transform: "translateY(-50%)" } : undefined}
                className={`absolute ${chatButtonY === null ? "top-3/4 -translate-y-1/2" : ""} right-0 z-10 inline-flex cursor-grab items-center gap-2 rounded-l-full rounded-r-none border-y border-l px-4 py-2.5 text-sm font-semibold shadow-md transition-shadow hover:shadow-lg active:cursor-grabbing ${
                  viewMode === "source"
                    ? "border-stone-700 bg-stone-900 text-stone-200 hover:bg-stone-800"
                    : "border-outline/20 bg-surface text-on-surface hover:bg-primary/5"
                }`}
              >
                <svg viewBox="0 0 62 60" width="18" height="18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" className="shrink-0">
                  <path d="M 4,50 C 8,35 18,15 32,6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 9,52 C 13,36 24,16 39,7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 14,53 C 19,37 30,17 45,8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 19,54 C 25,38 36,18 51,9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 24,55 C 30,39 42,19 56,10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 29,55 C 36,40 47,21 58,14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 33,54 C 40,41 51,24 58,20" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 37,53 C 43,42 53,27 57,26" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  <path d="M 40,52 C 45,43 53,31 56,32" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                </svg>
                Chat
              </button>
            )}
            {activeSection ? (
              <>
                <div className="flex shrink-0 items-center justify-end gap-3 px-12 pt-3 pb-1 text-[12px] text-stone-500">
                  <span className="rounded-full bg-stone-200/70 px-2 py-0.5 text-[11px] text-stone-500">
                    Press ? for shortcuts
                  </span>
                  <SaveStatusPill
                    status={saveStatus}
                    lastSavedAt={lastSavedAt}
                    error={saveError}
                    onRetry={retrySave}
                  />
                  <span>{editorMetricsLabel}</span>
                  {saveStatus !== "saved" && (
                    <span>Edited {formatRelativeTime(activeSection.updated_at)}</span>
                  )}
                </div>
                {viewMode === "visual" ? (
                  <>
                    <WriterProseEditor
                      value={activeSection.draft_latex ?? ""}
                      onChange={handleEditorChange}
                      editorKey={`${activeSection.id}:${proseRefreshToken}`}
                      onMount={setProseEditorEl}
                    />
                    <WriterEditorOverlay
                      ref={editorOverlayRef}
                      editor={proseAdapter}
                      documentId={document.id}
                      section={activeSection}
                      token={token}
                      onSectionUpdate={handleSectionUpdate}
                      onPendingChange={setHasPendingEditorPatch}
                      onError={setError}
                      proseMode
                    />
                  </>
                ) : (
                  <>
                    <LaTeXEditor
                      value={editorContent}
                      onChange={handleEditorChange}
                      onMountEditor={setMonacoEditor}
                    />
                    <WriterEditorOverlay
                      ref={editorOverlayRef}
                      editor={monacoEditor}
                      documentId={document.id}
                      section={activeSection}
                      token={token}
                      onSectionUpdate={handleSectionUpdate}
                      onPendingChange={setHasPendingEditorPatch}
                      onError={setError}
                    />
                  </>
                )}
              </>
            ) : (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <span
                    className={`material-symbols-outlined ${viewMode === "source" ? "text-stone-600" : "text-stone-400"}`}
                    style={{ fontSize: "40px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 40" }}
                    aria-hidden="true"
                  >
                    article
                  </span>
                  <p className={`mt-3 text-sm ${viewMode === "source" ? "text-stone-500" : "text-stone-500"}`}>
                    Select a section to start editing
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Resizable tabbed panel */}
        {!isRightPanelOpen && (
          <button
            type="button"
            onClick={() => setIsRightPanelOpen(true)}
            aria-label="Open side panel"
            className="flex h-full w-8 shrink-0 items-center justify-center border-l border-outline/20 bg-surface-container text-on-surface-variant hover:bg-primary/5 hover:text-primary"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "20px" }} aria-hidden="true">
              chevron_left
            </span>
          </button>
        )}
        {isRightPanelOpen && (
        <div
          className="relative flex shrink-0 flex-col overflow-hidden border-l border-outline/20"
          style={{ width: `${rightPanelWidth}px` }}
        >
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize writer side panel"
            aria-valuemin={WRITER_RIGHT_PANEL_MIN_WIDTH}
            aria-valuemax={WRITER_RIGHT_PANEL_MAX_WIDTH}
            aria-valuenow={rightPanelWidth}
            tabIndex={0}
            onMouseDown={handleRightPanelMouseDown}
            onKeyDown={handleRightPanelKeyDown}
            className="absolute left-0 top-0 z-20 h-full w-2 -translate-x-1 cursor-col-resize outline-none transition-colors hover:bg-primary/30 focus:bg-primary/30"
          />
          {/* Tab bar */}
          <div id="ob-tabs" className="flex h-9 shrink-0 items-stretch border-b border-outline/20 bg-surface-container">
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
                <span className="material-symbols-outlined" style={{ fontSize: "14px" }} aria-hidden="true">
                  {tab.icon}
                </span>
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            ))}
            <button
              type="button"
              onClick={() => setIsRightPanelOpen(false)}
              aria-label="Close side panel"
              className="flex h-full w-9 items-center justify-center border-l border-outline/20 text-on-surface-variant hover:bg-primary/5 hover:text-primary"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }} aria-hidden="true">
                chevron_right
              </span>
            </button>
          </div>

          {/* Tab content */}
          <div id="ob-questions" className="flex-1 overflow-hidden" role="tabpanel">
            {rightTab === "questions" && (
              <WriterQuestionsPanel
                documentId={document.id}
                documentPaperType={document.paper_type}
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
        )}
      </div>

      {/* Assemble modal */}
      {assembleResult && (
        <AssembleModal result={assembleResult} onClose={() => setAssembleResult(null)} />
      )}

      {shortcuts.showCheatsheet && (
        <WriterShortcutsModal
          modifierLabel={shortcuts.modifierLabel}
          onClose={() => shortcuts.setShowCheatsheet(false)}
        />
      )}

      {/* Document chat panel (floating) */}
      <WriterChatPanel
        documentId={document.id}
        userId={writerChatUserId}
        token={token}
        sections={document.sections}
        onAfterPatchApplied={refreshDocument}
        onScrollToInlineDiff={scrollToInlineDiff}
        onChatBusyChange={setChatApplyInFlight}
        onPatchesAvailable={handlePatchesAvailable}
        externalPatchStatusUpdates={chatPatchStatusUpdates}
        open={chatOpen}
        onClose={closeChatPanel}
      />

      {/* Inline diff overlay. Source mode uses Monaco APIs (decorations / view zones).
          Visual mode renders coalesced strikethrough rects + a prose card via
          latexOffsetToDomPosition + range.getClientRects(). */}
      {viewMode === "source" && (
        <WriterChatInlineDiff
          documentId={document.id}
          sections={document.sections}
          activeSectionId={activeSectionId}
          monacoEditor={monacoEditor}
          token={token}
          pendingPatches={pendingChatPatches}
          onPatchResolved={handleInlinePatchResolved}
          onAfterPatchApplied={refreshDocument}
          setChatBusy={setChatApplyInFlight}
          flashKey={inlineFlashKey}
        />
      )}
      {viewMode === "visual" && (
        <WriterChatInlineDiffProse
          documentId={document.id}
          sections={document.sections}
          activeSectionId={activeSectionId}
          proseAdapter={proseAdapter}
          token={token}
          pendingPatches={pendingChatPatches}
          onPatchResolved={handleInlinePatchResolved}
          onAfterPatchApplied={refreshDocument}
          setChatBusy={setChatApplyInFlight}
          flashKey={inlineFlashKey}
          onRequestSourceView={requestSourceView}
        />
      )}
    </div>
  );
}
