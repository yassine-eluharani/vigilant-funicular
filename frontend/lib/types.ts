// ── Auth ──────────────────────────────────────────────────────────────────────

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

// ── Job ───────────────────────────────────────────────────────────────────────

export interface Job {
  url: string;
  url_encoded: string;
  title: string;
  company: string | null;
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
  favorited?: boolean;
  locked?: boolean;
  // Detail fields (only present on single-job fetch)
  resume_text?: string;
  cover_letter_text?: string;
  full_description?: string;
  closed?: boolean;
  closed_reason?: string | null;
}

// ── User / Tier ───────────────────────────────────────────────────────────────

export interface UserInfo {
  id: number;
  email: string;
  full_name: string;
  tier: "free" | "pro";
  has_profile: boolean;
  tailors_used: number;
  covers_used: number;
  tailor_limit: number | null;
  cover_limit: number | null;
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
  locked_count: number;
  sites: string[];
  score_distribution: Record<string, number>;
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

// ── Profile ───────────────────────────────────────────────────────────────────

export interface Profile {
  personal?: {
    full_name?: string;
    preferred_name?: string;
    email?: string;
    phone?: string;
    city?: string;
    province_state?: string;
    country?: string;
    postal_code?: string;
    linkedin_url?: string;
    github_url?: string;
    portfolio_url?: string;
    website_url?: string;
  };
  work_authorization?: {
    legally_authorized_to_work?: boolean;
    require_sponsorship?: boolean;
    work_permit_type?: string;
  };
  availability?: {
    earliest_start_date?: string;
    available_for_full_time?: boolean;
    available_for_contract?: boolean;
  };
  compensation?: {
    salary_expectation?: string;
    salary_currency?: string;
    salary_range_min?: number;
    salary_range_max?: number;
  };
  experience?: {
    years_of_experience_total?: number;
    education_level?: string;
    current_job_title?: string;
    current_company?: string;
    target_role?: string;
  };
  skills_boundary?: {
    languages?: string[];
    frameworks?: string[];
    devops?: string[];
    databases?: string[];
    tools?: string[];
  };
  resume_facts?: {
    preserved_companies?: string[];
    preserved_projects?: string[];
    preserved_school?: string;
    real_metrics?: string[];
  };
  eeo_voluntary?: Record<string, string>;
}

// ── System Status ─────────────────────────────────────────────────────────────

export interface SystemStatus {
  tier: 1 | 2;
  tier_label: string;
  llm_provider: string;
  llm_model: string;
}
