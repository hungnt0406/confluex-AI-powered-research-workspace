"use client";

import {
  ChangeEvent,
  FormEvent,
  Fragment,
  KeyboardEvent,
  ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  type ChatMessage,
  type ChatMode,
  type ComposerNotice,
  type DeepSearchPlanMessage,
  type DeepSearchThinkingState,
  useChat,
} from "@/components/ChatProvider";
import { ProjectPaper } from "@/lib/api";
import Logo from "@/components/Logo";

const SUGGESTIONS = [
  "The impact of LLMs on Academic Integrity",
  "Microplastics in urban soil ecosystems",
  "Policy-driven shifts in remote education",
];

type PendingReferenceUpload = {
  file: File;
  topic: string;
};

export default function ChatWorkspace() {
  const {
    messages,
    activeProject,
    selectedPapers,
    busy,
    uploadingReferenceFile,
    composerNotice,
    chatMode,
    setChatMode,
    clearComposerNotice,
    submitMessage,
    startDeepSearchPlan,
    editDeepSearchPlan,
    startNewResearch,
    uploadReferenceFile,
    togglePaperSelection,
  } = useChat();
  const [draft, setDraft] = useState("");
  const [localComposerNotice, setLocalComposerNotice] = useState<ComposerNotice | null>(null);
  const [pendingReferenceUpload, setPendingReferenceUpload] =
    useState<PendingReferenceUpload | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const composerBusy = busy || uploadingReferenceFile;
  const visibleComposerNotice = localComposerNotice ?? composerNotice;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!activeProject) return;
    setPendingReferenceUpload(null);
  }, [activeProject?.id]);

  useEffect(() => {
    if (!composerNotice) return;
    setLocalComposerNotice(null);
  }, [composerNotice]);

  async function send(text: string) {
    if (!text.trim() || composerBusy) return;
    setDraft("");
    await submitMessage(text);
  }

  function onEditDeepSearchPlan(planId: string) {
    const question = editDeepSearchPlan(planId);
    if (question !== null) {
      setDraft(question);
    }
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

  async function performReferenceUpload(file: File, topic?: string) {
    if (!isPdfFile(file)) {
      clearComposerNotice();
      setLocalComposerNotice({ tone: "error", message: "Only PDF files are supported." });
      return false;
    }
    setLocalComposerNotice(null);
    clearComposerNotice();

    try {
      await uploadReferenceFile(file, topic ? { topic: topic.trim() } : undefined);
      return true;
    } catch {
      return false;
    }
  }

  function openReferencePicker() {
    if (composerBusy) return;
    clearComposerNotice();
    setLocalComposerNotice(null);
    fileInputRef.current?.click();
  }

  function onReferenceFilePicked(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!file) return;

    if (activeProject) {
      setPendingReferenceUpload(null);
      void performReferenceUpload(file);
      return;
    }

    clearComposerNotice();
    setLocalComposerNotice(null);
    setPendingReferenceUpload({ file, topic: draft.trim() });
  }

  async function confirmPendingReferenceUpload() {
    if (!pendingReferenceUpload) return;
    const topic = pendingReferenceUpload.topic.trim();
    if (!topic) {
      clearComposerNotice();
      setLocalComposerNotice({
        tone: "warning",
        message: "Add a research topic before uploading a PDF without an active project.",
      });
      return;
    }

    const uploaded = await performReferenceUpload(pendingReferenceUpload.file, topic);
    if (uploaded) {
      setPendingReferenceUpload(null);
    }
  }

  const showGreeting = messages.length === 0 && !activeProject;
  const composerPlaceholder = chatMode === "deep_search"
    ? activeProject
      ? "Run Deep Search across selected papers and web…"
      : "Describe a topic for Deep Search…"
    : activeProject
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
                    message={message}
                    disabled={composerBusy}
                    onStartDeepSearchPlan={(planId) => void startDeepSearchPlan(planId)}
                    onEditDeepSearchPlan={onEditDeepSearchPlan}
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
              <SelectedPapersStrip
                papers={selectedPapers.map((paper) => ({
                  id: paper.id,
                  title: paper.title,
                  isUploaded: isUploadedPaper(paper),
                }))}
                onRemove={togglePaperSelection}
              />
            )}
            {pendingReferenceUpload && !activeProject && (
              <div className="mb-3 rounded-2xl border border-outline/30 bg-surface-container-low px-3 py-3 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.2em] text-hint">
                      Reference PDF
                    </p>
                    <p className="mt-1 truncate text-xs font-medium text-on-surface">
                      {pendingReferenceUpload.file.name}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPendingReferenceUpload(null)}
                    disabled={composerBusy}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-primary/5 disabled:opacity-40"
                    aria-label="Cancel pending PDF upload"
                  >
                    <span className="material-symbols-outlined text-lg">close</span>
                  </button>
                </div>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                  <input
                    type="text"
                    value={pendingReferenceUpload.topic}
                    onChange={(e) =>
                      setPendingReferenceUpload((prev) =>
                        prev ? { ...prev, topic: e.target.value } : prev,
                      )
                    }
                    disabled={composerBusy}
                    autoFocus
                    className="h-10 flex-1 rounded-xl border border-outline/30 bg-background px-3 text-sm text-on-surface outline-none transition-colors placeholder:text-hint focus:border-primary/40 disabled:opacity-60"
                    placeholder="Add a topic for this uploaded PDF"
                    aria-label="Topic for uploaded PDF"
                  />
                  <button
                    type="button"
                    onClick={() => void confirmPendingReferenceUpload()}
                    disabled={composerBusy || !pendingReferenceUpload.topic.trim()}
                    className="inline-flex h-10 items-center justify-center rounded-xl bg-primary px-4 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-30"
                  >
                    Upload PDF
                  </button>
                </div>
              </div>
            )}
            {visibleComposerNotice && <ComposerInlineNotice notice={visibleComposerNotice} />}
            <ModeToggle mode={chatMode} onChange={setChatMode} disabled={composerBusy} />
            <form
              onSubmit={onSubmit}
              className="flex w-full items-center gap-1 bg-surface-container-low rounded-2xl border border-outline/30 px-2 py-2 focus-within:border-primary/40 transition-all shadow-sm"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={onReferenceFilePicked}
                className="sr-only"
                tabIndex={-1}
              />
              <button
                type="button"
                onClick={openReferencePicker}
                className="relative top-[2px] flex-shrink-0 p-2 text-secondary hover:bg-primary/5 rounded-lg transition-colors"
                disabled={composerBusy}
                title={activeProject ? "Upload PDF reference" : "Upload PDF to start a topic"}
                aria-label={activeProject ? "Upload PDF reference" : "Upload PDF to start a topic"}
              >
                <span className="material-symbols-outlined text-xl">add_circle</span>
              </button>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKey}
                disabled={composerBusy}
                className="min-h-10 flex-1 bg-transparent border-none focus:ring-0 text-base leading-6 px-1 py-[7px] resize-none font-ui text-on-surface placeholder:text-hint max-h-52 outline-none"
                placeholder={composerPlaceholder}
                aria-label={composerPlaceholder}
                rows={1}
              />
              <button
                type="submit"
                disabled={composerBusy || !draft.trim()}
                className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-primary text-white shadow-sm transition-all hover:opacity-90 active:scale-95 disabled:opacity-20"
              >
                <span className="material-symbols-outlined text-lg">arrow_upward</span>
              </button>
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

