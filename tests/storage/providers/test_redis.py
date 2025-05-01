"""
Tests for the Redis-based session store.
"""
import pytest
from unittest.mock import MagicMock

from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from tests.storage.test_base import create_test_session

# Skip if the real redis package is not available
pytest.importorskip("redis")

from a2a_session_manager.storage.providers.redis import RedisSessionStore


class TestRedisSessionStore:
    """Tests for the RedisSessionStore class."""

    # --------------------------------------------------------------------- #
    # Fixtures
    # --------------------------------------------------------------------- #
    @pytest.fixture
    def mock_redis(self):
        """
        A fully-featured MagicMock that behaves like a Redis client.
        Every Redis verb remains a MagicMock, so assertion helpers
        such as `assert_called_once`, `reset_mock`, `assert_not_called`
        keep working.
        """
        client = MagicMock()
        self.stored_data = {}

        # --- helpers implementing the fake in-memory “database” -----------
        def _get(key):
            return self.stored_data.get(key)

        def _set(key, value, ex=None):
            self.stored_data[key] = value
            return True

        def _setex(key, ttl, value):
            self.stored_data[key] = value
            return True

        def _delete(key):
            self.stored_data.pop(key, None)
            return 1

        def _expire(key, ttl):
            return 1 if key in self.stored_data else 0

        # --- keep each verb a MagicMock, wire behaviour via side_effect ---
        client.get = MagicMock(side_effect=_get)
        client.set = MagicMock(side_effect=_set)
        client.setex = MagicMock(side_effect=_setex)
        client.delete = MagicMock(side_effect=_delete)
        client.expire = MagicMock(side_effect=_expire)

        # Leave `keys` as a plain MagicMock so individual tests can
        # freely override `return_value` and still use call assertions.
        client.keys = MagicMock()

        return client

    @pytest.fixture
    def store(self, mock_redis):
        """A RedisSessionStore wired to the mocked Redis client."""
        return RedisSessionStore(
            redis_client=mock_redis,
            key_prefix="test:",
            expiration_seconds=None,
        )

    # --------------------------------------------------------------------- #
    # Tests
    # --------------------------------------------------------------------- #
    def test_save_and_get(self, store, mock_redis):
        """Saving and retrieving a session works end-to-end."""
        session = create_test_session()
        store.save(session)

        mock_redis.set.assert_called_once()

        retrieved = store.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        assert [e.message for e in retrieved.events] == [
            "Test message 1",
            "Test message 2",
        ]

    def test_get_nonexistent(self, store, mock_redis):
        """Requesting a missing session returns None."""
        mock_redis.get.return_value = None
        assert store.get("does-not-exist") is None

    def test_delete(self, store, mock_redis):
        """Deleting removes the session from Redis and the cache."""
        session = create_test_session()
        store.save(session)

        mock_redis.delete.reset_mock()
        store.delete(session.id)

        mock_redis.delete.assert_called_once()
        assert store.get(session.id) is None

    def test_list_sessions(self, store, mock_redis):
        """Listing all sessions (no extra prefix)."""
        mock_redis.keys.return_value = [f"test:{i}".encode() for i in range(3)]

        session_ids = store.list_sessions()

        mock_redis.keys.assert_called_once_with("test:*")
        assert session_ids == ["0", "1", "2"]

    def test_list_sessions_with_prefix(self, store, mock_redis):
        """Listing sessions with an additional filter prefix."""
        mock_redis.keys.return_value = [
            f"test:filtered_{i}".encode() for i in range(3)
        ]

        session_ids = store.list_sessions(prefix="filtered_")

        mock_redis.keys.assert_called_once_with("test:filtered_*")
        assert len(session_ids) == 3
        for i in range(3):
            assert f"filtered_{i}" in session_ids

    def test_update_session(self, store):
        """Saving the same ID twice updates the stored record."""
        session = create_test_session()
        store.save(session)

        session.events.append(
            SessionEvent(
                message="Test message 3",
                source=EventSource.USER,
                type=EventType.MESSAGE,
            )
        )
        store.save(session)

        retrieved = store.get(session.id)
        assert retrieved is not None
        assert len(retrieved.events) == 3
        assert retrieved.events[-1].message == "Test message 3"

    def test_expiration(self, mock_redis):
        """When expiration_seconds is set, `setex` is used instead of `set`."""
        expiry_store = RedisSessionStore(
            redis_client=mock_redis,
            key_prefix="test:",
            expiration_seconds=3600,
        )
        session = create_test_session()

        mock_redis.set.reset_mock()
        mock_redis.setex.reset_mock()

        expiry_store.save(session)

        mock_redis.setex.assert_called_once()
        mock_redis.set.assert_not_called()

    def test_set_expiration(self, store, mock_redis):
        """Manual expire call is forwarded to Redis."""
        session = create_test_session()
        store.save(session)

        mock_redis.expire.reset_mock()
        store.set_expiration(session.id, 7200)

        mock_redis.expire.assert_called_once()

    def test_auto_save_false(self, mock_redis):
        """When auto_save is False, objects stay cached until flush()."""
        store = RedisSessionStore(redis_client=mock_redis, auto_save=False)
        session = create_test_session()
        store.save(session)

        mock_redis.set.assert_not_called()

        # Retrieve comes from cache
        assert store.get(session.id).id == session.id

        mock_redis.set.reset_mock()
        store.flush()
        mock_redis.set.assert_called()
