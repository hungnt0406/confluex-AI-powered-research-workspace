"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { latexOffsetToDomPosition } from "@/lib/dom-latex-map";
import {
  Block,
  InlineNode,
  citationChipLabel,
  parseLatexToBlocks,
} from "@/lib/latex-prose";

// NOTE: Accept/Reject/stale handling is duplicated from
// `WriterChatInlineDiff` (source-mode). It's intentionally kept inline here
// because the source-mode flow is tangled with Monaco decoration/view-zone
// teardown timers that don't apply to prose mode.
//
// Rendering strategy: instead of overlaying coloured rects on the editor
// and floating a card below the paragraph, we hide the affected paragraph
// via `visibility: hidden` and render a diff replacement on top of it that
// mirrors its bounding box. The replacement renders the paragraph's text
// flow with each patch shown inline as `<s>old</s> <strong>new</strong>`
// immediately followed by an inline Accept/Reject toolbar — so the user
// reads the diff in the same plane as the surrounding prose.

export interface PendingChatPatch {
  key: string;
  chatId: string;
  messageId: string;
  patchIndex: number;
  patch: ChatSectionPatch;
}

export interface ProseAdapterLike {
  getDomNode?: () => HTMLElement | null;
  onDidChangeCursorSelection: (fn: () => void) => { dispose: () => void };
  onDidChangeCursorPosition: (fn: () => void) => { dispose: () => void };
}

function callGetDomNode(adapter: ProseAdapterLike | null): HTMLElement | null {
  if (!adapter || typeof adapter.getDomNode !== "function") return null;
  return adapter.getDomNode();
}

export interface WriterChatInlineDiffProseProps {
  documentId: string;
  sections: WriterSectionRead[];
  activeSectionId: string | null;
  proseAdapter: ProseAdapterLike | null;
  token: string;
  pendingPatches: PendingChatPatch[];
  onPatchResolved: (key: string, status: "applied" | "rejected" | "stale") => void;
  onAfterPatchApplied: () => void | Promise<void>;
  setChatBusy: (busy: boolean) => void;
  flashKey: string | null;
  onRequestSourceView?: () => void;
}

interface PatchPlacement {
  entry: PendingChatPatch;
  block: HTMLElement | null;
  startNode: Node | null;
  startOffset: number;
  endNode: Node | null;
  endOffset: number;
  textStart: number;
  textEnd: number;
  // Width of the strikethrough span, used only to skip layout when the range
  // produced zero-area rects (e.g. the entire span is inside a citation chip).
  rectsCount: number;
  // True when this is the block where the new text + accept/reject toolbar
  // should be rendered (after the strikethrough). For single-block patches
  // this is always true; for multi-block patches only the last block has it.
  isLast: boolean;
}

interface BlockOverlay {
  block: HTMLElement;
  blockTop: number;
  blockLeft: number;
  blockWidth: number;
  computed: BlockStyleSnapshot;
  patches: PatchPlacement[];
}

interface FallbackPlacement {
  entry: PendingChatPatch;
  cardTop: number;
  cardLeft: number;
  cardWidth: number;
}

// Insertions (zero-width patch spans) are rendered as a card *below* the
// containing paragraph, leaving the paragraph fully visible. The paragraph
// keeps its proper citation chips / formatting and the new content reads
// like a clearly-marked addition.
interface InsertionPlacement {
  entry: PendingChatPatch;
  block: HTMLElement;
  cardTop: number;
  cardLeft: number;
  cardWidth: number;
  computed: BlockStyleSnapshot;
}

interface BlockStyleSnapshot {
  fontFamily: string;
  fontSize: string;
  fontWeight: string;
  fontStyle: string;
  lineHeight: string;
  color: string;
  letterSpacing: string;
  textAlign: string;
  paddingTop: string;
  paddingRight: string;
  paddingBottom: string;
  paddingLeft: string;
  marginTop: string;
}

const CARD_GUTTER_PX = 16;

function snapshotBlockStyle(block: HTMLElement): BlockStyleSnapshot {
  const cs = window.getComputedStyle(block);
  return {
    fontFamily: cs.fontFamily,
    fontSize: cs.fontSize,
    fontWeight: cs.fontWeight,
    fontStyle: cs.fontStyle,
    lineHeight: cs.lineHeight,
    color: cs.color,
    letterSpacing: cs.letterSpacing,
    textAlign: cs.textAlign,
    paddingTop: cs.paddingTop,
    paddingRight: cs.paddingRight,
    paddingBottom: cs.paddingBottom,
    paddingLeft: cs.paddingLeft,
    marginTop: cs.marginTop,
  };
}

