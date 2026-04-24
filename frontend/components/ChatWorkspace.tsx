"use client";

import { FormEvent, Fragment, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { useChat } from "@/components/ChatProvider";
import Logo from "@/components/Logo";

const SUGGESTIONS = [
  "The impact of LLMs on Academic Integrity",
  "Microplastics in urban soil ecosystems",
  "Policy-driven shifts in remote education",
];

export default function ChatWorkspace() {
  const {
    messages,
    activeProject,
    selectedPapers,
    busy,
    submitMessage,
    startNewResearch,
  } = useChat();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setDraft("");
    await submitMessage(text);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(draft);
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(draft);
    }
  }

  const showGreeting = messages.length === 0 && !activeProject;
  const composerPlaceholder = activeProject
    ? "Ask a grounded question about the selected papers…"
    : "Describe a research topic to begin…";

  return (
    <main className="min-w-0 flex-1 flex flex-col relative h-full bg-background overflow-hidden">
      <header className="h-14 flex items-center justify-between px-4 sticky top-0 bg-background/80 backdrop-blur-md z-40 md:justify-center">
        <button className="md:hidden p-2 text-on-surface-variant">
          <span className="material-symbols-outlined">menu</span>
        </button>
        <div className="text-sm font-bold text-on-surface flex items-center gap-2">
          <Logo size="sm" />
          <span className="material-symbols-outlined text-xs text-hint">expand_more</span>
        </div>
        <div className="md:hidden">
          <button onClick={startNewResearch} className="p-2 text-on-surface-variant">
            <span className="material-symbols-outlined">edit_square</span>
          </button>
        </div>
      </header>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div ref={scrollRef} className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="chat-container px-4 py-12 space-y-12">
            {showGreeting && (
              <div className="flex flex-col items-center text-center space-y-6 py-10">
                <div className="space-y-2">
                  <h2 className="font-headline text-2xl font-medium text-on-surface">
                    How can I assist your research today?
                  </h2>
                  <p className="font-body text-xs text-secondary max-w-md mx-auto leading-relaxed">
                    I&apos;m your AI Research Agent, ready to help you explore,{" "}
                    <span className="text-primary font-semibold">synthesize</span>, and organize
                    academic literature.
                  </p>
                </div>
              </div>
            )}

            {showGreeting && <OpeningAgentMessage onPick={(text) => void send(text)} />}

            <div className="space-y-8">
              {messages.map((message) =>
                message.role === "user" ? (
                  <UserBubble key={message.id} text={message.content} />
                ) : (
                  <AgentBubble
                    key={message.id}
                    text={message.content}
                    kind={message.kind ?? "text"}
                  />
                ),
              )}
              {busy && <TypingIndicator />}
            </div>
          </div>
        </div>

        <div className="w-full bg-gradient-to-t from-background via-background to-transparent pt-10 pb-6">
          <div className="chat-container px-4">
            {activeProject && (
              <SelectedPapersStrip titles={selectedPapers.map((paper) => paper.title)} />
            )}
            <form
              onSubmit={onSubmit}
              className="relative flex flex-col w-full bg-surface-container-low rounded-2xl border border-outline/30 focus-within:border-primary/40 transition-all shadow-sm"
            >
              {!draft && (
                <div className="pointer-events-none absolute left-4 right-14 top-3.5 overflow-hidden text-ellipsis whitespace-nowrap text-base text-hint">
                  {composerPlaceholder}
                </div>
              )}
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKey}
                disabled={busy}
                className="w-full bg-transparent border-none focus:ring-0 text-base py-3.5 px-4 pr-12 resize-none font-ui text-on-surface placeholder:text-hint max-h-52 outline-none"
                placeholder=""
                aria-label={composerPlaceholder}
                rows={1}
              />
              <div className="flex items-center justify-between px-2 pb-2">
                <div className="flex items-center gap-0.5">
                  <button
                    type="button"
                    className="p-2 text-secondary hover:bg-primary/5 rounded-lg transition-colors"
                    disabled
                    title="Coming soon"
                  >
                    <span className="material-symbols-outlined text-xl">add_circle</span>
                  </button>
                  <button
                    type="button"
                    className="p-2 text-secondary hover:bg-primary/5 rounded-lg transition-colors"
                    disabled
                    title="Coming soon"
                  >
                    <span className="material-symbols-outlined text-xl">mic</span>
                  </button>
                </div>
                <button
                  type="submit"
                  disabled={busy || !draft.trim()}
                  className="bg-primary text-white w-8 h-8 rounded-lg shadow-sm hover:opacity-90 active:scale-95 transition-all flex items-center justify-center disabled:opacity-20"
                >
                  <span className="material-symbols-outlined text-lg">arrow_upward</span>
                </button>
              </div>
            </form>
            <p className="font-ui text-[10px] text-center mt-3 text-hint uppercase tracking-[0.2em] font-medium">
              Secured Academic Session • 225M Papers Indexed
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}

