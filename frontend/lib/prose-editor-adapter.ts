// Adapts the contenteditable prose editor into the MonacoEditorLike shape that
// `WriterEditorOverlay` was built for. This lets the existing AI-edit popover
// (selection toolbar, diff preview, accept/refine/discard, findings, web search)
// work over the Visual editor without duplicating the UI.

import type {
  MonacoDisposable,
  MonacoEditorLike,
  MonacoModelLike,
  MonacoPosition,
  MonacoSelection,
} from "@/components/WriterEditorOverlay";
import {
  domPositionToLatexOffset,
  getLineContent,
  getLineCount,
  latexOffsetToDomPosition,
  lineColumnToOffset,
  offsetToLineColumn,
} from "@/lib/dom-latex-map";

function clampInNode(node: Node, offset: number): number {
  if (node.nodeType === Node.TEXT_NODE) {
    return Math.max(0, Math.min(node.textContent?.length ?? 0, offset));
  }
  return Math.max(0, Math.min(node.childNodes.length, offset));
}

export function createProseEditorAdapter(
  editor: HTMLElement,
  getLatex: () => string,
): MonacoEditorLike {
  const model: MonacoModelLike = {
    getValue: () => getLatex(),
    getOffsetAt: ({ lineNumber, column }) => lineColumnToOffset(getLatex(), lineNumber, column),
    getPositionAt: (offset) => offsetToLineColumn(getLatex(), offset),
    getLineContent: (lineNumber) => getLineContent(getLatex(), lineNumber),
    getLineCount: () => getLineCount(getLatex()),
  };

  function currentRange(): Range | null {
    if (typeof window === "undefined") return null;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return null;
    const range = sel.getRangeAt(0);
    if (!editor.contains(range.startContainer) && !editor.contains(range.endContainer)) {
      return null;
    }
    return range;
  }

  function rangeToSelection(range: Range): MonacoSelection {
    const startOffset = domPositionToLatexOffset(editor, range.startContainer, range.startOffset);
    const endOffset = domPositionToLatexOffset(editor, range.endContainer, range.endOffset);
    const lo = Math.min(startOffset, endOffset);
    const hi = Math.max(startOffset, endOffset);
    const latex = getLatex();
    const start = offsetToLineColumn(latex, lo);
    const end = offsetToLineColumn(latex, hi);
    return {
      startLineNumber: start.lineNumber,
      startColumn: start.column,
      endLineNumber: end.lineNumber,
      endColumn: end.column,
      isEmpty: () => lo === hi,
    };
  }

  function addSelectionListener(fn: () => void): MonacoDisposable {
    // Only forward selection changes that are inside our editor. Focusing the
    // overlay's prompt textarea (or any other input) moves window.getSelection
    // away from the contenteditable; if we forwarded that, the overlay would
    // clear its saved selection and close the dialog the user just opened.
    const handler = () => {
      if (typeof window === "undefined") return;
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) {
        fn();
        return;
      }
      const range = sel.getRangeAt(0);
      if (!editor.contains(range.startContainer) && !editor.contains(range.endContainer)) {
        return;
      }
      fn();
    };
    document.addEventListener("selectionchange", handler);
    return { dispose: () => document.removeEventListener("selectionchange", handler) };
  }

  return {
    getModel: () => model,
    getDomNode: () => editor,
    getSelection: () => {
      const range = currentRange();
      if (!range) return null;
      return rangeToSelection(range);
    },
    getPosition: (): MonacoPosition | null => {
      const range = currentRange();
      if (!range) return null;
      const off = domPositionToLatexOffset(editor, range.startContainer, range.startOffset);
      return offsetToLineColumn(getLatex(), off);
    },
    getScrolledVisiblePosition: ({ lineNumber, column }) => {
      if (typeof document === "undefined") return null;
      const offset = lineColumnToOffset(getLatex(), lineNumber, column);
      const pos = latexOffsetToDomPosition(editor, offset);
      if (!pos) return null;
      const range = document.createRange();
      try {
        range.setStart(pos.node, clampInNode(pos.node, pos.offset));
        range.collapse(true);
      } catch {
        return null;
      }
      let rect = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) {
        const fallback =
          pos.node.nodeType === Node.ELEMENT_NODE
            ? (pos.node as HTMLElement)
            : pos.node.parentElement;
        if (fallback) rect = fallback.getBoundingClientRect();
      }
      const editorRect = editor.getBoundingClientRect();
      return {
        top: rect.top - editorRect.top,
        left: rect.left - editorRect.left,
        height: rect.height || 20,
      };
    },
    onDidChangeCursorSelection: addSelectionListener,
    onDidChangeCursorPosition: addSelectionListener,
  };
}
