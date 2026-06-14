export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}
export function saveToken(t: string) { localStorage.setItem("access_token", t); }
export function clearToken() { localStorage.removeItem("access_token"); }

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("refresh_token");
}
export function saveRefreshToken(t: string) { localStorage.setItem("refresh_token", t); }
export function clearRefreshToken() { localStorage.removeItem("refresh_token"); }

export function clearAllTokens() { clearToken(); clearRefreshToken(); }

export async function tryRefresh(): Promise<boolean> {
  const rt = getRefreshToken();
  if (!rt) return false;
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!res.ok) { clearAllTokens(); return false; }
    const data = await res.json();
    saveToken(data.access_token);
    saveRefreshToken(data.refresh_token);
    return true;
  } catch {
    clearAllTokens();
    return false;
  }
}

async function request<T>(path: string, options: RequestInit = {}, requireAuth = false): Promise<T> {
  const token = getToken();
  if (requireAuth && !token) throw new Error("AUTH_REQUIRED");

  function buildHeaders(t: string | null): Record<string, string> {
    const h: Record<string, string> = { ...(options.headers as Record<string, string>) };
    if (t) h["Authorization"] = `Bearer ${t}`;
    if (!(options.body instanceof FormData)) h["Content-Type"] = "application/json";
    return h;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...options, headers: buildHeaders(token) });
  } catch (err) {
    throw new Error(`API 서버에 연결할 수 없습니다. FastAPI가 실행 중인지 확인하세요. (${err instanceof Error ? err.message : "network error"})`);
  }

  // 401이면 refresh 시도 후 1회 재요청
  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      try {
        res = await fetch(`${BASE_URL}${path}`, { ...options, headers: buildHeaders(getToken()) });
      } catch (err) {
        throw new Error(`API 서버에 연결할 수 없습니다. FastAPI가 실행 중인지 확인하세요. (${err instanceof Error ? err.message : "network error"})`);
      }
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export type ChatMsg = { role: "user" | "assistant"; content: string };

export type ConvSummary = {
  id: number; title: string; model_name: string;
  message_count: number; project_id: number | null;
  active_leaf_id: number | null; note: string | null;
  created_at: string; updated_at: string;
};

export type MsgResp = {
  id: number; conversation_id: number; parent_id: number | null;
  role: string; content: string;
  tokens_input: number | null; tokens_output: number | null;
  is_regenerated: boolean; deleted_at: string | null;
  note: string | null; created_at: string;
};

export type ConvDetail = ConvSummary & { messages: MsgResp[] };

export type ProjectSummary = {
  id: number;
  name: string;
  file_count: number;
  chunk_count: number;
  created_at: string;
};

export type SendMessageResponse = {
  user_message: MsgResp;
  assistant_message: MsgResp;
};

export type ModelOptions = {
  temperature?: number;
  top_p?: number;
  top_k?: number;
  min_p?: number;
  seed?: number | null;
  repeat_penalty?: number;
  repeat_last_n?: number;
  presence_penalty?: number;
  frequency_penalty?: number;
  num_predict?: number;
  num_ctx?: number;
  num_gpu?: number;
  low_vram?: boolean;
  f16_kv?: boolean;
  request_timeout_seconds?: number;
};

