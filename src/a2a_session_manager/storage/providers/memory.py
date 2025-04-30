# a2a_session_manager/storage/providers/memory.py
""
"""
In-memory session storage implementation.
"""
from typing import Any, Dict, List, Optional

from a2a_session_manager.storage.base import SessionStoreInterface


class InMemorySessionStore(SessionStoreInterface):
    """A simple in-memory store for Session objects.
    
    This implementation stores sessions in a dictionary and is not
    persistent across application restarts.
    """
    
    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._data: Dict[str, Any] = {}

    def get(self, session_id: str) -> Optional[Any]:
        """Retrieve a session by its ID, or None if not found."""
        return self._data.get(session_id)

    def save(self, session: Any) -> None:
        """Save or update a session object in the store."""
        self._data[session.id] = session
    
    def delete(self, session_id: str) -> None:
        """Delete a session by its ID."""
        if session_id in self._data:
            del self._data[session_id]
    
    def list_sessions(self, prefix: str = "") -> List[str]:
        """List all session IDs, optionally filtered by prefix."""
        if not prefix:
            return list(self._data.keys())
        return [sid for sid in self._data.keys() if sid.startswith(prefix)]
    
    def clear(self) -> None:
        """Clear all sessions from the store."""
        self._data.clear()