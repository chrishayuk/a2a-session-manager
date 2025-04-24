# a2a_session_manager/session_run.py
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict


class RunStatus(str, Enum):
    """Status of a session run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionRun(BaseModel):
    """A single execution or "run" within a session."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    status: RunStatus = RunStatus.PENDING
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def mark_running(self) -> None:
        """Mark the run as started/running."""
        self.status = RunStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """Mark the run as completed successfully."""
        self.status = RunStatus.COMPLETED
        self.ended_at = datetime.now(timezone.utc)

    def mark_failed(self) -> None:
        """Mark the run as failed."""
        self.status = RunStatus.FAILED
        self.ended_at = datetime.now(timezone.utc)

    def mark_cancelled(self) -> None:
        """Mark the run as cancelled."""
        self.status = RunStatus.CANCELLED
        self.ended_at = datetime.now(timezone.utc)