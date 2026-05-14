"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  Block,
  InlineNode,
  citationChipLabel,
  parseLatexToBlocks,
  serializeBlocksToLatex,
} from "@/lib/latex-prose";

interface WriterProseEditorProps {
  value: string;
  onChange: (latex: string) => void;
  editorKey: string;
  onMount?: (el: HTMLElement | null) => void;
}

// The contenteditable surface is uncontrolled. To replace its contents
// (e.g., on section switch or after an AI patch lands), the parent should
// bump `editorKey` so we re-mount with the new initial value.
export function WriterProseEditor(props: WriterProseEditorProps) {
  return <WriterProseEditorImpl key={props.editorKey} {...props} />;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inlineToHtml(node: InlineNode): string {
  switch (node.type) {
    case "text":
      return escapeHtml(node.value);
    case "bold":
      return `<strong data-bold="1">${escapeHtml(node.value)}</strong>`;
    case "emph":
      return `<em data-emph="1">${escapeHtml(node.value)}</em>`;
    case "cite":
      return `<span class="wp-cite" contenteditable="false" data-cite-keys="${escapeHtml(
        node.keys.join(","),
      )}" title="${escapeHtml(node.keys.join(", "))}"><span class="material-symbols-outlined" aria-hidden="true">menu_book</span>${escapeHtml(
        citationChipLabel(node.keys),
      )}</span>`;
    case "todo":
      return `<span class="wp-todo" contenteditable="false" data-todo-text="${escapeHtml(
        node.value,
      )}" title="${escapeHtml(node.value)}"><span class="material-symbols-outlined" aria-hidden="true">flag</span>${escapeHtml(
        node.value,
      )}</span>`;
  }
}

function blockToHtml(block: Block): string {
  if (block.type === "heading") {
    const level = block.level === 1 ? "h2" : block.level === 2 ? "h3" : "h4";
    return `<${level} data-block-type="heading" data-level="${block.level}" class="wp-heading wp-h${block.level}">${escapeHtml(
      block.text,
    )}</${level}>`;
  }
  if (block.type === "raw") {
    return `<pre data-block-type="raw" class="wp-raw">${escapeHtml(block.latex)}</pre>`;
  }
  const inner = block.inline.map(inlineToHtml).join("") || "<br />";
  return `<p data-block-type="paragraph" class="wp-paragraph">${inner}</p>`;
}

function renderBlocksToHtml(blocks: Block[]): string {
  if (blocks.length === 0) {
    return `<p data-block-type="paragraph" class="wp-paragraph"><br /></p>`;
  }
  return blocks.map(blockToHtml).join("");
}

function readInlineFromNode(node: Node): InlineNode[] {
  const out: InlineNode[] = [];
  node.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) {
      const text = child.textContent ?? "";
      if (text.length > 0) out.push({ type: "text", value: text });
      return;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) return;
    const el = child as HTMLElement;

    if (el.dataset.citeKeys !== undefined) {
      const keys = el.dataset.citeKeys
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      out.push({ type: "cite", keys });
      return;
    }
    if (el.dataset.todoText !== undefined) {
      out.push({ type: "todo", value: el.dataset.todoText });
      return;
    }
    if (el.dataset.bold !== undefined) {
      out.push({ type: "bold", value: el.textContent ?? "" });
      return;
    }
    if (el.dataset.emph !== undefined) {
      out.push({ type: "emph", value: el.textContent ?? "" });
      return;
    }
    if (el.tagName === "BR") {
      out.push({ type: "text", value: "\n" });
      return;
    }
    // Unknown element (e.g., div from Enter key): flatten its text.
    const childInline = readInlineFromNode(el);
    if (childInline.length > 0) out.push(...childInline);
  });
  // Merge adjacent text nodes.
  const merged: InlineNode[] = [];
  for (const n of out) {
    const last = merged[merged.length - 1];
    if (n.type === "text" && last && last.type === "text") {
      last.value += n.value;
    } else {
      merged.push(n);
    }
  }
  return merged;
}

