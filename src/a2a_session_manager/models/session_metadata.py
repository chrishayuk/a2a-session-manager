# a2a_session_manager/models/session_metadata.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SessionMetadata(BaseModel):
    """Core metadata associated with a session."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Free-form properties for session-level identifiers and custom data
    properties: Dict[str, Any] = Field(default_factory=dict)
    
    def set_property(self, key: str, value: Any) -> None:
        """Add or update a custom metadata property."""
        self.properties[key] = value

    def get_property(self, key: str) -> Any:
        """Retrieve a metadata property by key."""
        return self.properties.get(key)

