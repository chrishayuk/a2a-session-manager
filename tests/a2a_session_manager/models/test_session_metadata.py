# tests/session_metadata.py
import pytest
from datetime import datetime, timezone, timedelta
import time

from a2a_session_manager.models.session_metadata import SessionMetadata

def test_default_timestamps_are_set_and_utc():
    before = datetime.now(timezone.utc)
    time.sleep(0.001)
    meta = SessionMetadata()
    time.sleep(0.001)
    after = datetime.now(timezone.utc)

    # created_at and updated_at should be between before and after
    assert before < meta.created_at < after
    assert before < meta.updated_at < after

    # timezone info must be UTC
    assert meta.created_at.tzinfo == timezone.utc
    assert meta.updated_at.tzinfo == timezone.utc

def test_properties_initially_empty():
    meta = SessionMetadata()
    assert isinstance(meta.properties, dict)
    assert meta.properties == {}

def test_set_and_get_property():
    meta = SessionMetadata()
    assert meta.get_property("nonexistent") is None

    meta.set_property("foo", 123)
    assert "foo" in meta.properties
    assert meta.get_property("foo") == 123

    # Overwriting works
    meta.set_property("foo", "bar")
    assert meta.get_property("foo") == "bar"

def test_model_dump_includes_properties_and_timestamps():
    meta = SessionMetadata()
    meta.set_property("x", True)
    d = meta.model_dump()

    assert "created_at" in d
    assert "updated_at" in d
    assert d["properties"] == {"x": True}

def test_updating_updated_at_manually():
    # You might manually bump updated_at
    meta = SessionMetadata()
    old = meta.updated_at
    new_ts = old + timedelta(days=1)
    meta.updated_at = new_ts

    assert meta.updated_at == new_ts
    # created_at remains unchanged
    assert meta.created_at < meta.updated_at

