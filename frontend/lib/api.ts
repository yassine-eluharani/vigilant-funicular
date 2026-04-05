import type {
  Job,
  JobsResponse,
  Stats,
  Task,
  ApplyStatus,
  Profile,
  SystemStatus,
} from "./types";

// Use NEXT_PUBLIC_API_URL in browser, fallback to relative for SSR behind nginx
const BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.API_URL ?? "http://backend:8000");

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const err = await res.text().catch(() => res.statusText);
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export const getStats = (): Promise<Stats> => req("/api/stats");

// ── Jobs ──────────────────────────────────────────────────────────────────────

export interface JobsQuery {
  min_score?: number;
  max_score?: number;
  site?: string;
  search?: string;
  status?: string;
  offset?: number;
  limit?: number;
}

export function getJobs(q: JobsQuery = {}): Promise<JobsResponse> {
  const params = new URLSearchParams();
  if (q.min_score != null) params.set("min_score", String(q.min_score));
  if (q.max_score != null) params.set("max_score", String(q.max_score));
  if (q.site)              params.set("site", q.site);
  if (q.search)            params.set("search", q.search);
  if (q.status)            params.set("status", q.status);
  if (q.offset != null)    params.set("offset", String(q.offset));
  if (q.limit != null)     params.set("limit", String(q.limit));
  return req(`/api/jobs?${params}`);
}

export const getJob = (encodedUrl: string): Promise<Job> =>
  req(`/api/jobs/${encodedUrl}`);

export const saveResume = (encodedUrl: string, text: string): Promise<{ ok: boolean; task_id: string }> =>
  req(`/api/jobs/${encodedUrl}/resume`, { method: "PUT", body: JSON.stringify({ text }) });

export const markApplied = (encodedUrl: string) =>
  req(`/api/jobs/${encodedUrl}/mark-applied`, { method: "POST" });

export const dismissJob = (encodedUrl: string) =>
  req(`/api/jobs/${encodedUrl}/dismiss`, { method: "POST" });

export const restoreJob = (encodedUrl: string) =>
  req(`/api/jobs/${encodedUrl}/restore`, { method: "POST" });

export const markStatus = (encodedUrl: string, status: string) =>
  req(`/api/jobs/${encodedUrl}/mark-status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

export const tailorJob = (encodedUrl: string, validation_mode = "normal") =>
  req<{ task_id: string }>(`/api/jobs/${encodedUrl}/tailor?validation_mode=${validation_mode}`, {
    method: "POST",
  });

// ── Pipeline ──────────────────────────────────────────────────────────────────

export interface PipelineRunOptions {
  stages: string[];
  min_score?: number;
  workers?: number;
  validation?: string;
  stream?: boolean;
}

export const runPipeline = (opts: PipelineRunOptions): Promise<{ task_id: string }> =>
  req("/api/pipeline/run", { method: "POST", body: JSON.stringify(opts) });

export const getTask = (taskId: string, since = 0): Promise<Task> =>
  req(`/api/tasks/${taskId}?since=${since}`);

// ── Apply workers ─────────────────────────────────────────────────────────────

export const getApplyStatus = (): Promise<ApplyStatus> => req("/api/apply/status");

export interface ApplyStartOptions {
  workers?: number;
  limit?: number;
  min_score?: number;
  headless?: boolean;
  continuous?: boolean;
  model?: string;
}

export const startApply = (opts: ApplyStartOptions): Promise<{ ok: boolean; pid?: number }> =>
  req("/api/apply/start", { method: "POST", body: JSON.stringify(opts) });

export const stopApply = (): Promise<{ ok: boolean }> =>
  req("/api/apply/stop", { method: "POST" });

// ── Config ────────────────────────────────────────────────────────────────────

export const getProfile = (): Promise<Profile> => req("/api/profile");
export const updateProfile = (data: Profile): Promise<{ ok: boolean }> =>
  req("/api/profile", { method: "PUT", body: JSON.stringify(data) });

export const getSearches = (): Promise<Record<string, unknown>> =>
  req("/api/config/searches");
export const updateSearches = (data: Record<string, unknown>) =>
  req("/api/config/searches", { method: "PUT", body: JSON.stringify(data) });

export const getEmployers = (): Promise<Record<string, unknown>> =>
  req("/api/config/employers");
export const updateEmployers = (data: Record<string, unknown>) =>
  req("/api/config/employers", { method: "PUT", body: JSON.stringify(data) });

export const getEnvConfig = (): Promise<Record<string, string | null>> =>
  req("/api/config/env");
export const updateEnvConfig = (data: Record<string, string>) =>
  req("/api/config/env", { method: "PUT", body: JSON.stringify(data) });

export const getResumeText = (): Promise<{ text: string; exists: boolean }> =>
  req("/api/config/resume");
export const updateResumeText = (text: string) =>
  req("/api/config/resume", { method: "PUT", body: JSON.stringify({ text }) });

export async function uploadResumePdf(file: File): Promise<{ ok: boolean; size: number; task_id: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/config/resume/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
  return res.json();
}

// ── System ────────────────────────────────────────────────────────────────────

export const getSystemStatus = (): Promise<SystemStatus> => req("/api/system/status");

// ── Database ──────────────────────────────────────────────────────────────────

export const purgeDatabase = (): Promise<{ deleted: number }> =>
  req("/api/database", { method: "DELETE" });

// ── URL helpers ───────────────────────────────────────────────────────────────

export const resumeUrl  = (encodedUrl: string) => `${BASE}/api/resume/${encodedUrl}`;
export const coverUrl   = (encodedUrl: string) => `${BASE}/api/cover-letter/${encodedUrl}`;
export const sseTaskUrl = (taskId: string)     => `${BASE}/api/stream/task/${taskId}`;
export const sseApplyUrl = ()                   => `${BASE}/api/stream/apply`;