export async function streamConvMessage(
  convId: number,
  content: string,
  parentId?: number,
  imageB64?: string,
  projectId?: number,
  thinkMode?: boolean,
  webSearch?: boolean,
  modelOptions?: ModelOptions,
  ragTopK?: number,
  webMaxResults?: number,
  externalSignal?: AbortSignal,
): Promise<Response> {
  const token = getToken();
  if (!token) throw new Error("AUTH_REQUIRED");
  const timeoutMs = Math.max(10, modelOptions?.request_timeout_seconds ?? 300) * 1000;
  const controller = new AbortController();
  window.setTimeout(() => controller.abort(), timeoutMs);
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  const body = JSON.stringify({
    content,
    parent_id: parentId ?? null,
    image_b64: imageB64 ?? null,
    project_id: projectId ?? null,
    think_mode: thinkMode ?? false,
    web_search: webSearch ?? false,
    model_options: modelOptions ?? {},
    rag_top_k: ragTopK ?? 5,
    web_max_results: webMaxResults ?? 5,
  });
  const makeReq = (t: string) =>
    fetch(`${BASE_URL}/chat/conversations/${convId}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
      body,
      signal: controller.signal,
    });

  let res: Response;
  try {
    res = await makeReq(token);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`응답 제한 시간(${Math.round(timeoutMs / 1000)}초)을 초과했습니다.`);
    }
    throw new Error(`스트리밍 API 연결이 끊겼습니다. FastAPI 로그를 확인하세요. (${err instanceof Error ? err.message : "network error"})`);
  }
  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      try {
        res = await makeReq(getToken()!);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          throw new Error(`응답 제한 시간(${Math.round(timeoutMs / 1000)}초)을 초과했습니다.`);
        }
        throw new Error(`스트리밍 API 연결이 끊겼습니다. FastAPI 로그를 확인하세요. (${err instanceof Error ? err.message : "network error"})`);
      }
    }
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
  }
  return res;
}

export const api = {
  // 인증 불필요
  chat: (messages: ChatMsg[], modelOptions?: ModelOptions) =>
    request<{ reply: string }>("/chat/", { method: "POST", body: JSON.stringify({ messages, model_options: modelOptions ?? {} }) }),

  // 인증
  register: (email: string, password: string) =>
    request("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }
    ),

  quickReview: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ filename: string; language: string; result: string }>(
      "/review/quick", { method: "POST", body: form }
    );
  },

  uploadFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ file_id: number; filename: string; language: string; chunk_count: number }>(
      "/code/upload", { method: "POST", body: form }, true
    );
  },

  requestReview: (file_id: number) =>
    request<{ id: number; status: string }>("/review/", { method: "POST", body: JSON.stringify({ file_id }) }, true),

  getReview: (id: number) =>
    request<{ id: number; status: string; result: string | null; error: string | null; created_at: string }>(
      `/review/${id}`, {}, true
    ),

  uploadProject: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ project_id: number; name: string; file_count: number; chunk_count: number }>(
      "/code/upload-project", { method: "POST", body: form }, true
    );
  },

  listProjects: () =>
    request<ProjectSummary[]>("/code/projects", {}, true),

  // ── 대화 (Conversation) ───────────────────────────────────────────────
  createConversation: (project_id?: number) =>
    request<ConvSummary>(
      "/chat/conversations",
      { method: "POST", body: JSON.stringify({ project_id: project_id ?? null }) },
      true
    ),

  listConversations: () =>
    request<ConvSummary[]>("/chat/conversations", {}, true),

  getConversation: (id: number) =>
    request<ConvDetail>(`/chat/conversations/${id}`, {}, true),

  deleteConversation: (id: number) =>
    request<void>(`/chat/conversations/${id}`, { method: "DELETE" }, true),

  updateConversationNote: (id: number, note: string | null) =>
    request<ConvSummary>(
      `/chat/conversations/${id}/note`,
      { method: "PATCH", body: JSON.stringify({ note }) },
      true
    ),

  deleteMessage: (convId: number, msgId: number) =>
    request<void>(`/chat/conversations/${convId}/messages/${msgId}`, { method: "DELETE" }, true),

  updateMessageNote: (convId: number, msgId: number, note: string | null) =>
    request<void>(
      `/chat/conversations/${convId}/messages/${msgId}/note`,
      { method: "PATCH", body: JSON.stringify({ note }) },
      true
    ),

  regenerateMessage: (convId: number, msgId: number, modelOptions?: ModelOptions) =>
    request<SendMessageResponse>(
      `/chat/conversations/${convId}/messages/${msgId}/regenerate`,
      { method: "POST", body: JSON.stringify({ model_options: modelOptions ?? {} }) },
      true
    ),

  getMessageSiblings: (convId: number, msgId: number) =>
    request<{ siblings: { id: number; created_at: string }[] }>(
      `/chat/conversations/${convId}/messages/${msgId}/siblings`,
      {},
      true
    ),

};
