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
  ProjectTokenUsage,
  RunPipelineResponse,
  api,
  streamProjectConversation,
  uploadProjectReferenceFile,
} from "@/lib/api";

const ACTIVE_PROJECT_STORAGE_PREFIX = "a20.active_project";
const SELECTED_PAPERS_STORAGE_PREFIX = "a20.selected_papers";
const GENERATED_OVERVIEW_PROMPT_PREFIX = "Give me a structured overview of this paper relative to: ";
const MAX_SELECTED_PAPERS = 5;
const DEFAULT_CITATION_FORMAT = "APA";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  kind?: "text" | "status" | "summary";
  createdAt: string;
};

export type ComposerNotice = {
  tone: "success" | "warning" | "error";
  message: string;
};

export type UploadReferenceFileOptions = {
  topic?: string;
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
  tokenUsage: ProjectTokenUsage | null;
  busy: boolean;
  uploadingReferenceFile: boolean;
  error: string | null;
  composerNotice: ComposerNotice | null;
  lastUploadedPaperId: string | null;
  selectProject: (id: string) => Promise<void>;
  renameProject: (id: string, title: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  startNewResearch: () => void;
  submitMessage: (text: string) => Promise<void>;
  uploadReferenceFile: (file: File, options?: UploadReferenceFileOptions) => Promise<void>;
  togglePaperSelection: (paperId: string) => void;
  clearComposerNotice: () => void;
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

function buildProjectShellMessages(project: Project, papers: ProjectPaper[]): ChatMessage[] {
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

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { token, user } = useAuth();
  const authedRef = useRef(token);
  const activeProjectIdRef = useRef<string | null>(null);
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
  const [tokenUsage, setTokenUsage] = useState<ProjectTokenUsage | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadingReferenceFile, setUploadingReferenceFile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composerNotice, setComposerNotice] = useState<ComposerNotice | null>(null);
  const [lastUploadedPaperId, setLastUploadedPaperId] = useState<string | null>(null);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  activeProjectIdRef.current = activeProject?.id ?? null;

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

  const fetchProjectTokenUsage = useCallback(async (projectId: string) => {
    return api<ProjectTokenUsage>(`/projects/${projectId}/token-usage`, {
      token: authedRef.current,
    });
  }, []);

  const clearComposerNotice = useCallback(() => {
    setComposerNotice(null);
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
    setTokenUsage(null);
    setComposerNotice(null);
    setLastUploadedPaperId(null);
    setError(null);
  }, []);

  const selectProject = useCallback(
    async (projectId: string) => {
      if (!authedRef.current) return;
      setBusy(true);
      setError(null);
      setComposerNotice(null);
      setLastUploadedPaperId(null);
      try {
        setActiveProject(null);
        setPapers([]);
        setSelectedPaperIds([]);
        setMessages([]);
        setConversation(null);
        setRunSummary(null);
        setTokenUsage(null);
        const project = await api<Project>(`/projects/${projectId}`, {
          token: authedRef.current,
        });

        const nextPapers = await fetchProjectPapers(project.id);
        const nextTokenUsage = await fetchProjectTokenUsage(project.id);
        setPapers(nextPapers);
        setTokenUsage(nextTokenUsage);
        setQueries([]);

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

        const fallbackSelectedPaperIds = normalizeSelectedPaperIds(
          restoredConversation?.selected_paper_ids ?? [],
          nextPapers,
        );
        const nextSelectedPaperIds =
          normalizedSavedSelectedPaperIds !== null
            ? normalizedSavedSelectedPaperIds
            : fallbackSelectedPaperIds;

        setActiveProject(project);
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
    [fetchProjectPapers, fetchProjectTokenUsage, user?.id],
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
      setComposerNotice(null);
      setLastUploadedPaperId(null);

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

  const uploadReferenceFile = useCallback(
    async (file: File, options?: UploadReferenceFileOptions) => {
      if (!authedRef.current || uploadingReferenceFile) return;

      setUploadingReferenceFile(true);
      setError(null);
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
          await refreshProjects();

          if (activeProjectIdRef.current && activeProjectIdRef.current !== project.id) {
            return;
          }

          setActiveProject(project);
          setMessages([]);
          setConversation(null);
          setQueries([]);
          setRunSummary(null);
          setTokenUsage(null);

          const nextPapers = await fetchProjectPapers(project.id);
          const nextTokenUsage = await fetchProjectTokenUsage(project.id);
          setPapers(nextPapers);
          setTokenUsage(nextTokenUsage);
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
        const nextPapers = await fetchProjectPapers(project.id);
        const nextTokenUsage = await fetchProjectTokenUsage(project.id);
        const nextSelectedPaperIds = normalizeSelectedPaperIds(selectedPaperIds, nextPapers);

        if (activeProjectIdRef.current !== project.id) {
          return;
        }

        setPapers(nextPapers);
        setTokenUsage(nextTokenUsage);
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
        const detail = err?.message ?? "Failed to upload the reference PDF.";
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
      fetchProjectTokenUsage,
      refreshProjects,
      selectedPaperIds,
      uploadingReferenceFile,
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

      setMessages((prev) => [
        ...prev,
        {
          id: assistantMessageId,
          role: "assistant",
          kind: assistantKind,
          content: "",
          createdAt: now(),
        },
      ]);

      const path = conversationId
        ? `/projects/${projectId}/conversations/${conversationId}/messages/stream`
        : `/projects/${projectId}/conversations/stream`;

      await streamProjectConversation(path, {
        token: authedRef.current,
        json: { paper_ids: paperIds, question },
        onEvent: (event) => {
          if (event.event === "conversation") {
            setConversation(event.data);
            return;
          }

          if (event.event === "token") {
            const delta = event.data.delta;
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, content: `${message.content}${delta}` }
                  : message,
              ),
            );
            return;
          }

          if (event.event === "done") {
            completedConversation = event.data;
            setConversation(event.data);
            const assistantTurn = [...event.data.messages]
              .reverse()
              .find((message) => message.role === "assistant");
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessageId
                  ? {
                    ...message,
                    id: assistantTurn?.id ?? message.id,
                    content: assistantTurn?.content ?? message.content,
                    createdAt: assistantTurn?.created_at ?? message.createdAt,
                  }
                  : message,
              ),
            );
            return;
          }

          if (event.event === "error") {
            streamedError = event.data.detail;
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessageId
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
      if (!completedConversation) {
        throw new Error("The streaming chat response ended before it was persisted.");
      }
      setTokenUsage(await fetchProjectTokenUsage(projectId));
      return completedConversation;
    },
    [fetchProjectTokenUsage],
  );

  const submitMessage = useCallback(
    async (text: string) => {
      if (!authedRef.current) return;
      const trimmed = text.trim();
      if (!trimmed) return;
      setBusy(true);
      setError(null);
      setComposerNotice(null);
      setLastUploadedPaperId(null);

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

          const project = await api<Project>("/projects", {
            method: "POST",
            token: authedRef.current,
            json: buildProjectCreatePayload(trimmed),
          });
          setActiveProject(project);
          await refreshProjects();

          const runResponse = await api<RunPipelineResponse>(`/projects/${project.id}/run`, {
            method: "POST",
            token: authedRef.current,
          });
          setRunSummary(runResponse);
          setQueries(runResponse.queries);

          const nextPapers = await fetchProjectPapers(project.id);
          const nextTokenUsage = await fetchProjectTokenUsage(project.id);
          setPapers(nextPapers);
          setTokenUsage(nextTokenUsage);

          const nextSelectedPaperIds: string[] = [];
          setSelectedPaperIds(nextSelectedPaperIds);

          if (nextPapers.length === 0) {
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

          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              kind: "summary",
              content: `Pipeline complete — ${runResponse.candidate_count} candidates, ${runResponse.ranked_count} ranked, ${runResponse.summary_count} summarized. No papers are selected yet.`,
              createdAt: now(),
            },
          ]);
          await streamProjectChatTurn({
            projectId: project.id,
            paperIds: nextSelectedPaperIds,
            question: trimmed,
          });
          return;
        }

        const nextSelectedPaperIds = normalizeSelectedPaperIds(selectedPaperIds, papers);
        if (!arePaperIdListsEqual(selectedPaperIds, nextSelectedPaperIds)) {
          setSelectedPaperIds(nextSelectedPaperIds);
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
    [
      activeProject,
      conversation,
      fetchProjectPapers,
      fetchProjectTokenUsage,
      papers,
      refreshProjects,
      selectedPaperIds,
      streamProjectChatTurn,
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
      queries,
      conversation,
      runSummary,
      tokenUsage,
      busy,
      uploadingReferenceFile,
      error,
      composerNotice,
      lastUploadedPaperId,
      selectProject,
      renameProject,
      deleteProject,
      startNewResearch,
      submitMessage,
      uploadReferenceFile,
      togglePaperSelection,
      clearComposerNotice,
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
      tokenUsage,
      busy,
      uploadingReferenceFile,
      error,
      composerNotice,
      lastUploadedPaperId,
      selectProject,
      renameProject,
      deleteProject,
      startNewResearch,
      submitMessage,
      uploadReferenceFile,
      togglePaperSelection,
      clearComposerNotice,
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
