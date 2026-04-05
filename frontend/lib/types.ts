// ── Job ───────────────────────────────────────────────────────────────────────

export interface Job {
  url: string;
  url_encoded: string;
  title: string;
  company: string;
  site: string | null;
  location: string | null;
  salary: string | null;
  fit_score: number | null;
  score_reasoning: string | null;
  tailored_resume_path: string | null;
  cover_letter_path: string | null;
  apply_status: string | null;
  applied_at: string | null;
  application_url: string | null;
  discovered_at: string | null;
  tailored_at: string | null;
  has_pdf: boolean;
  has_cover_pdf: boolean;
  // Detail fields (only present on single-job fetch)
  resume_text?: string;
  cover_letter_text?: string;
  full_description?: string;
}

export interface JobsResponse {
  jobs: Job[];
  total: number;
  offset: number;
  limit: number;
}

// ── Stats / Funnel ────────────────────────────────────────────────────────────

export interface Funnel {
  discovered: number;
  pending_enrich: number;
  enriched: number;
  pending_filter: number;
  location_filtered: number;
  scored: number;
  pending_score: number;
  tailored: number;
  pending_tailor: number;
  cover: number;
  pending_cover: number;
  ready_to_apply: number;
  applied: number;
  interviews: number;
  offers: number;
  rejected_count: number;
  apply_errors: number;
}

export interface Stats {
  tailored: number;
  pending: number;
  applied: number;
  dismissed: number;
  untailored: number;
  location_filtered: number;
  ready_to_apply: number;
  interviews: number;
  offers: number;
  rejected: number;
  sites: string[];
  funnel: Funnel;
}

// ── Background Task ───────────────────────────────────────────────────────────

export type TaskStatus = "pending" | "running" | "done" | "error";

export interface Task {
  status: TaskStatus;
  result: unknown | null;
  error: string | null;
  log_lines: string[];
  log_total: number;
}

// ── Apply Workers ─────────────────────────────────────────────────────────────

export interface WorkerState {
  worker_id: number;
  status: string; // starting | applying | applied | failed | expired | captcha | idle | done
  job_title: string;
  company: string;
  score: number;
  start_time: number;
  actions: number;
  last_action: string;
  jobs_applied: number;
  jobs_failed: number;
  jobs_done: number;
  total_cost: number;
  log_file: string | null;
}

export interface ApplyStatus {
  running: boolean;
  workers: WorkerState[];
  events: string[];
  totals: {
    applied: number;
    failed: number;
    cost: number;
  };
}

// ── Profile ───────────────────────────────────────────────────────────────────

export interface Profile {
  personal?: {
    name?: string;
    email?: string;
    phone?: string;
    city?: string;
    country?: string;
    linkedin?: string;
    github?: string;
    portfolio?: string;
  };
  work_authorization?: {
    legally_authorized?: boolean;
    needs_sponsorship?: boolean;
    permit_type?: string;
    target_regions?: string[];
  };
  skills_boundary?: Record<string, string[]>;
  resume_facts?: {
    companies?: string[];
    projects?: string[];
    school?: string;
    metrics?: string[];
  };
  eeo?: Record<string, string>;
}

// ── System Status ─────────────────────────────────────────────────────────────

export interface SystemStatus {
  tier: 1 | 2 | 3;
  tier_label: string;
  llm_provider: string;
  llm_model: string;
  has_chrome: boolean;
  has_claude_cli: boolean;
}
