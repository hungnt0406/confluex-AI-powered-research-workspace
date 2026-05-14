// Maps DOM positions inside the prose editor to character offsets in the
// underlying LaTeX text, and vice versa. The mapping mirrors what
// `WriterProseEditor` renders:
//
//   - block elements (data-block-type) are paragraphs / headings / raw, joined
//     by "\n\n" in LaTeX
//   - headings render as `\section{title}` / `\subsection{...}` / `\subsubsection{...}`
//   - chips with data-cite-keys / data-todo-text are atomic `\cite{...}` / `\todo{...}`
//   - <strong data-bold> -> `\textbf{...}`, <em data-emph> -> `\emph{...}`
//   - <br> contributes one newline

const HEADING_CMD: Record<string, string> = {
  "1": "section",
  "2": "subsection",
  "3": "subsubsection",
};

function blockPrefixLen(el: HTMLElement): number {
  if (el.dataset.blockType === "heading") {
    const cmd = HEADING_CMD[el.dataset.level ?? "1"] ?? "section";
    return cmd.length + 2; // "\<cmd>{"
  }
  return 0;
}

function blockSuffixLen(el: HTMLElement): number {
  return el.dataset.blockType === "heading" ? 1 : 0;
}

function citeLatexLength(el: HTMLElement): number {
  const keys = (el.dataset.citeKeys ?? "")
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean);
  return `\\cite{${keys.join(",")}}`.length;
}

function todoLatexLength(el: HTMLElement): number {
  return `\\todo{${el.dataset.todoText ?? ""}}`.length;
}

function nodeLatexLength(node: Node): number {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent?.length ?? 0;
  if (node.nodeType !== Node.ELEMENT_NODE) return 0;
  const el = node as HTMLElement;
  if (el.dataset.citeKeys !== undefined) return citeLatexLength(el);
  if (el.dataset.todoText !== undefined) return todoLatexLength(el);
  if (el.dataset.bold !== undefined) return `\\textbf{${el.textContent ?? ""}}`.length;
  if (el.dataset.emph !== undefined) return `\\emph{${el.textContent ?? ""}}`.length;
  if (el.tagName === "BR") return 1;
  let sum = 0;
  el.childNodes.forEach((c) => {
    sum += nodeLatexLength(c);
  });
  return sum;
}

function innerLatexLength(el: HTMLElement): number {
  let sum = 0;
  el.childNodes.forEach((c) => {
    sum += nodeLatexLength(c);
  });
  return sum;
}

function blockLatexLength(el: HTMLElement): number {
  return blockPrefixLen(el) + innerLatexLength(el) + blockSuffixLen(el);
}

function offsetWithinChildren(parent: HTMLElement, target: Node, targetOffset: number): number {
  if (parent === target) {
    let accum = 0;
    for (let i = 0; i < targetOffset && i < parent.childNodes.length; i += 1) {
      accum += nodeLatexLength(parent.childNodes[i]);
    }
    return accum;
  }
  let accum = 0;
  for (let i = 0; i < parent.childNodes.length; i += 1) {
    const child = parent.childNodes[i];
    if (child === target) {
      if (child.nodeType === Node.TEXT_NODE) return accum + targetOffset;
      const el = child as HTMLElement;
      if (el.dataset.citeKeys !== undefined || el.dataset.todoText !== undefined) return accum;
      if (el.dataset.bold !== undefined) {
        return accum + "\\textbf{".length + offsetWithinChildren(el, child, targetOffset);
      }
      if (el.dataset.emph !== undefined) {
        return accum + "\\emph{".length + offsetWithinChildren(el, child, targetOffset);
      }
      return accum + offsetWithinChildren(el, child, targetOffset);
    }
    if (child.nodeType === Node.ELEMENT_NODE && (child as HTMLElement).contains(target)) {
      const el = child as HTMLElement;
      if (el.dataset.citeKeys !== undefined || el.dataset.todoText !== undefined) return accum;
      if (el.dataset.bold !== undefined) {
        return accum + "\\textbf{".length + offsetWithinChildren(el, target, targetOffset);
      }
      if (el.dataset.emph !== undefined) {
        return accum + "\\emph{".length + offsetWithinChildren(el, target, targetOffset);
      }
      return accum + offsetWithinChildren(el, target, targetOffset);
    }
    accum += nodeLatexLength(child);
  }
  return accum;
}

