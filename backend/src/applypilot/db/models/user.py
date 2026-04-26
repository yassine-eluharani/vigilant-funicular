from typing import Optional
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    __tablename__ = "users"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    clerk_id: Optional[str] = Field(default=None, index=True, unique=True)
    email: str = Field(unique=True)
    full_name: str
    created_at: str
    last_login: Optional[str] = None
    tier: str = Field(default="free")
    tailors_used: int = Field(default=0)
    covers_used: int = Field(default=0)
    usage_reset_at: Optional[str] = None
    searches_json: Optional[str] = None
    profile_json: Optional[str] = None
    resume_text: Optional[str] = None
    email_notifications: int = Field(default=0)
