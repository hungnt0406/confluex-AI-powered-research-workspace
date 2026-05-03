export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "a20.token";
const USER_KEY = "a20.user";

export type AuthUser = { id: string; email: string; created_at: string };

export function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function loadUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as AuthUser) : null;
}

export function saveSession(token: string, user: AuthUser) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  init: RequestInit & { token?: string | null; json?: unknown; formData?: FormData } = {},
): Promise<T> {
  const { token, json, formData, headers, ...rest } = init;
  if (json !== undefined && formData !== undefined) {
    throw new Error("api() received both json and formData; only one body type is supported.");
  }
  const finalHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers as Record<string, string> | undefined),
  };
  if (json !== undefined) finalHeaders["Content-Type"] = "application/json";
  if (token) finalHeaders["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: json !== undefined ? JSON.stringify(json) : formData ?? rest.body,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (Array.isArray(data?.detail)) detail = data.detail.map((d: any) => d.msg).join("; ");
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ---- Typed helpers --------------------------------------------------------

export type Project = {
  id: string;
  user_id: string;
  title: string;
  topic_description: string;
  citation_format: string;
  year_start: number;
  candidate_limit: number;
  summary_limit: number;
  created_at: string;
};

export type ProjectTitleUpdate = {
  title: string;
};

export type RunPipelineResponse = {
  status: "completed";
  project_id: string;
  queries: string[];
  candidate_count: number;
  ranked_count: number;
  summary_count: number;
  qa_flags: string[];
  errors: string[];
};

export type TokenUsageBreakdownRow = {
  key: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_credits: number | null;
  request_count: number;
};

export type TokenUsageDailyRow = {
  day: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_credits: number | null;
  request_count: number;
};

export type ProjectTokenUsage = {
  project_id: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  cached_tokens: number;
  cost_credits: number | null;
  request_count: number;
  by_feature: TokenUsageBreakdownRow[];
  by_model: TokenUsageBreakdownRow[];
  by_day: TokenUsageDailyRow[];
};

export type AdminAccess = {
  is_admin: boolean;
};

export type AdminUsageUserRow = {
  user_id: string;
  user_email: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_credits: number | null;
  request_count: number;
};

export type AdminUsageProjectRow = {
  project_id: string;
  project_title: string;
  user_id: string;
  user_email: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_credits: number | null;
  request_count: number;
};

export type AdminUsageEventRow = {
  id: string;
  created_at: string;
  user_id: string;
  user_email: string;
  project_id: string;
  project_title: string;
  provider: string;
  endpoint: string;
  feature: string;
  model: string | null;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  reasoning_tokens: number;
  cached_tokens: number;
  cost_credits: number | null;
  user_prompt: string | null;
};

export type AdminTokenUsage = {
  date_from: string | null;
  date_to: string | null;
  user_id: string | null;
  project_id: string | null;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  cached_tokens: number;
  cost_credits: number | null;
  request_count: number;
  by_feature: TokenUsageBreakdownRow[];
  by_model: TokenUsageBreakdownRow[];
  by_day: TokenUsageDailyRow[];
  by_user: AdminUsageUserRow[];
  by_project: AdminUsageProjectRow[];
  recent_events: AdminUsageEventRow[];
};

export type PaperSummary = {
  problem: string | null;
  method: string | null;
  result: string | null;
  relevance_to_topic: string | null;
  has_error: boolean;
  error_message: string | null;
};

export type ProjectPaper = {
  id: string;
  project_id: string;
  reference_file_id: string | null;
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  doi: string | null;
  source: string;
  source_paper_id: string | null;
  source_url: string | null;
  pdf_url: string | null;
  citation_count: number | null;
  reference_count: number | null;
  status: string;
  relevance_score: number | null;
  summary: PaperSummary | null;
};

export type ReferenceFileRead = {
  id: string;
  project_id: string;
  original_filename: string;
  content_type: string | null;
  byte_size: number;
  sha256: string;
  parse_status: string;
  extracted_title: string | null;
  extracted_authors: string[];
  extracted_year: number | null;
  extracted_abstract: string | null;
  linked_paper_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type Paginated<T> = {
  data: T[];
  meta: { total: number; page: number; per_page: number; total_pages: number };
};

export type CitationGraphPaper = {
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  doi: string | null;
  source: string;
  source_paper_id: string | null;
  source_url: string | null;
  pdf_url: string | null;
  citation_count: number | null;
};

export type CitationGraph = {
  paper_id: string;
  resolved_by: string;
  resolved_source_paper_id: string;
  citation_count: number | null;
  reference_count: number | null;
  cited_by: CitationGraphPaper[];
  references: CitationGraphPaper[];
};

export async function fetchPaperCitationGraph(
  projectId: string,
  paperId: string,
  token: string,
  options?: { limit?: number },
): Promise<CitationGraph> {
  const limit = options?.limit ?? 20;
  return api<CitationGraph>(
    `/projects/${projectId}/papers/${paperId}/citation-graph?limit=${limit}`,
    { token },
  );
}

export type PaperMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type PaperConversation = {
  id: string;
  paper_id: string;
  created_at: string;
  updated_at: string;
  messages: PaperMessage[];
};

export type PaperConversationSummary = {
  id: string;
  paper_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  opening_question: string | null;
};

export type ProjectMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type ProjectConversation = {
  id: string;
  project_id: string;
  selected_paper_ids: string[];
  created_at: string;
  updated_at: string;
  messages: ProjectMessage[];
};

export type ProjectConversationSummary = {
  id: string;
  project_id: string;
  selected_paper_ids: string[];
  created_at: string;
  updated_at: string;
  message_count: number;
  opening_question: string | null;
};

export type ProjectConversationStreamEvent =
  | { event: "status"; data: { phase: "retrieving" | "generating" | "persisting" } }
  | { event: "conversation"; data: ProjectConversation }
  | { event: "token"; data: { delta: string } }
  | { event: "done"; data: ProjectConversation }
  | { event: "error"; data: { detail: string } };

export type DeepSearchSource = {
  id: string;
  run_id: string;
  source_type: "paper" | "paper_chunk" | "citation_graph" | "web";
  title: string;
  url: string | null;
  paper_id: string | null;
  snippet: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type DeepSearchSourceEventData = {
  id: string;
  source_type: "paper" | "paper_chunk" | "citation_graph" | "web";
  title: string;
  url: string | null;
  paper_id: string | null;
  note: string;
};

export type DeepSearchActivityEventType =
  "stage_start" | "stage_update" | "source_found" | "stage_complete" | "finalizing";

export type DeepSearchActivityChipType =
  "paper" | "website" | "pdf" | "document" | "dataset" | "code" | "other";

export type DeepSearchActivitySource = {
  id: string;
  type?: DeepSearchActivityChipType;
  source_type: string;
  title: string;
  url: string | null;
  paper_id: string | null;
};

export type DeepSearchActivityEventData = {
  type?: DeepSearchActivityEventType;
  event_type?: DeepSearchActivityEventType;
  phase: string;
  stage?: string;
  title: string;
  message?: string;
  detail?: string;
  sources?: DeepSearchActivitySource[];
};

export type DeepSearchRunSummary = {
  id: string;
  project_id: string;
  user_prompt: string;
  status: "running" | "completed" | "failed";
  selected_paper_ids: string[];
  source_count: number;
  warning_count: number;
  qa_flag_count: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type DeepSearchRun = DeepSearchRunSummary & {
  plan: Record<string, unknown>;
  report_body: string;
  source_summary: Record<string, unknown>;
  warnings: string[];
  qa_flags: Record<string, unknown>[];
  sources: DeepSearchSource[];
};

export type DeepSearchStreamEvent =
  | { event: "run"; data: DeepSearchRunSummary }
  | { event: "status"; data: { phase: string } }
  | { event: "activity"; data: DeepSearchActivityEventData }
  | { event: "source"; data: DeepSearchSourceEventData }
  | { event: "token"; data: { delta: string } }
  | { event: "done"; data: DeepSearchRun }
  | { event: "error"; data: { detail: string; run_id?: string } };

export type AuthResponse = { access_token: string; token_type: string; user: AuthUser };

export async function streamProjectConversation(
  path: string,
  options: {
    token: string;
    json: { paper_ids: string[]; question: string };
    onEvent: (event: ProjectConversationStreamEvent) => void;
  },
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      Authorization: `Bearer ${options.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(options.json),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (Array.isArray(data?.detail)) detail = data.detail.map((d: any) => d.msg).join("; ");
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }

  if (!response.body) {
    throw new Error("Streaming response body was not available.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flushFrame = (frame: string) => {
    const lines = frame.split(/\r?\n/);
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (!line || line.startsWith(":")) continue;
      if (line.startsWith("event:")) eventName = line.slice("event:".length).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trimStart());
    }
    if (!dataLines.length) return;
    const data = JSON.parse(dataLines.join("\n"));
    options.onEvent({ event: eventName, data } as ProjectConversationStreamEvent);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    for (const frame of frames) flushFrame(frame);
  }

  buffer += decoder.decode();
  if (buffer.trim()) flushFrame(buffer);
}

export async function streamDeepSearchRun(
  path: string,
  options: {
    token: string;
    json: { paper_ids: string[]; question: string };
    onEvent: (event: DeepSearchStreamEvent) => void;
  },
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      Authorization: `Bearer ${options.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(options.json),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (Array.isArray(data?.detail)) detail = data.detail.map((d: any) => d.msg).join("; ");
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }

  if (!response.body) {
    throw new Error("Streaming response body was not available.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flushFrame = (frame: string) => {
    const lines = frame.split(/\r?\n/);
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (!line || line.startsWith(":")) continue;
      if (line.startsWith("event:")) eventName = line.slice("event:".length).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trimStart());
    }
    if (!dataLines.length) return;
    const data = JSON.parse(dataLines.join("\n"));
    options.onEvent({ event: eventName, data } as DeepSearchStreamEvent);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    for (const frame of frames) flushFrame(frame);
  }

  buffer += decoder.decode();
  if (buffer.trim()) flushFrame(buffer);
}

export async function uploadProjectReferenceFile(
  projectId: string,
  file: File,
  token: string,
): Promise<ReferenceFileRead> {
  const formData = new FormData();
  formData.set("file", file);
  return api<ReferenceFileRead>(`/projects/${projectId}/reference-files`, {
    method: "POST",
    token,
    formData,
  });
}
