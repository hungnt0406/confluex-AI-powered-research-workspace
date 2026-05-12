"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useAuth } from "@/components/AuthProvider";
import {
  CitationGraph,
  CitationGraphPaper,
  DeepSearchRun,
  DeepSearchActivityEventData,
  DeepSearchActivityChipType,
  DeepSearchActivityEventType,
  DeepSearchActivitySource,
  DeepSearchSource,
  DeepSearchSourceEventData,
  DeepSearchRunSummary,
  Paginated,
  Project,
  ProjectConversation,
  ProjectConversationSummary,
  ProjectPaper,
  ProjectTitleUpdate,
  RunPipelineResponse,
  api,
  fetchPaperCitationGraph,
  importCitationGraphPaper,
  isInsufficientCreditsError,
  notifyCreditBalanceChanged,
  streamDeepSearchRun,
  streamProjectPipeline,
  streamProjectConversation,
  uploadProjectReferenceFile,
} from "@/lib/api";

const ACTIVE_PROJECT_STORAGE_PREFIX = "a20.active_project";
const SELECTED_PAPERS_STORAGE_PREFIX = "a20.selected_papers";
const GENERATED_OVERVIEW_PROMPT_PREFIX = "Give me a structured overview of this paper relative to: ";
const MAX_SELECTED_PAPERS = 5;
const DEFAULT_CITATION_FORMAT = "APA";

function citationGraphCacheKey(projectId: string, paperId: string, limit: number) {
  return `${projectId}:${paperId}:${limit}`;
}

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  kind?: "text" | "status" | "summary" | "deep_search_plan" | "deep_search_thinking";
  sources?: DeepSearchDisplaySource[];
  deepSearchPlan?: DeepSearchPlanMessage;
  thinking?: DeepSearchThinkingState;
  createdAt: string;
};

export type ChatMode = "standard" | "deep_search" | "deep_research_max";

export type DeepSearchDisplaySource = {
  id: string;
  title: string;
  url: string | null;
  sourceType: DeepSearchSource["source_type"] | DeepSearchActivityChipType;
  note?: string;
};

export type DeepSearchPlanMessage = {
  id: string;
  question: string;
  projectId: string | null;
  status: "generating" | "pending" | "started" | "editing" | "superseded";
  questions: string[];
  mode: "standard" | "max";
  createdAt: string;
};

export type DeepSearchThinkingStep = {
  phase: string;
  title: string;
  detail: string;
  status: "pending" | "active" | "complete";
  sources: DeepSearchDisplaySource[];
};

export type DeepSearchThinkingState = {
  id: string;
  question: string;
  completed: boolean;
  steps: DeepSearchThinkingStep[];
};

export type ComposerNotice = {
  tone: "success" | "warning" | "error";
  message: string;
};

export type UploadReferenceFileOptions = {
  topic?: string;
};

export type InsufficientCreditsNotice = {
  message: string;
  required?: number;
  balance?: number;
  href: string;
  ctaLabel: string;
};

type ChatState = {
  projects: Project[];
  activeProject: Project | null;
  messages: ChatMessage[];
  papers: ProjectPaper[];
  selectedPaperIds: string[];
  selectedPapers: ProjectPaper[];
  deepSearchSources: DeepSearchDisplaySource[];
  pendingDeepSearchPlan: DeepSearchPlanMessage | null;
  queries: string[];
  conversation: ProjectConversation | null;
  runSummary: RunPipelineResponse | null;
  busy: boolean;
  uploadingReferenceFile: boolean;
  error: string | null;
  insufficientCredits: InsufficientCreditsNotice | null;
  composerNotice: ComposerNotice | null;
  lastUploadedPaperId: string | null;
  chatMode: ChatMode;
  setChatMode: (mode: ChatMode) => void;
  selectProject: (id: string) => Promise<void>;
  renameProject: (id: string, title: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  startNewResearch: () => void;
  submitMessage: (text: string) => Promise<void>;
  startDeepSearchPlan: (planId: string) => Promise<void>;
  editDeepSearchPlan: (planId: string) => string | null;
  uploadReferenceFile: (file: File, options?: UploadReferenceFileOptions) => Promise<void>;
  togglePaperSelection: (paperId: string) => void;
  citationGraphCache: Record<string, CitationGraph>;
  getCitationGraph: (
    projectId: string,
    paperId: string,
    options?: { limit?: number; force?: boolean },
  ) => Promise<CitationGraph>;
  prefetchCitationGraphs: (
    projectId: string,
    paperIds: string[],
    options?: { limit?: number },
  ) => Promise<void>;
  addCitationGraphPaperToProject: (
    projectId: string,
    paper: CitationGraphPaper,
  ) => Promise<{ paper: ProjectPaper; created: boolean }>;
  clearComposerNotice: () => void;
  clearInsufficientCredits: () => void;
  refreshProjects: () => Promise<void>;
};

type ProjectChatSnapshot = {
  project: Project;
  messages: ChatMessage[];
  papers: ProjectPaper[];
  selectedPaperIds: string[];
  queries: string[];
  conversation: ProjectConversation | null;
  runSummary: RunPipelineResponse | null;
};

const ChatContext = createContext<ChatState | null>(null);

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function now() {
  return new Date().toISOString();
}

function getActiveProjectStorageKey(userId: string) {
  return `${ACTIVE_PROJECT_STORAGE_PREFIX}.${userId}`;
}

function getSelectedPapersStorageKey(userId: string, projectId: string) {
  return `${SELECTED_PAPERS_STORAGE_PREFIX}.${userId}.${projectId}`;
}

function loadSavedActiveProjectId(userId: string | null | undefined) {
  if (typeof window === "undefined" || !userId) return null;
  return window.localStorage.getItem(getActiveProjectStorageKey(userId));
}

function loadRouteProjectId() {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("project");
}

function persistActiveProjectId(userId: string | null | undefined, projectId: string | null) {
  if (typeof window === "undefined" || !userId) return;
  const storageKey = getActiveProjectStorageKey(userId);
  if (projectId) {
    window.localStorage.setItem(storageKey, projectId);
    return;
  }
  window.localStorage.removeItem(storageKey);
}

function loadSavedSelectedPaperIds(
  userId: string | null | undefined,
  projectId: string | null,
): string[] | null {
  if (typeof window === "undefined" || !userId || !projectId) return null;
  const raw = window.localStorage.getItem(getSelectedPapersStorageKey(userId, projectId));
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : [];
  } catch {
    return null;
  }
}

function persistSelectedPaperIds(
  userId: string | null | undefined,
  projectId: string | null,
  paperIds: string[],
) {
  if (typeof window === "undefined" || !userId || !projectId) return;
  const storageKey = getSelectedPapersStorageKey(userId, projectId);
  window.localStorage.setItem(storageKey, JSON.stringify(paperIds));
}

function normalizeSelectedPaperIds(paperIds: string[], papers: ProjectPaper[]) {
  const availableIds = new Set(papers.map((paper) => paper.id));
  return Array.from(new Set(paperIds)).filter((paperId) => availableIds.has(paperId)).slice(0, MAX_SELECTED_PAPERS);
}

function arePaperIdListsEqual(left: string[], right: string[]) {
  return left.length === right.length && left.every((paperId, index) => paperId === right[index]);
}

function buildProjectCreatePayload(topic: string) {
  return {
    title: topic.slice(0, 120),
    topic_description: topic,
    citation_format: DEFAULT_CITATION_FORMAT,
  };
}

function isUploadedProjectPaper(paper: ProjectPaper) {
  return Boolean(paper.reference_file_id) || paper.source.trim().toLowerCase() === "user_upload";
}

function hasDiscoveredProjectPapers(papers: ProjectPaper[]) {
  return papers.some((paper) => !isUploadedProjectPaper(paper));
}

function patchProjectPaper(papers: ProjectPaper[], updatedPaper: ProjectPaper) {
  return papers.map((paper) => (paper.id === updatedPaper.id ? updatedPaper : paper));
}

function pipelineSummaryPaper(data: { paper: ProjectPaper } | ProjectPaper) {
  return "paper" in data ? data.paper : data;
}

function buildProjectShellMessages(
  project: Project,
  papers: ProjectPaper[],
  options: { omitEmptyPaperStatus?: boolean } = {},
): ChatMessage[] {
  const uploadedPaperCount = papers.filter(isUploadedProjectPaper).length;
  const hasOnlyUploadedPapers = uploadedPaperCount > 0 && uploadedPaperCount === papers.length;
  const initial: ChatMessage[] = [
    {
      id: uid(),
      role: "user",
      content: project.topic_description,
      kind: "text",
      createdAt: project.created_at,
    },
  ];

  if (papers.length > 0) {
    initial.push({
      id: uid(),
      role: "assistant",
      kind: "summary",
      content: hasOnlyUploadedPapers
        ? `This project currently contains ${uploadedPaperCount} uploaded paper${uploadedPaperCount === 1 ? "" : "s"}. Choose which ones to use for grounded questions, or run discovery to find related work.`
        : `I found ${papers.length} ranked papers for "${project.title}". No papers are selected yet. You can choose up to ${MAX_SELECTED_PAPERS} papers for grounded questions.`,
      createdAt: now(),
    });
    return initial;
  }

  if (!options.omitEmptyPaperStatus) {
    initial.push({
      id: uid(),
      role: "assistant",
      kind: "status",
      content: "This project has no ranked papers yet. Send a follow-up message to run the discovery pipeline.",
      createdAt: now(),
    });
  }
  return initial;
}

