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
  PaperConversation,
  Project,
  ProjectPaper,
  RunPipelineResponse,
  api,
} from "@/lib/api";

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
  queries: string[];
  conversation: PaperConversation | null;
  groundingPaper: ProjectPaper | null;
  runSummary: RunPipelineResponse | null;
  busy: boolean;
  error: string | null;
  selectProject: (id: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  startNewResearch: () => void;
  submitMessage: (text: string) => Promise<void>;
  refreshProjects: () => Promise<void>;
};

const ChatContext = createContext<ChatState | null>(null);

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function now() {
  return new Date().toISOString();
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const authedRef = useRef(token);
  authedRef.current = token;

  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [papers, setPapers] = useState<ProjectPaper[]>([]);
  const [queries, setQueries] = useState<string[]>([]);
  const [conversation, setConversation] = useState<PaperConversation | null>(null);
  const [groundingPaper, setGroundingPaper] = useState<ProjectPaper | null>(null);
  const [runSummary, setRunSummary] = useState<RunPipelineResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshProjects = useCallback(async () => {
    if (!authedRef.current) return;
    const list = await api<Project[]>("/projects", { token: authedRef.current });
    setProjects(list);
  }, []);

  useEffect(() => {
    if (token) refreshProjects().catch((e) => setError(String(e)));
  }, [token, refreshProjects]);

  const startNewResearch = useCallback(() => {
    setActiveProject(null);
    setMessages([]);
    setPapers([]);
    setQueries([]);
    setConversation(null);
    setGroundingPaper(null);
    setRunSummary(null);
    setError(null);
  }, []);

  const selectProject = useCallback(
    async (projectId: string) => {
      if (!authedRef.current) return;
      setBusy(true);
      setError(null);
      try {
        const project = await api<Project>(`/projects/${projectId}`, {
          token: authedRef.current,
        });
        setActiveProject(project);
        setConversation(null);
        setGroundingPaper(null);
        setRunSummary(null);

        const papersResponse = await api<Paginated<ProjectPaper>>(
          `/projects/${project.id}/papers?per_page=30`,
          { token: authedRef.current },
        );
        setPapers(papersResponse.data);

        const topPaper = papersResponse.data[0] ?? null;
        setGroundingPaper(topPaper);
        setQueries([]);

        const initial: ChatMessage[] = [
          {
            id: uid(),
            role: "user",
            content: project.topic_description,
            kind: "text",
            createdAt: project.created_at,
          },
        ];
        if (papersResponse.data.length > 0) {
          initial.push({
            id: uid(),
            role: "assistant",
            kind: "summary",
            content: `I found ${papersResponse.data.length} ranked papers for "${project.title}". Top pick: "${topPaper?.title}". Ask a question about this paper and I'll ground my answer in it.`,
            createdAt: now(),
          });
        } else {
          initial.push({
            id: uid(),
            role: "assistant",
            kind: "status",
            content: `This project has no ranked papers yet. Send a follow-up message to run the discovery pipeline.`,
            createdAt: now(),
          });
        }
        setMessages(initial);
      } catch (err: any) {
        setError(err?.message ?? "Failed to load project.");
      } finally {
        setBusy(false);
      }
    },
    [],
  );

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
        // Branch 1: first message of a brand new research thread -> create project + run pipeline.
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
          setGroundingPaper(topPaper);

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

          const conversation = await api<PaperConversation>(
            `/projects/${project.id}/papers/${topPaper.id}/conversations`,
            {
              method: "POST",
              token: authedRef.current,
              json: {
                question: `Give me a structured overview of this paper relative to: ${trimmed}`,
              },
            },
          );
          setConversation(conversation);

          const lastAssistant = [...conversation.messages]
            .reverse()
            .find((m) => m.role === "assistant");
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              kind: "summary",
              content: `Pipeline complete — ${runResponse.candidate_count} candidates, ${runResponse.ranked_count} ranked, ${runResponse.summary_count} summarized. Grounded on "${topPaper.title}".`,
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

        // Branch 2: follow-up inside an existing project.
        if (!groundingPaper) {
          // Try to (re)load ranked papers then pick the top.
          const papersResponse = await api<Paginated<ProjectPaper>>(
            `/projects/${activeProject.id}/papers?per_page=30`,
            { token: authedRef.current },
          );
          setPapers(papersResponse.data);
          const topPaper = papersResponse.data[0] ?? null;
          setGroundingPaper(topPaper);
          if (!topPaper) {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "assistant",
                kind: "status",
                content: "No ranked papers available on this project yet.",
                createdAt: now(),
              },
            ]);
            return;
          }
        }

        const paper = groundingPaper!;
        if (!conversation) {
          const created = await api<PaperConversation>(
            `/projects/${activeProject.id}/papers/${paper.id}/conversations`,
            {
              method: "POST",
              token: authedRef.current,
              json: { question: trimmed },
            },
          );
          setConversation(created);
          const assistantTurn = [...created.messages]
            .reverse()
            .find((m) => m.role === "assistant");
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

        const updated = await api<PaperConversation>(
          `/projects/${activeProject.id}/papers/${paper.id}/conversations/${conversation.id}/messages`,
          {
            method: "POST",
            token: authedRef.current,
            json: { question: trimmed },
          },
        );
        setConversation(updated);
        const last = [...updated.messages].reverse().find((m) => m.role === "assistant");
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "assistant",
            kind: "text",
            content: last?.content ?? "(No grounded answer returned.)",
            createdAt: last?.created_at ?? now(),
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
    [activeProject, groundingPaper, conversation, refreshProjects],
  );

  const value = useMemo<ChatState>(
    () => ({
      projects,
      activeProject,
      messages,
      papers,
      queries,
      conversation,
      groundingPaper,
      runSummary,
      busy,
      error,
      selectProject,
      deleteProject,
      startNewResearch,
      submitMessage,
      refreshProjects,
    }),
    [
      projects,
      activeProject,
      messages,
      papers,
      queries,
      conversation,
      groundingPaper,
      runSummary,
      busy,
      error,
      selectProject,
      deleteProject,
      startNewResearch,
      submitMessage,
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
