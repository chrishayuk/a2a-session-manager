# tests/test_session.py
import pytest
import time
from uuid import UUID
from datetime import datetime, timezone

# session
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_metadata import SessionMetadata
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.session_run import SessionRun, RunStatus
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider

MessageT = str  # simple alias for tests

@pytest.fixture(autouse=True)
def in_memory_store():
    """Reset and register an in-memory store for each test."""
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    return store


def test_default_fields_and_metadata():
    sess = Session[MessageT]()
    # id is a valid UUID
    assert isinstance(sess.id, str)
    UUID(sess.id)
    # metadata is default SessionMetadata
    assert isinstance(sess.metadata, SessionMetadata)
    # no children, runs, events, or state
    assert sess.child_ids == []
    assert sess.runs == []
    assert sess.events == []
    assert sess.state == {}


def test_last_update_time_without_events():
    sess = Session[MessageT]()
    assert sess.last_update_time == sess.metadata.created_at


def test_last_update_time_with_events():
    sess = Session[MessageT]()
    e1 = SessionEvent(message="m1")
    time.sleep(0.001)
    e2 = SessionEvent(message="m2")
    sess.events = [e1, e2]
    assert sess.last_update_time == max(e1.timestamp, e2.timestamp)


def test_active_run_selection():
    sess = Session[MessageT]()
    r1 = SessionRun(status=RunStatus.COMPLETED)
    r2 = SessionRun(status=RunStatus.RUNNING)
    r3 = SessionRun(status=RunStatus.COMPLETED)
    sess.runs = [r1, r2, r3]
    assert sess.active_run is r2
    # without running
    sess.runs = [r1, r3]
    assert sess.active_run is None


def test_add_and_remove_child():
    sess = Session[MessageT]()
    sess.add_child('c1')
    assert sess.child_ids == ['c1']
    # duplicate
    sess.add_child('c1')
    assert sess.child_ids == ['c1']
    sess.remove_child('c1')
    assert sess.child_ids == []


def test_hierarchy_sync_and_ancestors(in_memory_store):
    # create parent and save
    parent = Session[MessageT]()
    in_memory_store.save(parent)
    # create child with parent_id
    child = Session[MessageT](__pydantic_initialised__=True, parent_id=parent.id)
    # model_validator should sync
    assert child.id in parent.child_ids
    # ancestors
    anc = child.ancestors()
    assert [s.id for s in anc] == [parent.id]


def test_descendants(in_memory_store):
    # build root->child->grand
    root = Session[MessageT]()
    child = Session[MessageT]()
    grand = Session[MessageT]()
    in_memory_store.save(root)
    in_memory_store.save(child)
    in_memory_store.save(grand)
    root.child_ids = [child.id]
    child.child_ids = [grand.id]
    desc = root.descendants()
    ids = [s.id for s in desc]
    assert child.id in ids and grand.id in ids
    # child descendants
    assert [s.id for s in child.descendants()] == [grand.id]


def test_sync_nonexistent_parent_does_not_error():
    sess = Session[MessageT](parent_id='nope')
    assert sess.parent_id == 'nope'
