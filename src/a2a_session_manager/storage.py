# a2a_session_manager/storage.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

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


class InMemorySessionStore(SessionStoreInterface):
    """A simple in-memory store for Session objects."""
    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def get(self, session_id: str) -> Optional[Any]:
        return self._data.get(session_id)

    def save(self, session: Any) -> None:
        self._data[session.id] = session


class SessionStoreProvider:
    """Provider for a globally-shared (but overrideable) session store."""
    _store: SessionStoreInterface = InMemorySessionStore()

    @classmethod
    def get_store(cls) -> SessionStoreInterface:
        return cls._store

    @classmethod
    def set_store(cls, store: SessionStoreInterface) -> None:
        cls._store = store