function findContainingBlock(node: Node, root: HTMLElement): HTMLElement | null {
  let cur: Node | null = node;
  while (cur && cur !== root) {
    if (cur.nodeType === Node.ELEMENT_NODE) {
      const el = cur as HTMLElement;
      if (el.dataset.blockType) return el;
      const display = window.getComputedStyle(el).display;
      if (display === "block" || display === "list-item" || display === "flex") return el;
    }
    cur = cur.parentNode;
  }
  return null;
}

// Compute the plain-text character offset of (node, offset) within `block`.
// This walks text nodes in document order — no string search — so it stays
// safe even when the same substring appears multiple times.
function textOffsetWithinBlock(block: HTMLElement, node: Node, offset: number): number {
  if (node === block) {
    let count = 0;
    const limit = Math.min(offset, block.childNodes.length);
    for (let i = 0; i < limit; i += 1) {
      count += (block.childNodes[i].textContent ?? "").length;
    }
    return count;
  }

  if (node.nodeType === Node.TEXT_NODE) {
    let count = 0;
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let cur = walker.nextNode();
    while (cur) {
      if (cur === node) return count + offset;
      count += cur.textContent?.length ?? 0;
      cur = walker.nextNode();
    }
    return count;
  }

  if (node.nodeType !== Node.ELEMENT_NODE) return 0;
  const el = node as HTMLElement;

  // Sum text content of nodes before `el` in document order.
  let prefix = 0;
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  let cur = walker.nextNode();
  while (cur) {
    if (el === cur || el.contains(cur)) break;
    prefix += cur.textContent?.length ?? 0;
    cur = walker.nextNode();
  }

  // Plus text content of first `offset` children of `el`.
  let inner = 0;
  const limit = Math.min(offset, el.childNodes.length);
  for (let i = 0; i < limit; i += 1) {
    inner += (el.childNodes[i].textContent ?? "").length;
  }
  return prefix + inner;
}

function renderInline(node: InlineNode, key: number): JSX.Element | string {
  switch (node.type) {
    case "text":
      return node.value;
    case "bold":
      return <strong key={key}>{node.value}</strong>;
    case "emph":
      return <em key={key}>{node.value}</em>;
    case "cite":
      return (
        <span
          key={key}
          className="mx-0.5 inline-flex items-center rounded-full bg-emerald-100 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200"
        >
          {citationChipLabel(node.keys)}
        </span>
      );
    case "todo":
      return (
        <span
          key={key}
          className="mx-0.5 inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-900 dark:bg-amber-900/40 dark:text-amber-200"
        >
          {node.value}
        </span>
      );
  }
}

function renderInlineList(nodes: InlineNode[]): JSX.Element {
  return (
    <>
      {nodes.map((n, i) => (
        <Fragment key={i}>{renderInline(n, i)}</Fragment>
      ))}
    </>
  );
}

// Render `new_text` as inline content. The patch text might be a full
// paragraph or just a fragment; in either case we flatten to inline nodes
// so it can sit beside the surrounding prose.
function renderNewTextInline(latex: string): JSX.Element {
  const blocks: Block[] = parseLatexToBlocks(latex);
  if (blocks.length === 0) {
    return <>{latex}</>;
  }
  const inline: InlineNode[] = [];
  for (let i = 0; i < blocks.length; i += 1) {
    const b = blocks[i];
    if (b.type === "paragraph") {
      if (i > 0) inline.push({ type: "text", value: " " });
      inline.push(...b.inline);
    } else if (b.type === "heading") {
      if (i > 0) inline.push({ type: "text", value: " " });
      inline.push({ type: "text", value: b.text });
    } else {
      if (i > 0) inline.push({ type: "text", value: " " });
      inline.push({ type: "text", value: b.latex });
    }
  }
  return renderInlineList(inline);
}

interface AcceptToolbarProps {
  entry: PendingChatPatch;
  busy: boolean;
  stale: boolean;
  inFlightError: string | null;
  flash: boolean;
  onAccept: () => void;
  onReject: () => void;
}