function ModeToggle({
  mode,
  onChange,
  disabled,
}: {
  mode: ChatMode;
  onChange: (mode: ChatMode) => void;
  disabled: boolean;
}) {
  return (
    <div
      className="mb-3 inline-flex rounded-xl border border-outline/30 bg-surface-container-low p-1"
      role="group"
      aria-label="Chat mode"
    >
      <button
        type="button"
        onClick={() => onChange("standard")}
        disabled={disabled}
        aria-pressed={mode === "standard"}
        className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-[11px] font-medium transition-colors disabled:opacity-40 ${
          mode === "standard"
            ? "bg-background text-on-surface shadow-sm"
            : "text-secondary hover:bg-primary/5 hover:text-on-surface"
        }`}
      >
        <span className="material-symbols-outlined text-sm" aria-hidden="true">
          chat
        </span>
        Standard
      </button>
      <button
        type="button"
        onClick={() => onChange("deep_search")}
        disabled={disabled}
        aria-pressed={mode === "deep_search"}
        className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-[11px] font-medium transition-colors disabled:opacity-40 ${
          mode === "deep_search"
            ? "bg-background text-on-surface shadow-sm"
            : "text-secondary hover:bg-primary/5 hover:text-on-surface"
        }`}
      >
        <span className="material-symbols-outlined text-sm" aria-hidden="true">
          travel_explore
        </span>
        Deep Search
      </button>
    </div>
  );
}