function buildRestoredConversationMessages(
  project: Project,
  restoredConversation: ProjectConversation,
): ChatMessage[] {
  const generatedOverviewPrompt = `${GENERATED_OVERVIEW_PROMPT_PREFIX}${project.topic_description}`;

  return restoredConversation.messages
    .filter(
      (message, index) =>
        message.role !== "system" &&
        !(
          index === 0 &&
          message.role === "user" &&
          (message.content === generatedOverviewPrompt || message.content === project.topic_description)
        ),
    )
    .map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      kind: message.role === "system" ? ("status" as const) : ("text" as const),
      createdAt: message.created_at,
    }));
}

function restoredChatSortKey(message: ChatMessage) {
  const parsed = Date.parse(message.createdAt);
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

function sortRestoredChatMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .map((message, index) => ({
      index,
      message,
      sortKey: restoredChatSortKey(message),
    }))
    .sort((left, right) => {
      if (left.sortKey < right.sortKey) return -1;
      if (left.sortKey > right.sortKey) return 1;
      return left.index - right.index;
    })
    .map(({ message }) => message);
}

function deepSearchSourceEventToDisplaySource(
  source: DeepSearchSourceEventData,
): DeepSearchDisplaySource {
  return {
    id: source.id,
    title: source.title,
    url: source.url,
    sourceType: source.source_type,
    note: source.note,
  };
}

function activitySourceTypeFromBackend(sourceType: string): DeepSearchActivityChipType {
  if (sourceType === "paper") return "paper";
  if (sourceType === "paper_chunk") return "pdf";
  if (sourceType === "web") return "website";
  if (sourceType === "citation_graph") return "paper";
  return "other";
}

function deepSearchActivitySourceToDisplaySource(
  source: DeepSearchActivitySource,
): DeepSearchDisplaySource {
  return {
    id: source.id,
    title: source.title,
    url: source.url,
    sourceType: source.type ?? activitySourceTypeFromBackend(source.source_type),
  };
}

function deepSearchSourceToDisplaySource(source: DeepSearchSource): DeepSearchDisplaySource {
  const sourceId = typeof source.metadata?.source_id === "string"
    ? source.metadata.source_id
    : source.id;
  return {
    id: sourceId,
    title: source.title,
    url: source.url,
    sourceType: source.source_type,
    note: source.note ?? (typeof source.metadata?.note === "string" ? source.metadata.note : undefined),
  };
}

