# a2a_session_manager/models/session_event.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Generic, Optional, TypeVar
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

# session manager
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType

# Generic type for event message content
MessageT = TypeVar('MessageT')

class SessionEvent(BaseModel, Generic[MessageT]):
    """An event in a session."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: Optional[MessageT] = None
    task_id: Optional[str] = None
    type: EventType = EventType.MESSAGE
    source: EventSource = EventSource.LLM
    metadata: Dict[str, Any] = Field(default_factory=dict)
