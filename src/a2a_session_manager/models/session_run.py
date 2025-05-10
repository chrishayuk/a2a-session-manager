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

    @classmethod
    async def create(cls, metadata: Optional[Dict[str, Any]] = None) -> SessionRun:
        """Create a new session run asynchronously."""
        return cls(
            status=RunStatus.PENDING,
            metadata=metadata or {}
        )

    async def mark_running(self) -> None:
        """Mark the run as started/running asynchronously."""
        self.status = RunStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    async def mark_completed(self) -> None:
        """Mark the run as completed successfully asynchronously."""
        self.status = RunStatus.COMPLETED
        self.ended_at = datetime.now(timezone.utc)

    async def mark_failed(self) -> None:
        """Mark the run as failed asynchronously."""
        self.status = RunStatus.FAILED
        self.ended_at = datetime.now(timezone.utc)

    async def mark_cancelled(self) -> None:
        """Mark the run as cancelled asynchronously."""
        self.status = RunStatus.CANCELLED
        self.ended_at = datetime.now(timezone.utc)
        
    async def update_metadata(self, key: str, value: Any) -> None:
        """Update a metadata value asynchronously."""
        self.metadata[key] = value
        
    async def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value asynchronously."""
        return self.metadata.get(key, default)
        
    async def get_duration(self) -> Optional[float]:
        """Get the duration of the run in seconds asynchronously."""
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()