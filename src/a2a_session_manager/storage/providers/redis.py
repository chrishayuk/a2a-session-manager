# src/a2a_session_manager/storage/providers/redis.py
"""
Redis-based session storage implementation.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union, cast

# Note: redis is an optional dependency, so we import it conditionally
try:
    import redis
    from redis import Redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    # Define a dummy class for type checking
    class Redis:  # type: ignore
        pass

from a2a_session_manager.models.session import Session
from a2a_session_manager.storage.base import SessionStoreInterface
from a2a_session_manager.exceptions import SessionManagerError

# Type variable for serializable models
T = TypeVar('T', bound='Session')

# Setup logging
logger = logging.getLogger(__name__)


class RedisStorageError(SessionManagerError):
    """Raised when Redis storage operations fail."""
    pass


class RedisSessionStore(SessionStoreInterface, Generic[T]):
    """
    A session store that persists sessions to Redis.
    
    This implementation stores sessions as JSON documents in Redis,
    with configurable key prefixes and expiration.
    """
    
    def __init__(self, 
                redis_client: Redis, 
                key_prefix: str = "session:",
                expiration_seconds: Optional[int] = None,
                session_class: Type[T] = Session,
                auto_save: bool = True):
        """
        Initialize the Redis session store.
        
        Args:
            redis_client: Pre-configured Redis client
            key_prefix: Prefix for Redis keys
            expiration_seconds: Optional TTL for sessions
            session_class: The Session class to use for deserialization
            auto_save: Whether to automatically save on each update
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis package is not installed. "
                "Install it with 'pip install redis'."
            )
        
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.expiration_seconds = expiration_seconds
        self.session_class = session_class
        self.auto_save = auto_save
        # In-memory cache for better performance
        self._cache: Dict[str, T] = {}
    
    def _get_key(self, session_id: str) -> str:
        """Get the Redis key for a session ID."""
        return f"{self.key_prefix}{session_id}"
    
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
        
        # If not in cache, try to load from Redis
        key = self._get_key(session_id)
        try:
            data = self.redis.get(key)
            if not data:
                return None
            
            session_dict = json.loads(data)
            session = cast(T, self.session_class.model_validate(session_dict))
            
            # Update cache
            self._cache[session_id] = session
            return session
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load session {session_id} from Redis: {e}")
            return None

    def save(self, session: T) -> None:
        """Save a session to the store."""
        session_id = session.id
        # Update cache
        self._cache[session_id] = session
        
        if self.auto_save:
            self._save_to_redis(session)
    
    def _save_to_redis(self, session: T) -> None:
        """Save a session to Redis."""
        session_id = session.id
        key = self._get_key(session_id)
        
        try:
            # Convert session to JSON
            session_dict = session.model_dump()
            data = json.dumps(session_dict, default=self._json_default)
            
            # Save to Redis with optional expiration
            if self.expiration_seconds:
                self.redis.setex(key, self.expiration_seconds, data)
            else:
                self.redis.set(key, data)
        except (RedisError, TypeError) as e:
            logger.error(f"Failed to save session {session_id} to Redis: {e}")
            raise RedisStorageError(f"Failed to save session {session_id}: {str(e)}")

    def delete(self, session_id: str) -> None:
        """Delete a session by its ID."""
        # Remove from cache
        if session_id in self._cache:
            del self._cache[session_id]
        
        # Remove from Redis
        key = self._get_key(session_id)
        try:
            self.redis.delete(key)
        except RedisError as e:
            logger.error(f"Failed to delete session {session_id} from Redis: {e}")
            raise RedisStorageError(f"Failed to delete session {session_id}: {str(e)}")
    
    def list_sessions(self, prefix: str = "") -> List[str]:
        """List all session IDs, optionally filtered by prefix."""
        search_pattern = f"{self.key_prefix}{prefix}*"
        try:
            # Get all keys matching the pattern
            keys = self.redis.keys(search_pattern)
            # Extract session IDs by removing the prefix
            session_ids = [
                key.decode('utf-8').replace(self.key_prefix, '') 
                for key in keys
            ]
            return session_ids
        except RedisError as e:
            logger.error(f"Failed to list sessions from Redis: {e}")
            raise RedisStorageError(f"Failed to list sessions: {str(e)}")
    
    def flush(self) -> None:
        """Force save all cached sessions to Redis."""
        for session in self._cache.values():
            try:
                self._save_to_redis(session)
            except RedisStorageError:
                # Already logged in _save_to_redis
                pass
    
    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
    
    def set_expiration(self, session_id: str, seconds: int) -> None:
        """Set or update expiration for a session."""
        key = self._get_key(session_id)
        try:
            self.redis.expire(key, seconds)
        except RedisError as e:
            logger.error(f"Failed to set expiration for session {session_id}: {e}")
            raise RedisStorageError(f"Failed to set expiration for session {session_id}: {str(e)}")


def create_redis_session_store(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    key_prefix: str = "session:",
    expiration_seconds: Optional[int] = None,
    session_class: Type[T] = Session,
    auto_save: bool = True,
    **redis_kwargs: Any
) -> RedisSessionStore[T]:
    """
    Create a Redis-based session store.
    
    Args:
        host: Redis host
        port: Redis port
        db: Redis database number
        password: Optional Redis password
        key_prefix: Prefix for Redis keys
        expiration_seconds: Optional TTL for sessions
        session_class: The Session class to use
        auto_save: Whether to automatically save on each update
        **redis_kwargs: Additional arguments for Redis client
        
    Returns:
        A configured RedisSessionStore
    """
    if not REDIS_AVAILABLE:
        raise ImportError(
            "Redis package is not installed. "
            "Install it with 'pip install redis'."
        )
    
    redis_client = redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        **redis_kwargs
    )
    
    return RedisSessionStore(
        redis_client=redis_client,
        key_prefix=key_prefix,
        expiration_seconds=expiration_seconds,
        session_class=session_class,
        auto_save=auto_save
    )