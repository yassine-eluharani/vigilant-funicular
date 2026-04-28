"""Pydantic v2 request/response models for every typed endpoint (BE-003).

These models are the source of truth for the API surface. Every router
function that accepts a JSON body should declare a typed parameter here, and
every endpoint returning structured data should set ``response_model`` so the
generated OpenAPI schema is accurate.

The frontend's hand-mirrored types in ``frontend/lib/types.ts`` are the
compatibility contract — these schemas match those shapes field-for-field
(including which fields are optional vs. nullable). Don't change a response
shape here without auditing the frontend reader for that field.

All bodies that the previous routers read via ``body.get("foo", "")`` are
modelled with the same default semantics so tests / clients that omit the
field still work.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Base config — allow extra fields on responses by default so adding a new
# DB column doesn't immediately break clients, but stay strict on requests.
# ---------------------------------------------------------------------------


class _ResponseModel(BaseModel):
    """Base for response bodies — tolerant of extra DB-derived keys."""
    model_config = ConfigDict(extra="allow")


class _RequestModel(BaseModel):
    """Base for request bodies — strict-ish but permissive of unknown keys
    so legacy callers don't break when a field is renamed/dropped server-side.
    """
    model_config = ConfigDict(extra="allow")


# === auth ===================================================================


class MeResponse(_ResponseModel):
    """GET /api/auth/me — current user identity + tier + usage."""
    id: int
    email: str
    full_name: str
    tier: Literal["free", "pro"]
    has_profile: bool
    tailors_used: int
    covers_used: int
    tailor_limit: Optional[int] = None
    cover_limit: Optional[int] = None


# === jobs ===================================================================


class JobItem(_ResponseModel):
    """A single row in GET /api/jobs.

    Mirrors the frontend's `Job` interface (frontend/lib/types.ts). All fields
    that the frontend treats as ``string | null`` are ``Optional[str]`` here;
    fields that may not appear at all (detail-only) are ``Optional[...]`` with
    a default of None and live alongside the list-shape fields.

    Extra fields are allowed because the underlying DB row carries more
    columns than the frontend reads — keeping ``extra="allow"`` lets us pass
    the dict through ``response_model`` without losing data the UI hasn't
    started reading yet.
    """
    url: str
    url_encoded: str = ""
    title: Optional[str] = None
    company: Optional[str] = None
    site: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    fit_score: Optional[int] = None
    score_reasoning: Optional[str] = None
    tailored_resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    apply_status: Optional[str] = None
    applied_at: Optional[str] = None
    application_url: Optional[str] = None
    discovered_at: Optional[str] = None
    tailored_at: Optional[str] = None
    has_pdf: bool = False
    has_cover_pdf: bool = False
    favorited: Optional[bool] = None
    locked: Optional[bool] = None

    # Detail-only fields (only present on single-job fetch)
    resume_text: Optional[str] = None
    cover_letter_text: Optional[str] = None
    full_description: Optional[str] = None
    closed: Optional[bool] = None
    closed_reason: Optional[str] = None


class JobListResponse(_ResponseModel):
    """GET /api/jobs — paginated list."""
    jobs: list[JobItem]
    total: int
    offset: int
    limit: int


class FunnelStats(_ResponseModel):
    discovered: int
    pending_enrich: int
    enriched: int
    pending_filter: int
    location_filtered: int
    scored: int
    pending_score: int
    tailored: int
    pending_tailor: int
    cover: int
    pending_cover: int
    ready_to_apply: int
    applied: int
    interviews: int
    offers: int
    rejected_count: int
    apply_errors: int


class StatsResponse(_ResponseModel):
    """GET /api/stats — dashboard counters + funnel."""
    tailored: int
    pending: int
    applied: int
    dismissed: int
    untailored: int
    location_filtered: int
    ready_to_apply: int
    interviews: int
    offers: int
    rejected: int
    locked_count: int
    sites: list[str]
    score_distribution: dict[str, int]
    funnel: FunnelStats


class SaveResumeRequest(_RequestModel):
    """PUT /api/jobs/{encoded_url}/resume — overwrite the tailored resume text."""
    text: str = ""


class SaveResumeResponse(_ResponseModel):
    ok: bool


class TailorResponse(_ResponseModel):
    """POST /api/jobs/{encoded_url}/tailor — kicks off background tailor."""
    task_id: str


class CoverResponse(_ResponseModel):
    """POST /api/jobs/{encoded_url}/cover — kicks off background cover letter."""
    task_id: str


class FavoriteResponse(_ResponseModel):
    favorited: bool


class MarkStatusRequest(_RequestModel):
    """POST /api/jobs/{encoded_url}/mark-status — update apply_status."""
    status: str = ""


class StatusMutationResponse(_ResponseModel):
    """Generic shape for mark-applied / dismiss / restore / mark-status."""
    ok: bool
    status: str


# === pipeline ===============================================================


class PipelineRunRequest(_RequestModel):
    """POST /api/pipeline/run — explicit pipeline kickoff (score-only today)."""
    stages: list[str] = Field(default_factory=lambda: ["score"])
    workers: int = 1
    stream: bool = False
    # Forward-compat: the frontend may send these but the route ignores them
    # for now. Declaring them keeps validation friendly.
    min_score: Optional[int] = None
    validation: Optional[str] = None


class PipelineRunResponse(_ResponseModel):
    """POST /api/pipeline/run — task_id is null when nothing to do."""
    task_id: Optional[str] = None
    skipped: Optional[bool] = None
    reason: Optional[str] = None


class MaybeScoreResponse(_ResponseModel):
    """POST /api/pipeline/maybe-score — idempotent auto-score trigger."""
    started: bool
    task_id: Optional[str] = None
    reason: Optional[str] = None


class TaskStatusResponse(_ResponseModel):
    """GET /api/tasks/{task_id} — poll background task progress."""
    status: Literal["pending", "running", "done", "error"]
    result: Any = None
    error: Optional[str] = None
    log_lines: list[str]
    log_total: int


# === config =================================================================


class PersonalProfile(_RequestModel):
    full_name: Optional[str] = None
    preferred_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    province_state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    website_url: Optional[str] = None


class WorkAuthorization(_RequestModel):
    legally_authorized_to_work: Optional[bool] = None
    require_sponsorship: Optional[bool] = None
    work_permit_type: Optional[str] = None


class Availability(_RequestModel):
    earliest_start_date: Optional[str] = None
    available_for_full_time: Optional[bool] = None
    available_for_contract: Optional[bool] = None


class Compensation(_RequestModel):
    salary_expectation: Optional[str] = None
    salary_currency: Optional[str] = None
    salary_range_min: Optional[float] = None
    salary_range_max: Optional[float] = None


class Experience(_RequestModel):
    years_of_experience_total: Optional[float] = None
    education_level: Optional[str] = None
    current_job_title: Optional[str] = None
    current_company: Optional[str] = None
    target_role: Optional[str] = None


class SkillsBoundary(_RequestModel):
    languages: Optional[list[str]] = None
    frameworks: Optional[list[str]] = None
    devops: Optional[list[str]] = None
    databases: Optional[list[str]] = None
    tools: Optional[list[str]] = None


class ResumeFacts(_RequestModel):
    preserved_companies: Optional[list[str]] = None
    preserved_projects: Optional[list[str]] = None
    preserved_school: Optional[str] = None
    real_metrics: Optional[list[str]] = None


class Profile(_RequestModel):
    """Mirrors `frontend/lib/types.ts::Profile`. Every field optional —
    the frontend posts deeply partial profiles as the user fills in the form.
    """
    personal: Optional[PersonalProfile] = None
    work_authorization: Optional[WorkAuthorization] = None
    availability: Optional[Availability] = None
    compensation: Optional[Compensation] = None
    experience: Optional[Experience] = None
    skills_boundary: Optional[SkillsBoundary] = None
    resume_facts: Optional[ResumeFacts] = None
    eeo_voluntary: Optional[dict[str, str]] = None


class ProfileUpdateResponse(_ResponseModel):
    ok: bool
    scoring_task_id: Optional[str] = None


class SearchQuery(_RequestModel):
    query: str
    tier: int = 1


class SearchLocation(_RequestModel):
    location: str
    remote: bool = False


class SearchDefaults(_RequestModel):
    results_per_site: Optional[int] = None
    hours_old: Optional[int] = None


class SearchLocationFilters(_RequestModel):
    accept_patterns: Optional[list[str]] = None
    reject_patterns: Optional[list[str]] = None


class SearchConfig(_RequestModel):
    """Mirrors `frontend/lib/types.ts::SearchConfig`. Round-trips through
    the searches GET/PUT — must accept extra keys the frontend may surface
    (e.g. ``description_reject_patterns`` injected by GET).
    """
    queries: Optional[list[SearchQuery]] = None
    locations: Optional[list[SearchLocation]] = None
    boards: Optional[list[str]] = None
    country: Optional[str] = None
    defaults: Optional[SearchDefaults] = None
    exclude_titles: Optional[list[str]] = None
    location: Optional[SearchLocationFilters] = None


class SearchesUpdateResponse(_ResponseModel):
    ok: bool


class EnvConfigResponse(_ResponseModel):
    """GET /api/config/env — slim presence flags only (SEC-001)."""
    gemini_configured: bool
    openai_configured: bool
    llm_url_set: bool
    llm_model: Optional[str] = None


class ResumeUpdateRequest(_RequestModel):
    """PUT /api/config/resume — overwrite the user's master resume text."""
    text: str = ""


