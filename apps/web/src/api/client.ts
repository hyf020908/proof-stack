import { useAuthStore } from "../auth/store";
import type {
  AnalysisEvent,
  AnalysisProgress,
  AnalysisRun,
  AuditEvent,
  AuthTokens,
  ChangedFile,
  EvidenceResponse,
  Finding,
  ImpactGraph,
  Organization,
  Page,
  PolicyDecision,
  Project,
  PublicSystemConfig,
  Requirement,
  TestExecution,
  User,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor(message: string, status: number, requestId?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  auth?: boolean;
  retryAuth?: boolean;
}

let refreshPromise: Promise<string | null> | null = null;

const errorMessage = (payload: unknown, fallback: string): string => {
  if (!payload || typeof payload !== "object") return fallback;
  const value = payload as Record<string, unknown>;
  if (typeof value.message === "string") return value.message;
  if (typeof value.detail === "string") return value.detail;
  if (Array.isArray(value.detail)) {
    return value.detail
      .map((entry) => {
        if (entry && typeof entry === "object") {
          const message = (entry as Record<string, unknown>).msg;
          if (typeof message === "string") return message;
        }
        return typeof entry === "string" ? entry : "Invalid request value";
      })
      .join("; ");
  }
  if (typeof value.error === "string") return value.error;
  if (value.error && typeof value.error === "object" && "message" in value.error) {
    return String(value.error.message);
  }
  return fallback;
};

const refreshAccessToken = async (): Promise<string | null> => {
  if (refreshPromise) return refreshPromise;
  const refreshToken = useAuthStore.getState().refreshToken;
  if (!refreshToken) return null;

  refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
    .then(async (response) => {
      if (!response.ok) return null;
      const tokens = (await response.json()) as AuthTokens;
      useAuthStore.getState().setSession(tokens, useAuthStore.getState().user);
      return tokens.access_token;
    })
    .catch(() => null)
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
};

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, retryAuth = true, headers: providedHeaders, ...init } = options;
  const headers = new Headers(providedHeaders);
  const token = useAuthStore.getState().accessToken;

  if (auth && token) headers.set("Authorization", `Bearer ${token}`);
  if (body !== undefined && !(body instanceof FormData))
    headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiError(
      "ProofStack API is unreachable. Confirm that the API service is running.",
      0,
      undefined,
      error,
    );
  }

  if (response.status === 401 && auth && retryAuth && useAuthStore.getState().refreshToken) {
    const nextToken = await refreshAccessToken();
    if (nextToken) return apiRequest<T>(path, { ...options, retryAuth: false });
    useAuthStore.getState().clearSession();
  }

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = undefined;
    }
    throw new ApiError(
      errorMessage(payload, `Request failed with status ${response.status}.`),
      response.status,
      response.headers.get("x-request-id") ?? undefined,
      payload,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const asPage = <T>(payload: Page<T> | T[]): Page<T> =>
  Array.isArray(payload)
    ? { items: payload, total: payload.length, page: 1, page_size: payload.length }
    : payload;

const queryString = (values: Record<string, string | number | boolean | undefined>): string => {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `?${query}` : "";
};

export const api = {
  auth: {
    login: (email: string, password: string) =>
      apiRequest<AuthTokens>("/auth/login", {
        method: "POST",
        body: { email, password },
        auth: false,
      }),
    register: (input: {
      email: string;
      password: string;
      display_name: string;
      organization_name: string;
    }) => apiRequest<AuthTokens>("/auth/register", { method: "POST", body: input, auth: false }),
    demo: () => apiRequest<AuthTokens>("/auth/demo", { method: "POST", auth: false }),
    me: () => apiRequest<User>("/auth/me"),
  },
  organization: {
    current: () => apiRequest<Organization>("/organizations/current"),
    update: (input: Pick<Organization, "name">) =>
      apiRequest<Organization>("/organizations/current", { method: "PATCH", body: input }),
    members: () => apiRequest<Page<User> | User[]>("/organizations/current/members").then(asPage),
  },
  projects: {
    list: (input: { page?: number; page_size?: number; search?: string } = {}) =>
      apiRequest<Page<Project> | Project[]>(`/projects${queryString(input)}`).then(asPage),
    get: (id: string) => apiRequest<Project>(`/projects/${id}`),
    create: (input: {
      name: string;
      slug?: string;
      description?: string;
      default_branch?: string;
      repository_provider?: string;
      repository_url?: string | null;
    }) => apiRequest<Project>("/projects", { method: "POST", body: input }),
    update: (id: string, input: Partial<Project>) =>
      apiRequest<Project>(`/projects/${id}`, { method: "PATCH", body: input }),
    remove: (id: string) => apiRequest<void>(`/projects/${id}`, { method: "DELETE" }),
  },
  analyses: {
    list: (projectId: string, input: { page?: number; page_size?: number } = {}) =>
      apiRequest<Page<AnalysisRun> | AnalysisRun[]>(
        `/projects/${projectId}/analyses${queryString(input)}`,
      ).then(asPage),
    get: (id: string) => apiRequest<AnalysisRun>(`/analyses/${id}`),
    startDemo: (projectId: string, input: Record<string, unknown>) =>
      apiRequest<AnalysisRun>(`/projects/${projectId}/analyses/demo`, {
        method: "POST",
        body: input,
      }),
    startGitHub: (projectId: string, input: Record<string, unknown>) =>
      apiRequest<AnalysisRun>(`/projects/${projectId}/analyses/github`, {
        method: "POST",
        body: input,
      }),
    startUpload: (projectId: string, form: FormData) =>
      apiRequest<AnalysisRun>(`/projects/${projectId}/analyses/upload`, {
        method: "POST",
        body: form,
      }),
    cancel: (id: string) => apiRequest<AnalysisRun>(`/analyses/${id}/cancel`, { method: "POST" }),
    progress: (id: string) => apiRequest<AnalysisProgress>(`/analyses/${id}/progress`),
    events: (id: string) =>
      apiRequest<Page<AnalysisEvent> | AnalysisEvent[]>(`/analyses/${id}/events`).then(asPage),
    findings: (id: string, input: Record<string, string | number | undefined> = {}) =>
      apiRequest<Page<Finding> | Finding[]>(`/analyses/${id}/findings${queryString(input)}`).then(
        asPage,
      ),
    files: (id: string) =>
      apiRequest<Page<ChangedFile> | ChangedFile[]>(`/analyses/${id}/changed-files`).then(asPage),
    graph: (id: string) => apiRequest<ImpactGraph>(`/analyses/${id}/graph`),
    requirements: (id: string) =>
      apiRequest<Page<Requirement> | Requirement[]>(`/analyses/${id}/requirements`).then(asPage),
    tests: (id: string) =>
      apiRequest<Page<TestExecution> | TestExecution[]>(`/analyses/${id}/tests`).then(asPage),
    policies: (id: string) =>
      apiRequest<Page<PolicyDecision> | PolicyDecision[]>(`/analyses/${id}/policy-decisions`).then(
        asPage,
      ),
    evidence: (id: string) => apiRequest<EvidenceResponse>(`/analyses/${id}/evidence`),
  },
  findings: {
    update: (id: string, status: Finding["status"]) =>
      apiRequest<Finding>(`/findings/${id}`, { method: "PATCH", body: { status } }),
  },
  policies: {
    list: () =>
      apiRequest<Page<{ name: string; version?: number }> | Array<{ name: string }>>(
        "/policies",
      ).then(asPage),
    validate: (document: string) =>
      apiRequest<{ valid: boolean; errors: string[] }>("/policies/validate", {
        method: "POST",
        body: { document },
      }),
  },
  audit: {
    list: (input: Record<string, string | number | undefined> = {}) =>
      apiRequest<Page<AuditEvent> | AuditEvent[]>(`/audit-events${queryString(input)}`).then(
        asPage,
      ),
  },
  system: {
    version: () => apiRequest<{ version: string }>("/version", { auth: false }),
    ready: () => apiRequest<Record<string, unknown>>("/ready", { auth: false }),
    config: () => apiRequest<PublicSystemConfig>("/system/public-config", { auth: false }),
  },
};

export async function downloadEvidence(analysisId: string): Promise<void> {
  const token = useAuthStore.getState().accessToken;
  const response = await fetch(`${API_BASE}/analyses/${analysisId}/evidence/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new ApiError("Evidence download failed.", response.status);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `proofstack-evidence-${analysisId}.zip`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
