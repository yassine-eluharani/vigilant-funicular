from typing import Optional
from sqlmodel import SQLModel, Field


class UserJob(SQLModel, table=True):
    __tablename__ = "user_jobs"  # type: ignore[assignment]

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    job_url: str = Field(primary_key=True, foreign_key="jobs.url")

    fit_score: Optional[int] = None
    score_reasoning: Optional[str] = None
    scored_at: Optional[str] = None

    tailored_resume_path: Optional[str] = None
    tailored_resume_text: Optional[str] = None
    tailored_at: Optional[str] = None
    tailor_attempts: int = Field(default=0)

    cover_letter_path: Optional[str] = None
    cover_letter_text: Optional[str] = None
    cover_letter_at: Optional[str] = None
    cover_attempts: int = Field(default=0)

    apply_status: Optional[str] = None
    applied_at: Optional[str] = None
    apply_error: Optional[str] = None

    favorited: int = Field(default=0)
    dismissed_at: Optional[str] = None
    notes: Optional[str] = None
