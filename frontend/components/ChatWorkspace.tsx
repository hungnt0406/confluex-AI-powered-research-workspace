"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
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

  return (
    <main className="flex-1 flex flex-col relative h-full bg-background overflow-hidden">
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
            <form
              onSubmit={onSubmit}
              className="relative flex flex-col w-full bg-surface-container-low rounded-2xl border border-outline/30 focus-within:border-primary/40 transition-all shadow-sm"
            >
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKey}
                disabled={busy}
                className="w-full bg-transparent border-none focus:ring-0 text-base py-3.5 px-4 pr-12 resize-none font-ui text-on-surface placeholder:text-hint max-h-52 outline-none"
                placeholder={
                  activeProject
                    ? "Ask a grounded follow-up about this project…"
                    : "Describe a research topic to begin…"
                }
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
        className={`flex-1 space-y-2 text-xs leading-relaxed font-body whitespace-pre-wrap ${
          isStatus ? "italic text-on-surface-variant" : "text-on-surface"
        }`}
      >
        {text}
      </div>
    </div>
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
