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
  Paginated,
  Project,
  ProjectConversation,
  ProjectConversationSummary,
  ProjectPaper,
  ProjectTitleUpdate,
  RunPipelineResponse,
  api,
} from "@/lib/api";

const ACTIVE_PROJECT_STORAGE_PREFIX = "a20.active_project";
const SELECTED_PAPERS_STORAGE_PREFIX = "a20.selected_papers";
const GENERATED_OVERVIEW_PROMPT_PREFIX = "Give me a structured overview of this paper relative to: ";
const MAX_SELECTED_PAPERS = 5;

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  kind?: "text" | "status" | "summary";
  createdAt: string;
};

type ChatState = {
  projects: Project[];
  activeProject: Project | null;
  messages: ChatMessage[];
  papers: ProjectPaper[];
  selectedPaperIds: string[];
  selectedPapers: ProjectPaper[];
  queries: string[];
  conversation: ProjectConversation | null;
  runSummary: RunPipelineResponse | null;
  busy: boolean;
  error: string | null;
  selectProject: (id: string) => Promise<void>;
  renameProject: (id: string, title: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  startNewResearch: () => void;
  submitMessage: (text: string) => Promise<void>;
  togglePaperSelection: (paperId: string) => void;
  refreshProjects: () => Promise<void>;
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

function persistActiveProjectId(userId: string | null | undefined, projectId: string | null) {
  if (typeof window === "undefined" || !userId) return;
  const storageKey = getActiveProjectStorageKey(userId);
  if (projectId) {
    window.localStorage.setItem(storageKey, projectId);
    return;
  }
  window.localStorage.removeItem(storageKey);
}

function loadSavedSelectedPaperIds(userId: string | null | undefined, projectId: string | null) {
  if (typeof window === "undefined" || !userId || !projectId) return [];
  const raw = window.localStorage.getItem(getSelectedPapersStorageKey(userId, projectId));
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : [];
  } catch {
    return [];
  }
}

function persistSelectedPaperIds(
  userId: string | null | undefined,
  projectId: string | null,
  paperIds: string[],
) {
  if (typeof window === "undefined" || !userId || !projectId) return;
  const storageKey = getSelectedPapersStorageKey(userId, projectId);
  if (paperIds.length > 0) {
    window.localStorage.setItem(storageKey, JSON.stringify(paperIds));
    return;
  }
  window.localStorage.removeItem(storageKey);
}

function normalizeSelectedPaperIds(paperIds: string[], papers: ProjectPaper[]) {
  const availableIds = new Set(papers.map((paper) => paper.id));
  return Array.from(new Set(paperIds)).filter((paperId) => availableIds.has(paperId)).slice(0, MAX_SELECTED_PAPERS);
}

function buildSelectionStatusText(selectedPapers: ProjectPaper[]) {
  if (selectedPapers.length === 0) {
    return "No papers are selected for future questions.";
  }
  if (selectedPapers.length === 1) {
    return `Selected paper for future questions: "${selectedPapers[0]?.title}".`;
  }
  return `Selected papers for future questions: ${selectedPapers.map((paper) => `"${paper.title}"`).join(", ")}.`;
}

function buildProjectShellMessages(project: Project, papers: ProjectPaper[]): ChatMessage[] {
  const topPaper = papers[0] ?? null;
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
      content: `I found ${papers.length} ranked papers for "${project.title}". Top pick: "${topPaper?.title}". You can now choose up to ${MAX_SELECTED_PAPERS} papers for grounded questions.`,
      createdAt: now(),
    });
    return initial;
  }

  initial.push({
    id: uid(),
    role: "assistant",
    kind: "status",
    content: "This project has no ranked papers yet. Send a follow-up message to run the discovery pipeline.",
    createdAt: now(),
  });
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
          message.content === generatedOverviewPrompt
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

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { token, user } = useAuth();
  const authedRef = useRef(token);
  const restoreAttemptedRef = useRef(false);
  authedRef.current = token;

  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [papers, setPapers] = useState<ProjectPaper[]>([]);
  const [selectedPaperIds, setSelectedPaperIds] = useState<string[]>([]);
  const [queries, setQueries] = useState<string[]>([]);
  const [conversation, setConversation] = useState<ProjectConversation | null>(null);
  const [runSummary, setRunSummary] = useState<RunPipelineResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectsLoaded, setProjectsLoaded] = useState(false);

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

  useEffect(() => {
    if (token) refreshProjects().catch((e) => setError(String(e)));
  }, [token, refreshProjects]);

  useEffect(() => {
    persistActiveProjectId(user?.id, activeProject?.id ?? null);
  }, [user?.id, activeProject?.id]);

  useEffect(() => {
    persistSelectedPaperIds(user?.id, activeProject?.id ?? null, selectedPaperIds);
  }, [user?.id, activeProject?.id, selectedPaperIds]);

  const selectedPapers = useMemo(
    () => selectedPaperIds
      .map((paperId) => papers.find((paper) => paper.id === paperId) ?? null)
      .filter((paper): paper is ProjectPaper => paper !== null),
    [papers, selectedPaperIds],
  );

  const startNewResearch = useCallback(() => {
    setActiveProject(null);
    setMessages([]);
    setPapers([]);
    setSelectedPaperIds([]);
    setQueries([]);
    setConversation(null);
    setRunSummary(null);
    setError(null);
  }, []);

  const selectProject = useCallback(
    async (projectId: string) => {
      if (!authedRef.current) return;
      setBusy(true);
      setError(null);
      try {
        setPapers([]);
        setSelectedPaperIds([]);
        setMessages([]);
        const project = await api<Project>(`/projects/${projectId}`, {
          token: authedRef.current,
        });
        setActiveProject(project);
        setConversation(null);
        setRunSummary(null);

        const papersResponse = await api<Paginated<ProjectPaper>>(
          `/projects/${project.id}/papers?per_page=30`,
          { token: authedRef.current },
        );
        const nextPapers = papersResponse.data;
        setPapers(nextPapers);
        setQueries([]);

        const savedSelectedPaperIds = normalizeSelectedPaperIds(
          loadSavedSelectedPaperIds(user?.id, project.id),
          nextPapers,
        );

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

        const fallbackSelectedPaperIds = normalizeSelectedPaperIds(
          restoredConversation?.selected_paper_ids ?? [],
          nextPapers,
        );
        const topPaperId = nextPapers[0]?.id;
        const nextSelectedPaperIds =
          savedSelectedPaperIds.length > 0
            ? savedSelectedPaperIds
            : fallbackSelectedPaperIds.length > 0
              ? fallbackSelectedPaperIds
              : topPaperId
                ? [topPaperId]
                : [];

        setSelectedPaperIds(nextSelectedPaperIds);
        setConversation(restoredConversation);

        const shellMessages = buildProjectShellMessages(project, nextPapers);
        setMessages(
          restoredConversation
            ? [...shellMessages, ...buildRestoredConversationMessages(project, restoredConversation)]
            : shellMessages,
        );
      } catch (err: any) {
        if (err?.status === 404) {
          persistActiveProjectId(user?.id, null);
        }
        setError(err?.message ?? "Failed to load project.");
      } finally {
        setBusy(false);
      }
    },
    [user?.id],
  );

  useEffect(() => {
    if (!projectsLoaded || activeProject || restoreAttemptedRef.current) return;

    restoreAttemptedRef.current = true;
    const savedProjectId = loadSavedActiveProjectId(user?.id);
    if (!savedProjectId) return;

    if (!projects.some((project) => project.id === savedProjectId)) {
      persistActiveProjectId(user?.id, null);
      return;
    }

    void selectProject(savedProjectId);
  }, [projectsLoaded, projects, activeProject, selectProject, user?.id]);

  const deleteProject = useCallback(
    async (projectId: string) => {
      if (!authedRef.current) return;
      setBusy(true);
      setError(null);

      try {
        await api<void>(`/projects/${projectId}`, {
          method: "DELETE",
          token: authedRef.current,
        });
        setProjects((prev) => prev.filter((project) => project.id !== projectId));
        if (activeProject?.id === projectId) {
          startNewResearch();
        }
      } catch (err: any) {
        setError(err?.message ?? "Failed to delete project.");
      } finally {
        setBusy(false);
      }
    },
    [activeProject, startNewResearch],
  );

  const renameProject = useCallback(
    async (projectId: string, title: string) => {
      if (!authedRef.current) return;
      const trimmedTitle = title.trim();
      if (!trimmedTitle) return;

      setBusy(true);
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
        setActiveProject((prev) => (prev?.id === projectId ? updatedProject : prev));
      } catch (err: any) {
        setError(err?.message ?? "Failed to rename project.");
        throw err;
      } finally {
        setBusy(false);
      }
    },
    [],
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

  const submitMessage = useCallback(
    async (text: string) => {
      if (!authedRef.current) return;
      const trimmed = text.trim();
      if (!trimmed) return;
      setBusy(true);
      setError(null);

      const userMessage: ChatMessage = {
        id: uid(),
        role: "user",
        content: trimmed,
        kind: "text",
        createdAt: now(),
      };
      setMessages((prev) => [...prev, userMessage]);

      try {
        if (!activeProject) {
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              kind: "status",
              content: "Creating your project and running the Searcher → Reader pipeline…",
              createdAt: now(),
            },
          ]);

          const title = trimmed.slice(0, 120);
          const project = await api<Project>("/projects", {
            method: "POST",
            token: authedRef.current,
            json: {
              title,
              topic_description: trimmed,
              citation_format: "APA",
            },
          });
          setActiveProject(project);
          await refreshProjects();

          const runResponse = await api<RunPipelineResponse>(`/projects/${project.id}/run`, {
            method: "POST",
            token: authedRef.current,
          });
          setRunSummary(runResponse);
          setQueries(runResponse.queries);

          const papersResponse = await api<Paginated<ProjectPaper>>(
            `/projects/${project.id}/papers?per_page=30`,
            { token: authedRef.current },
          );
          setPapers(papersResponse.data);

          const topPaper = papersResponse.data[0] ?? null;
          const nextSelectedPaperIds = topPaper ? [topPaper.id] : [];
          setSelectedPaperIds(nextSelectedPaperIds);

          if (!topPaper) {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "assistant",
                kind: "status",
                content:
                  runResponse.errors.length > 0
                    ? `Pipeline finished with errors: ${runResponse.errors.join("; ")}`
                    : "The pipeline finished but did not return any ranked papers. Try refining your topic.",
                createdAt: now(),
              },
            ]);
            return;
          }

          const createdConversation = await api<ProjectConversation>(
            `/projects/${project.id}/conversations`,
            {
              method: "POST",
              token: authedRef.current,
              json: {
                paper_ids: nextSelectedPaperIds,
                question: `${GENERATED_OVERVIEW_PROMPT_PREFIX}${trimmed}`,
              },
            },
          );
          setConversation(createdConversation);

          const lastAssistant = [...createdConversation.messages]
            .reverse()
            .find((message) => message.role === "assistant");
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              kind: "summary",
              content: `Pipeline complete — ${runResponse.candidate_count} candidates, ${runResponse.ranked_count} ranked, ${runResponse.summary_count} summarized. Currently selected: "${topPaper.title}".`,
              createdAt: now(),
            },
            {
              id: uid(),
              role: "assistant",
              kind: "text",
              content: lastAssistant?.content ?? "(No grounded answer returned.)",
              createdAt: lastAssistant?.created_at ?? now(),
            },
          ]);
          return;
        }

        let nextSelectedPaperIds = normalizeSelectedPaperIds(selectedPaperIds, papers);
        if (nextSelectedPaperIds.length === 0) {
          const topPaperId = papers[0]?.id;
          nextSelectedPaperIds = topPaperId ? [topPaperId] : [];
          setSelectedPaperIds(nextSelectedPaperIds);
        }
        if (nextSelectedPaperIds.length === 0) {
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              kind: "status",
              content: "No ranked papers are selected for this project yet.",
              createdAt: now(),
            },
          ]);
          return;
        }

        if (!conversation) {
          const createdConversation = await api<ProjectConversation>(
            `/projects/${activeProject.id}/conversations`,
            {
              method: "POST",
              token: authedRef.current,
              json: { paper_ids: nextSelectedPaperIds, question: trimmed },
            },
          );
          setConversation(createdConversation);
          const assistantTurn = [...createdConversation.messages]
            .reverse()
            .find((message) => message.role === "assistant");
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              kind: "text",
              content: assistantTurn?.content ?? "(No grounded answer returned.)",
              createdAt: assistantTurn?.created_at ?? now(),
            },
          ]);
          return;
        }

        const updatedConversation = await api<ProjectConversation>(
          `/projects/${activeProject.id}/conversations/${conversation.id}/messages`,
          {
            method: "POST",
            token: authedRef.current,
            json: { paper_ids: nextSelectedPaperIds, question: trimmed },
          },
        );
        setConversation(updatedConversation);
        const lastAssistant = [...updatedConversation.messages]
          .reverse()
          .find((message) => message.role === "assistant");
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "assistant",
            kind: "text",
            content: lastAssistant?.content ?? "(No grounded answer returned.)",
            createdAt: lastAssistant?.created_at ?? now(),
          },
        ]);
      } catch (err: any) {
        const detail = err?.message ?? "Something went wrong.";
        setError(detail);
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "assistant",
            kind: "status",
            content: `Error: ${detail}`,
            createdAt: now(),
          },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [activeProject, selectedPaperIds, papers, conversation, refreshProjects],
  );

  const value = useMemo<ChatState>(
    () => ({
      projects,
      activeProject,
      messages,
      papers,
      selectedPaperIds,
      selectedPapers,
      queries,
      conversation,
      runSummary,
      busy,
      error,
      selectProject,
      renameProject,
      deleteProject,
      startNewResearch,
      submitMessage,
      togglePaperSelection,
      refreshProjects,
    }),
    [
      projects,
      activeProject,
      messages,
      papers,
      selectedPaperIds,
      selectedPapers,
      queries,
      conversation,
      runSummary,
      busy,
      error,
      selectProject,
      renameProject,
      deleteProject,
      startNewResearch,
      submitMessage,
      togglePaperSelection,
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
