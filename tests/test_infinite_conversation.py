"""
Tests for the InfiniteConversationManager.

These tests verify that the InfiniteConversationManager correctly handles:
- Session segmentation based on token thresholds
- Summarization of conversation segments
- Context building across session segments
- Retrieving full conversation history
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from a2a_session_manager.infinite_conversation import (
    InfiniteConversationManager,
    SummarizationStrategy
)


# Set up test fixtures

@pytest.fixture
def store():
    """Create and configure a test session store."""
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    return store


@pytest.fixture
def llm_callback():
    """Create a mock LLM callback function."""
    async def mock_callback(messages, model="gpt-4"):
        """Mock LLM callback that returns a fixed summary."""
        system_msg = next((m for m in messages if m.get("role") == "system"), None)
        
        if system_msg and "summary" in system_msg.get("content", "").lower():
            if "key points" in system_msg.get("content", "").lower():
                return "Key points summary: Point 1, Point 2, Point 3"
            elif "topics" in system_msg.get("content", "").lower():
                return "Topic-based summary: Topic A, Topic B, Topic C"
            elif "user's main questions" in system_msg.get("content", "").lower():
                return "User asked about X, Y, and Z"
            else:
                return "This is a test summary of the conversation"
                
        return "This is a test LLM response"
    
    return AsyncMock(side_effect=mock_callback)


@pytest.fixture
def manager(store, llm_callback):
    """Create an InfiniteConversationManager for testing."""
    return InfiniteConversationManager(
        token_threshold=1000,  # Low threshold for testing
        summary_model="test-model",
        max_context_depth=3
    )


@pytest.fixture
def session(store):
    """Create a test session with some messages."""
    session = Session()
    
    # Add some messages
    messages = [
        {"role": "user", "content": "Hello, this is a test message 1"},
        {"role": "assistant", "content": "This is a test response 1"},
        {"role": "user", "content": "This is test message 2"},
        {"role": "assistant", "content": "This is a test response 2"}
    ]
    
    for msg in messages:
        event = SessionEvent(
            message=msg["content"],
            source=EventSource.USER if msg["role"] == "user" else EventSource.LLM,
            type=EventType.MESSAGE
        )
        session.add_event(event)
    
    store.save(session)
    return session


# Tests for basic functionality

@pytest.mark.asyncio
async def test_process_message_no_segmentation(manager, session, llm_callback):
    """Test processing a message that doesn't trigger segmentation."""
    session_id = session.id
    
    # Process a message
    new_session_id = await manager.process_message(
        session_id,
        "This is a test message that shouldn't trigger segmentation",
        EventSource.USER,
        llm_callback
    )
    
    # Should return the same session ID
    assert new_session_id == session_id
    
    # Should have added the message to the session
    updated_session = SessionStoreProvider.get_store().get(session_id)
    assert len(updated_session.events) == 5
    assert updated_session.events[-1].message == "This is a test message that shouldn't trigger segmentation"


@pytest.mark.asyncio
async def test_process_message_with_segmentation(manager, session, llm_callback):
    """Test processing a message that triggers segmentation."""
    session_id = session.id
    
    # Patch the _get_session_token_count method to force segmentation
    with patch.object(manager, '_get_session_token_count', return_value=1500):
        # Process a message
        new_session_id = await manager.process_message(
            session_id,
            "This message should trigger segmentation",
            EventSource.USER,
            llm_callback
        )
        
        # Should return a different session ID
        assert new_session_id != session_id
        
        # Original session should have a summary event
        original_session = SessionStoreProvider.get_store().get(session_id)
        summary_events = [e for e in original_session.events if e.type == EventType.SUMMARY]
        assert len(summary_events) == 1
        
        # New session should have a reference event
        new_session = SessionStoreProvider.get_store().get(new_session_id)
        reference_events = [
            e for e in new_session.events 
            if e.type == EventType.REFERENCE and e.metadata and e.metadata.get("context_bridge")
        ]
        assert len(reference_events) == 1
        
        # New session should have parent_id pointing to original session
        assert new_session.parent_id == session_id


@pytest.mark.asyncio
async def test_different_summarization_strategies(store, llm_callback):
    """Test that different summarization strategies produce different summaries."""
    # Create a test session
    session = Session()
    for i in range(5):
        session.add_event(SessionEvent(
            message=f"Test message {i}",
            source=EventSource.USER if i % 2 == 0 else EventSource.LLM,
            type=EventType.MESSAGE
        ))
    store.save(session)
    
    # Test each strategy
    summaries = {}
    for strategy in [
        SummarizationStrategy.BASIC,
        SummarizationStrategy.KEY_POINTS,
        SummarizationStrategy.QUERY_FOCUSED,
        SummarizationStrategy.TOPIC_BASED
    ]:
        manager = InfiniteConversationManager(
            token_threshold=1000,
            summarization_strategy=strategy
        )
        
        # Force create a summary
        summary = await manager._create_summary(session, llm_callback)
        summaries[strategy] = summary
    
    # Each strategy should produce a different summary
    assert len(set(summaries.values())) == 4


# Tests for context building

