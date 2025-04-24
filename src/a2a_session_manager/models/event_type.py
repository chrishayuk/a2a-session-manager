# a2a_session_manager/models/event_type.py
from enum import Enum

class EventType(str, Enum):
    """Types of session events."""
    MESSAGE = "message"
    SUMMARY = "summary"
    TOOL_CALL = "tool_call"