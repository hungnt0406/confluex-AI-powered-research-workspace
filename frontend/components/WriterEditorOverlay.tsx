"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  EditPatchResponse,
  EditRequest,
  WriterSectionRead,
  applyWriterEdit,
  isInsufficientCreditsError,
  previewWriterEdit,
} from "@/lib/api";
import { domPositionToLatexOffset } from "@/lib/dom-latex-map";

export interface MonacoPosition {
  lineNumber: number;
  column: number;
}

export interface MonacoSelection {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
  isEmpty: () => boolean;
}

export interface MonacoModelLike {
  getValue: () => string;
  getOffsetAt: (position: MonacoPosition) => number;
  getPositionAt: (offset: number) => MonacoPosition;
  getLineContent: (lineNumber: number) => string;
  getLineCount: () => number;
}

export interface MonacoDisposable {
  dispose: () => void;
}

export interface MonacoEditorLike {
  getModel: () => MonacoModelLike | null;
  getDomNode?: () => HTMLElement | null;
  getSelection: () => MonacoSelection | null;
  getPosition: () => MonacoPosition | null;
  getScrolledVisiblePosition: (position: MonacoPosition) => { top: number; left: number; height: number } | null;
  onDidChangeCursorSelection: (listener: () => void) => MonacoDisposable;
  onDidChangeCursorPosition: (listener: () => void) => MonacoDisposable;
}

type Mode = "selection" | "insertion";

interface WriterEditorOverlayProps {
  editor: MonacoEditorLike | null;
  documentId: string;
  section: WriterSectionRead | null;
  token: string;
  onSectionUpdate: (section: WriterSectionRead) => void;
  onPendingChange: (pending: boolean) => void;
  onError: (message: string) => void;
  proseMode?: boolean;
}

interface FloatingPoint {
  top: number;
  left: number;
}

function buttonClass(primary = false) {
  return primary
    ? "inline-flex h-8 items-center gap-1.5 rounded-full bg-primary px-3 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
    : "inline-flex h-8 items-center gap-1.5 rounded-full border border-outline/20 bg-surface-container-lowest px-3 text-xs font-semibold text-on-surface hover:bg-primary/5 disabled:opacity-50";
}

function previewText(text: string) {
  return text.trim();
}

function spanFromSelection(model: MonacoModelLike, selection: MonacoSelection) {
  const start = model.getOffsetAt({
    lineNumber: selection.startLineNumber,
    column: selection.startColumn,
  });
  const end = model.getOffsetAt({
    lineNumber: selection.endLineNumber,
    column: selection.endColumn,
  });
  return { start: Math.min(start, end), end: Math.max(start, end) };
}

function editorViewportOrigin(editor: MonacoEditorLike): FloatingPoint {
  const rect = editor.getDomNode?.()?.getBoundingClientRect();
  return { top: rect?.top ?? 0, left: rect?.left ?? 0 };
}

function clampViewportLeft(left: number) {
  if (typeof window === "undefined") return Math.max(12, left);
  return Math.min(Math.max(12, left), Math.max(12, window.innerWidth - 464));
}

function positionForOffset(editor: MonacoEditorLike, model: MonacoModelLike, offset: number): FloatingPoint | null {
  const position = model.getPositionAt(Math.max(0, offset));
  const visible = editor.getScrolledVisiblePosition(position);
  if (!visible) return null;
  const origin = editorViewportOrigin(editor);
  return {
    top: Math.max(8, origin.top + visible.top - 44),
    left: clampViewportLeft(origin.left + visible.left),
  };
}

const POPOVER_WIDTH = 380;
const PATCH_CARD_WIDTH = 448;
const POPOVER_GAP = 12;
const POPOVER_EST_HEIGHT = 360;

interface PopoverPlacement {
  top: number;
  left: number;
  maxHeight: number;
}

interface PlacementOptions {
  width?: number;
  estHeight?: number;
}

