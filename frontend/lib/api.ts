export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const CREDIT_BALANCE_REFRESH_EVENT = "a20.credit_balance.refresh";

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
  required?: number;
  balance?: number;
  payload?: unknown;

  constructor(
    status: number,
    message: string,
    options: { required?: number; balance?: number; payload?: unknown } = {},
  ) {
    super(message);
    this.status = status;
    this.required = options.required;
    this.balance = options.balance;
    this.payload = options.payload;
  }
}

export type InsufficientCreditsError = ApiError & {
  status: 402;
};

function numberFromUnknown(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function fieldFromPayload(payload: unknown, field: "required" | "balance"): number | undefined {
  if (!payload || typeof payload !== "object") return undefined;
  const record = payload as Record<string, unknown>;
  const direct = numberFromUnknown(record[field]);
  if (direct !== undefined) return direct;
  const detail = record.detail;
  if (!detail || typeof detail !== "object") return undefined;
  return numberFromUnknown((detail as Record<string, unknown>)[field]);
}

function messageFromPayload(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") return fallback;
  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (Array.isArray(record.detail)) {
    return record.detail
      .map((item) => (item && typeof item === "object" ? (item as Record<string, unknown>).msg : null))
      .filter((item): item is string => typeof item === "string")
      .join("; ");
  }
  if (record.detail && typeof record.detail === "object") {
    const detail = record.detail as Record<string, unknown>;
    if (typeof detail.detail === "string") return detail.detail;
    if (typeof detail.message === "string") return detail.message;
  }
  if (typeof record.message === "string") return record.message;
  return fallback;
}

async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    /* ignore */
  }
  return new ApiError(response.status, messageFromPayload(payload, response.statusText), {
    required: fieldFromPayload(payload, "required"),
    balance: fieldFromPayload(payload, "balance"),
    payload,
  });
}

export function isInsufficientCreditsError(error: unknown): error is InsufficientCreditsError {
  return error instanceof ApiError && error.status === 402;
}

export function notifyCreditBalanceChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CREDIT_BALANCE_REFRESH_EVENT));
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
    throw await apiErrorFromResponse(response);
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

export type CreditPack = {
  id: string;
  name: string;
  credits: number;
  usd_cents: number;
  vnd_amount?: number;
  badge?: string | null;
};

export type CreditTransaction = {
  id: string;
  user_id?: string;
  delta: number;
  balance_after: number;
  kind: "topup" | "consume" | "grant" | "refund" | "adjust" | string;
  feature: string | null;
  reference_id: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};

export type CreditBalance = {
  credit_balance: number;
  is_unlimited?: boolean;
  recent_transactions: CreditTransaction[];
};

export type PaymentOrderStatus = "pending" | "paid" | "expired" | "cancelled";

export type PaymentOrder = {
  order_id?: string;
  id?: string;
  pack_id?: string;
  credits?: number;
  usd_amount?: number;
  usd_cents?: number;
  vnd_amount: number;
  fx_rate_usd_to_vnd?: number;
  reference_code: string;
  qr_url?: string | null;
  qr_payload?: string | null;
  status: PaymentOrderStatus;
  sepay_va_account?: string | null;
  sepay_va_bank_bin?: string | null;
  account_number?: string | null;
  bank_account?: string | null;
  bank_bin?: string | null;
  created_at?: string;
  paid_at?: string | null;
  expires_at: string;
};

export function paymentOrderId(order: PaymentOrder) {
  return order.order_id ?? order.id ?? "";
}

export async function fetchCreditPacks(token?: string | null): Promise<CreditPack[]> {
  return api<CreditPack[]>("/payments/packs", { token });
}

export async function createPaymentOrder(packId: string, token: string): Promise<PaymentOrder> {
  return api<PaymentOrder>("/payments/orders", {
    method: "POST",
    token,
    json: { pack_id: packId },
  });
}

export async function fetchPaymentOrder(orderId: string, token: string): Promise<PaymentOrder> {
  return api<PaymentOrder>(`/payments/orders/${orderId}`, { token });
}

export async function fetchCreditBalance(token: string): Promise<CreditBalance> {
  return api<CreditBalance>("/payments/balance", { token });
}

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

