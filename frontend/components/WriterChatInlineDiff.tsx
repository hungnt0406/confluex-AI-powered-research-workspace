"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import {
  ApiError,
  ChatSectionPatch,
  WriterSectionRead,
  acceptWriterChatPatch,
  isInsufficientCreditsError,
  rejectWriterChatPatch,
} from "@/lib/api";
import type { MonacoEditorLike, MonacoPosition } from "@/components/WriterEditorOverlay";

export interface PendingChatPatch {
  key: string;
  chatId: string;
  messageId: string;
  patchIndex: number;
  patch: ChatSectionPatch;
}

// Subset of the runtime Monaco editor API we need beyond MonacoEditorLike.
// We layer this on top of the lighter MonacoEditorLike interface so we keep
// type-safety without forcing changes to the shared overlay types.
interface MonacoRange {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
}

interface MonacoDecorationOptions {
  isWholeLine?: boolean;
  inlineClassName?: string;
  className?: string;
  linesDecorationsClassName?: string;
  glyphMarginClassName?: string;
  hoverMessage?: { value: string };
}

interface MonacoDecorationDescriptor {
  range: MonacoRange;
  options: MonacoDecorationOptions;
}

interface MonacoViewZone {
  afterLineNumber: number;
  heightInPx: number;
  domNode: HTMLElement;
  suppressMouseDown?: boolean;
}

interface MonacoViewZoneAccessor {
  addZone: (zone: MonacoViewZone) => string;
  removeZone: (id: string) => void;
}

interface MonacoContentWidgetPosition {
  position: MonacoPosition;
  preference: number[];
}

interface MonacoContentWidget {
  getId: () => string;
  getDomNode: () => HTMLElement;
  getPosition: () => MonacoContentWidgetPosition | null;
}

interface MonacoEditorRichLike extends MonacoEditorLike {
  deltaDecorations?: (oldIds: string[], newDecorations: MonacoDecorationDescriptor[]) => string[];
  changeViewZones?: (callback: (accessor: MonacoViewZoneAccessor) => void) => void;
  addContentWidget?: (widget: MonacoContentWidget) => void;
  removeContentWidget?: (widget: MonacoContentWidget) => void;
  layoutContentWidget?: (widget: MonacoContentWidget) => void;
  revealRangeInCenter?: (range: MonacoRange, scrollType?: number) => void;
  getLayoutInfo?: () => { contentWidth?: number };
  getDomNode?: () => HTMLElement | null;
}

function measureZoneHeight(
  newText: string,
  contentWidth: number,
  fontFamily: string,
  fontSize: number,
): number {
  const probe = document.createElement("div");
  probe.className = "writer-chat-zone-block";
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  probe.style.left = "-10000px";
  probe.style.top = "0";
  probe.style.width = `${Math.max(120, contentWidth)}px`;
  probe.style.fontFamily = fontFamily;
  probe.style.fontSize = `${fontSize}px`;
  probe.style.whiteSpace = "pre-wrap";
  probe.style.overflowWrap = "anywhere";
  probe.textContent = newText;
  document.body.appendChild(probe);
  const height = probe.getBoundingClientRect().height;
  document.body.removeChild(probe);
  return Math.ceil(height) + 8;
}

export interface WriterChatInlineDiffProps {
  documentId: string;
  sections: WriterSectionRead[];
  activeSectionId: string | null;
  monacoEditor: MonacoEditorLike | null;
  token: string;
  pendingPatches: PendingChatPatch[];
  onPatchResolved: (patchKey: string, status: "applied" | "rejected" | "stale") => void;
  onAfterPatchApplied: () => void | Promise<void>;
  setChatBusy: (busy: boolean) => void;
  flashKey: string | null;
}

interface ResolvedPatch {
  entry: PendingChatPatch;
  globalStart: number;
  globalEnd: number;
  startLine: number;
  endLine: number;
  newTextLines: number;
}

const CONTENT_WIDGET_PREFERENCE_ABOVE = 1;
const CONTENT_WIDGET_PREFERENCE_BELOW = 2;

