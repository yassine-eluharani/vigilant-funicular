from typing import Optional
from sqlmodel import SQLModel, Field


class Job(SQLModel, table=True):
    __tablename__ = "jobs"  # type: ignore[assignment]

    # Discovery
    url: str = Field(primary_key=True)
    title: Optional[str] = None
    company: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    site: Optional[str] = None
    strategy: Optional[str] = None
    discovered_at: Optional[str] = None

    # Enrichment
    full_description: Optional[str] = None
    application_url: Optional[str] = None
    detail_scraped_at: Optional[str] = None
    detail_error: Optional[str] = None

    # Filter (location restriction is a fact about the job, not per-user)
    filtered_at: Optional[str] = None

    # Structured metadata extracted once per job
    job_metadata_json: Optional[str] = None

    # DEPRECATED: legacy per-user columns — reads still work, new writes go to user_jobs
    fit_score: Optional[int] = None
    score_reasoning: Optional[str] = None
    scored_at: Optional[str] = None
    tailored_resume_path: Optional[str] = None
    tailored_at: Optional[str] = None
    tailor_attempts: int = Field(default=0)
    cover_letter_path: Optional[str] = None
    cover_letter_at: Optional[str] = None
    cover_attempts: int = Field(default=0)
    favorited: int = Field(default=0)
    applied_at: Optional[str] = None
    apply_status: Optional[str] = None
    apply_error: Optional[str] = None
    apply_attempts: int = Field(default=0)
    agent_id: Optional[str] = None
    last_attempted_at: Optional[str] = None
    apply_duration_ms: Optional[int] = None
    apply_task_id: Optional[str] = None
    verification_confidence: Optional[str] = None