class ResumeResponse(_ResponseModel):
    """GET /api/config/resume — current master resume text."""
    text: str
    exists: bool


class ResumeUpdateResponse(_ResponseModel):
    ok: bool
    scoring_task_id: Optional[str] = None


class ResumeUploadResponse(_ResponseModel):
    """POST /api/config/resume/upload — PDF upload + extract-in-background."""
    ok: bool
    size: int
    task_id: str


class ParseResumeRequest(_RequestModel):
    """POST /api/config/resume/parse — LLM-extract structured fields."""
    text: str = ""


class ParseResumeResponse(_ResponseModel):
    """POST /api/config/resume/parse — extracted fields blob.

    The LLM may omit any key, so ``extracted`` is a free-form dict. The
    frontend's ``ExtractedResume`` type names the shape it expects but every
    field is optional.
    """
    ok: bool
    extracted: dict[str, Any]


class NotificationsResponse(_ResponseModel):
    email_notifications: bool


class NotificationsUpdateRequest(_RequestModel):
    email_notifications: bool = False


class SystemStatusResponse(_ResponseModel):
    """GET /api/system/status — live runtime tier + LLM provider info."""
    tier: int
    tier_label: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class SchedulerStatusResponse(_ResponseModel):
    """GET /api/scheduler/status — last discovery-worker sync info."""
    last_sync: Optional[str] = None
    jobs_found: int = 0


# === stripe =================================================================


class CreateCheckoutResponse(_ResponseModel):
    checkout_url: str


class CreateBillingPortalResponse(_ResponseModel):
    portal_url: str


class StripeWebhookResponse(_ResponseModel):
    """POST /api/stripe/webhook — generic ack. The webhook payload itself is
    untyped (Stripe's event shape is enormous); we only model the response.
    """
    received: bool
    duplicate: Optional[bool] = None


# === stream =================================================================
# SSE endpoints (`/api/stream/task/{id}`, `/api/stream/user/events`) return
# `StreamingResponse` whose payload is line-delimited SSE events, not JSON.
# Pydantic models don't apply — leave those routes unannotated.
