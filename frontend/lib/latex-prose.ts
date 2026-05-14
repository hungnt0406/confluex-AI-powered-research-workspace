// Lightweight LaTeX ↔ prose converter for the writer Visual editor.
//
// We render LaTeX as styled prose blocks while keeping LaTeX as the
// storage format. Supported constructs:
//   - \section{...}, \subsection{...}, \subsubsection{...}
//   - \textbf{...}, \emph{...}, \textit{...}
//   - \cite{key1,key2,...}      (atomic chip)
//   - \todo{...}                (atomic callout)
//
// Anything else is preserved verbatim as plain text so the LaTeX is never
// silently mutated by a round-trip.

export type InlineNode =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "emph"; value: string }
  | { type: "cite"; keys: string[] }
  | { type: "todo"; value: string };

export type Block =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; inline: InlineNode[] }
  | { type: "raw"; latex: string };

interface MacroMatch {
  start: number;
  end: number;
  node: InlineNode;
}

const HEADING_LEVELS: Record<string, 1 | 2 | 3> = {
  section: 1,
  subsection: 2,
  subsubsection: 3,
};

function findBalancedBrace(source: string, openIndex: number): number {
  // Returns the index of the matching closing brace, or -1.
  let depth = 0;
  for (let i = openIndex; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "\\" && i + 1 < source.length) {
      i += 1;
      continue;
    }
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function parseInline(text: string): InlineNode[] {
  const matches: MacroMatch[] = [];
  const macroRegex = /\\(textbf|emph|textit|cite|todo)\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = macroRegex.exec(text)) !== null) {
    const openBrace = m.index + m[0].length - 1;
    const close = findBalancedBrace(text, openBrace);
    if (close === -1) continue;
    const inner = text.slice(openBrace + 1, close);
    const name = m[1];
    let node: InlineNode;
    if (name === "textbf") node = { type: "bold", value: inner };
    else if (name === "emph" || name === "textit") node = { type: "emph", value: inner };
    else if (name === "cite")
      node = {
        type: "cite",
        keys: inner.split(",").map((k) => k.trim()).filter(Boolean),
      };
    else node = { type: "todo", value: inner };
    matches.push({ start: m.index, end: close + 1, node });
    macroRegex.lastIndex = close + 1;
  }

  const result: InlineNode[] = [];
  let cursor = 0;
  for (const match of matches) {
    if (match.start > cursor) {
      result.push({ type: "text", value: text.slice(cursor, match.start) });
    }
    result.push(match.node);
    cursor = match.end;
  }
  if (cursor < text.length) {
    result.push({ type: "text", value: text.slice(cursor) });
  }
  return result.length > 0 ? result : [{ type: "text", value: text }];
}

export function parseLatexToBlocks(latex: string): Block[] {
  const blocks: Block[] = [];
  // Normalize newlines, then split on blank lines for paragraphs.
  const normalized = latex.replace(/\r\n?/g, "\n");
  const chunks = normalized.split(/\n{2,}/);

  for (const rawChunk of chunks) {
    const chunk = rawChunk.replace(/^\n+|\n+$/g, "");
    if (!chunk) continue;

    // Heading? Allow only when the chunk *is* the heading line (no extra prose).
    const headingMatch = /^\\(section|subsection|subsubsection)\s*\{/.exec(chunk);
    if (headingMatch) {
      const openBrace = headingMatch.index + headingMatch[0].length - 1;
      const close = findBalancedBrace(chunk, openBrace);
      if (close !== -1) {
        const title = chunk.slice(openBrace + 1, close);
        const tail = chunk.slice(close + 1).trim();
        blocks.push({
          type: "heading",
          level: HEADING_LEVELS[headingMatch[1]],
          text: title,
        });
        if (tail) {
          blocks.push({ type: "paragraph", inline: parseInline(tail) });
        }
        continue;
      }
    }

    // Unrecognized command-only blocks like \begin{...} ... \end{...} —
    // preserve verbatim so Source mode can still see them.
    if (/^\\(begin|end|usepackage|documentclass)\b/.test(chunk)) {
      blocks.push({ type: "raw", latex: chunk });
      continue;
    }

    blocks.push({ type: "paragraph", inline: parseInline(chunk) });
  }

  return blocks;
}

function escapeBraceContent(text: string): string {
  // We don't escape much — we only preserve user-supplied text. Stripping
  // newlines inside macros keeps the round-trip stable.
  return text.replace(/\s*\n+\s*/g, " ").trim();
}

function serializeInline(nodes: InlineNode[]): string {
  return nodes
    .map((n) => {
      switch (n.type) {
        case "text":
          return n.value;
        case "bold":
          return `\\textbf{${escapeBraceContent(n.value)}}`;
        case "emph":
          return `\\emph{${escapeBraceContent(n.value)}}`;
        case "cite":
          return `\\cite{${n.keys.join(",")}}`;
        case "todo":
          return `\\todo{${escapeBraceContent(n.value)}}`;
      }
    })
    .join("");
}

export function serializeBlocksToLatex(blocks: Block[]): string {
  const parts: string[] = [];
  for (const block of blocks) {
    if (block.type === "heading") {
      const cmd =
        block.level === 1 ? "section" : block.level === 2 ? "subsection" : "subsubsection";
      parts.push(`\\${cmd}{${escapeBraceContent(block.text)}}`);
    } else if (block.type === "paragraph") {
      parts.push(serializeInline(block.inline));
    } else {
      parts.push(block.latex);
    }
  }
  return parts.join("\n\n");
}

// Helpers for the editor: build a label for citation chips.
export function citationChipLabel(keys: string[]): string {
  if (keys.length === 0) return "cite";
  if (keys.length === 1) return keys[0];
  return `${keys[0]} +${keys.length - 1}`;
}
