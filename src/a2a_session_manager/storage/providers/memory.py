# a2a_session_manager/storage/providers/memory.py
"""
Async in-memory session storage implementation.
"""
from typing import Any, Dict, List, Optional

from a2a_session_manager.storage.base import SessionStoreInterface


class InMemorySessionStore(SessionStoreInterface):
    """A simple in-memory store for Session objects with async interface.
    
    This implementation stores sessions in a dictionary and is not
    persistent across application restarts.
    """
    
    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._data: Dict[str, Any] = {}

    async def get(self, session_id: str) -> Optional[Any]:
        """Async: Retrieve a session by its ID, or None if not found."""
        return self._data.get(session_id)

    async def save(self, session: Any) -> None:
        """Async: Save or update a session object in the store."""
        self._data[session.id] = session
    
    async def delete(self, session_id: str) -> None:
        """Async: Delete a session by its ID."""
        if session_id in self._data:
            del self._data[session_id]
    
    async def list_sessions(self, prefix: str = "") -> List[str]:
        """Async: List all session IDs, optionally filtered by prefix."""
        if not prefix:
            return list(self._data.keys())
        return [sid for sid in self._data.keys() if sid.startswith(prefix)]
    
    async def clear(self) -> None:
        """Async: Clear all sessions from the store."""
        self._data.clear()