function dedupeDeepSearchSources(sources: DeepSearchDisplaySource[]) {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const key = source.url ?? `${source.id}:${source.title}:${source.sourceType}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function deepSearchActivityEventType(
  activity: DeepSearchActivityEventData,
): DeepSearchActivityEventType {
  return activity.event_type ?? activity.type ?? "stage_update";
}

function deepSearchActivityTitle(activity: DeepSearchActivityEventData) {
  return activity.title || activity.stage || formatDeepSearchPhase(activity.phase);
}

function deepSearchActivityMessage(activity: DeepSearchActivityEventData) {
  return activity.message ?? activity.detail ?? "I am updating the research progress.";
}

function truncateForUi(text: string, maxLength: number) {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function createDeepSearchPlanMessage(
  question: string,
  projectId: string | null,
  mode: "standard" | "max" = "standard",
): ChatMessage & { deepSearchPlan: DeepSearchPlanMessage } {
  const createdAt = now();
  const plan: DeepSearchPlanMessage = {
    id: uid(),
    question,
    projectId,
    status: "generating",
    questions: [],
    mode,
    createdAt,
  };
  return {
    id: `deep-search-plan-${plan.id}`,
    role: "assistant",
    kind: "deep_search_plan",
    content: "Here's a research plan for that topic.",
    deepSearchPlan: plan,
    createdAt,
  };
}

const DEEP_SEARCH_THINKING_PHASES = [
  "planning",
  "project_evidence",
  "academic_search",
  "web_search",
  "deciding",
  "summarizing_sources",
  "writing",
  "verifying",
] as const;

function deepSearchThinkingDefinition(phase: string, question: string) {
  const compactQuestion = truncateForUi(question, 140);
  const definitions: Record<string, { title: string; detail: string }> = {
    planning: {
      title: "Defining the research paradigm",
      detail: `I am turning "${compactQuestion}" into focused research questions and deciding which evidence paths to inspect first.`,
    },
    project_evidence: {
      title: "Reading selected project papers",
      detail: "I am extracting relevant abstracts, summaries, and available PDF chunks from the selected papers.",
    },
    academic_search: {
      title: "Mapping the academic landscape",
      detail: "I am searching scholarly providers for papers that can confirm, refine, or challenge the project evidence.",
    },
    web_search: {
      title: "Researching websites",
      detail: "I am checking current web sources for recent context, implementations, and supporting material.",
    },
    deciding: {
      title: "Reasoning about gaps",
      detail: "I am reviewing what I've found and deciding what to search next.",
    },
    summarizing_sources: {
      title: "Uncovering source signals",
      detail: "I am compressing each source into a short evidence note and filtering duplicate results.",
    },
    writing: {
      title: "Synthesizing the report",
      detail: "I am drafting the final answer and attaching named source links to factual claims.",
    },
    verifying: {
      title: "Resolving verification and citation gaps",
      detail: "I am checking whether claims are cited and flagging weak or web-only evidence.",
    },
    persisting: {
      title: "Saving research artifacts",
      detail: "I am storing the report, source list, warnings, and QA flags for refresh and later review.",
    },
  };
  return definitions[phase] ?? {
    title: formatDeepSearchPhase(phase),
    detail: "I am advancing the deep research workflow and preparing the next step.",
  };
}

function buildInitialDeepSearchThinkingSteps(question: string): DeepSearchThinkingStep[] {
  return DEEP_SEARCH_THINKING_PHASES.map((phase, index) => ({
    phase,
    ...deepSearchThinkingDefinition(phase, question),
    status: index === 0 ? "active" : "pending",
    sources: [],
  }));
}

function createDeepSearchThinkingMessage(question: string): ChatMessage {
  const thinking: DeepSearchThinkingState = {
    id: uid(),
    question,
    completed: false,
    steps: buildInitialDeepSearchThinkingSteps(question),
  };
  return {
    id: `deep-search-thinking-${thinking.id}`,
    role: "assistant",
    kind: "deep_search_thinking",
    content: "Show thinking",
    thinking,
    createdAt: now(),
  };
}

function upsertDeepSearchThinkingPhase(
  thinking: DeepSearchThinkingState,
  phase: string,
): DeepSearchThinkingState {
  const definition = deepSearchThinkingDefinition(phase, thinking.question);
  const existingIndex = thinking.steps.findIndex((step) => step.phase === phase);
  if (existingIndex >= 0) {
    const nextSteps = thinking.steps.map((step, index) => ({
      ...step,
      title: index === existingIndex ? definition.title : step.title,
      detail: index === existingIndex ? definition.detail : step.detail,
      status: index < existingIndex
        ? "complete" as const
        : index === existingIndex
          ? "active" as const
          : "pending" as const,
    }));
    return { ...thinking, completed: false, steps: nextSteps };
  }

  const nextSteps = thinking.steps.map((step) => ({
    ...step,
    status: "complete" as const,
  }));
  return {
    ...thinking,
    completed: false,
    steps: [
      ...nextSteps,
      {
        phase,
        title: definition.title,
        detail: definition.detail,
        status: "active",
        sources: [],
      },
    ],
  };
}

function appendDeepSearchThinkingSourceToState(
  thinking: DeepSearchThinkingState,
  source: DeepSearchSourceEventData,
): DeepSearchThinkingState {
  const displaySource = deepSearchSourceEventToDisplaySource(source);
  const targetPhase = source.source_type === "web" ? "web_search" : "academic_search";
  const existingStep = thinking.steps.find((step) => step.phase === targetPhase);
  const steps = existingStep
    ? thinking.steps
    : [
      ...thinking.steps,
      {
        phase: targetPhase,
        ...deepSearchThinkingDefinition(targetPhase, thinking.question),
        status: "complete" as const,
        sources: [],
      },
    ];

  return {
    ...thinking,
    steps: steps.map((step) => {
      if (step.phase !== targetPhase) return step;
      const nextSources = dedupeDeepSearchSources([...step.sources, displaySource]).slice(0, 18);
      return { ...step, sources: nextSources };
    }),
  };
}

function applyDeepSearchThinkingActivityToState(
  thinking: DeepSearchThinkingState,
  activity: DeepSearchActivityEventData,
): DeepSearchThinkingState {
  const eventType = deepSearchActivityEventType(activity);
  const activitySources = (activity.sources ?? []).map(deepSearchActivitySourceToDisplaySource);
  const existingIndex = thinking.steps.findIndex((step) => step.phase === activity.phase);
  const activityStep = {
    phase: activity.phase,
    title: deepSearchActivityTitle(activity),
    detail: deepSearchActivityMessage(activity),
    status: eventType === "stage_complete" ? "complete" as const : "active" as const,
    sources: dedupeDeepSearchSources(activitySources),
  };

  if (existingIndex < 0) {
    return {
      ...thinking,
      completed: false,
      steps: [
        ...thinking.steps.map((step) => ({ ...step, status: "complete" as const })),
        activityStep,
      ],
    };
  }

  return {
    ...thinking,
    completed: false,
    steps: thinking.steps.map((step, index) => {
      if (index < existingIndex) {
        return { ...step, status: "complete" as const };
      }
      if (index > existingIndex) {
        return { ...step, status: "pending" as const };
      }
      return {
        ...step,
        title: deepSearchActivityTitle(activity),
        detail: deepSearchActivityMessage(activity),
        status: eventType === "stage_complete" ? "complete" as const : "active" as const,
        sources: dedupeDeepSearchSources([...step.sources, ...activitySources]).slice(0, 18),
      };
    }),
  };
}

function completeDeepSearchThinkingState(
  thinking: DeepSearchThinkingState,
): DeepSearchThinkingState {
  return {
    ...thinking,
    completed: true,
    steps: thinking.steps.map((step) => ({ ...step, status: "complete" })),
  };
}

function buildRestoredDeepSearchMessages(project: Project, runs: DeepSearchRun[]): ChatMessage[] {
  return [...runs]
    .sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at))
    .flatMap((run) => {
      const messages: ChatMessage[] = [];
      if (run.user_prompt.trim() && run.user_prompt !== project.topic_description) {
        messages.push({
          id: `deep-search-${run.id}-prompt`,
          role: "user",
          content: run.user_prompt,
          kind: "text",
          createdAt: run.created_at,
        });
      }

      if (run.report_body.trim()) {
        messages.push({
          id: `deep-search-${run.id}`,
          role: "assistant",
          content: run.report_body,
          kind: "summary",
          sources: run.sources.map(deepSearchSourceToDisplaySource),
          createdAt: run.created_at,
        });
      }
      return messages;
    });
}

function formatDeepSearchPhase(phase: string) {
  return phase
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function insufficientCreditsMessage(required?: number, balance?: number) {
  if (required !== undefined && balance !== undefined) {
    return `Top up to continue. This action needs ${required.toLocaleString("en-US")} credits and your balance is ${balance.toLocaleString("en-US")}.`;
  }
  if (required !== undefined) {
    return `Top up to continue. This action needs ${required.toLocaleString("en-US")} credits.`;
  }
  return "Top up to continue. Your current credit balance is too low for this action.";
}

function insufficientCreditsNoticeFromError(error: unknown): InsufficientCreditsNotice | null {
  if (!isInsufficientCreditsError(error)) return null;
  return {
    message: insufficientCreditsMessage(error.required, error.balance),
    required: error.required,
    balance: error.balance,
    href: "/billing/checkout?pack=topup_deep",
    ctaLabel: "Top up to continue - $6 for 800 credits",
  };
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { token, user } = useAuth();
  const authedRef = useRef(token);
  const activeProjectIdRef = useRef<string | null>(null);
  const projectViewRevisionRef = useRef(0);
  const restoreAttemptedRef = useRef(false);
  const deepSearchStatusMessageIds = useRef<Set<string>>(new Set());
  const citationGraphRequestRefs = useRef<Map<string, Promise<CitationGraph>>>(new Map());
  const projectSnapshotsRef = useRef<Record<string, ProjectChatSnapshot>>({});
  authedRef.current = token;

  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [papers, setPapers] = useState<ProjectPaper[]>([]);
  const [citationGraphCache, setCitationGraphCache] = useState<Record<string, CitationGraph>>({});
  const [selectedPaperIds, setSelectedPaperIds] = useState<string[]>([]);
  const [queries, setQueries] = useState<string[]>([]);
  const [conversation, setConversation] = useState<ProjectConversation | null>(null);
  const [runSummary, setRunSummary] = useState<RunPipelineResponse | null>(null);
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [busyProjectIds, setBusyProjectIds] = useState<Record<string, boolean>>({});
  const [uploadingReferenceFile, setUploadingReferenceFile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [insufficientCredits, setInsufficientCredits] =
    useState<InsufficientCreditsNotice | null>(null);
  const [composerNotice, setComposerNotice] = useState<ComposerNotice | null>(null);
  const [lastUploadedPaperId, setLastUploadedPaperId] = useState<string | null>(null);
  const [chatMode, setChatMode] = useState<ChatMode>("standard");
  const [pendingDeepSearchPlan, setPendingDeepSearchPlan] =
    useState<DeepSearchPlanMessage | null>(null);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  activeProjectIdRef.current = activeProject?.id ?? null;
  const busy = workspaceBusy || Boolean(activeProject?.id && busyProjectIds[activeProject.id]);

  const refreshProjects = useCallback(async () => {
    if (!authedRef.current) return;
    setProjectsLoaded(false);
    try {
      const list = await api<Project[]>("/projects", { token: authedRef.current });
      setProjects(list);
    } finally {
      setProjectsLoaded(true);
    }
  }, []);

  const fetchProjectPapers = useCallback(async (projectId: string) => {
    const papersResponse = await api<Paginated<ProjectPaper>>(
      `/projects/${projectId}/papers?per_page=30`,
      { token: authedRef.current },
    );
    return papersResponse.data;
  }, []);

  const getCitationGraph = useCallback(
    async (
      projectId: string,
      paperId: string,
      options?: { limit?: number; force?: boolean },
    ) => {
      if (!authedRef.current) {
        throw new Error("You must be signed in to load a citation graph.");
      }
      const limit = options?.limit ?? 20;
      const key = citationGraphCacheKey(projectId, paperId, limit);
      if (!options?.force && citationGraphCache[key]) {
        return citationGraphCache[key];
      }

      const inFlight = citationGraphRequestRefs.current.get(key);
      if (!options?.force && inFlight) {
        return inFlight;
      }

      const request = fetchPaperCitationGraph(projectId, paperId, authedRef.current, { limit })
        .then((payload) => {
          setCitationGraphCache((current) => ({ ...current, [key]: payload }));
          return payload;
        })
        .finally(() => {
          citationGraphRequestRefs.current.delete(key);
        });
      citationGraphRequestRefs.current.set(key, request);
      return request;
    },
    [citationGraphCache],
  );

  const prefetchCitationGraphs = useCallback(
    async (projectId: string, paperIds: string[], options?: { limit?: number }) => {
      const limit = options?.limit ?? 20;
      for (const paperId of paperIds) {
        const key = citationGraphCacheKey(projectId, paperId, limit);
        if (citationGraphCache[key] || citationGraphRequestRefs.current.has(key)) continue;
        try {
          await getCitationGraph(projectId, paperId, { limit });
        } catch {
          /* Prefetch failures should not interrupt the foreground graph. */
        }
      }
    },
    [citationGraphCache, getCitationGraph],
  );

  const addCitationGraphPaperToProject = useCallback(
    async (projectId: string, paper: CitationGraphPaper) => {
      if (!authedRef.current) {
        throw new Error("You must be signed in to add a paper.");
      }
      const result = await importCitationGraphPaper(projectId, paper, authedRef.current);
      const nextPapers = await fetchProjectPapers(projectId);
      setPapers(nextPapers);
      return result;
    },
    [fetchProjectPapers],
  );

  const clearComposerNotice = useCallback(() => {
    setComposerNotice(null);
  }, []);

  const clearInsufficientCredits = useCallback(() => {
    setInsufficientCredits(null);
  }, []);

  const userFacingErrorMessage = useCallback((err: unknown, fallback: string) => {
    const creditNotice = insufficientCreditsNoticeFromError(err);
    if (creditNotice) {
      setInsufficientCredits(creditNotice);
      return creditNotice.message;
    }
    return err instanceof Error ? err.message : fallback;
  }, []);

  const setProjectBusy = useCallback((projectId: string, isBusy: boolean) => {
    setBusyProjectIds((prev) => {
      if (isBusy) return { ...prev, [projectId]: true };
      const { [projectId]: _removed, ...rest } = prev;
      return rest;
    });
  }, []);

  const clearVisibleProjectState = useCallback(() => {
    projectViewRevisionRef.current += 1;
    activeProjectIdRef.current = null;
    setActiveProject(null);
    setMessages([]);
    setPapers([]);
    setSelectedPaperIds([]);
    setQueries([]);
    setConversation(null);
    setRunSummary(null);
  }, []);

  const applyProjectSnapshot = useCallback((snapshot: ProjectChatSnapshot) => {
    activeProjectIdRef.current = snapshot.project.id;
    setActiveProject(snapshot.project);
    setMessages(snapshot.messages);
    setPapers(snapshot.papers);
    setSelectedPaperIds(snapshot.selectedPaperIds);
    setQueries(snapshot.queries);
    setConversation(snapshot.conversation);
    setRunSummary(snapshot.runSummary);
  }, []);

  const saveProjectSnapshot = useCallback(
    (snapshot: ProjectChatSnapshot, options: { activate?: boolean } = {}) => {
      projectSnapshotsRef.current[snapshot.project.id] = snapshot;
      if (options.activate || activeProjectIdRef.current === snapshot.project.id) {
        applyProjectSnapshot(snapshot);
      }
    },
    [applyProjectSnapshot],
  );

  const updateProjectSnapshot = useCallback(
    (
      projectId: string,
      updater: (snapshot: ProjectChatSnapshot) => ProjectChatSnapshot,
      applyActive?: (snapshot: ProjectChatSnapshot) => void,
    ) => {
      const current = projectSnapshotsRef.current[projectId];
      if (!current) return null;
      const next = updater(current);
      projectSnapshotsRef.current[projectId] = next;
      if (activeProjectIdRef.current === projectId) {
        if (applyActive) {
          applyActive(next);
        } else {
          applyProjectSnapshot(next);
        }
      }
      return next;
    },
    [applyProjectSnapshot],
  );

  const updateProjectMessages = useCallback(
    (projectId: string, updater: (messages: ChatMessage[]) => ChatMessage[]) =>
      updateProjectSnapshot(
        projectId,
        (snapshot) => ({ ...snapshot, messages: updater(snapshot.messages) }),
        (snapshot) => setMessages(snapshot.messages),
      ),
    [updateProjectSnapshot],
  );

  const appendDeepSearchStatusMessage = useCallback(
    (content: string, role: "assistant" | "system" = "system") => {
      const statusIds = deepSearchStatusMessageIds.current;
      if (statusIds.size > 0) {
        const lastStatusId = [...statusIds].at(-1)!;
        setMessages((prev) =>
          prev.map((m) => (m.id === lastStatusId ? { ...m, content, role } : m)),
        );
        return;
      }
      const messageId = uid();
      statusIds.add(messageId);
      setMessages((prev) => [
        ...prev,
        {
          id: messageId,
          role,
          kind: "status",
          content,
          createdAt: now(),
        },
      ]);
    },
    [],
  );

  const clearDeepSearchStatusMessages = useCallback(() => {
    const statusIds = deepSearchStatusMessageIds.current;
    if (statusIds.size === 0) return;

    setMessages((prev) => prev.filter((message) => !statusIds.has(message.id)));
    statusIds.clear();
  }, []);

  const updateDeepSearchThinkingPhase = useCallback((messageId: string, phase: string) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === messageId && message.thinking
          ? { ...message, thinking: upsertDeepSearchThinkingPhase(message.thinking, phase) }
          : message,
      ),
    );
  }, []);

  const appendDeepSearchThinkingSource = useCallback(
    (messageId: string, source: DeepSearchSourceEventData) => {
      const displaySource = deepSearchSourceEventToDisplaySource(source);
      setMessages((prev) =>
        prev.map((message) =>
          message.id === messageId && message.thinking
            ? {
              ...message,
              sources: dedupeDeepSearchSources([...(message.sources ?? []), displaySource]),
              thinking: appendDeepSearchThinkingSourceToState(message.thinking, source),
            }
            : message,
        ),
      );
    },
    [],
  );

  const applyDeepSearchThinkingActivity = useCallback(
    (messageId: string, activity: DeepSearchActivityEventData) => {
      const activitySources = (activity.sources ?? []).map(deepSearchActivitySourceToDisplaySource);
      setMessages((prev) =>
        prev.map((message) =>
          message.id === messageId && message.thinking
            ? {
              ...message,
              sources: dedupeDeepSearchSources([...(message.sources ?? []), ...activitySources]),
              thinking: applyDeepSearchThinkingActivityToState(message.thinking, activity),
            }
            : message,
        ),
      );
    },
    [],
  );

  const completeDeepSearchThinking = useCallback((messageId: string) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === messageId && message.thinking
          ? { ...message, thinking: completeDeepSearchThinkingState(message.thinking) }
          : message,
      ),
    );
  }, []);

  const ensureDeepSearchRelatedPapers = useCallback(
    async ({
      projectId,
      currentPapers,
      paperIdsToKeep,
      shouldRunDiscovery,
    }: {
      projectId: string;
      currentPapers: ProjectPaper[];
      paperIdsToKeep: string[];
      shouldRunDiscovery: boolean;
    }) => {
      if (!authedRef.current) throw new Error("You must be logged in to search papers.");

      if (!shouldRunDiscovery) {
        return normalizeSelectedPaperIds(paperIdsToKeep, currentPapers);
      }

      appendDeepSearchStatusMessage("Finding related papers for the sidebar...");
      const runResponse = await api<RunPipelineResponse>(`/projects/${projectId}/run`, {
        method: "POST",
        token: authedRef.current,
      });
      notifyCreditBalanceChanged();

      const nextPapers = await fetchProjectPapers(projectId);
      const nextSelectedPaperIds = normalizeSelectedPaperIds(paperIdsToKeep, nextPapers);
      updateProjectSnapshot(
        projectId,
        (snapshot) => ({
          ...snapshot,
          runSummary: runResponse,
          queries: runResponse.queries,
          papers: nextPapers,
          selectedPaperIds: nextSelectedPaperIds,
        }),
        (snapshot) => {
          setRunSummary(snapshot.runSummary);
          setQueries(snapshot.queries);
          setPapers(snapshot.papers);
          setSelectedPaperIds(snapshot.selectedPaperIds);
        },
      );
      return nextSelectedPaperIds;
    },
    [appendDeepSearchStatusMessage, fetchProjectPapers, updateProjectSnapshot],
  );

  useEffect(() => {
    if (token) refreshProjects().catch((e) => setError(String(e)));
  }, [token, refreshProjects]);

  useEffect(() => {
    if (!activeProject && !restoreAttemptedRef.current) return;
    persistActiveProjectId(user?.id, activeProject?.id ?? null);
  }, [user?.id, activeProject?.id]);

  useEffect(() => {
    persistSelectedPaperIds(user?.id, activeProject?.id ?? null, selectedPaperIds);
  }, [user?.id, activeProject?.id, selectedPaperIds]);

  useEffect(() => {
    if (!activeProject) return;
    projectSnapshotsRef.current[activeProject.id] = {
      project: activeProject,
      messages,
      papers,
      selectedPaperIds,
      queries,
      conversation,
      runSummary,
    };
  }, [activeProject, conversation, messages, papers, queries, runSummary, selectedPaperIds]);

  const selectedPapers = useMemo(
    () => selectedPaperIds
      .map((paperId) => papers.find((paper) => paper.id === paperId) ?? null)
      .filter((paper): paper is ProjectPaper => paper !== null),
    [papers, selectedPaperIds],
  );
  const deepSearchSources = useMemo(
    () => dedupeDeepSearchSources(messages.flatMap((message) => message.sources ?? [])),
    [messages],
  );

  const startNewResearch = useCallback(() => {
    clearVisibleProjectState();
    setComposerNotice(null);
    setLastUploadedPaperId(null);
    setPendingDeepSearchPlan(null);
    setError(null);
    setInsufficientCredits(null);
  }, [clearVisibleProjectState]);

  const selectProject = useCallback(
    async (projectId: string) => {
      if (!authedRef.current) return;
      projectViewRevisionRef.current += 1;
      const cachedSnapshot = projectSnapshotsRef.current[projectId];
      if (cachedSnapshot) {
        setWorkspaceBusy(false);
        setError(null);
        setInsufficientCredits(null);
        setComposerNotice(null);
        setLastUploadedPaperId(null);
        setPendingDeepSearchPlan(null);
        applyProjectSnapshot(cachedSnapshot);
        return;
      }

      setWorkspaceBusy(true);
      setError(null);
      setInsufficientCredits(null);
      setComposerNotice(null);
      setLastUploadedPaperId(null);
      setPendingDeepSearchPlan(null);
      try {
        clearVisibleProjectState();
        const project = await api<Project>(`/projects/${projectId}`, {
          token: authedRef.current,
        });

        const nextPapers = await fetchProjectPapers(project.id);

        const savedSelectedPaperIds = loadSavedSelectedPaperIds(user?.id, project.id);
        const normalizedSavedSelectedPaperIds = savedSelectedPaperIds === null
          ? null
          : normalizeSelectedPaperIds(savedSelectedPaperIds, nextPapers);

        const conversationSummaries = await api<ProjectConversationSummary[]>(
          `/projects/${project.id}/conversations`,
          { token: authedRef.current },
        );
        const latestConversation = conversationSummaries[0] ?? null;
        const restoredConversation = latestConversation
          ? await api<ProjectConversation>(
            `/projects/${project.id}/conversations/${latestConversation.id}`,
            { token: authedRef.current },
          )
          : null;
        const deepSearchRunSummaries = await api<DeepSearchRunSummary[]>(
          `/projects/${project.id}/deep-search-runs`,
          { token: authedRef.current },
        );
        const restoredDeepSearchRuns = await Promise.all(
          deepSearchRunSummaries
            .filter((summary) => summary.status === "completed")
            .map((summary) =>
              api<DeepSearchRun>(
                `/projects/${project.id}/deep-search-runs/${summary.id}`,
                { token: authedRef.current },
              ),
            ),
        );
        const restoredDeepSearchMessages = buildRestoredDeepSearchMessages(
          project,
          restoredDeepSearchRuns,
        );
        const restoredConversationMessages = restoredConversation
          ? buildRestoredConversationMessages(project, restoredConversation)
          : [];
        const restoredChatMessages = sortRestoredChatMessages([
          ...restoredConversationMessages,
          ...restoredDeepSearchMessages,
        ]);

        const fallbackSelectedPaperIds = normalizeSelectedPaperIds(
          restoredConversation?.selected_paper_ids ?? [],
          nextPapers,
        );
        const nextSelectedPaperIds =
          normalizedSavedSelectedPaperIds !== null
            ? normalizedSavedSelectedPaperIds
            : fallbackSelectedPaperIds;

        const shellMessages = buildProjectShellMessages(project, nextPapers, {
          omitEmptyPaperStatus: restoredDeepSearchMessages.length > 0,
        });
        saveProjectSnapshot(
          {
            project,
            messages: [...shellMessages, ...restoredChatMessages],
            papers: nextPapers,
            selectedPaperIds: nextSelectedPaperIds,
            queries: [],
            conversation: restoredConversation,
            runSummary: null,
          },
          { activate: true },
        );
      } catch (err: any) {
        if (err?.status === 404) {
          persistActiveProjectId(user?.id, null);
        }
        setError(userFacingErrorMessage(err, "Failed to load project."));
      } finally {
        setWorkspaceBusy(false);
      }
    },
    [
      applyProjectSnapshot,
      clearVisibleProjectState,
      fetchProjectPapers,
      saveProjectSnapshot,
      user?.id,
      userFacingErrorMessage,
    ],
  );

  useEffect(() => {
    if (!projectsLoaded || activeProject || restoreAttemptedRef.current) return;

    restoreAttemptedRef.current = true;
    const routeProjectId = loadRouteProjectId();
    const savedProjectId = routeProjectId ?? loadSavedActiveProjectId(user?.id);
    if (!savedProjectId) return;

    if (!projects.some((project) => project.id === savedProjectId)) {
      if (!routeProjectId) persistActiveProjectId(user?.id, null);
      return;
    }

    void selectProject(savedProjectId);
  }, [projectsLoaded, projects, activeProject, selectProject, user?.id]);

  const deleteProject = useCallback(
    async (projectId: string) => {
      if (!authedRef.current) return;
      setWorkspaceBusy(true);
      setError(null);
      setComposerNotice(null);
      setLastUploadedPaperId(null);

      try {
        await api<void>(`/projects/${projectId}`, {
          method: "DELETE",
          token: authedRef.current,
        });
        setProjects((prev) => prev.filter((project) => project.id !== projectId));
        const { [projectId]: _deletedSnapshot, ...remainingSnapshots } = projectSnapshotsRef.current;
        projectSnapshotsRef.current = remainingSnapshots;
        setProjectBusy(projectId, false);
        if (activeProject?.id === projectId) {
          startNewResearch();
        }
      } catch (err: any) {
        setError(userFacingErrorMessage(err, "Failed to delete project."));
      } finally {
        setWorkspaceBusy(false);
      }
    },
    [activeProject, setProjectBusy, startNewResearch, userFacingErrorMessage],
  );

  const renameProject = useCallback(
    async (projectId: string, title: string) => {
      if (!authedRef.current) return;
      const trimmedTitle = title.trim();
      if (!trimmedTitle) return;

      setWorkspaceBusy(true);
      setError(null);

      try {
        const updatedProject = await api<Project>(`/projects/${projectId}`, {
          method: "PATCH",
          token: authedRef.current,
          json: { title: trimmedTitle } satisfies ProjectTitleUpdate,
        });
        setProjects((prev) =>
          prev.map((project) =>
            project.id === projectId ? { ...project, title: updatedProject.title } : project,
          ),
        );
        updateProjectSnapshot(
          projectId,
          (snapshot) => ({ ...snapshot, project: updatedProject }),
          (snapshot) => setActiveProject(snapshot.project),
        );
        setActiveProject((prev) => (prev?.id === projectId ? updatedProject : prev));
      } catch (err: any) {
        setError(userFacingErrorMessage(err, "Failed to rename project."));
        throw err;
      } finally {
        setWorkspaceBusy(false);
      }
    },
    [updateProjectSnapshot, userFacingErrorMessage],
  );

  const togglePaperSelection = useCallback(
    (paperId: string) => {
      if (!activeProject) return;
      setSelectedPaperIds((prev) => {
        const normalizedPrev = normalizeSelectedPaperIds(prev, papers);
        const isSelected = normalizedPrev.includes(paperId);
        if (isSelected) {
          return normalizedPrev.filter((id) => id !== paperId);
        }

        if (normalizedPrev.length >= MAX_SELECTED_PAPERS) {
          setError(`You can select up to ${MAX_SELECTED_PAPERS} papers for one grounded answer.`);
          return normalizedPrev;
        }

        setError(null);
        return [...normalizedPrev, paperId];
      });
    },
    [activeProject, papers],
  );

  const uploadReferenceFile = useCallback(
    async (file: File, options?: UploadReferenceFileOptions) => {
      if (!authedRef.current || uploadingReferenceFile) return;

      setUploadingReferenceFile(true);
      setError(null);
      setInsufficientCredits(null);
      setComposerNotice(null);
      setLastUploadedPaperId(null);

      try {
        let project = activeProject;

        if (!project) {
          const trimmedTopic = options?.topic?.trim() ?? "";
          if (!trimmedTopic) {
            throw new Error("A research topic is required before uploading a reference PDF.");
          }

          project = await api<Project>("/projects", {
            method: "POST",
            token: authedRef.current,
            json: buildProjectCreatePayload(trimmedTopic),
          });

          const referenceFile = await uploadProjectReferenceFile(project.id, file, authedRef.current);
          notifyCreditBalanceChanged();
          await refreshProjects();

          if (activeProjectIdRef.current && activeProjectIdRef.current !== project.id) {
            return;
          }

          setActiveProject(project);
          setMessages([]);
          setConversation(null);
          setQueries([]);
          setRunSummary(null);

          const nextPapers = await fetchProjectPapers(project.id);
          setPapers(nextPapers);
          setSelectedPaperIds([]);

          const matchedUploadedPaper = referenceFile.linked_paper_id
            ? nextPapers.find((paper) => paper.id === referenceFile.linked_paper_id) ?? null
            : null;
          setLastUploadedPaperId(matchedUploadedPaper?.id ?? null);
          setComposerNotice(
            matchedUploadedPaper
              ? {
                tone: "success",
                message: `Uploaded "${file.name}" and added "${matchedUploadedPaper.title}" to this project.`,
              }
              : {
                tone: "warning",
                message: referenceFile.error_message
                  ? `Uploaded "${file.name}", but no linked paper was added: ${referenceFile.error_message}`
                  : `Uploaded "${file.name}", but no linked paper was added to the project.`,
              },
          );
          return;
        }

        const referenceFile = await uploadProjectReferenceFile(project.id, file, authedRef.current);
        notifyCreditBalanceChanged();
        const nextPapers = await fetchProjectPapers(project.id);
        const nextSelectedPaperIds = normalizeSelectedPaperIds(selectedPaperIds, nextPapers);

        if (activeProjectIdRef.current !== project.id) {
          return;
        }

        setPapers(nextPapers);
        if (!arePaperIdListsEqual(selectedPaperIds, nextSelectedPaperIds)) {
          setSelectedPaperIds(nextSelectedPaperIds);
        }

        const linkedPaper = referenceFile.linked_paper_id
          ? nextPapers.find((paper) => paper.id === referenceFile.linked_paper_id) ?? null
          : null;

        setLastUploadedPaperId(linkedPaper?.id ?? null);
        setComposerNotice(
          linkedPaper
            ? {
              tone: "success",
              message: `Uploaded "${file.name}" and added "${linkedPaper.title}" to this project's papers.`,
            }
            : {
              tone: "warning",
              message: referenceFile.error_message
                ? `Uploaded "${file.name}", but no linked paper was added: ${referenceFile.error_message}`
                : `Uploaded "${file.name}", but no linked paper was added to the project.`,
            },
        );
      } catch (err: any) {
        const detail = userFacingErrorMessage(err, "Failed to upload the reference PDF.");
        setError(detail);
        setComposerNotice({
          tone: "error",
          message: detail,
        });
        throw err;
      } finally {
        setUploadingReferenceFile(false);
      }
    },
    [
      activeProject,
      fetchProjectPapers,
      refreshProjects,
      selectedPaperIds,
      uploadingReferenceFile,
      userFacingErrorMessage,
    ],
  );

  const streamProjectChatTurn = useCallback(
    async ({
      projectId,
      conversationId,
      paperIds,
      question,
      assistantKind = "text",
    }: {
      projectId: string;
      conversationId?: string;
      paperIds: string[];
      question: string;
      assistantKind?: ChatMessage["kind"];
    }) => {
      if (!authedRef.current) throw new Error("You must be logged in to chat.");

      const assistantMessageId = uid();
      let completedConversation: ProjectConversation | null = null;
      let streamedError: string | null = null;

      const assistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: "assistant",
        kind: assistantKind,
        content: "",
        createdAt: now(),
      };
      const seededSnapshot = updateProjectSnapshot(
        projectId,
        (snapshot) => ({
          ...snapshot,
          messages: [...snapshot.messages, assistantMessage],
        }),
        (snapshot) => setMessages(snapshot.messages),
      );
      if (!seededSnapshot) {
        setMessages((prev) => [...prev, assistantMessage]);
      }

      const path = conversationId
        ? `/projects/${projectId}/conversations/${conversationId}/messages/stream`
        : `/projects/${projectId}/conversations/stream`;

      await streamProjectConversation(path, {
        token: authedRef.current,
        json: { paper_ids: paperIds, question },
        onEvent: (event) => {
          if (event.event === "conversation") {
            updateProjectSnapshot(
              projectId,
              (snapshot) => ({ ...snapshot, conversation: event.data }),
              (snapshot) => setConversation(snapshot.conversation),
            );
            return;
          }

          if (event.event === "token") {
            const delta = event.data.delta;
            updateProjectSnapshot(
              projectId,
              (snapshot) => ({
                ...snapshot,
                messages: snapshot.messages.map((message) =>
                  message.id === assistantMessageId
                    ? { ...message, content: `${message.content}${delta}` }
                    : message,
                ),
              }),
              (snapshot) => setMessages(snapshot.messages),
            );
            return;
          }

          if (event.event === "done") {
            completedConversation = event.data;
            const assistantTurn = [...event.data.messages]
              .reverse()
              .find((message) => message.role === "assistant");
            updateProjectSnapshot(
              projectId,
              (snapshot) => ({
                ...snapshot,
                conversation: event.data,
                messages: snapshot.messages.map((message) =>
                  message.id === assistantMessageId
                    ? {
                      ...message,
                      id: assistantTurn?.id ?? message.id,
                      content: assistantTurn?.content ?? message.content,
                      createdAt: assistantTurn?.created_at ?? message.createdAt,
                    }
                    : message,
                ),
              }),
              (snapshot) => {
                setConversation(snapshot.conversation);
                setMessages(snapshot.messages);
              },
            );
            return;
          }

          if (event.event === "error") {
            streamedError = event.data.detail;
            updateProjectSnapshot(
              projectId,
              (snapshot) => ({
                ...snapshot,
                messages: snapshot.messages.map((message) =>
                  message.id === assistantMessageId
                    ? {
                      ...message,
                      kind: "status",
                      content: `Error: ${event.data.detail}`,
                    }
                    : message,
                ),
              }),
              (snapshot) => setMessages(snapshot.messages),
            );
          }
        },
      });

      if (streamedError) {
        throw new Error(streamedError);
      }
      if (!completedConversation) {
        throw new Error("The streaming chat response ended before it was persisted.");
      }
      notifyCreditBalanceChanged();
      return completedConversation;
    },
    [updateProjectSnapshot],
  );

  const streamDeepSearchTurn = useCallback(
    async ({
      projectId,
      paperIds,
      question,
      mode = "standard",
    }: {
      projectId: string;
      paperIds: string[];
      question: string;
      mode?: "standard" | "max";
    }) => {
      if (!authedRef.current) throw new Error("You must be logged in to chat.");

      const thinkingMessage = createDeepSearchThinkingMessage(question);
      const thinkingMessageId = thinkingMessage.id;
      const collectedSources: DeepSearchDisplaySource[] = [];
      let completedRun: DeepSearchRun | null = null;
      let streamedError: string | null = null;
      let assistantMessageId: string | null = null;

      const updateDeepSearchMessages = (updater: (messages: ChatMessage[]) => ChatMessage[]) => {
        const updatedSnapshot = updateProjectMessages(projectId, updater);
        if (!updatedSnapshot && activeProjectIdRef.current === projectId) {
          setMessages((prev) => updater(prev));
        }
      };

      const clearProjectDeepSearchStatusMessages = () => {
        const statusIds = deepSearchStatusMessageIds.current;
        if (statusIds.size === 0) return;
        updateDeepSearchMessages((prev) => prev.filter((message) => !statusIds.has(message.id)));
        statusIds.clear();
      };

      const ensureDeepSearchAnswerMessage = (initialContent = "") => {
        if (assistantMessageId) return assistantMessageId;

        const nextMessageId = uid();
        assistantMessageId = nextMessageId;
        updateDeepSearchMessages((prev) => [
          ...prev,
          {
            id: nextMessageId,
            role: "assistant",
            kind: "summary",
            content: initialContent,
            sources: [...collectedSources],
            createdAt: now(),
          },
        ]);
        return nextMessageId;
      };

      clearProjectDeepSearchStatusMessages();
      updateDeepSearchMessages((prev) => [...prev, thinkingMessage]);

      await streamDeepSearchRun(`/projects/${projectId}/deep-search/stream`, {
        token: authedRef.current,
        json: { paper_ids: paperIds, question, mode },
        onEvent: (event) => {
          if (event.event === "run") {
            updateDeepSearchMessages((prev) =>
              prev.map((message) =>
                message.id === thinkingMessageId && message.thinking
                  ? {
                    ...message,
                    thinking: upsertDeepSearchThinkingPhase(message.thinking, "planning"),
                  }
                  : message,
              ),
            );
            return;
          }

          if (event.event === "status") {
            updateDeepSearchMessages((prev) =>
              prev.map((message) =>
                message.id === thinkingMessageId && message.thinking
                  ? {
                    ...message,
                    thinking: upsertDeepSearchThinkingPhase(message.thinking, event.data.phase),
                  }
                  : message,
              ),
            );
            return;
          }

          if (event.event === "activity") {
            updateDeepSearchMessages((prev) =>
              prev.map((message) =>
                message.id === thinkingMessageId && message.thinking
                  ? {
                    ...message,
                    sources: dedupeDeepSearchSources([
                      ...(message.sources ?? []),
                      ...(event.data.sources ?? []).map(deepSearchActivitySourceToDisplaySource),
                    ]),
                    thinking: applyDeepSearchThinkingActivityToState(message.thinking, event.data),
                  }
                  : message,
              ),
            );
            return;
          }

          if (event.event === "source") {
            collectedSources.push(deepSearchSourceEventToDisplaySource(event.data));
            const displaySource = deepSearchSourceEventToDisplaySource(event.data);
            updateDeepSearchMessages((prev) =>
              prev.map((message) => {
                if (message.id === thinkingMessageId && message.thinking) {
                  return {
                    ...message,
                    sources: dedupeDeepSearchSources([...(message.sources ?? []), displaySource]),
                    thinking: appendDeepSearchThinkingSourceToState(message.thinking, event.data),
                  };
                }
                if (message.id === assistantMessageId) {
                  return { ...message, sources: [...collectedSources] };
                }
                return message;
              }),
            );
            return;
          }

          if (event.event === "token") {
            const delta = event.data.delta;
            const targetMessageId = ensureDeepSearchAnswerMessage();
            updateDeepSearchMessages((prev) =>
              prev.map((message) =>
                message.id === targetMessageId
                  ? { ...message, content: `${message.content}${delta}` }
                  : message,
              ),
            );
            return;
          }

          if (event.event === "done") {
            completedRun = event.data;
            const finalSources = event.data.sources.map(deepSearchSourceToDisplaySource);
            clearProjectDeepSearchStatusMessages();
            const targetMessageId = ensureDeepSearchAnswerMessage(event.data.report_body);
            updateDeepSearchMessages((prev) =>
              prev.map((message) =>
                message.id === thinkingMessageId && message.thinking
                  ? { ...message, thinking: completeDeepSearchThinkingState(message.thinking) }
                  :
                message.id === targetMessageId
                  ? {
                    ...message,
                    content: event.data.report_body,
                    sources: finalSources,
                    createdAt: event.data.completed_at ?? message.createdAt,
                  }
                  : message,
              ),
            );
            return;
          }

          if (event.event === "error") {
            streamedError = event.data.detail;
            const targetMessageId = ensureDeepSearchAnswerMessage();
            updateDeepSearchMessages((prev) =>
              prev.map((message) =>
                message.id === targetMessageId
                  ? {
                    ...message,
                    kind: "status",
                    content: `Error: ${event.data.detail}`,
                  }
                  : message,
              ),
            );
          }
        },
      });

      if (streamedError) {
        throw new Error(streamedError);
      }
      if (!completedRun) {
        throw new Error("The deep search stream ended before the run was persisted.");
      }
      notifyCreditBalanceChanged();
      return completedRun;
    },
    [updateProjectMessages],
  );

  const startDeepSearchPlan = useCallback(
    async (planId: string) => {
      if (!authedRef.current || busy) return;
      const plan = pendingDeepSearchPlan?.id === planId ? pendingDeepSearchPlan : null;
      if (!plan || plan.status !== "pending") return;

      const viewRevisionAtStart = projectViewRevisionRef.current;
      let targetProjectId = plan.projectId ?? activeProject?.id ?? null;
      if (targetProjectId) {
        if (activeProject && !projectSnapshotsRef.current[targetProjectId]) {
          projectSnapshotsRef.current[targetProjectId] = {
            project: activeProject,
            messages,
            papers,
            selectedPaperIds,
            queries,
            conversation,
            runSummary,
          };
        }
        setProjectBusy(targetProjectId, true);
      } else {
        setWorkspaceBusy(true);
      }
      setError(null);
      setComposerNotice(null);
      setLastUploadedPaperId(null);
      setPendingDeepSearchPlan(null);
      const markPlanStarted = (source: ChatMessage[]) =>
        source.map((message) =>
          message.deepSearchPlan?.id === planId
            ? {
              ...message,
              deepSearchPlan: { ...message.deepSearchPlan, status: "started" as const },
            }
            : message,
        );
      if (targetProjectId && projectSnapshotsRef.current[targetProjectId]) {
        updateProjectMessages(targetProjectId, markPlanStarted);
      } else {
        setMessages((prev) => markPlanStarted(prev));
      }

      try {
        if (!plan.projectId || !activeProject) {
          appendDeepSearchStatusMessage("Creating your project for Deep Search…", "assistant");

          const project = await api<Project>("/projects", {
            method: "POST",
            token: authedRef.current,
            json: buildProjectCreatePayload(plan.question),
          });
          targetProjectId = project.id;
          setProjectBusy(project.id, true);
          await refreshProjects();

          const nextPapers = await fetchProjectPapers(project.id);
          const shouldActivateCreatedProject =
            projectViewRevisionRef.current === viewRevisionAtStart;
          if (shouldActivateCreatedProject) {
            setWorkspaceBusy(false);
          }
          saveProjectSnapshot(
            {
              project,
              messages,
              papers: nextPapers,
              selectedPaperIds: [],
              queries: [],
              conversation: null,
              runSummary: null,
            },
            { activate: shouldActivateCreatedProject },
          );

          const nextSelectedPaperIds = await ensureDeepSearchRelatedPapers({
            projectId: project.id,
            currentPapers: [],
            paperIdsToKeep: [],
            shouldRunDiscovery: true,
          });

          clearDeepSearchStatusMessages();
          await streamDeepSearchTurn({
            projectId: project.id,
            paperIds: nextSelectedPaperIds,
            question: plan.question,
            mode: plan.mode,
          });
          return;
        }

        if (plan.projectId !== activeProject.id) {
          throw new Error("This Deep Search plan belongs to a different project.");
        }

        const nextSelectedPaperIds = normalizeSelectedPaperIds(selectedPaperIds, papers);
        if (!arePaperIdListsEqual(selectedPaperIds, nextSelectedPaperIds)) {
          updateProjectSnapshot(
            activeProject.id,
            (snapshot) => ({ ...snapshot, selectedPaperIds: nextSelectedPaperIds }),
            (snapshot) => setSelectedPaperIds(snapshot.selectedPaperIds),
          );
        }

        const deepSearchPaperIds = await ensureDeepSearchRelatedPapers({
          projectId: activeProject.id,
          currentPapers: papers,
          paperIdsToKeep: nextSelectedPaperIds,
          shouldRunDiscovery: !hasDiscoveredProjectPapers(papers),
        });

        await streamDeepSearchTurn({
          projectId: activeProject.id,
          paperIds: deepSearchPaperIds,
          question: plan.question,
          mode: plan.mode,
        });
      } catch (err: any) {
        const detail = userFacingErrorMessage(err, "Something went wrong.");
        setError(detail);
        const errorMessage: ChatMessage = {
          id: uid(),
          role: "assistant",
          kind: "status",
          content: `Error: ${detail}`,
          createdAt: now(),
        };
        if (targetProjectId && projectSnapshotsRef.current[targetProjectId]) {
          updateProjectMessages(targetProjectId, (prev) => [...prev, errorMessage]);
        } else {
          setMessages((prev) => [...prev, errorMessage]);
        }
      } finally {
        if (targetProjectId) {
          setProjectBusy(targetProjectId, false);
        } else {
          setWorkspaceBusy(false);
        }
      }
    },
    [
      activeProject,
      appendDeepSearchStatusMessage,
      busy,
      clearDeepSearchStatusMessages,
      conversation,
      ensureDeepSearchRelatedPapers,
      fetchProjectPapers,
      messages,
      papers,
      pendingDeepSearchPlan,
      queries,
      refreshProjects,
      runSummary,
      saveProjectSnapshot,
      selectedPaperIds,
      setProjectBusy,
      streamDeepSearchTurn,
      updateProjectMessages,
      updateProjectSnapshot,
      userFacingErrorMessage,
    ],
  );

  const editDeepSearchPlan = useCallback(
    (planId: string) => {
      if (busy) return null;
      const plan = pendingDeepSearchPlan?.id === planId ? pendingDeepSearchPlan : null;
      if (!plan || plan.status !== "pending") return null;

      setPendingDeepSearchPlan(null);
      setMessages((prev) =>
        prev.map((message) =>
          message.deepSearchPlan?.id === planId
            ? {
              ...message,
              content: "Research plan moved back to the composer for editing.",
              deepSearchPlan: { ...message.deepSearchPlan, status: "editing" },
            }
            : message,
        ),
      );
      return plan.question;
    },
    [busy, pendingDeepSearchPlan],
  );

  const submitMessage = useCallback(
    async (text: string) => {
      if (!authedRef.current) return;
      const trimmed = text.trim();
      if (!trimmed) return;
      const viewRevisionAtSubmit = projectViewRevisionRef.current;
      setError(null);
      setInsufficientCredits(null);
      setComposerNotice(null);
      setLastUploadedPaperId(null);

      const userMessage: ChatMessage = {
        id: uid(),
        role: "user",
        content: trimmed,
        kind: "text",
        createdAt: now(),
      };
      let targetProjectId = activeProject?.id ?? null;
      if (targetProjectId && activeProject && !projectSnapshotsRef.current[targetProjectId]) {
        projectSnapshotsRef.current[targetProjectId] = {
          project: activeProject,
          messages,
          papers,
          selectedPaperIds,
          queries,
          conversation,
          runSummary,
        };
      }
      if (targetProjectId && projectSnapshotsRef.current[targetProjectId]) {
        updateProjectMessages(targetProjectId, (prev) => [...prev, userMessage]);
      } else {
        setMessages((prev) => [...prev, userMessage]);
      }
      const updateTargetMessages = (updater: (messages: ChatMessage[]) => ChatMessage[]) => {
        if (targetProjectId && projectSnapshotsRef.current[targetProjectId]) {
          updateProjectMessages(targetProjectId, updater);
          return;
        }
        setMessages((prev) => updater(prev));
      };

      if (pendingDeepSearchPlan) {
        updateTargetMessages((prev) =>
          prev.map((message) =>
            message.deepSearchPlan?.id === pendingDeepSearchPlan.id
              ? {
                ...message,
                deepSearchPlan: { ...message.deepSearchPlan, status: "superseded" },
              }
              : message,
          ),
        );
        setPendingDeepSearchPlan(null);
      }

      if (chatMode === "deep_search" || chatMode === "deep_research_max") {
        const deepMode = chatMode === "deep_research_max" ? "max" : "standard";
        const planMessage = createDeepSearchPlanMessage(trimmed, activeProject?.id ?? null, deepMode);
        setPendingDeepSearchPlan(planMessage.deepSearchPlan);
        updateTargetMessages((prev) => [...prev, planMessage]);

        const planId = planMessage.deepSearchPlan.id;
        api<{ questions: string[] }>("/pipeline/deep-search/plan", {
          method: "POST",
          token: authedRef.current,
          json: { question: trimmed, mode: deepMode },
        })
          .then(({ questions }) => {
            updateTargetMessages((prev) =>
              prev.map((m) =>
                m.kind === "deep_search_plan" && m.deepSearchPlan?.id === planId
                  ? {
                      ...m,
                      deepSearchPlan: { ...m.deepSearchPlan!, status: "pending", questions },
                    }
                  : m,
              ),
            );
            setPendingDeepSearchPlan((prev) =>
              prev?.id === planId ? { ...prev, status: "pending", questions } : prev,
            );
          })
          .catch(() => {
            const compact = trimmed.slice(0, 200);
            const fallback: string[] =
              deepMode === "max"
                ? [
                    "What is the architecture and technical design of the primary method?",
                    "What specific challenges or conditions does this approach address?",
                    "What competing or alternative approaches exist for the same task?",
                    "How does this method compare empirically on precision, recall, F1, and speed?",
                    "What datasets and training procedures are required?",
                  ]
                : [
                    compact,
                    `What recent academic evidence addresses: ${compact}?`,
                    `What are the key debates, limitations, or open problems related to: ${compact}?`,
                    `What implementation context or real-world examples are relevant to: ${compact}?`,
                  ];
            updateTargetMessages((prev) =>
              prev.map((m) =>
                m.kind === "deep_search_plan" && m.deepSearchPlan?.id === planId
                  ? {
                      ...m,
                      deepSearchPlan: { ...m.deepSearchPlan!, status: "pending", questions: fallback },
                    }
                  : m,
              ),
            );
            setPendingDeepSearchPlan((prev) =>
              prev?.id === planId ? { ...prev, status: "pending", questions: fallback } : prev,
            );
          });

        return;
      }

      if (targetProjectId) {
        setProjectBusy(targetProjectId, true);
      } else {
        setWorkspaceBusy(true);
      }
      try {
        if (!activeProject) {
          const pipelineStatusId = uid();
          const pipelineStatusMessage: ChatMessage = {
            id: pipelineStatusId,
            role: "assistant",
            kind: "status",
            content: "Creating your project and finding related papers…",
            createdAt: now(),
          };
          setMessages((prev) => [...prev, pipelineStatusMessage]);

          const project = await api<Project>("/projects", {
            method: "POST",
            token: authedRef.current,
            json: buildProjectCreatePayload(trimmed),
          });
          targetProjectId = project.id;
          setProjectBusy(project.id, true);
          const shouldActivateCreatedProject =
            projectViewRevisionRef.current === viewRevisionAtSubmit;
          if (shouldActivateCreatedProject) {
            setWorkspaceBusy(false);
          }
          saveProjectSnapshot(
            {
              project,
              messages: [userMessage, pipelineStatusMessage],
              papers: [],
              selectedPaperIds: [],
              queries: [],
              conversation: null,
              runSummary: null,
            },
            { activate: shouldActivateCreatedProject },
          );
          await refreshProjects();

          let completedRun: RunPipelineResponse | null = null;
          let streamedError: string | null = null;

          await streamProjectPipeline(project.id, {
            token: authedRef.current,
            onEvent: (event) => {
              if (event.event === "status") {
                const detail = event.data.detail ?? formatDeepSearchPhase(event.data.phase);
                updateProjectMessages(
                  project.id,
                  (prev) =>
                    prev.map((message) =>
                      message.id === pipelineStatusId
                        ? { ...message, content: detail }
                        : message,
                    ),
                );
                return;
              }

              if (event.event === "papers") {
                updateProjectSnapshot(
                  project.id,
                  (snapshot) => ({
                    ...snapshot,
                    queries: event.data.queries,
                    papers: event.data.papers,
                    selectedPaperIds: [],
                    messages: snapshot.messages.map((message) =>
                      message.id === pipelineStatusId
                        ? {
                          ...message,
                          content: `Found ${event.data.ranked_count} ranked paper${event.data.ranked_count === 1 ? "" : "s"}. Summarizing related papers…`,
                        }
                        : message,
                    ),
                  }),
                  (snapshot) => {
                    setQueries(event.data.queries);
                    setPapers(event.data.papers);
                    setSelectedPaperIds([]);
                    setMessages(snapshot.messages);
                  },
                );
                return;
              }

              if (event.event === "summary") {
                const updatedPaper = pipelineSummaryPaper(event.data);
                updateProjectSnapshot(
                  project.id,
                  (snapshot) => ({
                    ...snapshot,
                    papers: patchProjectPaper(snapshot.papers, updatedPaper),
                  }),
                  () => setPapers((current) => patchProjectPaper(current, updatedPaper)),
                );
                return;
              }

              if (event.event === "done") {
                completedRun = event.data;
                updateProjectSnapshot(
                  project.id,
                  (snapshot) => ({
                    ...snapshot,
                    runSummary: event.data,
                    queries: event.data.queries,
                  }),
                  (snapshot) => {
                    setRunSummary(event.data);
                    setQueries(snapshot.queries);
                  },
                );
                return;
              }

              if (event.event === "error") {
                streamedError = event.data.detail;
                updateProjectMessages(
                  project.id,
                  (prev) =>
                    prev.map((message) =>
                      message.id === pipelineStatusId
                        ? { ...message, content: `Error: ${event.data.detail}` }
                        : message,
                    ),
                );
              }
            },
          });

          if (streamedError) {
            throw new Error(streamedError);
          }
          if (!completedRun) {
            throw new Error("The pipeline stream ended before the run was completed.");
          }
          notifyCreditBalanceChanged();

          const nextPapers = await fetchProjectPapers(project.id);

          const nextSelectedPaperIds: string[] = [];
          updateProjectSnapshot(
            project.id,
            (snapshot) => ({
              ...snapshot,
              papers: nextPapers,
              selectedPaperIds: nextSelectedPaperIds,
              messages: snapshot.messages.filter((m) => m.id !== pipelineStatusId),
            }),
            (snapshot) => {
              setPapers(snapshot.papers);
              setSelectedPaperIds(snapshot.selectedPaperIds);
              setMessages(snapshot.messages);
            },
          );

          await streamProjectChatTurn({
            projectId: project.id,
            paperIds: nextSelectedPaperIds,
            question: trimmed,
          });
          return;
        }

        const nextSelectedPaperIds = normalizeSelectedPaperIds(selectedPaperIds, papers);
        if (!arePaperIdListsEqual(selectedPaperIds, nextSelectedPaperIds)) {
          updateProjectSnapshot(
            activeProject.id,
            (snapshot) => ({ ...snapshot, selectedPaperIds: nextSelectedPaperIds }),
            (snapshot) => setSelectedPaperIds(snapshot.selectedPaperIds),
          );
        }

        if (!conversation) {
          await streamProjectChatTurn({
            projectId: activeProject.id,
            paperIds: nextSelectedPaperIds,
            question: trimmed,
          });
          return;
        }

        await streamProjectChatTurn({
          projectId: activeProject.id,
          conversationId: conversation.id,
          paperIds: nextSelectedPaperIds,
          question: trimmed,
        });
      } catch (err: any) {
        const detail = userFacingErrorMessage(err, "Something went wrong.");
        setError(detail);
        const errorMessage: ChatMessage = {
          id: uid(),
          role: "assistant",
          kind: "status",
          content: `Error: ${detail}`,
          createdAt: now(),
        };
        if (targetProjectId && projectSnapshotsRef.current[targetProjectId]) {
          updateProjectMessages(targetProjectId, (prev) => [...prev, errorMessage]);
        } else {
          setMessages((prev) => [...prev, errorMessage]);
        }
      } finally {
        if (targetProjectId) {
          setProjectBusy(targetProjectId, false);
        } else {
          setWorkspaceBusy(false);
        }
      }
    },
    [
      activeProject,
      chatMode,
      conversation,
      fetchProjectPapers,
      messages,
      papers,
      pendingDeepSearchPlan,
      queries,
      refreshProjects,
      runSummary,
      saveProjectSnapshot,
      selectedPaperIds,
      setProjectBusy,
      streamProjectChatTurn,
      updateProjectMessages,
      updateProjectSnapshot,
      userFacingErrorMessage,
    ],
  );

  const value = useMemo<ChatState>(
    () => ({
      projects,
      activeProject,
      messages,
      papers,
      selectedPaperIds,
      selectedPapers,
      deepSearchSources,
      pendingDeepSearchPlan,
      queries,
      conversation,
      runSummary,
      busy,
      uploadingReferenceFile,
      error,
      insufficientCredits,
      composerNotice,
      lastUploadedPaperId,
      chatMode,
      setChatMode,
      selectProject,
      renameProject,
      deleteProject,
      startNewResearch,
      submitMessage,
      startDeepSearchPlan,
      editDeepSearchPlan,
      uploadReferenceFile,
      togglePaperSelection,
      citationGraphCache,
      getCitationGraph,
      prefetchCitationGraphs,
      addCitationGraphPaperToProject,
      clearComposerNotice,
      clearInsufficientCredits,
      refreshProjects,
    }),
    [
      projects,
      activeProject,
      messages,
      papers,
      selectedPaperIds,
      selectedPapers,
      deepSearchSources,
      pendingDeepSearchPlan,
      queries,
      conversation,
      runSummary,
      busy,
      uploadingReferenceFile,
      error,
      insufficientCredits,
      composerNotice,
      lastUploadedPaperId,
      chatMode,
      selectProject,
      renameProject,
      deleteProject,
      startNewResearch,
      submitMessage,
      startDeepSearchPlan,
      editDeepSearchPlan,
      uploadReferenceFile,
      togglePaperSelection,
      citationGraphCache,
      getCitationGraph,
      prefetchCitationGraphs,
      addCitationGraphPaperToProject,
      clearComposerNotice,
      clearInsufficientCredits,
      refreshProjects,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatState {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used inside ChatProvider");
  return ctx;
}
