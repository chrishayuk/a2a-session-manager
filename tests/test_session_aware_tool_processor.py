# tests/test_session_aware_tool_processor.py
"""
Tests for SessionAwareToolProcessor.

These tests verify the integration between a2a_session_manager
and the tool execution system.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from a2a_session_manager.session_aware_tool_processor import SessionAwareToolProcessor

# Mock the chuk_tool_processor imports
class MockToolResult:
    def __init__(self, **kwargs):
        self.tool_name = kwargs.get("tool_name", "mock_tool")
        self.arguments = kwargs.get("arguments", {})
        self.result = kwargs.get("result", {})
    
    def model_dump(self):
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result
        }


@pytest.fixture
def setup_session_store():
    """Set up an in-memory session store with a test session."""
    # Create and configure the store
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a test session
    session = Session()
    store.save(session)
    
    return session.id


@pytest.mark.asyncio
async def test_process_llm_message_success(setup_session_store):
    """Test successful tool call processing."""
    session_id = setup_session_store
    
    # Mock the ToolProcessor.process_text method
    with patch('a2a_session_manager.session_aware_tool_processor.ToolProcessor.process_text') as mock_process_text:
        # Configure the mock to return a successful result
        tool_result = MockToolResult(
            tool_name="test_tool",
            arguments={"arg1": "value1"},
            result={"status": "success", "data": "test_result"}
        )
        mock_process_text.return_value = [tool_result]
        
        # Create the processor
        processor = SessionAwareToolProcessor(session_id=session_id)
        
        # Test with a sample assistant message
        assistant_msg = {
            "role": "assistant",
            "content": "I'll use the test_tool to help you.",
            "tool_calls": [{"type": "function", "function": {"name": "test_tool", "arguments": '{"arg1": "value1"}'}}]
        }
        
        # Mock LLM call function
        async def mock_llm_call(prompt):
            return {"role": "assistant", "content": "Retry response"}
        
        # Process the message
        results = await processor.process_llm_message(assistant_msg, mock_llm_call)
        
        # Verify results
        assert len(results) == 1
        assert results[0].tool_name == "test_tool"
        
        # Check that session was updated correctly
        store = SessionStoreProvider.get_store()
        session = store.get(session_id)
        
        # Should have a run
        assert len(session.runs) == 1
        assert session.runs[0].status.value == "completed"
        
        # Should have events
        assert len(session.events) >= 2  # At least the parent event and one child
        
        # First event should be the parent event with the assistant message
        parent_event = session.events[0]
        assert parent_event.source == EventSource.SYSTEM
        assert parent_event.type == EventType.MESSAGE
        assert parent_event.message == assistant_msg
        
        # Second event should be the tool call result
        tool_event = session.events[1]
        assert tool_event.type == EventType.TOOL_CALL
        assert tool_event.source == EventSource.SYSTEM
        assert tool_event.metadata.get("parent_event_id") == parent_event.id
        assert tool_event.message["tool_name"] == "test_tool"


@pytest.mark.asyncio
async def test_process_llm_message_retry_success(setup_session_store):
    """Test tool call processing with retry."""
    session_id = setup_session_store
    
    # Mock the ToolProcessor.process_text method
    with patch('a2a_session_manager.session_aware_tool_processor.ToolProcessor.process_text') as mock_process_text:
        # First call returns empty list (no tool calls found)
        # Second call returns a successful result
        tool_result = MockToolResult(
            tool_name="test_tool",
            arguments={"arg1": "value1"},
            result={"status": "success", "data": "test_result"}
        )
        mock_process_text.side_effect = [[], [tool_result]]
        
        # Create the processor
        processor = SessionAwareToolProcessor(session_id=session_id)
        
        # Test with a sample assistant message
        assistant_msg = {
            "role": "assistant",
            "content": "I'll help you with that.",
            "tool_calls": []  # Empty tool calls initially
        }
        
        # Mock LLM call function that returns a message with tool calls on retry
        retry_assistant_msg = {
            "role": "assistant",
            "content": "I'll use the test_tool to help you.",
            "tool_calls": [{"type": "function", "function": {"name": "test_tool", "arguments": '{"arg1": "value1"}'}}]
        }
        
        async def mock_llm_call(prompt):
            return retry_assistant_msg
        
        # Process the message
        results = await processor.process_llm_message(assistant_msg, mock_llm_call)
        
        # Verify results
        assert len(results) == 1
        assert results[0].tool_name == "test_tool"
        
        # Check that session was updated correctly
        store = SessionStoreProvider.get_store()
        session = store.get(session_id)
        
        # Should have a completed run
        assert len(session.runs) == 1
        assert session.runs[0].status.value == "completed"
        
        # Should have events: parent + retry summary + tool call
        assert len(session.events) >= 3
        
        # Verify the retry event was created
        retry_events = [e for e in session.events if e.type == EventType.SUMMARY]
        assert len(retry_events) >= 1
        retry_event = retry_events[0]
        assert retry_event.metadata.get("parent_event_id") is not None
        assert "Retry" in str(retry_event.message)


@pytest.mark.asyncio
async def test_process_llm_message_max_retries_exceeded(setup_session_store):
    """Test tool call processing with max retries exceeded."""
    session_id = setup_session_store
    
    # Mock the ToolProcessor.process_text method to always return empty results
    with patch('a2a_session_manager.session_aware_tool_processor.ToolProcessor.process_text') as mock_process_text:
        mock_process_text.return_value = []
        
        # Create the processor with 2 max retries
        processor = SessionAwareToolProcessor(session_id=session_id, max_llm_retries=2)
        
        # Test with a sample assistant message
        assistant_msg = {
            "role": "assistant",
            "content": "I'll help you with that.",
            "tool_calls": []  # Empty tool calls
        }
        
        # Mock LLM call function that always returns messages without valid tool calls
        async def mock_llm_call(prompt):
            return {"role": "assistant", "content": "I still can't figure out how to use the tools."}
        
        # Process the message - should raise RuntimeError
        with pytest.raises(RuntimeError, match="Max LLM retries exceeded"):
            await processor.process_llm_message(assistant_msg, mock_llm_call)
        
        # Check that session was updated correctly
        store = SessionStoreProvider.get_store()
        session = store.get(session_id)
        
        # Should have a failed run
        assert len(session.runs) == 1
        assert session.runs[0].status.value == "failed"
        
        # Should have events: parent + 2 retry summaries + error message
        assert len(session.events) >= 4
        
        # Check for error message event
        error_events = [e for e in session.events if "error" in str(e.message)]
        assert len(error_events) >= 1


@pytest.mark.asyncio
async def test_session_not_found():
    """Test behavior when session is not found."""
    # Create store with no sessions
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create processor with non-existent session ID
    processor = SessionAwareToolProcessor(session_id="nonexistent")
    
    # Mock LLM call function
    async def mock_llm_call(prompt):
        return {"role": "assistant", "content": "Response"}
    
    # Process message should raise RuntimeError
    with pytest.raises(RuntimeError, match="Session .* not found"):
        await processor.process_llm_message({"role": "assistant", "content": "Test"}, mock_llm_call)


@pytest.mark.asyncio
async def test_custom_retry_prompt(setup_session_store):
    """Test custom retry prompt."""
    session_id = setup_session_store
    
    # Mock the ToolProcessor.process_text method
    with patch('a2a_session_manager.session_aware_tool_processor.ToolProcessor.process_text') as mock_process_text:
        # First call fails, second succeeds
        tool_result = MockToolResult(tool_name="test_tool")
        mock_process_text.side_effect = [[], [tool_result]]
        
        # Create processor with custom retry prompt
        custom_prompt = "USE THE TOOLS! Try again and return a proper tool_call."
        processor = SessionAwareToolProcessor(
            session_id=session_id, 
            llm_retry_prompt=custom_prompt
        )
        
        # Mock LLM call function that captures the prompt
        captured_prompt = None
        
        async def mock_llm_call(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return {"role": "assistant", "content": "Retry with tool", "tool_calls": [{}]}
        
        # Process message
        await processor.process_llm_message({"role": "assistant", "content": "Test"}, mock_llm_call)
        
        # Verify custom prompt was used
        assert captured_prompt == custom_prompt