function SelectedPapersStrip({ titles }: { titles: string[] }) {
  const visibleTitles = titles.slice(0, 3);
  const remainingCount = Math.max(titles.length - visibleTitles.length, 0);

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <span className="text-[10px] uppercase tracking-[0.2em] text-hint">
        Selected Papers
      </span>
      {visibleTitles.length > 0 ? (
        <>
          {visibleTitles.map((title) => (
            <span
              key={title}
              className="inline-flex max-w-full items-center rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] text-primary"
            >
              <span className="truncate">{title}</span>
            </span>
          ))}
          {remainingCount > 0 && (
            <span className="inline-flex items-center rounded-full border border-outline/30 px-3 py-1 text-[11px] text-hint">
              +{remainingCount} more
            </span>
          )}
        </>
      ) : (
        <span className="text-[11px] text-hint">Choose at least one paper from the panel.</span>
      )}
    </div>
  );
}

function OpeningAgentMessage({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex gap-4 group">
      <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0 mt-1">
        <span className="material-symbols-outlined text-primary text-sm">school</span>
      </div>
      <div className="flex-1 space-y-4">
        <div className="prose prose-sm max-w-none text-on-surface leading-relaxed font-body">
          <p className="font-headline text-xl mb-3 text-on-surface font-medium">
            To begin our journey through the literature, we must first establish a precise focal
            point.
          </p>
          <p className="text-sm">
            Describe your research topic or question in detail. I&apos;ll help you expand your
            queries and find relevant papers.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => onPick(s)}
              className="font-ui px-3 py-2 rounded-xl border border-outline/50 bg-secondary-container/30 hover:bg-secondary-container transition-all text-xs font-medium text-primary"
            >
              &ldquo;{s}&rdquo;
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] px-4 py-2.5 rounded-2xl bg-primary text-on-primary text-xs whitespace-pre-wrap leading-relaxed shadow-sm">
        {text}
      </div>
    </div>
  );
}

function AgentBubble({ text, kind }: { text: string; kind: "text" | "status" | "summary" }) {
  const isStatus = kind === "status";
  return (
    <div className="flex gap-4">
      <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0 mt-1">
        <span className="material-symbols-outlined text-primary text-sm">
          {isStatus ? "hourglass_top" : "school"}
        </span>
      </div>
      <div
        className={`flex-1 text-xs leading-relaxed font-body ${
          isStatus ? "italic text-on-surface-variant" : "text-on-surface"
        }`}
      >
        {isStatus ? text : <MarkdownContent text={text} />}
      </div>
    </div>
  );
}

function MarkdownContent({ text }: { text: string }) {
  return <div className="space-y-3">{renderMarkdownBlocks(text)}</div>;
}