function resolvePatch(
  entry: PendingChatPatch,
  sections: WriterSectionRead[],
  activeSectionId: string | null,
  modelText: string | null,
): ResolvedPatch | null {
  if (!modelText) return null;
  // Monaco model only shows the active section's draft_latex. If the patch
  // targets a different section we cannot render an inline diff for it.
  if (entry.patch.section_id !== activeSectionId) return null;
  const section = sections.find((s) => s.id === entry.patch.section_id);
  if (!section) return null;
  const sectionDraft = section.draft_latex ?? "";
  const start = Math.max(0, Math.min(entry.patch.span.start, sectionDraft.length));
  const end = Math.max(start, Math.min(entry.patch.span.end, sectionDraft.length));
  // Stale guard: if the model text no longer contains the original_text at
  // [start,end] we still render with the offset we have but flag as stale.
  const startLine = (sectionDraft.slice(0, start).match(/\n/g)?.length ?? 0) + 1;
  const endLine = (sectionDraft.slice(0, end).match(/\n/g)?.length ?? 0) + 1;
  const newTextLines = Math.max(1, (entry.patch.new_text.match(/\n/g)?.length ?? 0) + 1);
  return {
    entry,
    globalStart: start,
    globalEnd: end,
    startLine,
    endLine,
    newTextLines,
  };
}

function createZoneNode(newText: string, isFlash: boolean): HTMLElement {
  const node = document.createElement("div");
  node.className = `writer-chat-zone-block${isFlash ? " writer-chat-flash" : ""}`;
  // Pre-line preserves \n while collapsing tabs gracefully.
  node.style.whiteSpace = "pre-wrap";
  node.textContent = newText;
  return node;
}

interface AcceptToolbarProps {
  resolved: ResolvedPatch;
  busy: boolean;
  stale: boolean;
  inFlightError: string | null;
  flash: boolean;
  onAccept: () => void;
  onReject: () => void;
}

function AcceptToolbar({
  resolved,
  busy,
  stale,
  inFlightError,
  flash,
  onAccept,
  onReject,
}: AcceptToolbarProps) {
  const rationale = resolved.entry.patch.rationale || "Suggested edit";
  const sectionTitle = resolved.entry.patch.section_title || "section";

  if (stale) {
    return (
      <div
        className={`writer-chat-accept-toolbar pointer-events-auto inline-flex items-center gap-1 rounded-full border border-rose-300/60 bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-700 shadow dark:border-rose-900/40 dark:bg-rose-950/40 dark:text-rose-200 ${
          flash ? "writer-chat-flash" : ""
        }`}
        title="The draft span no longer matches — ask again to regenerate."
      >
        <span aria-hidden="true">↻</span>
        Draft changed — ask again
      </div>
    );
  }

  return (
    <div
      className={`writer-chat-accept-toolbar pointer-events-auto inline-flex items-center gap-1 rounded-full border border-outline/30 bg-surface px-1 py-1 shadow-lg ring-1 ring-black/5 ${
        flash ? "writer-chat-flash" : ""
      }`}
      title={rationale}
    >
      <button
        type="button"
        onClick={onAccept}
        disabled={busy}
        className="inline-flex h-6 items-center gap-1 rounded-full bg-emerald-600 px-2.5 text-[11px] font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
        aria-label={`Accept inline edit for ${sectionTitle}`}
      >
        {busy ? (
          <span
            className="material-symbols-outlined animate-spin"
            style={{ fontSize: "12px" }}
            aria-hidden="true"
          >
            progress_activity
          </span>
        ) : (
          <span aria-hidden="true">✓</span>
        )}
        Accept
      </button>
      <button
        type="button"
        onClick={onReject}
        disabled={busy}
        className="inline-flex h-6 items-center gap-1 rounded-full border border-outline/30 bg-surface-container-lowest px-2.5 text-[11px] font-semibold text-on-surface hover:bg-primary/5 disabled:opacity-50"
        aria-label={`Reject inline edit for ${sectionTitle}`}
      >
        <span aria-hidden="true">✕</span>
        Reject
      </button>
      {inFlightError && (
        <span className="ml-1 max-w-[200px] truncate text-[10px] font-normal text-rose-600">
          {inFlightError}
        </span>
      )}
    </div>
  );
}