function AcceptToolbar({
  entry,
  busy,
  stale,
  inFlightError,
  flash,
  onAccept,
  onReject,
}: AcceptToolbarProps) {
  const rationale = entry.patch.rationale || "Suggested edit";
  const sectionTitle = entry.patch.section_title || "section";

  if (stale) {
    return (
      <span
        className={`writer-chat-accept-toolbar pointer-events-auto ml-1 inline-flex items-center gap-1 rounded-full border border-rose-300/60 bg-rose-50 px-2 py-0.5 align-baseline text-[10px] font-semibold text-rose-700 shadow-sm dark:border-rose-900/40 dark:bg-rose-950/40 dark:text-rose-200 ${
          flash ? "writer-chat-flash" : ""
        }`}
        title="The draft span no longer matches — ask again to regenerate."
      >
        <span aria-hidden="true">↻</span>
        Draft changed
      </span>
    );
  }

  return (
    <span
      className={`writer-chat-accept-toolbar pointer-events-auto ml-1 inline-flex items-center gap-0.5 align-baseline ${
        flash ? "writer-chat-flash" : ""
      }`}
      title={rationale}
    >
      <button
        type="button"
        onClick={onAccept}
        disabled={busy}
        className="inline-flex h-5 items-center justify-center rounded-full bg-emerald-600 px-1.5 text-[10px] font-semibold text-white shadow-sm hover:bg-emerald-500 disabled:opacity-50"
        aria-label={`Accept inline edit for ${sectionTitle}`}
      >
        {busy ? (
          <span
            className="material-symbols-outlined animate-spin"
            style={{ fontSize: "11px" }}
            aria-hidden="true"
          >
            progress_activity
          </span>
        ) : (
          <span aria-hidden="true">✓</span>
        )}
      </button>
      <button
        type="button"
        onClick={onReject}
        disabled={busy}
        className="inline-flex h-5 items-center justify-center rounded-full border border-stone-300 bg-white px-1.5 text-[10px] font-semibold text-stone-700 shadow-sm hover:bg-rose-50 hover:text-rose-700 disabled:opacity-50"
        aria-label={`Reject inline edit for ${sectionTitle}`}
      >
        <span aria-hidden="true">✕</span>
      </button>
      {inFlightError ? (
        <span className="ml-1 max-w-[200px] truncate text-[10px] font-normal text-rose-600">
          {inFlightError}
        </span>
      ) : null}
    </span>
  );
}

