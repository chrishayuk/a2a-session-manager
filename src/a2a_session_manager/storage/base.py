# a2a_session_manager/storage/base.py
"""
Base interfaces and providers for session storage.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar

T = TypeVar('T')

class SessionStoreInterface(ABC):
    """Interface for pluggable session stores."""
    
    @abstractmethod
    def get(self, session_id: str) -> Optional[Any]:
        """Retrieve a session by its ID, or None if not found."""
        ...

    @abstractmethod
    def save(self, session: Any) -> None:
        """Save or update a session object in the store."""
        ...
    
    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete a session by its ID."""
        ...
    
    @abstractmethod
    def list_sessions(self, prefix: str = "") -> List[str]:
        """List all session IDs, optionally filtered by prefix."""
        ...


class SessionStoreProvider:
    """Provider for a globally-shared (but overrideable) session store."""
    _store: Optional[SessionStoreInterface] = None

    @classmethod
    def get_store(cls) -> SessionStoreInterface:
        """Get the currently configured session store."""
        if cls._store is None:
            # Defer import to avoid circular imports
            # Use a local import to avoid circular dependency
            from a2a_session_manager.storage.providers.memory import InMemorySessionStore
            cls._store = InMemorySessionStore()
        return cls._store

    @classmethod
    def set_store(cls, store: SessionStoreInterface) -> None:
        """Set a new session store implementation."""
        cls._store = store