export function WriterChatInlineDiff({
  documentId,
  sections,
  activeSectionId,
  monacoEditor,
  token,
  pendingPatches,
  onPatchResolved,
  onAfterPatchApplied,
  setChatBusy,
  flashKey,
}: WriterChatInlineDiffProps) {
  const editorRich = monacoEditor as MonacoEditorRichLike | null;
  const [portalRoots, setPortalRoots] = useState<Record<string, HTMLElement>>({});
  const [busyKeys, setBusyKeys] = useState<Set<string>>(() => new Set());
  const [staleKeys, setStaleKeys] = useState<Set<string>>(() => new Set());
  const [errorByKey, setErrorByKey] = useState<Record<string, string>>({});
  const [creditsExhausted, setCreditsExhausted] = useState(false);

  const decorationIdsRef = useRef<string[]>([]);
  const zoneIdsRef = useRef<string[]>([]);
  const widgetsRef = useRef<MonacoContentWidget[]>([]);
  const staleTimersRef = useRef<Map<string, number>>(new Map());

  const modelText = useMemo(() => {
    const model = editorRich?.getModel?.();
    return model?.getValue() ?? null;
  }, [editorRich, pendingPatches]);

  const resolved = useMemo<ResolvedPatch[]>(() => {
    return pendingPatches
      .map((entry) => resolvePatch(entry, sections, activeSectionId, modelText))
      .filter((p): p is ResolvedPatch => p !== null);
  }, [pendingPatches, sections, activeSectionId, modelText]);

  // Mount Monaco decorations + view zones + content widgets whenever the
  // resolved set changes.
  useEffect(() => {
    if (!editorRich) return undefined;
    const model = editorRich.getModel?.();
    if (!model) return undefined;
    if (typeof document === "undefined") return undefined;

    const decorations: MonacoDecorationDescriptor[] = resolved.map((p) => {
      const startPos = model.getPositionAt(p.globalStart);
      const endPos = model.getPositionAt(p.globalEnd);
      const rationale = p.entry.patch.rationale || "Suggested edit";
      return {
        range: {
          startLineNumber: startPos.lineNumber,
          startColumn: startPos.column,
          endLineNumber: endPos.lineNumber,
          endColumn: endPos.column,
        },
        options: {
          inlineClassName: "writer-chat-removed",
          hoverMessage: { value: rationale },
        },
      };
    });

    // Apply decorations.
    if (typeof editorRich.deltaDecorations === "function") {
      decorationIdsRef.current = editorRich.deltaDecorations(
        decorationIdsRef.current,
        decorations,
      );
    }

    // Build view zones for the new_text block and content widgets for the
    // Accept/Reject toolbar. Each widget gets its own portal root so the
    // React state for buttons stays alive across rerenders.
    const newPortals: Record<string, HTMLElement> = {};
    const newZoneIds: string[] = [];
    const newWidgets: MonacoContentWidget[] = [];

    if (typeof editorRich.changeViewZones === "function") {
      // Measure each new_text block against the editor's actual content width
      // so wrapped paragraphs get enough vertical room. \n count is unreliable
      // because Monaco wraps long lines but the zone is a plain DOM block.
      const layout = editorRich.getLayoutInfo?.();
      const contentWidth = layout?.contentWidth ?? 720;
      const editorDom = editorRich.getDomNode?.();
      const computed = editorDom ? window.getComputedStyle(editorDom) : null;
      const fontFamily = computed?.fontFamily ?? "system-ui, sans-serif";
      const fontSize = computed ? parseFloat(computed.fontSize) || 13 : 13;
      editorRich.changeViewZones((accessor) => {
        // Remove previous zones.
        for (const id of zoneIdsRef.current) {
          try {
            accessor.removeZone(id);
          } catch {
            /* ignore */
          }
        }
        for (const p of resolved) {
          const isFlash = flashKey === p.entry.key;
          const node = createZoneNode(p.entry.patch.new_text, isFlash);
          const measured = measureZoneHeight(
            p.entry.patch.new_text,
            contentWidth - 28, // subtract our padding so the probe matches the visible width
            fontFamily,
            fontSize,
          );
          const heightInPx = Math.max(28, measured);
          const zoneId = accessor.addZone({
            afterLineNumber: p.endLine,
            heightInPx,
            domNode: node,
            suppressMouseDown: false,
          });
          newZoneIds.push(zoneId);
        }
      });
    }
    zoneIdsRef.current = newZoneIds;

    // Remove previous widgets.
    if (typeof editorRich.removeContentWidget === "function") {
      for (const w of widgetsRef.current) {
        try {
          editorRich.removeContentWidget(w);
        } catch {
          /* ignore */
        }
      }
    }

    if (typeof editorRich.addContentWidget === "function") {
      for (const p of resolved) {
        const node = document.createElement("div");
        node.style.pointerEvents = "auto";
        // Anchor the toolbar at the top-right of the diff block so it doesn't
        // overlap the new-text view zone (Cursor-style position).
        const widgetId = `writer-chat-inline-${p.entry.key}`;
        const position: MonacoContentWidgetPosition = {
          position: {
            lineNumber: p.startLine,
            column: Number.MAX_SAFE_INTEGER,
          },
          preference: [CONTENT_WIDGET_PREFERENCE_ABOVE, CONTENT_WIDGET_PREFERENCE_BELOW],
        };
        const widget: MonacoContentWidget = {
          getId: () => widgetId,
          getDomNode: () => node,
          getPosition: () => position,
        };
        try {
          editorRich.addContentWidget(widget);
          newWidgets.push(widget);
          newPortals[p.entry.key] = node;
        } catch {
          /* ignore */
        }
      }
    }
    widgetsRef.current = newWidgets;
    setPortalRoots(newPortals);

    return () => {
      // Tear down decorations.
      if (typeof editorRich.deltaDecorations === "function") {
        try {
          editorRich.deltaDecorations(decorationIdsRef.current, []);
        } catch {
          /* ignore */
        }
        decorationIdsRef.current = [];
      }
      // Tear down view zones.
      if (typeof editorRich.changeViewZones === "function") {
        editorRich.changeViewZones((accessor) => {
          for (const id of newZoneIds) {
            try {
              accessor.removeZone(id);
            } catch {
              /* ignore */
            }
          }
        });
        zoneIdsRef.current = [];
      }
      // Tear down content widgets.
      if (typeof editorRich.removeContentWidget === "function") {
        for (const w of newWidgets) {
          try {
            editorRich.removeContentWidget(w);
          } catch {
            /* ignore */
          }
        }
        widgetsRef.current = [];
      }
    };
  }, [editorRich, resolved, flashKey]);

  // Auto-clear stale flags after 5s so the editor doesn't keep a dead pill.
  useEffect(() => {
    const timers = staleTimersRef.current;
    return () => {
      timers.forEach((id) => window.clearTimeout(id));
      timers.clear();
    };
  }, []);

  const markStale = (key: string) => {
    setStaleKeys((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    const existing = staleTimersRef.current.get(key);
    if (existing) window.clearTimeout(existing);
    const timerId = window.setTimeout(() => {
      onPatchResolved(key, "stale");
      staleTimersRef.current.delete(key);
    }, 5000);
    staleTimersRef.current.set(key, timerId);
  };

  const setBusy = (key: string, busy: boolean) => {
    setBusyKeys((prev) => {
      const next = new Set(prev);
      if (busy) next.add(key);
      else next.delete(key);
      return next;
    });
    setChatBusy(busy);
  };

  const handleAccept = async (p: ResolvedPatch) => {
    const key = p.entry.key;
    setBusy(key, true);
    setErrorByKey((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    try {
      await acceptWriterChatPatch(
        documentId,
        p.entry.chatId,
        p.entry.messageId,
        p.entry.patchIndex,
        token,
      );
      onPatchResolved(key, "applied");
      await onAfterPatchApplied();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        markStale(key);
      } else if (isInsufficientCreditsError(err)) {
        setCreditsExhausted(true);
        setErrorByKey((prev) => ({ ...prev, [key]: "Out of credits" }));
      } else {
        setErrorByKey((prev) => ({
          ...prev,
          [key]: err instanceof Error ? err.message : "Accept failed",
        }));
      }
    } finally {
      setBusy(key, false);
    }
  };

  const handleReject = async (p: ResolvedPatch) => {
    const key = p.entry.key;
    setBusy(key, true);
    setErrorByKey((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    try {
      await rejectWriterChatPatch(
        documentId,
        p.entry.chatId,
        p.entry.messageId,
        p.entry.patchIndex,
        token,
      );
      onPatchResolved(key, "rejected");
    } catch (err) {
      setErrorByKey((prev) => ({
        ...prev,
        [key]: err instanceof Error ? err.message : "Reject failed",
      }));
    } finally {
      setBusy(key, false);
    }
  };

  if (!editorRich) return null;

  // The CSS for inline diff styling. Kept inline so this component is
  // self-contained and we don't need a separate global CSS file edit.
  const globalStyles = (
    <style jsx global>{`
      .writer-chat-removed {
        background: rgba(254, 226, 226, 0.55);
        color: rgb(159, 18, 57);
      }
      .dark .writer-chat-removed {
        background: rgba(159, 18, 57, 0.22);
        color: rgb(254, 202, 202);
      }
      .writer-chat-zone-block {
        background: rgba(220, 252, 231, 0.55);
        border-left: 3px solid rgb(16, 185, 129);
        padding: 8px 14px;
        font-size: 13px;
        line-height: 1.55;
        color: rgb(6, 78, 59);
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }
      .dark .writer-chat-zone-block {
        background: rgba(6, 78, 59, 0.28);
        color: rgb(209, 250, 229);
      }
      .writer-chat-accept-toolbar {
        transform: translate(-8px, 4px);
      }
      .writer-chat-flash {
        animation: writer-chat-flash-kf 1.2s ease-out 1;
      }
      @keyframes writer-chat-flash-kf {
        0% {
          box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.55);
          background-color: rgba(16, 185, 129, 0.18);
        }
        70% {
          box-shadow: 0 0 0 10px rgba(16, 185, 129, 0);
        }
        100% {
          box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
        }
      }
    `}</style>
  );

  return (
    <div role="status" aria-live="polite" className="contents">
      <span className="sr-only">
        {resolved.length > 0
          ? `${resolved.length} suggested ${resolved.length === 1 ? "edit" : "edits"} available`
          : ""}
      </span>
      {globalStyles}
      {creditsExhausted && (
        <div className="pointer-events-auto fixed bottom-4 left-1/2 z-[80] -translate-x-1/2 rounded-full border border-rose-200/60 bg-rose-50 px-4 py-2 text-[11px] font-semibold text-rose-700 shadow dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-200">
          Out of credits.{" "}
          <Link className="underline" href="/billing">
            Top up
          </Link>{" "}
          to accept inline edits.
        </div>
      )}
      {resolved.map((p) => {
        const node = portalRoots[p.entry.key];
        if (!node) return null;
        const busy = busyKeys.has(p.entry.key);
        const stale = staleKeys.has(p.entry.key);
        const inFlightError = errorByKey[p.entry.key] ?? null;
        const flash = flashKey === p.entry.key;
        return createPortal(
          <AcceptToolbar
            key={p.entry.key}
            resolved={p}
            busy={busy}
            stale={stale}
            inFlightError={inFlightError}
            flash={flash}
            onAccept={() => void handleAccept(p)}
            onReject={() => void handleReject(p)}
          />,
          node,
        );
      })}
    </div>
  );
}
