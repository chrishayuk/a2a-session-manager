# tests/session_event.py
import pytest
from datetime import datetime, timezone
import time
from uuid import UUID

from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource


def test_default_session_event_fields():
    before = datetime.now(timezone.utc)
    time.sleep(0.001)
    event = SessionEvent(message="hello")
    time.sleep(0.001)
    after = datetime.now(timezone.utc)

    # id is a valid UUID string
    assert isinstance(event.id, str)
    UUID(event.id)  # should not raise

    # timestamp is set automatically and is within bounds
    assert before < event.timestamp < after
    assert event.timestamp.tzinfo == timezone.utc

    # default type and source
    assert event.type == EventType.MESSAGE
    assert event.source == EventSource.LLM

    # default metadata is empty dict
    assert isinstance(event.metadata, dict)
    assert event.metadata == {}

    # message and task_id
    assert event.message == "hello"
    assert event.task_id is None


def test_custom_fields_assignment():
    payload = {"foo": "bar"}
    evt = SessionEvent(
        message=payload,
        task_id="task123",
        type=EventType.TOOL_CALL,
        source=EventSource.USER,
        metadata={"key": 42}
    )

    assert evt.message == payload
    assert evt.task_id == "task123"
    assert evt.type == EventType.TOOL_CALL
    assert evt.source == EventSource.USER
    assert evt.metadata == {"key": 42}


def test_serialization_round_trip():
    evt = SessionEvent(
        message="test",
        task_id="t1",
        type=EventType.SUMMARY,
        source=EventSource.SYSTEM,
        metadata={"m": True}
    )
    data = evt.model_dump()

    # Ensure string values
    assert data["message"] == "test"
    assert data["task_id"] == "t1"
    assert data["type"] == EventType.SUMMARY
    assert data["source"] == EventSource.SYSTEM
    assert data["metadata"] == {"m": True}

    json_str = evt.model_dump_json()
    assert "test" in json_str
    assert "SUMMARY" not in json_str  # uses value, not name
    assert EventType.SUMMARY.value in json_str
    assert EventSource.SYSTEM.value in json_str


def test_invalid_type_and_source_raise_validation_error():
    with pytest.raises(Exception):
        SessionEvent(type="invalid_type")
    with pytest.raises(Exception):
        SessionEvent(source="noone")