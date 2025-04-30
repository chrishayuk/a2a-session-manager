# a2a_session_manager/models/session.py
"""
Session model for the A2A Session Manager.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Generic, TypeVar, Union
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator

# Import models that Session depends on
from a2a_session_manager.models.session_metadata import SessionMetadata
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.token_usage import TokenUsage, TokenSummary
# Import SessionRun and RunStatus directly to avoid circular import
from a2a_session_manager.models.session_run import SessionRun, RunStatus

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
    
    # Token tracking - new field
    token_summary: TokenSummary = Field(default_factory=TokenSummary)

    @model_validator(mode="after")
    def _sync_hierarchy(cls, model: Session) -> Session:
        """After creation, sync this session with its parent in the store."""
        if model.parent_id:
            # Import here to avoid circular import
            from a2a_session_manager.storage import SessionStoreProvider
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
    
    @property
    def total_tokens(self) -> int:
        """Return the total number of tokens used in this session."""
        return self.token_summary.total_tokens
    
    @property
    def total_cost(self) -> float:
        """Return the total estimated cost of this session."""
        return self.token_summary.total_estimated_cost_usd

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
        
        # Import here to avoid circular import
        from a2a_session_manager.storage import SessionStoreProvider
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
        
        # Import here to avoid circular import
        from a2a_session_manager.storage import SessionStoreProvider
        store = SessionStoreProvider.get_store()
        
        while stack:
            cid = stack.pop()
            child = store.get(cid)
            if child:
                result.append(child)
                stack.extend(child.child_ids)
        return result
    
    def add_event(self, event: SessionEvent[MessageT]) -> None:
        """
        Add an event to the session and update token tracking.
        
        Args:
            event: The event to add
        """
        # Add the event
        self.events.append(event)
        
        # Update token summary if this event has token usage
        if event.token_usage:
            self.token_summary.add_usage(event.token_usage)
    
    def get_token_usage_by_source(self) -> Dict[str, TokenSummary]:
        """
        Get token usage statistics grouped by event source.
        
        Returns:
            A dictionary mapping event sources to token summaries
        """
        result: Dict[str, TokenSummary] = {}
        
        for event in self.events:
            if not event.token_usage:
                continue
                
            source = event.source.value
            if source not in result:
                result[source] = TokenSummary()
                
            result[source].add_usage(event.token_usage)
            
        return result
    
    def get_token_usage_by_run(self) -> Dict[str, TokenSummary]:
        """
        Get token usage statistics grouped by run.
        
        Returns:
            A dictionary mapping run IDs to token summaries
        """
        result: Dict[str, TokenSummary] = {}
        
        # Add an entry for events without a run
        result["no_run"] = TokenSummary()
        
        for event in self.events:
            if not event.token_usage:
                continue
                
            run_id = event.task_id or "no_run"
            if run_id not in result:
                result[run_id] = TokenSummary()
                
            result[run_id].add_usage(event.token_usage)
            
        return result
    
    def count_message_tokens(
        self, 
        message: Union[str, Dict[str, Any]], 
        model: str = "gpt-3.5-turbo"
    ) -> int:
        """
        Count tokens in a message.
        
        Args:
            message: The message to count tokens for (string or dict)
            model: The model to use for counting
            
        Returns:
            The number of tokens in the message
        """
        # If message is already a string, count directly
        if isinstance(message, str):
            return TokenUsage.count_tokens(message, model)
        
        # If it's a dict (like OpenAI messages), extract content
        if isinstance(message, dict) and "content" in message:
            return TokenUsage.count_tokens(message["content"], model)
            
        # If it's some other object, convert to string and count
        return TokenUsage.count_tokens(str(message), model)