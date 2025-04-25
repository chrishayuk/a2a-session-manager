# a2a_session_manager/models/session.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Generic, TypeVar
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator

# session
from a2a_session_manager.models.session_metadata import SessionMetadata
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.session_run import SessionRun, RunStatus
from a2a_session_manager.storage import SessionStoreProvider

MessageT = TypeVar('MessageT')

class Session(BaseModel, Generic[MessageT]):
    """A standalone conversation session with hierarchical support."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    metadata: SessionMetadata = Field(default_factory=SessionMetadata)

    parent_id: Optional[str] = None
    child_ids: List[str] = Field(default_factory=list)

    task_ids: List[str] = Field(default_factory=list)
    runs: List[SessionRun] = Field(default_factory=list)
    events: List[SessionEvent[MessageT]] = Field(default_factory=list)
    state: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sync_hierarchy(cls, model: Session) -> Session:
        """After creation, sync this session with its parent in the store."""
        if model.parent_id:
            store = SessionStoreProvider.get_store()
            parent = store.get(model.parent_id)
            if parent and model.id not in parent.child_ids:
                parent.child_ids.append(model.id)
                store.save(parent)
        return model

    @property
    def last_update_time(self) -> datetime:
        """Return timestamp of most recent event, or session creation."""
        if not self.events:
            return self.metadata.created_at
        return max(evt.timestamp for evt in self.events)

    @property
    def active_run(self) -> Optional[SessionRun]:
        """Return the currently running SessionRun, if any."""
        for run in reversed(self.runs):
            if run.status == RunStatus.RUNNING:
                return run
        return None

    def add_child(self, child_id: str) -> None:
        """Add a child session ID."""
        if child_id not in self.child_ids:
            self.child_ids.append(child_id)

    def remove_child(self, child_id: str) -> None:
        """Remove a child session ID."""
        if child_id in self.child_ids:
            self.child_ids.remove(child_id)

    def ancestors(self) -> List[Session]:
        """Fetch ancestor sessions from store."""
        result: List[Session] = []
        current = self.parent_id
        store = SessionStoreProvider.get_store()
        while current:
            parent = store.get(current)
            if not parent:
                break
            result.append(parent)
            current = parent.parent_id
        return result

    def descendants(self) -> List[Session]:
        """Fetch all descendant sessions from store in DFS order."""
        result: List[Session] = []
        stack = list(self.child_ids)
        store = SessionStoreProvider.get_store()
        while stack:
            cid = stack.pop()
            child = store.get(cid)
            if child:
                result.append(child)
                stack.extend(child.child_ids)
        return result
