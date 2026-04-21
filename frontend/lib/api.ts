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
  init: RequestInit & { token?: string | null; json?: unknown } = {},
): Promise<T> {
  const { token, json, headers, ...rest } = init;
  const finalHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers as Record<string, string> | undefined),
  };
  if (json !== undefined) finalHeaders["Content-Type"] = "application/json";
  if (token) finalHeaders["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
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
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  doi: string | null;
  source: string;
  source_url: string | null;
  pdf_url: string | null;
  citation_count: number | null;
  reference_count: number | null;
  status: string;
  relevance_score: number | null;
  summary: PaperSummary | null;
};

export type Paginated<T> = {
  data: T[];
  meta: { total: number; page: number; per_page: number; total_pages: number };
};

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

export type AuthResponse = { access_token: string; token_type: string; user: AuthUser };