function popoverPlacement(
  editor: MonacoEditorLike,
  startPos: MonacoPosition,
  endPos: MonacoPosition,
  { width = POPOVER_WIDTH, estHeight = POPOVER_EST_HEIGHT }: PlacementOptions = {},
): PopoverPlacement | null {
  const startVisible = editor.getScrolledVisiblePosition(startPos);
  if (!startVisible) return null;
  const endVisible = editor.getScrolledVisiblePosition(endPos) ?? startVisible;
  const origin = editorViewportOrigin(editor);
  const editorRect = editor.getDomNode?.()?.getBoundingClientRect();
  const viewportW = typeof window === "undefined" ? 1280 : window.innerWidth;
  const viewportH = typeof window === "undefined" ? 800 : window.innerHeight;
  const editorRight = editorRect ? editorRect.right : viewportW;

  const isMultiLine = startPos.lineNumber !== endPos.lineNumber;
  const preferredLeft = isMultiLine
    ? editorRight - width - 12
    : origin.left + endVisible.left + POPOVER_GAP;
  const maxLeft = Math.min(editorRight, viewportW) - width - 12;
  const left = Math.max(12, Math.min(preferredLeft, Math.max(12, maxLeft)));

  const desiredTop = origin.top + startVisible.top;
  const maxTop = viewportH - estHeight - 12;
  const top = Math.max(12, Math.min(desiredTop, Math.max(12, maxTop)));
  const maxHeight = Math.max(220, viewportH - top - 16);
  return { top, left, maxHeight };
}

function isBetweenParagraphs(model: MonacoModelLike, position: MonacoPosition | null) {
  if (!position) return false;
  const line = model.getLineContent(position.lineNumber).trim();
  const prev = position.lineNumber > 1 ? model.getLineContent(position.lineNumber - 1).trim() : "";
  const next =
    position.lineNumber < model.getLineCount()
      ? model.getLineContent(position.lineNumber + 1).trim()
      : "";
  return line === "" && (prev !== "" || next !== "");
}