function SelectedPapersStrip({
  papers,
  onRemove,
}: {
  papers: { id: string; title: string; isUploaded?: boolean }[];
  onRemove: (paperId: string) => void;
}) {
  const visiblePapers = papers.slice(0, 3);
  const remainingCount = Math.max(papers.length - visiblePapers.length, 0);

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <span className="text-[10px] uppercase tracking-[0.2em] text-hint">
        Selected Papers
      </span>
      {visiblePapers.length > 0 ? (
        <>
          {visiblePapers.map((paper) => (
            <span
              key={paper.id}
              className="group inline-flex max-w-full items-center rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] text-primary"
            >
              {paper.isUploaded && (
                <span className="mr-2 inline-flex items-center gap-1 rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.16em] text-primary/80">
                  <span
                    className="material-symbols-outlined"
                    aria-hidden="true"
                    style={{ fontSize: "10px" }}
                  >
                    upload_file
                  </span>
                  PDF
                </span>
              )}
              <span className="truncate">{paper.title}</span>
              <button
                type="button"
                onClick={() => onRemove(paper.id)}
                aria-label={`Remove ${paper.title} from selected papers`}
                className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-primary/70 opacity-0 transition-opacity hover:bg-primary/10 hover:text-primary focus:opacity-100 focus:outline-none focus:ring-1 focus:ring-primary/40 group-hover:opacity-100"
              >
                <span
                  className="material-symbols-outlined"
                  aria-hidden="true"
                  style={{ fontSize: "14px" }}
                >
                  close
                </span>
              </button>
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

function ComposerInlineNotice({ notice }: { notice: ComposerNotice }) {
  return (
    <div
      className={`mb-3 rounded-2xl border px-3 py-2 text-xs ${
        notice.tone === "success"
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
          : notice.tone === "warning"
            ? "border-amber-500/20 bg-amber-500/10 text-amber-700"
            : "border-rose-500/20 bg-rose-500/10 text-rose-700"
      }`}
      role={notice.tone === "error" ? "alert" : "status"}
    >
      {notice.message}
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

function AgentBubble({
  message,
  disabled,
  onStartDeepSearchPlan,
  onEditDeepSearchPlan,
}: {
  message: ChatMessage;
  disabled: boolean;
  onStartDeepSearchPlan: (planId: string) => void;
  onEditDeepSearchPlan: (planId: string) => void;
}) {
  const kind = message.kind ?? "text";
  const isStatus = kind === "status";
  const isPlan = kind === "deep_search_plan" && message.deepSearchPlan;
  const isThinking = kind === "deep_search_thinking" && message.thinking;

  return (
    <div className="flex gap-4">
      <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0 mt-1">
        <span className="material-symbols-outlined text-primary text-sm">
          {isStatus ? "hourglass_top" : isPlan || isThinking ? "travel_explore" : "school"}
        </span>
      </div>
      <div
        className={`flex-1 text-xs leading-relaxed font-body ${
          isStatus ? "italic text-on-surface-variant" : "text-on-surface"
        }`}
      >
        {isPlan ? (
          <DeepSearchPlanCard
            plan={message.deepSearchPlan!}
            disabled={disabled}
            onStart={() => onStartDeepSearchPlan(message.deepSearchPlan!.id)}
            onEdit={() => onEditDeepSearchPlan(message.deepSearchPlan!.id)}
          />
        ) : isThinking ? (
          <DeepSearchThinkingPanel thinking={message.thinking!} />
        ) : isStatus ? (
          message.content
        ) : (
          <MarkdownContent text={message.content} />
        )}
      </div>
    </div>
  );
}

function DeepSearchPlanCard({
  plan,
  disabled,
  onStart,
  onEdit,
}: {
  plan: DeepSearchPlanMessage;
  disabled: boolean;
  onStart: () => void;
  onEdit: () => void;
}) {
  const pending = plan.status === "pending";
  const statusLabel = pending
    ? "Ready in a few mins"
    : plan.status === "started"
      ? "Research started"
      : plan.status === "editing"
        ? "Editing in composer"
        : "Replaced by newer plan";
  return (
    <div className="max-w-3xl rounded-2xl bg-surface-container-low px-5 py-5 shadow-sm ring-1 ring-outline/20">
      <p className="text-sm text-on-surface">Here&apos;s a research plan for that topic.</p>
      <div className="mt-4 space-y-4">
        <h3 className="text-sm font-semibold text-on-surface">
          Deep Search Plan
        </h3>
        <div className="space-y-4">
          {plan.steps.map((step) => (
            <div key={step.title} className="flex gap-3">
              <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center text-on-surface-variant">
                <span
                  className="material-symbols-outlined"
                  aria-hidden="true"
                  style={{ fontSize: "18px" }}
                >
                  {step.title === "Analyze Results"
                    ? "filter_list"
                    : step.title === "Create Report"
                      ? "manage_search"
                      : "content_copy"}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-on-surface">{step.title}</p>
                <ol className="mt-2 list-decimal space-y-1.5 pl-4 text-xs leading-relaxed text-on-surface-variant marker:text-hint">
                  {step.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 pt-2 text-xs text-on-surface-variant">
          <span
            className="material-symbols-outlined"
            aria-hidden="true"
            style={{ fontSize: "17px" }}
          >
            schedule
          </span>
          <span>{statusLabel}</span>
        </div>
      </div>
      {pending && (
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onEdit}
            disabled={disabled}
            className="inline-flex h-10 items-center justify-center rounded-full border border-outline/50 px-5 text-xs font-semibold text-primary transition-colors hover:bg-primary/5 disabled:opacity-40"
          >
            Edit plan
          </button>
          <button
            type="button"
            onClick={onStart}
            disabled={disabled}
            className="inline-flex h-10 items-center justify-center rounded-full bg-primary px-6 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            Start research
          </button>
        </div>
      )}
    </div>
  );
}

function DeepSearchThinkingPanel({ thinking }: { thinking: DeepSearchThinkingState }) {
  const [expanded, setExpanded] = useState(true);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const steps = thinking.steps;
  const activeStep = [...steps].reverse().find((step) => step.status === "active");

  useEffect(() => {
    if (thinking.completed) return;

    const startedAt = Date.now();
    const intervalId = window.setInterval(() => {
      setElapsedSeconds(Math.max(1, Math.round((Date.now() - startedAt) / 1000)));
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [thinking.id, thinking.completed]);

  return (
    <div className="max-w-3xl">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="inline-flex items-center gap-2 text-xs font-semibold text-on-surface transition-colors hover:text-primary"
        aria-expanded={expanded}
      >
        <span
          className="material-symbols-outlined text-primary"
          aria-hidden="true"
          style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
        >
          auto_awesome
        </span>
        Show thinking
        <span className="material-symbols-outlined text-sm" aria-hidden="true">
          {expanded ? "expand_less" : "expand_more"}
        </span>
      </button>
      {expanded && (
        <div className="mt-3 space-y-4 border-l border-outline/30 pl-5">
          {!thinking.completed && (
            <div className="max-w-md">
              <div className="flex items-center gap-2 text-[11px] font-medium text-on-surface-variant">
                <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" aria-hidden="true" />
                <span>
                  Working for {elapsedSeconds}s
                  {activeStep ? ` · ${activeStep.title}` : ""}
                </span>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-outline/20">
                <div className="h-full w-1/2 rounded-full bg-primary/50 animate-[progress-shimmer_1.4s_ease-in-out_infinite]" />
              </div>
            </div>
          )}
          {steps.map((step) => (
            <div
              key={step.phase}
              className={
                step.status === "active"
                  ? "text-on-surface"
                  : step.status === "pending"
                    ? "text-on-surface-variant/55"
                    : "text-on-surface-variant"
              }
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    step.status === "active"
                      ? "bg-primary animate-pulse"
                      : step.status === "pending"
                        ? "bg-outline/50"
                        : "bg-outline"
                  }`}
                  aria-hidden="true"
                />
                <p className="text-xs font-semibold italic">{step.title}</p>
              </div>
              <p className="mt-1 text-xs italic leading-relaxed">
                {step.detail}
              </p>
              {step.sources.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {step.sources.map((source) => (
                    <a
                      key={`${step.phase}-${source.id}-${source.title}`}
                      href={source.url ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      className={`inline-flex h-9 max-w-[220px] items-center gap-2 rounded-full bg-surface-container-low px-3 text-[11px] not-italic text-on-surface-variant ring-1 ring-outline/20 ${source.url ? "hover:text-primary" : "pointer-events-none"}`}
                    >
                      <ThinkingSourceFavicon source={source} />
                      <span className="truncate">{source.title}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ThinkingSourceFavicon({ source }: { source: { url: string | null } }) {
  const [failed, setFailed] = useState(false);
  const faviconUrl = source.url ? getFaviconUrl(source.url) : null;

  if (!faviconUrl || failed) {
    return (
      <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-surface-container-high text-hint ring-1 ring-outline/20">
        <span
          className="material-symbols-outlined"
          aria-hidden="true"
          style={{ fontSize: "13px" }}
        >
          article
        </span>
      </span>
    );
  }

  return (
    <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-surface-container-high ring-1 ring-outline/20">
      <img
        src={faviconUrl}
        alt=""
        aria-hidden="true"
        className="h-3.5 w-3.5 object-contain"
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    </span>
  );
}

function getFaviconUrl(url: string) {
  try {
    const hostname = new URL(url).hostname;
    if (!hostname) return null;
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(hostname)}&sz=32`;
  } catch {
    return null;
  }
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

function isPdfFile(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function isUploadedPaper(paper: ProjectPaper) {
  return Boolean(paper.reference_file_id) || paper.source.trim().toLowerCase() === "user_upload";
}
