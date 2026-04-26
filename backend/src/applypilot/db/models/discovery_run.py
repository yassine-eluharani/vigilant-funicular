from typing import Optional
from sqlmodel import SQLModel, Field


class DiscoveryRun(SQLModel, table=True):
    __tablename__ = "discovery_runs"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    query: str
    location: str
    boards_json: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str = Field(default="pending")
    jobs_found: int = Field(default=0)