export function WriterChatInlineDiffProse({
  documentId,
  sections,
  activeSectionId,
  proseAdapter,
  token,
  pendingPatches,
  onPatchResolved,
  onAfterPatchApplied,
  setChatBusy,
  flashKey,
  onRequestSourceView,
}: WriterChatInlineDiffProseProps) {
  const [overlays, setOverlays] = useState<BlockOverlay[]>([]);
  const [insertions, setInsertions] = useState<InsertionPlacement[]>([]);
  const [fallbacks, setFallbacks] = useState<FallbackPlacement[]>([]);
  const [busyKeys, setBusyKeys] = useState<Set<string>>(() => new Set());
  const [staleKeys, setStaleKeys] = useState<Set<string>>(() => new Set());
  const [errorByKey, setErrorByKey] = useState<Record<string, string>>({});
  const [creditsExhausted, setCreditsExhausted] = useState(false);
  const [overlayRoot, setOverlayRoot] = useState<HTMLElement | null>(null);

  const diffCardsRef = useRef<Map<HTMLElement, HTMLDivElement>>(new Map());
  const insertionCardsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const hiddenBlocksRef = useRef<Map<HTMLElement, { visibility: string; marginBottom: string }>>(
    new Map(),
  );
  const insertionPaddedBlocksRef = useRef<Map<HTMLElement, string>>(new Map());
  const staleTimersRef = useRef<Map<string, number>>(new Map());
  const rafRef = useRef<number | null>(null);

  const visiblePatches = useMemo(() => {
    return pendingPatches.filter((p) => p.patch.section_id === activeSectionId);
  }, [pendingPatches, activeSectionId]);

  const computePlacements = useCallback((): {
    overlays: BlockOverlay[];
    insertions: InsertionPlacement[];
    fallbacks: FallbackPlacement[];
  } => {
    if (!proseAdapter || !overlayRoot) return { overlays: [], insertions: [], fallbacks: [] };
    const root = callGetDomNode(proseAdapter);
    if (!root || typeof document === "undefined")
      return { overlays: [], insertions: [], fallbacks: [] };
    // Position children relative to the overlay layer itself, not the editor
    // root: the layer is attached to root.parentElement, which usually has
    // padding (py-10 px-12 etc.) that shifts root downward. Using layerRect
    // gives an offset that matches what the user actually sees, regardless
    // of how much padding/margin sits between layer and root.
    const layerRect = overlayRoot.getBoundingClientRect();
    const innerWidth = layerRect.width - CARD_GUTTER_PX * 2;

    const byBlock = new Map<HTMLElement, PatchPlacement[]>();
    const ins: InsertionPlacement[] = [];
    const fbs: FallbackPlacement[] = [];

    for (const entry of visiblePatches) {
      const section = sections.find((s) => s.id === entry.patch.section_id);
      const draft = section?.draft_latex ?? "";
      const rawStart = entry.patch.span.start;
      const rawEnd = entry.patch.span.end;
      // If the draft has changed under us (e.g. a previous patch was just
      // accepted), the patch's offsets may point past the current content or
      // to entirely different text. Without this guard, stale patches collapse
      // to (0,0) and stack on top of each other — see the duplicate-key
      // overlap bug.
      if (rawStart > draft.length || rawEnd > draft.length) continue;
      const expectedOriginal = entry.patch.original_text ?? "";
      if (expectedOriginal && draft.substring(rawStart, rawEnd) !== expectedOriginal) continue;
      const start = Math.max(0, Math.min(rawStart, draft.length));
      const end = Math.max(start, Math.min(rawEnd, draft.length));

      const startPos = latexOffsetToDomPosition(root, start);
      const endPos = latexOffsetToDomPosition(root, end);
      if (!startPos || !endPos) {
        fbs.push({
          entry,
          cardTop: 8,
          cardLeft: CARD_GUTTER_PX,
          cardWidth: innerWidth,
        });
        continue;
      }

      const startBlock = findContainingBlock(startPos.node, root);
      const endBlock = findContainingBlock(endPos.node, root);
      if (!endBlock) {
        fbs.push({
          entry,
          cardTop: 8,
          cardLeft: CARD_GUTTER_PX,
          cardWidth: innerWidth,
        });
        continue;
      }

      // Insertions: zero-width latex span. Don't fall through to the
      // replacement path — the original paragraph should stay visible with
      // its proper citation chips, and the new content appears as a caret
      // card just below it.
      if (start === end) {
        const rect = endBlock.getBoundingClientRect();
        ins.push({
          entry,
          block: endBlock,
          cardTop: rect.bottom - layerRect.top + 4,
          cardLeft: rect.left - layerRect.left,
          cardWidth: rect.width,
          computed: snapshotBlockStyle(endBlock),
        });
        continue;
      }

      // Determine every block the patch crosses, in document order. A patch
      // that spans, say, a heading + a paragraph touches two blocks; we
      // need to strike through the relevant slice of each one.
      const topLevelChildren: HTMLElement[] = [];
      let endIdx = -1;
      let startIdx = -1;
      root.childNodes.forEach((n) => {
        if (n.nodeType !== Node.ELEMENT_NODE) return;
        const el = n as HTMLElement;
        const i = topLevelChildren.push(el) - 1;
        if (el === endBlock) endIdx = i;
        if (startBlock && el === startBlock) startIdx = i;
      });
      if (!startBlock && endIdx >= 0) startIdx = endIdx;
      if (endIdx < 0 || startIdx < 0 || startIdx > endIdx) {
        fbs.push({
          entry,
          cardTop: 8,
          cardLeft: CARD_GUTTER_PX,
          cardWidth: innerWidth,
        });
        continue;
      }

      // For single-block patches keep the existing rectsCount guard so a
      // patch landing wholly inside a citation chip still routes to the
      // floating fallback card. For multi-block patches we skip the guard
      // — citation chips are an edge case there, and the strikethrough
      // covers entire intermediate blocks anyway.
      if (startIdx === endIdx) {
        const range = document.createRange();
        let rectsCount = 0;
        try {
          range.setStart(startPos.node, Math.min(startPos.offset, nodeMaxOffset(startPos.node)));
          range.setEnd(endPos.node, Math.min(endPos.offset, nodeMaxOffset(endPos.node)));
          const clientRects = Array.from(range.getClientRects()).filter(
            (r) => r.width > 0 && r.height > 0,
          );
          rectsCount = clientRects.length;
        } catch {
          // ignore
        }
        if (rectsCount === 0) {
          fbs.push({
            entry,
            cardTop: 8,
            cardLeft: CARD_GUTTER_PX,
            cardWidth: innerWidth,
          });
          continue;
        }
      }

      for (let bi = startIdx; bi <= endIdx; bi += 1) {
        const blk = topLevelChildren[bi];
        const fullLen = (blk.textContent ?? "").length;
        let segStart: number;
        let segEnd: number;
        if (bi === startIdx && bi === endIdx) {
          segStart = textOffsetWithinBlock(blk, startPos.node, startPos.offset);
          segEnd = textOffsetWithinBlock(blk, endPos.node, endPos.offset);
        } else if (bi === startIdx) {
          segStart = textOffsetWithinBlock(blk, startPos.node, startPos.offset);
          segEnd = fullLen;
        } else if (bi === endIdx) {
          segStart = 0;
          segEnd = textOffsetWithinBlock(blk, endPos.node, endPos.offset);
        } else {
          segStart = 0;
          segEnd = fullLen;
        }

        const list = byBlock.get(blk) ?? [];
        list.push({
          entry,
          block: blk,
          startNode: bi === startIdx ? startPos.node : null,
          startOffset: bi === startIdx ? startPos.offset : 0,
          endNode: bi === endIdx ? endPos.node : null,
          endOffset: bi === endIdx ? endPos.offset : 0,
          textStart: segStart,
          textEnd: Math.max(segStart, segEnd),
          rectsCount: 1,
          isLast: bi === endIdx,
        });
        byBlock.set(blk, list);
      }
    }

    const overlaysOut: BlockOverlay[] = [];
    for (const [block, patches] of byBlock.entries()) {
      const sorted = [...patches].sort((a, b) => a.textStart - b.textStart);
      const rect = block.getBoundingClientRect();
      overlaysOut.push({
        block,
        blockTop: rect.top - layerRect.top,
        blockLeft: rect.left - layerRect.left,
        blockWidth: rect.width,
        computed: snapshotBlockStyle(block),
        patches: sorted,
      });
    }
    return { overlays: overlaysOut, insertions: ins, fallbacks: fbs };
  }, [proseAdapter, sections, visiblePatches, overlayRoot]);

  // Cheap signature so we don't re-render when nothing visually changed.
  const overlaysSignature = useCallback((list: BlockOverlay[]): string => {
    return list
      .map((o) => {
        const patches = o.patches
          .map((p) => `${p.entry.key}:${p.textStart}:${p.textEnd}`)
          .join("|");
        return `${o.blockTop|0}:${o.blockLeft|0}:${o.blockWidth|0}:${patches}`;
      })
      .join(";");
  }, []);

  const fallbacksSignature = useCallback((list: FallbackPlacement[]): string => {
    return list
      .map((f) => `${f.entry.key}:${f.cardTop|0}:${f.cardLeft|0}:${f.cardWidth|0}`)
      .join(";");
  }, []);

  const insertionsSignature = useCallback((list: InsertionPlacement[]): string => {
    return list
      .map((i) => `${i.entry.key}:${i.cardTop|0}:${i.cardLeft|0}:${i.cardWidth|0}`)
      .join(";");
  }, []);

  const schedule = useCallback(() => {
    if (typeof window === "undefined") return;
    if (rafRef.current !== null) return;
    rafRef.current = window.requestAnimationFrame(() => {
      rafRef.current = null;
      const next = computePlacements();
      setOverlays((prev) =>
        overlaysSignature(prev) === overlaysSignature(next.overlays) ? prev : next.overlays,
      );
      setInsertions((prev) =>
        insertionsSignature(prev) === insertionsSignature(next.insertions)
          ? prev
          : next.insertions,
      );
      setFallbacks((prev) =>
        fallbacksSignature(prev) === fallbacksSignature(next.fallbacks) ? prev : next.fallbacks,
      );
    });
  }, [computePlacements, overlaysSignature, insertionsSignature, fallbacksSignature]);

  // Mount the overlay layer.
  useEffect(() => {
    if (!proseAdapter) {
      setOverlayRoot(null);
      return;
    }
    const root = callGetDomNode(proseAdapter);
    if (!root) {
      setOverlayRoot(null);
      return;
    }
    const existing = root.parentElement?.querySelector<HTMLElement>(
      "[data-writer-chat-overlay='1']",
    );
    let layer: HTMLElement;
    if (existing) {
      layer = existing;
    } else {
      layer = document.createElement("div");
      layer.dataset.writerChatOverlay = "1";
      layer.style.position = "absolute";
      layer.style.top = "0";
      layer.style.left = "0";
      layer.style.width = "100%";
      layer.style.height = "0";
      layer.style.pointerEvents = "none";
      layer.style.zIndex = "20";
      const parent = root.parentElement;
      if (parent) {
        const parentPos = window.getComputedStyle(parent).position;
        if (parentPos === "static") parent.style.position = "relative";
        parent.appendChild(layer);
      }
    }
    setOverlayRoot(layer);
  }, [proseAdapter]);

  // Recompute on resize / scroll / mutations / selection.
  useEffect(() => {
    if (!proseAdapter) return;
    const root = callGetDomNode(proseAdapter);
    if (!root || typeof window === "undefined") return;

    schedule();

    const scrollAncestors: (HTMLElement | Window)[] = [window];
    let parent: HTMLElement | null = root.parentElement;
    while (parent) {
      const overflowY = window.getComputedStyle(parent).overflowY;
      if (overflowY === "auto" || overflowY === "scroll") scrollAncestors.push(parent);
      parent = parent.parentElement;
    }

    const onScrollOrResize = () => schedule();
    scrollAncestors.forEach((tgt) => tgt.addEventListener("scroll", onScrollOrResize, true));
    window.addEventListener("resize", onScrollOrResize);

    const mo = new MutationObserver(() => schedule());
    mo.observe(root, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["style"],
    });

    const selDisp = proseAdapter.onDidChangeCursorSelection(() => schedule());
    const posDisp = proseAdapter.onDidChangeCursorPosition(() => schedule());

    return () => {
      scrollAncestors.forEach((tgt) =>
        tgt.removeEventListener("scroll", onScrollOrResize, true),
      );
      window.removeEventListener("resize", onScrollOrResize);
      mo.disconnect();
      selDisp.dispose();
      posDisp.dispose();
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [proseAdapter, schedule]);

  useEffect(() => {
    schedule();
  }, [visiblePatches, sections, flashKey, schedule]);

  // Hide affected paragraphs and pad them so the diff overlay (which may
  // grow taller) doesn't overlap content below.
  useEffect(() => {
    if (!proseAdapter) return;
    const stillHidden = new Set<HTMLElement>();
    for (const ov of overlays) {
      stillHidden.add(ov.block);
      if (!hiddenBlocksRef.current.has(ov.block)) {
        hiddenBlocksRef.current.set(ov.block, {
          visibility: ov.block.style.visibility,
          marginBottom: ov.block.style.marginBottom,
        });
      }
      ov.block.style.visibility = "hidden";
    }
    for (const [block, prev] of Array.from(hiddenBlocksRef.current.entries())) {
      if (!stillHidden.has(block)) {
        block.style.visibility = prev.visibility;
        block.style.marginBottom = prev.marginBottom;
        hiddenBlocksRef.current.delete(block);
      }
    }
  }, [overlays, proseAdapter]);

  // After each render, measure each diff card and apply padding to the
  // hidden block so subsequent prose flows below the (possibly taller)
  // diff. We use ResizeObserver to react to card resize as well.
  useEffect(() => {
    if (overlays.length === 0) return;
    const observers = new Map<HTMLElement, ResizeObserver>();
    const applyPadding = (block: HTMLElement, card: HTMLDivElement) => {
      const cardHeight = card.getBoundingClientRect().height;
      const blockHeight = block.getBoundingClientRect().height;
      const delta = Math.max(0, Math.ceil(cardHeight - blockHeight));
      const prev = hiddenBlocksRef.current.get(block)?.marginBottom ?? "";
      // Preserve original margin (parseFloat returns NaN for "auto" etc.).
      const prevPx = Number.parseFloat(prev);
      const base = Number.isFinite(prevPx) ? prevPx : 0;
      block.style.marginBottom = `${base + delta}px`;
    };
    for (const ov of overlays) {
      const card = diffCardsRef.current.get(ov.block);
      if (!card) continue;
      applyPadding(ov.block, card);
      const ro = new ResizeObserver(() => applyPadding(ov.block, card));
      ro.observe(card);
      observers.set(ov.block, ro);
    }
    return () => {
      observers.forEach((o) => o.disconnect());
    };
  }, [overlays]);

  // Insertions don't hide the paragraph, but they do need to push content
  // below it down so the card doesn't overlap the next block.
  useEffect(() => {
    const stillPadded = new Set<HTMLElement>();
    for (const ins of insertions) {
      stillPadded.add(ins.block);
      if (!insertionPaddedBlocksRef.current.has(ins.block)) {
        insertionPaddedBlocksRef.current.set(ins.block, ins.block.style.marginBottom);
      }
    }
    for (const [block, prev] of Array.from(insertionPaddedBlocksRef.current.entries())) {
      if (!stillPadded.has(block) && !hiddenBlocksRef.current.has(block)) {
        block.style.marginBottom = prev;
        insertionPaddedBlocksRef.current.delete(block);
      }
    }

    if (insertions.length === 0) return;
    const observers = new Map<string, ResizeObserver>();
    const applyPadding = (ins: InsertionPlacement, card: HTMLDivElement) => {
      const cardHeight = card.getBoundingClientRect().height;
      const prev = insertionPaddedBlocksRef.current.get(ins.block) ?? "";
      const prevPx = Number.parseFloat(prev);
      const base = Number.isFinite(prevPx) ? prevPx : 0;
      // 8px gap above + below the card to keep it visually separated.
      ins.block.style.marginBottom = `${base + Math.ceil(cardHeight) + 12}px`;
    };
    for (const ins of insertions) {
      const card = insertionCardsRef.current.get(ins.entry.key);
      if (!card) continue;
      applyPadding(ins, card);
      const ro = new ResizeObserver(() => applyPadding(ins, card));
      ro.observe(card);
      observers.set(ins.entry.key, ro);
    }
    return () => {
      observers.forEach((o) => o.disconnect());
    };
  }, [insertions]);

  // Final unmount: restore everything we touched.
  useEffect(() => {
    return () => {
      hiddenBlocksRef.current.forEach((prev, block) => {
        block.style.visibility = prev.visibility;
        block.style.marginBottom = prev.marginBottom;
      });
      hiddenBlocksRef.current.clear();
      insertionPaddedBlocksRef.current.forEach((prev, block) => {
        block.style.marginBottom = prev;
      });
      insertionPaddedBlocksRef.current.clear();
    };
  }, []);

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
    const id = window.setTimeout(() => {
      onPatchResolved(key, "stale");
      staleTimersRef.current.delete(key);
    }, 5000);
    staleTimersRef.current.set(key, id);
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

  const handleAccept = async (entry: PendingChatPatch) => {
    const key = entry.key;
    setBusy(key, true);
    setErrorByKey((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    try {
      await acceptWriterChatPatch(
        documentId,
        entry.chatId,
        entry.messageId,
        entry.patchIndex,
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

  const handleReject = async (entry: PendingChatPatch) => {
    const key = entry.key;
    setBusy(key, true);
    setErrorByKey((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    try {
      await rejectWriterChatPatch(
        documentId,
        entry.chatId,
        entry.messageId,
        entry.patchIndex,
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

  if (!proseAdapter || !overlayRoot) return null;

  const overlayContent = (
    <div role="status" aria-live="polite" className="contents">
      <span className="sr-only">
        {visiblePatches.length > 0
          ? `${visiblePatches.length} suggested ${
              visiblePatches.length === 1 ? "edit" : "edits"
            } available`
          : ""}
      </span>
      {overlays.map((ov, ovIdx) => {
        const fullText = ov.block.textContent ?? "";
        const segments: JSX.Element[] = [];
        let cursor = 0;
        for (let i = 0; i < ov.patches.length; i += 1) {
          const p = ov.patches[i];
          const key = p.entry.key;
          const busy = busyKeys.has(key);
          const stale = staleKeys.has(key);
          const inFlightError = errorByKey[key] ?? null;
          const flash = flashKey === key;

          if (p.textStart > cursor) {
            segments.push(
              <Fragment key={`unchanged-${i}`}>
                {fullText.substring(cursor, p.textStart)}
              </Fragment>,
            );
          }
          if (p.textEnd > p.textStart) {
            segments.push(
              <span
                key={`old-${key}-${i}`}
                className="bg-rose-100/70 text-rose-900 line-through decoration-rose-500/70 decoration-1 dark:bg-rose-900/30 dark:text-rose-200"
              >
                {fullText.substring(p.textStart, p.textEnd)}
              </span>,
            );
          }
          if (p.isLast) {
            segments.push(
              <span
                key={`new-${key}`}
                className="ml-0.5 rounded-sm bg-emerald-100/70 px-0.5 font-semibold text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-100"
                title={p.entry.patch.rationale || "Suggested edit"}
              >
                {renderNewTextInline(p.entry.patch.new_text)}
              </span>,
            );
            segments.push(
              <AcceptToolbar
                key={`tb-${key}`}
                entry={p.entry}
                busy={busy}
                stale={stale}
                inFlightError={inFlightError}
                flash={flash}
                onAccept={() => void handleAccept(p.entry)}
                onReject={() => void handleReject(p.entry)}
              />,
            );
          }
          cursor = p.textEnd;
        }
        if (cursor < fullText.length) {
          segments.push(
            <Fragment key="trailing">{fullText.substring(cursor)}</Fragment>,
          );
        }

        // Per-block overlay key. Must include block identity (textStart of the
        // first segment + the patch keys) AND a positional discriminator,
        // because a single multi-block patch produces one overlay per block
        // that all share the same patch entry key. Reusing the same React key
        // for separate overlays makes the reconciler write segments from
        // different blocks into the same DOM node and produces a garbled
        // strikethrough.
        const firstSeg = ov.patches[0];
        const overlayKey = `ov-${ovIdx}:${firstSeg ? `${firstSeg.entry.key}:${firstSeg.textStart}` : "x"}`;
        return (
          <div
            key={overlayKey}
            data-writer-chat-card="1"
            ref={(el) => {
              if (el) diffCardsRef.current.set(ov.block, el);
              else diffCardsRef.current.delete(ov.block);
            }}
            style={{
              position: "absolute",
              top: `${ov.blockTop}px`,
              left: `${ov.blockLeft}px`,
              width: `${ov.blockWidth}px`,
              pointerEvents: "auto",
              fontFamily: ov.computed.fontFamily,
              fontSize: ov.computed.fontSize,
              fontWeight: ov.computed.fontWeight,
              fontStyle: ov.computed.fontStyle,
              lineHeight: ov.computed.lineHeight,
              color: ov.computed.color,
              letterSpacing: ov.computed.letterSpacing,
              textAlign: ov.computed.textAlign as React.CSSProperties["textAlign"],
              paddingTop: ov.computed.paddingTop,
              paddingRight: ov.computed.paddingRight,
              paddingBottom: ov.computed.paddingBottom,
              paddingLeft: ov.computed.paddingLeft,
              marginTop: ov.computed.marginTop,
              background: "transparent",
            }}
          >
            {segments}
          </div>
        );
      })}

      {insertions.map((ins) => {
        const key = ins.entry.key;
        const busy = busyKeys.has(key);
        const stale = staleKeys.has(key);
        const inFlightError = errorByKey[key] ?? null;
        const flash = flashKey === key;
        return (
          <div
            key={`ins-${key}`}
            data-writer-chat-card="1"
            ref={(el) => {
              if (el) insertionCardsRef.current.set(key, el);
              else insertionCardsRef.current.delete(key);
            }}
            style={{
              position: "absolute",
              top: `${ins.cardTop}px`,
              left: `${ins.cardLeft}px`,
              width: `${ins.cardWidth}px`,
              pointerEvents: "auto",
              fontFamily: ins.computed.fontFamily,
              fontSize: ins.computed.fontSize,
              lineHeight: ins.computed.lineHeight,
              letterSpacing: ins.computed.letterSpacing,
              textAlign: ins.computed.textAlign as React.CSSProperties["textAlign"],
            }}
            className={`rounded-sm border-l-[3px] border-l-emerald-500 bg-emerald-50/60 py-1.5 pl-2 pr-2 text-emerald-950 dark:bg-emerald-950/30 dark:text-emerald-100 ${
              flash ? "writer-chat-flash" : ""
            }`}
            title={ins.entry.patch.rationale || "Insert"}
          >
            <span
              aria-hidden="true"
              className="mr-1.5 inline-block select-none font-sans text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300"
            >
              ▸ Insert
            </span>
            <span className="font-semibold">
              {renderNewTextInline(ins.entry.patch.new_text)}
            </span>
            <AcceptToolbar
              entry={ins.entry}
              busy={busy}
              stale={stale}
              inFlightError={inFlightError}
              flash={flash}
              onAccept={() => void handleAccept(ins.entry)}
              onReject={() => void handleReject(ins.entry)}
            />
          </div>
        );
      })}

      {fallbacks.map((f) => {
        const key = f.entry.key;
        const busy = busyKeys.has(key);
        const stale = staleKeys.has(key);
        const inFlightError = errorByKey[key] ?? null;
        const flash = flashKey === key;
        return (
          <div
            key={`fb-${key}`}
            data-writer-chat-card="1"
            style={{
              position: "absolute",
              top: `${f.cardTop}px`,
              left: `${f.cardLeft}px`,
              width: `${f.cardWidth}px`,
              pointerEvents: "auto",
            }}
            className={`rounded-md border border-emerald-200 border-l-[3px] border-l-emerald-500 bg-emerald-50 px-3.5 py-2 text-[13px] leading-relaxed text-emerald-950 shadow-md dark:border-emerald-900/60 dark:bg-emerald-950 dark:text-emerald-100 ${
              flash ? "writer-chat-flash" : ""
            }`}
          >
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
              {f.entry.patch.rationale || "Suggested edit"}
            </div>
            <div className="writer-chat-inline-prose-body">
              {renderNewTextInline(f.entry.patch.new_text)}
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-emerald-800 dark:text-emerald-300">
              <span>This edit lands inside a citation chip.</span>
              {onRequestSourceView ? (
                <button
                  type="button"
                  onClick={onRequestSourceView}
                  className="rounded-full bg-emerald-200/70 px-2 py-0.5 font-semibold text-emerald-900 hover:bg-emerald-300/80 dark:bg-emerald-900/40 dark:text-emerald-100"
                >
                  Show source position
                </button>
              ) : null}
            </div>
            <div className="mt-2 flex justify-end">
              <AcceptToolbar
                entry={f.entry}
                busy={busy}
                stale={stale}
                inFlightError={inFlightError}
                flash={flash}
                onAccept={() => void handleAccept(f.entry)}
                onReject={() => void handleReject(f.entry)}
              />
            </div>
          </div>
        );
      })}
    </div>
  );

  return (
    <>
      {creditsExhausted ? (
        <div className="pointer-events-auto fixed bottom-4 left-1/2 z-[80] -translate-x-1/2 rounded-full border border-rose-200/60 bg-rose-50 px-4 py-2 text-[11px] font-semibold text-rose-700 shadow dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-200">
          Out of credits.{" "}
          <Link className="underline" href="/billing">
            Top up
          </Link>{" "}
          to accept inline edits.
        </div>
      ) : null}
      {createPortal(overlayContent, overlayRoot)}
    </>
  );
}

function nodeMaxOffset(node: Node): number {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent?.length ?? 0;
  return node.childNodes.length;
}
