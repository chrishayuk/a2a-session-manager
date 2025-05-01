# tests/test_session_prompt_builder.py
"""
Tests for the improved session prompt builder.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from a2a_session_manager.session_prompt_builder import (
    build_prompt_from_session,
    PromptStrategy,
    truncate_prompt_to_token_limit
)


@pytest.fixture
def empty_session():
    """Create an empty session."""
    return Session()


@pytest.fixture
def basic_session():
    """Create a session with basic user and assistant messages."""
    session = Session()
    
    # Add user message
    user_msg = SessionEvent(
        message="What's the weather like today?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    
    # Add assistant response
    assistant_msg = SessionEvent(
        message="I'll check the weather for you.",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(assistant_msg)
    
    return session


@pytest.fixture
def tool_session():
    """Create a session with tool calls."""
    session = Session()
    
    # Add user message
    user_msg = SessionEvent(
        message="What's the weather like in New York?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    
    # Add assistant response
    assistant_msg = SessionEvent(
        message="I'll check the weather for you.",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(assistant_msg)
    
    # Add tool call as child of assistant message
    tool_call = SessionEvent(
        message={
            "tool_name": "get_weather",
            "arguments": {"location": "New York"},
            "result": {
                "temperature": 72,
                "condition": "Sunny",
                "humidity": 45
            }
        },
        source=EventSource.SYSTEM,
        type=EventType.TOOL_CALL,
        metadata={"parent_event_id": assistant_msg.id}
    )
    session.add_event(tool_call)
    
    return session


@pytest.fixture
def retry_session():
    """Create a session with a retry summary."""
    session = Session()
    
    # Add user message
    user_msg = SessionEvent(
        message="What's the weather like in New York?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    
    # Add assistant response
    assistant_msg = SessionEvent(
        message="I'll check the weather for you.",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(assistant_msg)
    
    # Add retry summary as child of assistant message
    summary = SessionEvent(
        message={"note": "Retry due to unparsable tool_call", "attempt": 1},
        source=EventSource.SYSTEM,
        type=EventType.SUMMARY,
        metadata={"parent_event_id": assistant_msg.id}
    )
    session.add_event(summary)
    
    return session


@pytest.fixture
def hierarchical_session(basic_session):
    """Create a child session with a parent."""
    # Create parent session with a summary
    parent = basic_session
    summary = SessionEvent(
        message="User asked about weather and assistant offered to check it.",
        source=EventSource.SYSTEM,
        type=EventType.SUMMARY
    )
    parent.add_event(summary)
    
    # Create child session
    child = Session(parent_id=parent.id)
    
    # Add a message to the child
    user_msg = SessionEvent(
        message="What about tomorrow's forecast?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    child.add_event(user_msg)
    
    # Set up session store for hierarchy
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    store.save(parent)
    store.save(child)
    
    return child


def test_empty_session(empty_session):
    """Test building a prompt from an empty session."""
    prompt = build_prompt_from_session(empty_session)
    assert prompt == []


def test_minimal_strategy_basic(basic_session):
    """Test the minimal strategy with a basic session."""
    prompt = build_prompt_from_session(basic_session, PromptStrategy.MINIMAL)
    
    # Should have user message and assistant with null content
    assert len(prompt) == 2
    assert prompt[0]["role"] == "user"
    assert prompt[0]["content"] == "What's the weather like today?"
    assert prompt[1]["role"] == "assistant"
    assert prompt[1]["content"] is None


def test_minimal_strategy_tool(tool_session):
    """Test the minimal strategy with a session containing tool calls."""
    prompt = build_prompt_from_session(tool_session, PromptStrategy.MINIMAL)
    
    # Should have user, assistant, and tool message
    assert len(prompt) == 3
    assert prompt[0]["role"] == "user"
    assert prompt[1]["role"] == "assistant"
    assert prompt[1]["content"] is None
    assert prompt[2]["role"] == "tool"
    assert prompt[2]["name"] == "get_weather"
    
    # Tool content should be JSON string of result
    tool_content = json.loads(prompt[2]["content"])
    assert tool_content["temperature"] == 72
    assert tool_content["condition"] == "Sunny"


def test_minimal_strategy_retry(retry_session):
    """Test the minimal strategy with a retry summary."""
    prompt = build_prompt_from_session(retry_session, PromptStrategy.MINIMAL)
    
    # Should have user, assistant, and system message with retry note
    assert len(prompt) == 3
    assert prompt[0]["role"] == "user"
    assert prompt[1]["role"] == "assistant"
    assert prompt[1]["content"] is None
    assert prompt[2]["role"] == "system"
    assert "Retry" in prompt[2]["content"]


def test_task_focused_strategy(tool_session):
    """Test the task-focused strategy."""
    prompt = build_prompt_from_session(tool_session, PromptStrategy.TASK_FOCUSED)
    
    # Should have user, assistant, and successful tool
    assert len(prompt) == 3
    assert prompt[0]["role"] == "user"
    assert prompt[1]["role"] == "assistant"
    assert prompt[1]["content"] is None
    assert prompt[2]["role"] == "tool"
    assert "temperature" in prompt[2]["content"]


def test_tool_focused_strategy(tool_session):
    """Test the tool-focused strategy."""
    prompt = build_prompt_from_session(tool_session, PromptStrategy.TOOL_FOCUSED)
    
    # Should have user, assistant, and detailed tool info
    assert len(prompt) == 3
    assert prompt[0]["role"] == "user"
    assert prompt[1]["role"] == "assistant"
    assert prompt[2]["role"] == "tool"
    assert prompt[2]["name"] == "get_weather"
    
    # Parse tool content to check it includes the full result
    tool_content = json.loads(prompt[2]["content"])
    assert "temperature" in tool_content
    assert "condition" in tool_content


def test_conversation_strategy(basic_session):
    """Test the conversation strategy."""
    # Add a few more messages to make conversation longer
    user_msg2 = SessionEvent(
        message="Is it going to rain tomorrow?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    basic_session.add_event(user_msg2)
    
    assistant_msg2 = SessionEvent(
        message="Let me check the forecast for tomorrow.",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    basic_session.add_event(assistant_msg2)
    
    # Test conversation strategy
    prompt = build_prompt_from_session(basic_session, PromptStrategy.CONVERSATION)
    
    # Should include all messages in conversation order
    assert len(prompt) == 4
    assert prompt[0]["role"] == "user"
    assert prompt[0]["content"] == "What's the weather like today?"
    assert prompt[1]["role"] == "assistant"
    assert prompt[1]["content"] == "I'll check the weather for you."
    assert prompt[2]["role"] == "user"
    assert prompt[2]["content"] == "Is it going to rain tomorrow?"
    assert prompt[3]["role"] == "assistant"
    assert prompt[3]["content"] is None  # Last assistant message has null content


def test_hierarchical_strategy(hierarchical_session):
    """Test the hierarchical strategy."""
    prompt = build_prompt_from_session(
        hierarchical_session, 
        PromptStrategy.HIERARCHICAL,
        include_parent_context=True
    )
    
    # Should include system context from parent, plus user message
    assert len(prompt) >= 2
    assert prompt[0]["role"] == "system"
    assert "Context from previous conversation" in prompt[0]["content"]
    assert prompt[1]["role"] == "user"
    assert prompt[1]["content"] == "What about tomorrow's forecast?"


def test_truncate_prompt_to_token_limit():
    """Test truncating a prompt to fit within token limits."""
    # Create a long prompt
    long_prompt = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather like today?"},
        {"role": "assistant", "content": None},
        {"role": "tool", "content": json.dumps({"temperature": 72, "condition": "Sunny"})},
        {"role": "tool", "content": json.dumps({"forecast": "Clear skies all day"})},
        {"role": "tool", "content": json.dumps({"humidity": "45%", "wind": "5 mph"})},
    ]
    
    # Mock token counting to return a large value
    with patch('a2a_session_manager.models.token_usage.TokenUsage.count_tokens', 
              return_value=500):  # Pretend it's 500 tokens
        
        # Truncate to 300 tokens
        truncated = truncate_prompt_to_token_limit(long_prompt, 300)
        
        # Should keep first user and last few messages
        assert len(truncated) < len(long_prompt)
        
        # First message should be user
        assert truncated[0]["role"] == "user"
        
        # Should keep the assistant message
        assert any(msg["role"] == "assistant" for msg in truncated)
        
        # Should keep at least one tool message
        assert any(msg["role"] == "tool" for msg in truncated)


def test_strategy_as_string():
    """Test using strategy as a string instead of enum."""
    basic = Session()
    user_msg = SessionEvent(
        message="Hello",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    basic.add_event(user_msg)
    
    # Should handle string strategy
    prompt = build_prompt_from_session(basic, strategy="minimal")
    assert len(prompt) == 1
    assert prompt[0]["role"] == "user"
    
    # Should handle invalid string gracefully
    prompt = build_prompt_from_session(basic, strategy="invalid_strategy")
    assert len(prompt) == 1  # Falls back to minimal


def test_handling_different_message_formats():
    """Test handling different message formats."""
    session = Session()
    
    # Add message as string
    session.add_event(SessionEvent(
        message="Plain string message",
        source=EventSource.USER,
        type=EventType.MESSAGE
    ))
    
    # Add message as dict
    session.add_event(SessionEvent(
        message={"content": "Dict message", "extra_field": "value"},
        source=EventSource.LLM,
        type=EventType.MESSAGE
    ))
    
    # Build prompt
    prompt = build_prompt_from_session(session)
    
    # Should handle both formats
    assert prompt[0]["content"] == "Plain string message"
    assert prompt[1]["content"] is None  # Assistant content is always None