function readBlocksFromDom(container: HTMLElement): Block[] {
  const blocks: Block[] = [];
  container.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = (node.textContent ?? "").trim();
      if (text) blocks.push({ type: "paragraph", inline: [{ type: "text", value: text }] });
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node as HTMLElement;
    const blockType = el.dataset.blockType;

    if (blockType === "heading") {
      const level = Number(el.dataset.level ?? "1");
      const clamped = (level === 2 || level === 3 ? level : 1) as 1 | 2 | 3;
      blocks.push({ type: "heading", level: clamped, text: (el.textContent ?? "").trim() });
      return;
    }
    if (blockType === "raw") {
      blocks.push({ type: "raw", latex: el.textContent ?? "" });
      return;
    }
    // Default: paragraph.
    const inline = readInlineFromNode(el);
    // Drop completely empty paragraphs that only carry a <br>.
    const isEmpty =
      inline.length === 0 ||
      (inline.length === 1 && inline[0].type === "text" && inline[0].value.trim() === "");
    if (isEmpty) {
      blocks.push({ type: "paragraph", inline: [{ type: "text", value: "" }] });
      return;
    }
    blocks.push({ type: "paragraph", inline });
  });
  return blocks;
}

function WriterProseEditorImpl({ value, onChange, onMount }: WriterProseEditorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lastEmittedRef = useRef<string>(value);
  // Keep the latest onChange in a ref so handleInput is stable across renders.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const onMountRef = useRef(onMount);
  onMountRef.current = onMount;
  // initialValueRef captures the value at mount; the editor is uncontrolled
  // thereafter. To reset content (section switch), parent bumps `editorKey`.
  const initialValueRef = useRef(value);

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = renderBlocksToHtml(
      parseLatexToBlocks(initialValueRef.current),
    );
    lastEmittedRef.current = initialValueRef.current;
    onMountRef.current?.(containerRef.current);
    return () => {
      onMountRef.current?.(null);
    };
  }, []);

  const handleInput = useCallback(() => {
    if (!containerRef.current) return;
    const blocks = readBlocksFromDom(containerRef.current);
    const next = serializeBlocksToLatex(blocks);
    if (next === lastEmittedRef.current) return;
    lastEmittedRef.current = next;
    onChangeRef.current(next);
  }, []);

  return (
    <div className="h-full w-full overflow-auto bg-stone-50">
      <div className="mx-auto max-w-3xl px-12 py-10">
        <div
          ref={containerRef}
          contentEditable
          suppressContentEditableWarning
          spellCheck
          role="textbox"
          aria-multiline="true"
          aria-label="Document editor"
          className="wp-editor min-h-[60vh] outline-none font-serif text-[15px] leading-[1.75] text-stone-900"
          onInput={handleInput}
          onBlur={handleInput}
        />
      </div>
      <style jsx global>{`
        .wp-editor .wp-heading {
          font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
          font-weight: 700;
          color: rgb(28, 25, 23);
          line-height: 1.25;
        }
        .wp-editor .wp-h1 {
          font-size: 1.875rem;
          margin: 1.5rem 0 1rem;
          border-bottom: 1px solid rgb(231, 229, 228);
          padding-bottom: 0.4rem;
        }
        .wp-editor .wp-h2 {
          font-size: 1.4rem;
          margin: 1.25rem 0 0.75rem;
        }
        .wp-editor .wp-h3 {
          font-size: 1.15rem;
          margin: 1rem 0 0.5rem;
          color: rgb(68, 64, 60);
        }
        .wp-editor .wp-paragraph {
          margin: 0 0 0.9rem;
          min-height: 1.5em;
        }
        .wp-editor .wp-raw {
          margin: 0.5rem 0;
          padding: 0.6rem 0.8rem;
          background: rgb(244, 244, 245);
          border-left: 3px solid rgb(168, 162, 158);
          font-family: ui-monospace, SFMono-Regular, monospace;
          font-size: 12px;
          color: rgb(68, 64, 60);
          white-space: pre-wrap;
          border-radius: 4px;
        }
        .wp-editor .wp-cite,
        .wp-editor .wp-todo {
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
          padding: 0.05rem 0.45rem;
          margin: 0 0.1rem;
          border-radius: 9999px;
          font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
          font-size: 11px;
          font-weight: 600;
          vertical-align: baseline;
          line-height: 1.4;
          user-select: all;
          cursor: default;
        }
        .wp-editor .wp-cite {
          background: rgb(219, 234, 254);
          color: rgb(30, 64, 175);
          border: 1px solid rgb(191, 219, 254);
        }
        .wp-editor .wp-todo {
          background: rgb(254, 243, 199);
          color: rgb(146, 64, 14);
          border: 1px solid rgb(253, 224, 71);
        }
        .wp-editor .wp-cite .material-symbols-outlined,
        .wp-editor .wp-todo .material-symbols-outlined {
          font-size: 13px;
        }
        .wp-editor strong {
          font-weight: 700;
        }
        .wp-editor em {
          font-style: italic;
        }
        .wp-editor:focus-visible {
          outline: none;
        }
        .wp-editor [contenteditable="false"]::selection {
          background: transparent;
        }
      `}</style>
    </div>
  );
}
