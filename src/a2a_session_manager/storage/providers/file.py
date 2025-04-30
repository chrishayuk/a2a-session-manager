# a2a_session_manager/storage/providers/file.py
"""
File-based session storage implementation.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union, Generic

# session manager imports
from a2a_session_manager.models.session import Session
from a2a_session_manager.storage.base import SessionStoreInterface
from a2a_session_manager.exceptions import SessionManagerError

# Type variable for serializable models
T = TypeVar('T', bound='Session')

# Setup logging
logger = logging.getLogger(__name__)


class FileStorageError(SessionManagerError):
    """Raised when file storage operations fail."""
    pass


class SessionSerializer(Generic[T]):
    """Handles serialization and deserialization of session objects."""

    @classmethod
    def to_dict(cls, obj: T) -> Dict[str, Any]:
        """Convert a session object to a dictionary for serialization."""
        # Use Pydantic's model_dump method for serialization
        return obj.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any], model_class: Type[T]) -> T:
        """Convert a dictionary to a session object."""
        try:
            # Use Pydantic's model validation for deserialization
            return model_class.model_validate(data)
        except Exception as e:
            raise FileStorageError(f"Failed to deserialize {model_class.__name__}: {str(e)}")


class FileSessionStore(SessionStoreInterface, Generic[T]):
    """
    A session store that persists sessions to JSON files.
    
    This implementation stores each session as a separate JSON file in
    the specified directory.
    """
    
    def __init__(self, 
                directory: Union[str, Path], 
                session_class: Type[T] = Session,
                auto_save: bool = True):
        """
        Initialize the file session store.
        
        Args:
            directory: Directory where session files will be stored
            session_class: The Session class to use for deserialization
            auto_save: Whether to automatically save on each update
        """
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_class = session_class
        self.auto_save = auto_save
        # In-memory cache for better performance
        self._cache: Dict[str, T] = {}
    
    def _get_path(self, session_id: str) -> Path:
        """Get the file path for a session ID."""
        return self.directory / f"{session_id}.json"
    
    def _json_default(self, obj: Any) -> Any:
        """Handle non-serializable objects in JSON serialization."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def get(self, session_id: str) -> Optional[T]:
        """Retrieve a session by its ID."""
        # Check cache first
        if session_id in self._cache:
            return self._cache[session_id]
        
        # If not in cache, try to load from file
        file_path = self._get_path(session_id)
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            session = SessionSerializer.from_dict(data, self.session_class)
            # Update cache
            self._cache[session_id] = session
            return session
        except (FileStorageError, json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    def save(self, session: T) -> None:
        """Save a session to the store."""
        session_id = session.id
        # Update cache
        self._cache[session_id] = session
        
        if self.auto_save:
            self._save_to_file(session)
    
    def _save_to_file(self, session: T) -> None:
        """Save a session to its JSON file."""
        session_id = session.id
        file_path = self._get_path(session_id)
        
        try:
            data = SessionSerializer.to_dict(session)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, default=self._json_default, indent=2)
        except (FileStorageError, IOError, TypeError) as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            raise FileStorageError(f"Failed to save session {session_id}: {str(e)}")

    def delete(self, session_id: str) -> None:
        """Delete a session by its ID."""
        # Remove from cache
        if session_id in self._cache:
            del self._cache[session_id]
        
        # Remove file if it exists
        file_path = self._get_path(session_id)
        if file_path.exists():
            try:
                file_path.unlink()
            except IOError as e:
                logger.error(f"Failed to delete session file {session_id}: {e}")
                raise FileStorageError(f"Failed to delete session {session_id}: {str(e)}")
    
    def list_sessions(self, prefix: str = "") -> List[str]:
        """List all session IDs, optionally filtered by prefix."""
        try:
            # Get all JSON files in the directory
            files = self.directory.glob("*.json")
            # Extract the session IDs (filenames without extension)
            session_ids = [f.stem for f in files]
            # Filter by prefix if provided
            if prefix:
                session_ids = [sid for sid in session_ids if sid.startswith(prefix)]
            return session_ids
        except IOError as e:
            logger.error(f"Failed to list sessions: {e}")
            raise FileStorageError(f"Failed to list sessions: {str(e)}")
    
    def flush(self) -> None:
        """Force save all cached sessions to disk."""
        for session in self._cache.values():
            try:
                self._save_to_file(session)
            except FileStorageError:
                # Already logged in _save_to_file
                pass
    
    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()


def create_file_session_store(directory: Union[str, Path], 
                             session_class: Type[T] = Session,
                             auto_save: bool = True) -> FileSessionStore[T]:
    """
    Create a file-based session store.
    
    Args:
        directory: Directory where session files will be stored
        session_class: The Session class to use
        auto_save: Whether to automatically save on each update
        
    Returns:
        A configured FileSessionStore
    """
    return FileSessionStore(directory, session_class, auto_save)