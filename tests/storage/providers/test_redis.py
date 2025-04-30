# tests/storage/providers/test_redis.py
"""
Tests for the Redis-based session store.
"""
import pytest
import time
from unittest.mock import MagicMock, patch

from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from tests.storage.test_base import create_test_session

# Skip the entire module if redis is not installed
pytest.importorskip("redis")

# Now import the Redis store
from a2a_session_manager.storage.providers.redis import RedisSessionStore


class TestRedisSessionStore:
    """Tests for the RedisSessionStore class."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client for testing."""
        client = MagicMock()
        
        # Set up in-memory storage for the mock
        self.stored_data = {}
        
        # Mock Redis get/set/delete methods
        def mock_get(key):
            return self.stored_data.get(key)
            
        def mock_set(key, value, ex=None):
            self.stored_data[key] = value
            return True
            
        def mock_setex(key, time, value):
            self.stored_data[key] = value
            return True
            
        def mock_delete(key):
            if key in self.stored_data:
                del self.stored_data[key]
            return 1
            
        def mock_keys(pattern):
            # Convert pattern with * wildcard to Python startswith
            if pattern.endswith('*'):
                prefix = pattern[:-1]
                return [k.encode('utf-8') for k in self.stored_data.keys() 
                        if k.startswith(prefix)]
            return [k.encode('utf-8') for k in self.stored_data.keys() 
                    if k == pattern]
            
        def mock_expire(key, time):
            # Just check if key exists
            return 1 if key in self.stored_data else 0
        
        # Assign the mock methods
        client.get = mock_get
        client.set = mock_set
        client.setex = mock_setex
        client.delete = mock_delete
        client.keys = mock_keys
        client.expire = mock_expire
        
        return client
    
    @pytest.fixture
    def store(self, mock_redis):
        """Create a Redis store with the mock Redis client."""
        return RedisSessionStore(
            redis_client=mock_redis,
            key_prefix="test:",
            expiration_seconds=None
        )
    
    def test_save_and_get(self, store, mock_redis):
        """Test saving and retrieving a session."""
        # Create a session
        session = create_test_session()
        
        # Save the session
        store.save(session)
        
        # Redis set should have been called with the key and serialized data
        mock_redis.set.assert_called_once()
        
        # Retrieve the session
        retrieved = store.get(session.id)
        
        # Check that we got the expected data back
        assert retrieved is not None
        assert retrieved.id == session.id
        assert len(retrieved.events) == 2
        assert retrieved.events[0].message == "Test message 1"
        assert retrieved.events[1].message == "Test message 2"
    
    def test_get_nonexistent(self, store, mock_redis):
        """Test retrieving a non-existent session."""
        # Mock Redis to return None for get
        mock_redis.get.return_value = None
        
        # Try to get a session that doesn't exist
        nonexistent = store.get("does-not-exist")
        
        # Should return None
        assert nonexistent is None
    
    def test_delete(self, store, mock_redis):
        """Test deleting a session."""
        # Create and save a session
        session = create_test_session()
        store.save(session)
        
        # Clear the mock calls
        mock_redis.delete.reset_mock()
        
        # Delete the session
        store.delete(session.id)
        
        # Redis delete should have been called
        mock_redis.delete.assert_called_once()
        
        # Session should no longer be retrievable
        retrieved = store.get(session.id)
        assert retrieved is None
    
    def test_list_sessions(self, store, mock_redis):
        """Test listing sessions."""
        # Set up mock keys to return
        keys = [f"test:{i}".encode('utf-8') for i in range(3)]
        mock_redis.keys.return_value = keys
        
        # List all sessions
        session_ids = store.list_sessions()
        
        # Redis keys should have been called with the pattern
        mock_redis.keys.assert_called_once_with("test:*")
        
        # Should return the IDs without the prefix
        assert len(session_ids) == 3
        assert session_ids == ["0", "1", "2"]
    
    def test_list_sessions_with_prefix(self, store, mock_redis):
        """Test listing sessions with a prefix."""
        # Set up mock keys to return
        keys = [f"test:filtered_{i}".encode('utf-8') for i in range(3)]
        mock_redis.keys.return_value = keys
        
        # List sessions with prefix
        session_ids = store.list_sessions(prefix="filtered_")
        
        # Redis keys should have been called with the pattern
        mock_redis.keys.assert_called_once_with("test:filtered_*")
        
        # Should return the IDs without the prefix
        assert len(session_ids) == 3
        for i in range(3):
            assert f"filtered_{i}" in session_ids
    
    def test_update_session(self, store):
        """Test updating an existing session."""
        # Create and save a session
        session = create_test_session()
        store.save(session)
        
        # Modify the session
        session.events.append(
            SessionEvent(
                message="Test message 3",
                source=EventSource.USER,
                type=EventType.MESSAGE
            )
        )
        
        # Save again
        store.save(session)
        
        # Retrieve and check
        retrieved = store.get(session.id)
        assert retrieved is not None
        assert len(retrieved.events) == 3
        assert retrieved.events[2].message == "Test message 3"
    
    def test_expiration(self, store, mock_redis):
        """Test setting expiration on sessions."""
        # Create a store with expiration
        expiry_store = RedisSessionStore(
            redis_client=mock_redis,
            key_prefix="test:",
            expiration_seconds=3600  # 1 hour
        )
        
        # Create and save a session
        session = create_test_session()
        
        # Reset mock
        mock_redis.set.reset_mock()
        mock_redis.setex.reset_mock()
        
        # Save the session
        expiry_store.save(session)
        
        # Redis setex should be called instead of set
        mock_redis.setex.assert_called_once()
        mock_redis.set.assert_not_called()
    
    def test_set_expiration(self, store, mock_redis):
        """Test manually setting expiration on a session."""
        # Create and save a session
        session = create_test_session()
        store.save(session)
        
        # Reset mock
        mock_redis.expire.reset_mock()
        
        # Set expiration
        store.set_expiration(session.id, 7200)  # 2 hours
        
        # Redis expire should be called
        mock_redis.expire.assert_called_once()
    
    def test_auto_save_false(self, mock_redis):
        """Test store with auto_save=False."""
        # Create store with auto_save disabled
        store = RedisSessionStore(mock_redis, auto_save=False)
        
        # Create and save a session
        session = create_test_session()
        store.save(session)
        
        # Redis set should not have been called
        mock_redis.set.assert_not_called()
        
        # But we should still be able to get it from the store (from cache)
        retrieved = store.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        
        # Reset the mock
        mock_redis.set.reset_mock()
        
        # Now flush the store
        store.flush()
        
        # Redis set should have been called
        mock_redis.set.assert_called()