def test_build_context_for_llm_basic(manager, session):
    """Test building a basic context for an LLM call."""
    # Build context
    context = manager.build_context_for_llm(session.id)
    
    # Should include all messages from the session
    assert len(context) == 4
    
    # Check message types
    assert context[0]["role"] == "user"
    assert context[1]["role"] == "assistant"
    assert context[2]["role"] == "user"
    assert context[3]["role"] == "assistant"


def test_build_context_with_ancestors(manager, store):
    """Test building context that includes ancestor session summaries."""
    # Create a parent session with a summary
    parent = Session()
    parent.add_event(SessionEvent(
        message="This is a summary of previous conversation",
        source=EventSource.SYSTEM,
        type=EventType.SUMMARY
    ))
    store.save(parent)
    
    # Create a child session
    child = Session(parent_id=parent.id)
    child.add_event(SessionEvent(
        message="This is a message in the child session",
        source=EventSource.USER,
        type=EventType.MESSAGE
    ))
    store.save(child)
    
    # Build context
    context = manager.build_context_for_llm(child.id, include_summaries=True)
    
    # Should include the parent summary and child message
    assert len(context) == 2
    assert context[0]["role"] == "system"
    assert "Previous conversation context" in context[0]["content"]
    assert context[1]["role"] == "user"


def test_context_with_token_limit(manager, session):
    """Test building context with a token limit."""
    # Add many messages to exceed the token limit
    for i in range(20):
        session.add_event(SessionEvent(
            message=f"Additional message {i} that adds to the token count",
            source=EventSource.USER if i % 2 == 0 else EventSource.LLM,
            type=EventType.MESSAGE
        ))
    SessionStoreProvider.get_store().save(session)
    
    # Build context with a low token limit
    context = manager.build_context_for_llm(session.id, max_tokens=100)
    
    # Should include fewer messages than the total
    assert len(context) < 24  # 4 original + 20 new


# Tests for full conversation history

@pytest.mark.asyncio
async def test_full_conversation_history(store, llm_callback):
    """Test retrieving the full conversation history across segments."""
    # Create a conversation manager
    manager = InfiniteConversationManager(token_threshold=500)
    
    # Create the initial session
    session = Session()
    store.save(session)
    session_id = session.id
    
    # Add messages until we get a segmentation
    messages = []
    current_id = session_id
    
    for i in range(20):
        # Generate messages
        user_msg = f"User message {i}" + " additional text" * 5
        asst_msg = f"Assistant message {i}" + " response text" * 5
        
        # Add user message
        messages.append(("user", user_msg))
        current_id = await manager.process_message(
            current_id, user_msg, EventSource.USER, llm_callback
        )
        
        # Add assistant message
        messages.append(("assistant", asst_msg))
        current_id = await manager.process_message(
            current_id, asst_msg, EventSource.LLM, llm_callback
        )
        
        # If we've segmented, break
        if current_id != session_id:
            break
    
    # Get the full history
    history = manager.get_full_conversation_history(current_id)
    
    # Should include all user and assistant messages
    msg_count = sum(1 for role, _, _ in history if role in ["user", "assistant"])
    assert msg_count == len(messages)


# Tests for edge cases

@pytest.mark.asyncio
async def test_empty_session(manager, store, llm_callback):
    """Test handling an empty session."""
    # Create an empty session
    empty_session = Session()
    store.save(empty_session)
    
    # Process a message
    new_id = await manager.process_message(
        empty_session.id,
        "This is a message in an empty session",
        EventSource.USER,
        llm_callback
    )
    
    # Should add the message without segmentation
    assert new_id == empty_session.id
    updated = store.get(empty_session.id)
    assert len(updated.events) == 1


@pytest.mark.asyncio
async def test_session_not_found(manager, llm_callback):
    """Test handling a non-existent session."""
    with pytest.raises(ValueError, match="Session .* not found"):
        await manager.process_message(
            "non-existent-id",
            "This message shouldn't be processed",
            EventSource.USER,
            llm_callback
        )


@pytest.mark.asyncio
async def test_multi_level_hierarchy(store, llm_callback):
    """Test creating and navigating a multi-level hierarchy."""
    # Create a manager
    manager = InfiniteConversationManager(token_threshold=500)
    
    # Create initial session
    session = Session()
    store.save(session)
    current_id = session.id
    
    # Create a 3-level hierarchy by forcing segmentations
    levels = 3
    session_ids = [current_id]
    
    for i in range(levels - 1):
        # Add enough content to trigger segmentation
        with patch.object(manager, '_get_session_token_count', return_value=1500):
            current_id = await manager.process_message(
                current_id,
                f"Message that triggers segmentation level {i+1}",
                EventSource.USER,
                llm_callback
            )
            session_ids.append(current_id)
    
    # Get session chain
    chain = manager.get_session_chain(current_id)
    
    # Should have the expected levels
    assert len(chain) == levels
    
    # IDs should match the expected hierarchy
    for i, session in enumerate(chain):
        assert session.id == session_ids[i]
    
    # Each session should be a parent of the next
    for i in range(levels - 1):
        assert chain[i+1].parent_id == chain[i].id