function renderMarkdownBlocks(text: string): ReactNode[] {
  const lines = normalizeMarkdownForDisplay(text).split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push(
        <pre
          key={`code-${index}`}
          className="overflow-x-auto rounded-xl bg-surface-container-low px-3 py-2 text-[11px] leading-relaxed text-on-surface"
        >
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const content = headingMatch[2];
      const className =
        level === 1
          ? "text-lg font-semibold"
          : level === 2
            ? "text-base font-semibold"
            : "text-sm font-semibold";
      blocks.push(
        <div key={`heading-${index}`} className={className}>
          {renderInlineMarkdown(content)}
        </div>,
      );
      index += 1;
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={`ordered-${index}`} className="list-decimal space-y-1.5 pl-5 marker:text-hint">
          {items.map((item, itemIndex) => (
            <li key={`ordered-item-${itemIndex}`} className="pl-1">
              {renderInlineMarkdown(item)}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*+]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*+]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={`unordered-${index}`} className="list-disc space-y-1.5 pl-5 marker:text-hint">
          {items.map((item, itemIndex) => (
            <li key={`unordered-item-${itemIndex}`} className="pl-1">
              {renderInlineMarkdown(item)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    const paragraphLines: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith("```") &&
      !/^(#{1,6})\s+/.test(lines[index].trim()) &&
      !/^\d+\.\s+/.test(lines[index].trim()) &&
      !/^[-*+]\s+/.test(lines[index].trim())
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push(
      <p key={`paragraph-${index}`} className="whitespace-normal text-xs leading-relaxed">
        {renderInlineMarkdown(paragraphLines.join(" "))}
      </p>,
    );
  }

  return blocks;
}

function normalizeMarkdownForDisplay(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])([ \t]+)(#{1,6}\s+\S)/g, "$1\n\n$3");
}

function renderTextWithLinks(text: string, keyPrefix: string): ReactNode[] {
  const urlPattern = /https?:\/\/[^\s<]+/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let matchIndex = 0;

  for (const match of text.matchAll(urlPattern)) {
    const url = match[0];
    const start = match.index ?? 0;
    let trimmedUrl = url;
    let trailing = "";

    while (/[),.;!?]$/.test(trimmedUrl)) {
      trailing = trimmedUrl.slice(-1) + trailing;
      trimmedUrl = trimmedUrl.slice(0, -1);
    }

    if (start > cursor) {
      nodes.push(
        <Fragment key={`${keyPrefix}-text-${matchIndex}`}>
          {text.slice(cursor, start)}
        </Fragment>,
      );
    }

    nodes.push(
      <a
        key={`${keyPrefix}-link-${matchIndex}`}
        href={trimmedUrl}
        target="_blank"
        rel="noreferrer"
        className="text-primary underline underline-offset-2 break-all hover:opacity-80"
      >
        {trimmedUrl}
      </a>,
    );

    if (trailing) {
      nodes.push(
        <Fragment key={`${keyPrefix}-trailing-${matchIndex}`}>
          {trailing}
        </Fragment>,
      );
    }

    cursor = start + url.length;
    matchIndex += 1;
  }

  if (cursor < text.length) {
    nodes.push(
      <Fragment key={`${keyPrefix}-tail`}>
        {text.slice(cursor)}
      </Fragment>,
    );
  }

  return nodes.length > 0 ? nodes : [text];
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const matches = text.match(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g);
  if (!matches) {
    return renderTextWithLinks(text, "plain");
  }

  const nodes: ReactNode[] = [];
  let cursor = 0;
  let tokenIndex = 0;

  for (const match of matches) {
    const start = text.indexOf(match, cursor);
    if (start > cursor) {
      nodes.push(text.slice(cursor, start));
    }

    if (match.startsWith("**") && match.endsWith("**")) {
      nodes.push(
        <strong key={`strong-${tokenIndex}`} className="font-semibold text-on-surface">
          {match.slice(2, -2)}
        </strong>,
      );
    } else if (match.startsWith("`") && match.endsWith("`")) {
      nodes.push(
        <code
          key={`code-${tokenIndex}`}
          className="rounded bg-surface-container px-1 py-0.5 font-mono text-[11px] text-on-surface"
        >
          {match.slice(1, -1)}
        </code>,
      );
    } else if (match.startsWith("*") && match.endsWith("*")) {
      nodes.push(
        <em key={`em-${tokenIndex}`} className="italic">
          {match.slice(1, -1)}
        </em>,
      );
    }

    cursor = start + match.length;
    tokenIndex += 1;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }

  return nodes.flatMap((node, index) =>
    typeof node === "string" ? renderTextWithLinks(node, `text-${index}`) : [node],
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-4">
      <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0 mt-1">
        <span className="material-symbols-outlined text-primary text-sm">school</span>
      </div>
      <div className="flex items-center gap-1 mt-3">
        <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.3s]" />
        <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.15s]" />
        <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce" />
      </div>
    </div>
  );
}