export function domPositionToLatexOffset(
  editor: HTMLElement,
  node: Node,
  nodeOffset: number,
): number {
  if (node === editor) {
    let accum = 0;
    for (let i = 0; i < nodeOffset && i < editor.childNodes.length; i += 1) {
      const child = editor.childNodes[i] as HTMLElement;
      accum += blockLatexLength(child);
      if (i < editor.childNodes.length - 1) accum += 2;
    }
    return accum;
  }

  // Find the top-level block ancestor.
  let cursor: Node | null = node;
  while (cursor && cursor.parentNode !== editor) cursor = cursor.parentNode;
  if (!cursor) return 0;
  const topBlock = cursor as HTMLElement;

  let accum = 0;
  for (let i = 0; i < editor.childNodes.length; i += 1) {
    const child = editor.childNodes[i] as HTMLElement;
    if (child === topBlock) break;
    accum += blockLatexLength(child) + 2;
  }
  accum += blockPrefixLen(topBlock);
  accum += offsetWithinChildren(topBlock, node, nodeOffset);
  return accum;
}

function positionWithinBlock(
  parent: HTMLElement,
  remaining: number,
): { node: Node; offset: number } {
  let left = remaining;
  for (let i = 0; i < parent.childNodes.length; i += 1) {
    const child = parent.childNodes[i];
    if (child.nodeType === Node.TEXT_NODE) {
      const len = child.textContent?.length ?? 0;
      if (left <= len) return { node: child, offset: left };
      left -= len;
      continue;
    }
    const el = child as HTMLElement;
    const childLen = nodeLatexLength(el);
    if (left <= 0) return { node: parent, offset: i };
    if (left < childLen) {
      if (el.dataset.citeKeys !== undefined || el.dataset.todoText !== undefined) {
        return { node: parent, offset: i };
      }
      if (el.dataset.bold !== undefined) {
        const prefix = "\\textbf{".length;
        if (left <= prefix) return { node: parent, offset: i };
        left -= prefix;
        const inner = innerLatexLength(el);
        if (left > inner) return { node: parent, offset: i + 1 };
        return positionWithinBlock(el, left);
      }
      if (el.dataset.emph !== undefined) {
        const prefix = "\\emph{".length;
        if (left <= prefix) return { node: parent, offset: i };
        left -= prefix;
        const inner = innerLatexLength(el);
        if (left > inner) return { node: parent, offset: i + 1 };
        return positionWithinBlock(el, left);
      }
      return positionWithinBlock(el, left);
    }
    left -= childLen;
  }
  return { node: parent, offset: parent.childNodes.length };
}

export function latexOffsetToDomPosition(
  editor: HTMLElement,
  offset: number,
): { node: Node; offset: number } | null {
  let remaining = Math.max(0, offset);
  for (let i = 0; i < editor.childNodes.length; i += 1) {
    const block = editor.childNodes[i] as HTMLElement;
    const blockLen = blockLatexLength(block);
    if (remaining <= blockLen) {
      const prefix = blockPrefixLen(block);
      if (remaining <= prefix) return { node: block, offset: 0 };
      const inner = innerLatexLength(block);
      const innerOffset = remaining - prefix;
      if (innerOffset > inner) return { node: block, offset: block.childNodes.length };
      return positionWithinBlock(block, innerOffset);
    }
    remaining -= blockLen;
    if (remaining <= 2) {
      return { node: block, offset: block.childNodes.length };
    }
    remaining -= 2;
  }
  const last = editor.lastChild;
  if (last && last.nodeType === Node.ELEMENT_NODE) {
    const el = last as HTMLElement;
    return { node: el, offset: el.childNodes.length };
  }
  return { node: editor, offset: editor.childNodes.length };
}

export function offsetToLineColumn(
  latex: string,
  offset: number,
): { lineNumber: number; column: number } {
  const safe = Math.max(0, Math.min(latex.length, offset));
  let line = 1;
  let lastNewline = -1;
  for (let i = 0; i < safe; i += 1) {
    if (latex.charCodeAt(i) === 10) {
      line += 1;
      lastNewline = i;
    }
  }
  return { lineNumber: line, column: safe - lastNewline };
}

export function lineColumnToOffset(
  latex: string,
  lineNumber: number,
  column: number,
): number {
  let line = 1;
  let i = 0;
  while (line < lineNumber && i < latex.length) {
    if (latex.charCodeAt(i) === 10) line += 1;
    i += 1;
  }
  return Math.min(latex.length, i + Math.max(0, column - 1));
}

export function getLineContent(latex: string, lineNumber: number): string {
  const lines = latex.split("\n");
  return lines[lineNumber - 1] ?? "";
}

export function getLineCount(latex: string): number {
  if (!latex) return 1;
  let count = 1;
  for (let i = 0; i < latex.length; i += 1) {
    if (latex.charCodeAt(i) === 10) count += 1;
  }
  return count;
}