export function WriterEditorOverlay({
  editor,
  documentId,
  section,
  token,
  onSectionUpdate,
  onPendingChange,
  onError,
  proseMode = false,
}: WriterEditorOverlayProps) {
  const [selection, setSelection] = useState<MonacoSelection | null>(null);
  const [selectionPoint, setSelectionPoint] = useState<FloatingPoint | null>(null);
  const [insertPoint, setInsertPoint] = useState<FloatingPoint | null>(null);
  const [insertOffset, setInsertOffset] = useState<number | null>(null);
  const [pendingPatch, setPendingPatch] = useState<EditPatchResponse | null>(null);
  const [panelMode, setPanelMode] = useState<Mode | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastRequest, setLastRequest] = useState<EditRequest | null>(null);
  const [prompt, setPrompt] = useState("");
  const [findings, setFindings] = useState("");
  const [findingsOpen, setFindingsOpen] = useState(false);
  const [sourceRef, setSourceRef] = useState("");
  const [citeSource, setCiteSource] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [portalRoot, setPortalRoot] = useState<HTMLElement | null>(null);

  const panelModeRef = useRef(panelMode);
  panelModeRef.current = panelMode;
  const pendingPatchRef = useRef(pendingPatch);
  pendingPatchRef.current = pendingPatch;

  const model = useMemo(() => editor?.getModel() ?? null, [editor]);
  const patchPlacement = useMemo<PopoverPlacement | null>(() => {
    if (!editor || !model || !pendingPatch) return null;
    const startPos = model.getPositionAt(pendingPatch.span.start);
    const endPos = model.getPositionAt(pendingPatch.span.end);
    return popoverPlacement(editor, startPos, endPos, {
      width: PATCH_CARD_WIDTH,
      estHeight: 320,
    });
  }, [editor, model, pendingPatch]);

  const panelPlacement = useMemo<PopoverPlacement | null>(() => {
    if (!editor || !model || !panelMode) return null;
    if (panelMode === "selection" && selection) {
      return popoverPlacement(
        editor,
        { lineNumber: selection.startLineNumber, column: selection.startColumn },
        { lineNumber: selection.endLineNumber, column: selection.endColumn },
      );
    }
    if (panelMode === "insertion" && insertOffset !== null) {
      const pos = model.getPositionAt(insertOffset);
      return popoverPlacement(editor, pos, pos);
    }
    return null;
  }, [editor, insertOffset, model, panelMode, selection]);

  useEffect(() => {
    onPendingChange(Boolean(pendingPatch));
  }, [onPendingChange, pendingPatch]);

  useEffect(() => {
    setPortalRoot(document.body);
  }, []);

  const refreshSelection = useCallback(() => {
    if (!editor || !model) return;
    const nextSelection = editor.getSelection();
    if (nextSelection && !nextSelection.isEmpty()) {
      setSelection(nextSelection);
      const point = positionForOffset(
        editor,
        model,
        model.getOffsetAt({
          lineNumber: nextSelection.startLineNumber,
          column: nextSelection.startColumn,
        }),
      );
      setSelectionPoint(point);
      setInsertPoint(null);
      return;
    }
    setSelection(null);
    setSelectionPoint(null);
  }, [editor, model]);

  const refreshCursor = useCallback(() => {
    if (proseMode) return;
    if (!editor || !model) return;
    const currentSelection = editor.getSelection();
    if (currentSelection && !currentSelection.isEmpty()) return;
    const position = editor.getPosition();
    if (!isBetweenParagraphs(model, position)) {
      setInsertPoint(null);
      setInsertOffset(null);
      return;
    }
    const visible = position ? editor.getScrolledVisiblePosition(position) : null;
    if (!visible || !position) return;
    const origin = editorViewportOrigin(editor);
    setInsertOffset(model.getOffsetAt(position));
    setInsertPoint({ top: origin.top + visible.top - 3, left: origin.left + 10 });
  }, [editor, model, proseMode]);

  useEffect(() => {
    if (!editor) return undefined;
    refreshSelection();
    refreshCursor();
    const selectionDisposable = editor.onDidChangeCursorSelection(refreshSelection);
    const positionDisposable = editor.onDidChangeCursorPosition(refreshCursor);
    return () => {
      selectionDisposable.dispose();
      positionDisposable.dispose();
    };
  }, [editor, refreshCursor, refreshSelection]);

  useEffect(() => {
    setPendingPatch(null);
    setPanelMode(null);
    setLastRequest(null);
  }, [section?.id]);

  // Prose mode: show + button when hovering between block elements.
  useEffect(() => {
    if (!proseMode) return undefined;
    const dom = editor?.getDomNode?.();
    if (!dom) return undefined;

    const handleMouseMove = (e: MouseEvent) => {
      if (panelModeRef.current || pendingPatchRef.current) return;
      const blocks = Array.from(
        dom.querySelectorAll(":scope > [data-block-type]"),
      ) as HTMLElement[];
      if (blocks.length < 2) {
        setInsertPoint(null);
        setInsertOffset(null);
        return;
      }
      for (let i = 0; i < blocks.length - 1; i++) {
        const above = blocks[i].getBoundingClientRect();
        const below = blocks[i + 1].getBoundingClientRect();
        if (e.clientY >= above.bottom - 6 && e.clientY <= below.top + 6) {
          const midY = (above.bottom + below.top) / 2;
          const editorRect = dom.getBoundingClientRect();
          setInsertOffset(domPositionToLatexOffset(dom, dom, i + 1));
          setInsertPoint({ top: midY - 12, left: Math.max(8, editorRect.left - 28) });
          return;
        }
      }
      setInsertPoint(null);
      setInsertOffset(null);
    };

    dom.addEventListener("mousemove", handleMouseMove);
    return () => {
      dom.removeEventListener("mousemove", handleMouseMove);
    };
  }, [proseMode, editor]);

  // Close an open Edit panel when the user clicks back into the editor.
  // Without this, panelMode stays "selection" indefinitely (e.g., if the user
  // dismisses the dialog by clicking outside it), and every later selection
  // change just repositions the stale dialog instead of showing a fresh pill.
  useEffect(() => {
    if (!editor) return undefined;
    const dom = editor.getDomNode?.();
    if (!dom) return undefined;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && dom.contains(target)) {
        setPanelMode(null);
        setPrompt("");
        setFindings("");
        setFindingsOpen(false);
        setSourceRef("");
        setCiteSource(false);
        setWebSearch(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [editor]);

  const resetPanel = useCallback(() => {
    setPanelMode(null);
    setPrompt("");
    setFindings("");
    setFindingsOpen(false);
    setSourceRef("");
    setCiteSource(false);
    setWebSearch(false);
  }, []);

  const selectedSpan = useCallback(() => {
    if (!model || !selection) return null;
    return spanFromSelection(model, selection);
  }, [model, selection]);

  const preview = useCallback(
    async (request: EditRequest) => {
      if (!section) return;
      setIsLoading(true);
      try {
        const patch = await previewWriterEdit(documentId, section.id, request, token);
        setPendingPatch(patch);
        setLastRequest(request);
        resetPanel();
      } catch (error) {
        // Reset the panel on failure too — otherwise panelMode stays set, the
        // floating Edit button stays hidden, and the user has no way back.
        resetPanel();
        if (isInsufficientCreditsError(error)) {
          onError(
            `Top up to continue. This edit needs ${error.required ?? "more"} credits and your balance is ${error.balance ?? 0}.`,
          );
        } else {
          onError(error instanceof Error ? error.message : "Writer edit failed.");
        }
      } finally {
        setIsLoading(false);
      }
    },
    [documentId, onError, resetPanel, section, token],
  );

  const buildNewResults = useCallback(() => {
    const text = findings.trim();
    if (!text) return [];
    return [
      {
        text,
        source_ref: sourceRef.trim() || null,
        attach_as_citation: citeSource,
      },
    ];
  }, [citeSource, findings, sourceRef]);

  const submitPanel = useCallback(() => {
    const instruction = prompt.trim();
    if (!instruction) return;
    if (panelMode === "selection") {
      const span = selectedSpan();
      if (!span) return;
      void preview({
        instruction,
        span,
        new_results: buildNewResults(),
        web_search: webSearch,
        web_query: instruction,
      });
      return;
    }
    if (panelMode === "insertion" && insertOffset !== null) {
      void preview({
        instruction,
        insertion_offset: insertOffset,
        new_results: buildNewResults(),
        web_search: webSearch,
        web_query: instruction,
      });
    }
  }, [buildNewResults, insertOffset, panelMode, preview, prompt, selectedSpan, webSearch]);

  const acceptPatch = useCallback(async () => {
    if (!section || !pendingPatch) return;
    setIsLoading(true);
    try {
      const updated = await applyWriterEdit(documentId, section.id, pendingPatch, token);
      onSectionUpdate(updated);
      setPendingPatch(null);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Writer edit apply failed.");
    } finally {
      setIsLoading(false);
    }
  }, [documentId, onError, onSectionUpdate, pendingPatch, section, token]);

  const regenerate = useCallback(() => {
    if (lastRequest) void preview(lastRequest);
  }, [lastRequest, preview]);

  const refine = useCallback(() => {
    if (lastRequest?.instruction) setPrompt(lastRequest.instruction);
    setPanelMode(lastRequest?.span ? "selection" : "insertion");
    setPendingPatch(null);
  }, [lastRequest]);

  if (!editor || !model || !section || !portalRoot) return null;

  const panelTitle = panelMode === "insertion" ? "Write new paragraph" : "Edit selection";
  const panelPlaceholder =
    panelMode === "insertion"
      ? "Describe what this paragraph should cover — e.g. introduce the problem, summarize related work, motivate the method."
      : "Tell the editor what to do — fix grammar, paraphrase, expand, tighten, or rewrite using the findings below.";

  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-[70]">
      {selection && selectionPoint && !pendingPatch && !panelMode && (
        <div
          className="pointer-events-auto absolute flex gap-1 rounded-full border border-outline/20 bg-surface-container px-1 py-1 shadow-lg"
          style={{ top: selectionPoint.top, left: selectionPoint.left }}
        >
          <button
            type="button"
            onClick={() => {
              resetPanel();
              setPanelMode("selection");
            }}
            disabled={isLoading}
            className={buttonClass()}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>auto_awesome</span>
            Edit
          </button>
        </div>
      )}

      {insertPoint && !pendingPatch && !panelMode && (
        <button
          type="button"
          onClick={() => {
            resetPanel();
            setPanelMode("insertion");
          }}
          className="pointer-events-auto absolute flex h-6 w-6 items-center justify-center rounded-full border border-outline/20 bg-surface-container text-primary shadow-lg hover:bg-primary/10"
          style={{ top: insertPoint.top, left: insertPoint.left }}
          aria-label="Write new paragraph"
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>add</span>
        </button>
      )}

      {panelMode && panelPlacement && (
        <div
          role="dialog"
          aria-label={panelTitle}
          className="pointer-events-auto absolute flex w-[380px] max-w-[94vw] flex-col rounded-2xl border border-outline/20 bg-surface p-3 shadow-2xl"
          style={{
            top: panelPlacement.top,
            left: panelPlacement.left,
            maxHeight: `${panelPlacement.maxHeight}px`,
          }}
        >
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-on-surface">{panelTitle}</h2>
            <button type="button" onClick={resetPanel} aria-label="Close" className={buttonClass()}>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>close</span>
            </button>
          </div>
          <div className="mt-2 min-h-0 overflow-y-auto pr-1 custom-scrollbar">
            <textarea
              autoFocus
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={panelPlaceholder}
              className="h-24 w-full resize-none rounded-xl border border-outline/20 bg-background p-2.5 text-xs text-on-surface outline-none focus:border-primary/50"
            />

            <button
              type="button"
              onClick={() => setFindingsOpen((open) => !open)}
              className="mt-2 flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
                {findingsOpen ? "expand_less" : "expand_more"}
              </span>
              {findingsOpen ? "Hide findings" : "Add findings (optional)"}
            </button>

            {findingsOpen && (
              <div className="mt-2 space-y-2 rounded-xl border border-outline/10 bg-surface-container-lowest p-2.5">
                <textarea
                  value={findings}
                  onChange={(event) => setFindings(event.target.value)}
                  placeholder="Paste results, evidence, or a quote to weave in."
                  className="h-20 w-full resize-none rounded-lg border border-outline/20 bg-background p-2 text-xs text-on-surface outline-none focus:border-primary/50"
                />
                <input
                  value={sourceRef}
                  onChange={(event) => setSourceRef(event.target.value)}
                  placeholder="Source (optional) — e.g. Smith 2024"
                  className="h-8 w-full rounded-lg border border-outline/20 bg-background px-2.5 text-xs text-on-surface outline-none focus:border-primary/50"
                />
                <label className="flex items-center gap-2 text-[11px] text-on-surface-variant">
                  <input type="checkbox" checked={citeSource} onChange={(event) => setCiteSource(event.target.checked)} />
                  Cite this source
                </label>
              </div>
            )}

            <label className="mt-2 flex items-center gap-2 text-[11px] text-on-surface-variant">
              <input type="checkbox" checked={webSearch} onChange={(event) => setWebSearch(event.target.checked)} />
              Web search
            </label>
          </div>
          <div className="mt-3 flex shrink-0 justify-end gap-2 border-t border-outline/10 pt-3">
            <button type="button" onClick={resetPanel} className={buttonClass()}>
              Cancel
            </button>
            <button
              type="button"
              onClick={submitPanel}
              disabled={isLoading || !prompt.trim()}
              className={buttonClass(true)}
            >
              Preview
            </button>
          </div>
        </div>
      )}

      {pendingPatch && patchPlacement && (
        <div
          className="pointer-events-auto absolute flex w-[448px] max-w-[94vw] flex-col overflow-hidden rounded-2xl border border-outline/20 bg-surface p-3 shadow-xl"
          style={{
            top: patchPlacement.top,
            left: patchPlacement.left,
            maxHeight: `${patchPlacement.maxHeight}px`,
          }}
        >
          <div className="min-h-0 space-y-2 overflow-y-auto pr-1 text-xs custom-scrollbar">
            {pendingPatch.original_text && (
              <div className="whitespace-pre-wrap break-words rounded-xl border border-outline/10 bg-surface-container-lowest p-2 text-on-surface-variant line-through">
                {previewText(pendingPatch.original_text)}
              </div>
            )}
            <div className="whitespace-pre-wrap break-words rounded-xl bg-emerald-50 p-2 text-emerald-900 dark:bg-emerald-900/20 dark:text-emerald-100">
              {previewText(pendingPatch.new_text)}
            </div>
            <p className="text-[11px] text-on-surface-variant">{pendingPatch.rationale}</p>
            {pendingPatch.web_citations.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {pendingPatch.web_citations.map((citation) => (
                  <a
                    key={citation.url}
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: "11px" }}>public</span>
                    {citation.title}
                  </a>
                ))}
              </div>
            )}
          </div>
          <div className="mt-3 flex shrink-0 flex-wrap justify-end gap-2 border-t border-outline/10 pt-3">
            <button type="button" onClick={() => void acceptPatch()} disabled={isLoading} className={buttonClass(true)}>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>check</span>
              Accept
            </button>
            <button type="button" onClick={regenerate} disabled={isLoading || !lastRequest} className={buttonClass()}>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>refresh</span>
              Regenerate
            </button>
            <button type="button" onClick={refine} disabled={isLoading} className={buttonClass()}>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>edit</span>
              Refine
            </button>
            <button type="button" onClick={() => setPendingPatch(null)} disabled={isLoading} className={buttonClass()}>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>close</span>
              Discard
            </button>
          </div>
        </div>
      )}

      {pendingPatch && !patchPlacement && (
        <button
          type="button"
          onClick={() => setPendingPatch({ ...pendingPatch })}
          className="pointer-events-auto absolute bottom-4 right-4 rounded-full border border-outline/20 bg-surface-container px-3 py-2 text-xs font-semibold text-on-surface shadow-lg"
        >
          1 pending suggestion - Review
        </button>
      )}
    </div>,
    portalRoot,
  );
}
