# tests/event_type.py
import pytest
from a2a_session_manager.models.event_type import EventType


def test_event_type_members():
    # Ensure all expected members are present
    assert hasattr(EventType, 'MESSAGE')
    assert hasattr(EventType, 'SUMMARY')
    assert hasattr(EventType, 'TOOL_CALL')

    # Check values
    assert EventType.MESSAGE.value == 'message'
    assert EventType.SUMMARY.value == 'summary'
    assert EventType.TOOL_CALL.value == 'tool_call'


def test_event_type_iteration():
    # Iteration should yield all enum members
    members = [e for e in EventType]
    assert set(members) == {EventType.MESSAGE, EventType.SUMMARY, EventType.TOOL_CALL}


def test_event_type_equality_and_identity():
    # Equality and identity
    assert EventType('message') is EventType.MESSAGE
    assert EventType.MESSAGE == EventType.MESSAGE
    assert EventType.MESSAGE != EventType.SUMMARY


def test_event_type_invalid_value():
    # Constructing from an invalid value should raise ValueError
    with pytest.raises(ValueError):
        _ = EventType('invalid')

@pytest.mark.parametrize("value,expected", [
    ('message', EventType.MESSAGE),
    ('summary', EventType.SUMMARY),
    ('tool_call', EventType.TOOL_CALL),
])
def test_event_type_from_value(value, expected):
    # Casting from string returns correct enum member
    assert EventType(value) == expected
