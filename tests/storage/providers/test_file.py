# tests/storage/providers/test_file.py
"""
Tests for the file-based session store.
"""
import json
import os
import pytest
import shutil
import tempfile
from pathlib import Path

from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.storage.providers.file import FileSessionStore
from tests.storage.test_base import create_test_session


class TestFileSessionStore:
    """Tests for the FileSessionStore class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        # Create a temp directory
        temp_dir = tempfile.mkdtemp()
        
        # Return it for the test to use
        yield temp_dir
        
        # Clean up after the test
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def store(self, temp_dir):
        """Create a file-based store using the temp directory."""
        return FileSessionStore(temp_dir)
    
    def test_save_and_get(self, store, temp_dir):
        """Test saving and retrieving a session."""
        # Create a session
        session = create_test_session()
        
        # Save the session
        store.save(session)
        
        # Check that the file was created
        file_path = Path(temp_dir) / f"{session.id}.json"
        assert file_path.exists()
        
        # Retrieve the session
        retrieved = store.get(session.id)
        
        # Check that we got the expected data back
        assert retrieved is not None
        assert retrieved.id == session.id
        assert len(retrieved.events) == 2
        assert retrieved.events[0].message == "Test message 1"
        assert retrieved.events[1].message == "Test message 2"
    
    def test_get_nonexistent(self, store):
        """Test retrieving a non-existent session."""
        # Try to get a session that doesn't exist
        nonexistent = store.get("does-not-exist")
        
        # Should return None
        assert nonexistent is None
    
    def test_delete(self, store, temp_dir):
        """Test deleting a session."""
        # Create and save a session
        session = create_test_session()
        store.save(session)
        
        # Check it's there
        file_path = Path(temp_dir) / f"{session.id}.json"
        assert file_path.exists()
        
        # Delete the session
        store.delete(session.id)
        
        # Check it's gone from both the store and filesystem
        assert store.get(session.id) is None
        assert not file_path.exists()
    
    def test_list_sessions(self, store, temp_dir):
        """Test listing sessions."""
        # Create and save multiple sessions
        sessions = [create_test_session() for _ in range(3)]
        for session in sessions:
            store.save(session)
        
        # List all sessions
        session_ids = store.list_sessions()
        
        # Check we got all the sessions
        assert len(session_ids) == 3
        for session in sessions:
            assert session.id in session_ids
    
    def test_list_sessions_with_prefix(self, store):
        """Test listing sessions with a prefix filter."""
        # Create and save sessions with different prefixes
        prefixed_sessions = []
        for i in range(3):
            session = create_test_session()
            session.id = f"test_{i}"
            store.save(session)
            prefixed_sessions.append(session)
        
        # Create some other sessions
        for i in range(2):
            session = create_test_session()
            session.id = f"other_{i}"
            store.save(session)
        
        # List sessions with the "test_" prefix
        session_ids = store.list_sessions(prefix="test_")
        
        # Check we got only the test sessions
        assert len(session_ids) == 3
        for session in prefixed_sessions:
            assert session.id in session_ids
    
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
    
    def test_file_content(self, store, temp_dir):
        """Test the structure of the saved JSON file."""
        # Create and save a session
        session = create_test_session()
        store.save(session)
        
        # Read the file directly
        file_path = Path(temp_dir) / f"{session.id}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check the structure
        assert data["id"] == session.id
        assert len(data["events"]) == 2
        assert data["events"][0]["message"] == "Test message 1"
        assert data["events"][1]["message"] == "Test message 2"
    
    def test_auto_save_false(self, temp_dir):
        """Test store with auto_save=False."""
        # Create store with auto_save disabled
        store = FileSessionStore(temp_dir, auto_save=False)
        
        # Create and save a session
        session = create_test_session()
        store.save(session)
        
        # The file should not exist yet
        file_path = Path(temp_dir) / f"{session.id}.json"
        assert not file_path.exists()
        
        # But we should still be able to get it from the store (from cache)
        retrieved = store.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        
        # Now flush the store
        store.flush()
        
        # The file should now exist
        assert file_path.exists()
    
    def test_persistence_across_stores(self, temp_dir):
        """Test that sessions persist between different store instances."""
        # Create a store and save a session
        store1 = FileSessionStore(temp_dir)
        session = create_test_session()
        store1.save(session)
        
        # Create a new store instance pointing to the same directory
        store2 = FileSessionStore(temp_dir)
        
        # We should be able to retrieve the session
        retrieved = store2.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        assert len(retrieved.events) == 2
    
    def test_corrupted_file(self, store, temp_dir):
        """Test handling of corrupted JSON files."""
        # Create a corrupted file
        session_id = "corrupted"
        file_path = Path(temp_dir) / f"{session_id}.json"
        with open(file_path, 'w') as f:
            f.write("{not valid json")
        
        # Trying to get the session should return None
        assert store.get(session_id) is None