export type CitationGraphPaperImportResponse = {
  paper: ProjectPaper;
  created: boolean;
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

export async function importCitationGraphPaper(
  projectId: string,
  paper: CitationGraphPaper,
  token: string,
): Promise<CitationGraphPaperImportResponse> {
  return api<CitationGraphPaperImportResponse>(
    `/projects/${projectId}/papers/import-citation`,
    {
      method: "POST",
      token,
      json: paper,
    },
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

export type ProjectPipelinePapersEventData = {
  project_id: string;
  queries: string[];
  candidate_count: number;
  ranked_count: number;
  papers: ProjectPaper[];
};

export type ProjectPipelineStreamEvent =
  | { event: "status"; data: { phase: string; detail?: string } }
  | { event: "papers"; data: ProjectPipelinePapersEventData }
  | { event: "summary"; data: { paper: ProjectPaper } | ProjectPaper }
  | { event: "done"; data: RunPipelineResponse }
  | { event: "error"; data: { detail: string } };

export type DeepSearchSource = {
  id: string;
  run_id: string;
  source_type: "paper" | "paper_chunk" | "citation_graph" | "web";
  title: string;
  url: string | null;
  paper_id: string | null;
  snippet: string;
  note: string;
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

function parseSseFrame<TEvent>(frame: string): TEvent | null {
  const lines = frame.split(/\r?\n/);
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) eventName = line.slice("event:".length).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trimStart());
  }
  if (!dataLines.length) return null;
  const data = JSON.parse(dataLines.join("\n"));
  return { event: eventName, data } as TEvent;
}

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
    throw await apiErrorFromResponse(response);
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
    const data = JSON.parse(dataLines.join("\n")); console.log("SSE EVENT:", eventName, data);
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

export async function streamProjectPipeline(
  projectId: string,
  options: {
    token: string;
    onEvent: (event: ProjectPipelineStreamEvent) => void;
  },
): Promise<void> {
  const path = `/projects/${projectId}/run/stream`;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      Authorization: `Bearer ${options.token}`,
    },
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }

  if (!response.body) {
    throw new Error("Streaming response body was not available.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flushFrame = (frame: string) => {
    const event = parseSseFrame<ProjectPipelineStreamEvent>(frame);
    if (event) options.onEvent(event);
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
    json: { paper_ids: string[]; question: string; mode?: "standard" | "max" };
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
    throw await apiErrorFromResponse(response);
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
    const data = JSON.parse(dataLines.join("\n")); console.log("SSE EVENT:", eventName, data);
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

// ---- Writer types ----------------------------------------------------------

export interface WriterSectionRead {
  id: string;
  section_type: string;
  order_index: number;
  title: string;
  outline_text: string | null;
  user_inputs_json: Record<string, string>;
  draft_latex: string | null;
  low_confidence_spans_json: Array<{
    section_id: string;
    text: string;
    reason: string;
    suggested_query: string;
    char_offset: number;
  }>;
  cited_paper_ids_json: string[];
  status: string;
  updated_at: string;
}

export interface WriterSourcePaper {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  source: string;
  source_paper_id: string | null;
  source_url: string | null;
  pdf_url: string | null;
  reference_file_id: string | null;
}

export interface WriterDocumentRead {
  id: string;
  project_id: string;
  title: string;
  topic: string;
  thesis: string | null;
  paper_type: string;
  citation_style: string;
  preamble: string | null;
  source_paper_ids_json: string[];
  source_papers: WriterSourcePaper[];
  status: string;
  created_at: string;
  updated_at: string;
  sections: WriterSectionRead[];
}

export interface WriterDocumentSummaryRead {
  id: string;
  project_id: string;
  title: string;
  topic: string;
  paper_type: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SourceCandidate {
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  source: string;
  source_paper_id: string | null;
  source_url: string | null;
  pdf_url: string | null;
  pdf_available: boolean;
  arxiv_id: string | null;
}

export interface SectionVersionRead {
  id: string;
  section_id: string;
  draft_latex: string;
  created_at: string;
}

// ---- Writer API helpers ----------------------------------------------------

export async function createWriterDocument(
  projectId: string,
  data: { title: string; topic: string; thesis?: string; paper_type?: string; citation_style?: string },
  token: string,
): Promise<WriterDocumentRead> {
  return api<WriterDocumentRead>(`/projects/${projectId}/writer/documents`, {
    method: "POST",
    token,
    json: data,
  });
}

export async function listWriterDocuments(
  projectId: string,
  token: string,
): Promise<WriterDocumentSummaryRead[]> {
  return api<WriterDocumentSummaryRead[]>(`/projects/${projectId}/writer/documents`, { token });
}

export async function getWriterDocument(documentId: string, token: string): Promise<WriterDocumentRead> {
  return api<WriterDocumentRead>(`/writer/documents/${documentId}`, { token });
}

export async function updateWriterDocument(
  documentId: string,
  data: Partial<{ title: string; thesis: string; citation_style: string }>,
  token: string,
): Promise<WriterDocumentRead> {
  return api<WriterDocumentRead>(`/writer/documents/${documentId}`, {
    method: "PATCH",
    token,
    json: data,
  });
}

export async function deleteWriterDocument(documentId: string, token: string): Promise<void> {
  return api<void>(`/writer/documents/${documentId}`, { method: "DELETE", token });
}

export async function proposeOutline(
  documentId: string,
  token: string,
): Promise<{ outline_by_section: Record<string, string> }> {
  return api<{ outline_by_section: Record<string, string> }>(
    `/writer/documents/${documentId}/outline/propose`,
    { method: "POST", token },
  );
}

export async function applyOutline(
  documentId: string,
  outline_by_section: Record<string, string>,
  token: string,
): Promise<WriterDocumentRead> {
  return api<WriterDocumentRead>(`/writer/documents/${documentId}/outline`, {
    method: "PUT",
    token,
    json: { outline_by_section },
  });
}

export async function getSectionQuestions(
  documentId: string,
  sectionId: string,
  token: string,
): Promise<{ section_id: string; questions: string[] }> {
  return api<{ section_id: string; questions: string[] }>(
    `/writer/documents/${documentId}/sections/${sectionId}/questions`,
    { token },
  );
}

export async function submitSectionInputs(
  documentId: string,
  sectionId: string,
  user_inputs: Record<string, string>,
  token: string,
): Promise<WriterSectionRead> {
  return api<WriterSectionRead>(
    `/writer/documents/${documentId}/sections/${sectionId}/inputs`,
    { method: "PUT", token, json: { user_inputs } },
  );
}

export async function draftSection(
  documentId: string,
  sectionId: string,
  token: string,
): Promise<{ section: WriterSectionRead; warnings: string[] }> {
  return api<{ section: WriterSectionRead; warnings: string[] }>(
    `/writer/documents/${documentId}/sections/${sectionId}/draft`,
    { method: "POST", token },
  );
}

export async function saveSectionEdit(
  documentId: string,
  sectionId: string,
  draft_latex: string,
  token: string,
): Promise<WriterSectionRead> {
  return api<WriterSectionRead>(
    `/writer/documents/${documentId}/sections/${sectionId}`,
    { method: "PATCH", token, json: { draft_latex } },
  );
}

export async function getSectionVersions(
  documentId: string,
  sectionId: string,
  token: string,
): Promise<SectionVersionRead[]> {
  return api<SectionVersionRead[]>(
    `/writer/documents/${documentId}/sections/${sectionId}/versions`,
    { token },
  );
}

export async function revertToVersion(
  documentId: string,
  sectionId: string,
  versionId: string,
  token: string,
): Promise<WriterSectionRead> {
  return api<WriterSectionRead>(
    `/writer/documents/${documentId}/sections/${sectionId}/revert/${versionId}`,
    { method: "POST", token },
  );
}

export async function suggestSources(
  documentId: string,
  query: string,
  token: string,
): Promise<{ candidates: SourceCandidate[]; warnings: string[] }> {
  return api<{ candidates: SourceCandidate[]; warnings: string[] }>(
    `/writer/documents/${documentId}/sources/suggest`,
    { method: "POST", token, json: { query } },
  );
}

export async function attachSource(
  documentId: string,
  candidate: SourceCandidate,
  token: string,
): Promise<{ paper_id: string | null; requires_upload: boolean; message: string }> {
  return api<{ paper_id: string | null; requires_upload: boolean; message: string }>(
    `/writer/documents/${documentId}/sources/attach`,
    { method: "POST", token, json: { candidate } },
  );
}

export async function removeSource(documentId: string, paperId: string, token: string): Promise<void> {
  return api<void>(`/writer/documents/${documentId}/sources/${paperId}`, {
    method: "DELETE",
    token,
  });
}

export async function attachPaperById(
  documentId: string,
  paperId: string,
  token: string,
): Promise<{ paper_id: string | null; requires_upload: boolean; message: string }> {
  return api<{ paper_id: string | null; requires_upload: boolean; message: string }>(
    `/writer/documents/${documentId}/sources/attach-paper`,
    { method: "POST", token, json: { paper_id: paperId } },
  );
}

export async function getQaReport(
  documentId: string,
  token: string,
): Promise<{ unresolved_todos: unknown[]; total_count: number }> {
  return api<{ unresolved_todos: unknown[]; total_count: number }>(
    `/writer/documents/${documentId}/qa`,
    { token },
  );
}

export async function assembleDocument(
  documentId: string,
  token: string,
): Promise<{ tex: string; bib: string; unresolved_todo_count: number; warnings: string[] }> {
  return api<{ tex: string; bib: string; unresolved_todo_count: number; warnings: string[] }>(
    `/writer/documents/${documentId}/assemble`,
    { method: "POST", token },
  );
}

export async function exportDocument(documentId: string, token: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/writer/documents/${documentId}/export`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return response.blob();
}
