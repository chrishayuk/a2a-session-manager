# a2a_session_manager/models/project.py
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from typing import Any, Dict, List, Optional
from pydantic import Field

# session manager
from a2a_session_manager.models.access_control import AccessControlled
from a2a_session_manager.models.access_levels import AccessLevel


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Project(AccessControlled):
    """A project that contains sessions and organizes related work."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    tags: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = None  # for nested projects
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
