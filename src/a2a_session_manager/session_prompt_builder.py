# a2a_session_manager/session_prompt_builder.py
"""
Build optimized prompts for LLM calls from Session objects.

This module provides flexible prompt construction from session data,
with support for token management, relevance-based selection,
and hierarchical context awareness.
"""

from __future__ import annotations
import json
import logging
from typing import List, Dict, Any, Optional, Literal, Union
from enum import Enum

from a2a_session_manager.models.session import Session
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.token_usage import TokenUsage
from a2a_session_manager.storage import SessionStoreProvider

logger = logging.getLogger(__name__)

class PromptStrategy(str, Enum):
    """Different strategies for building prompts."""
    MINIMAL = "minimal"         # Original minimal approach
    TASK_FOCUSED = "task"       # Focus on the task with minimal context
    TOOL_FOCUSED = "tool"       # Emphasize tool usage and results
    CONVERSATION = "conversation"  # Include more conversation history
    HIERARCHICAL = "hierarchical"  # Include parent session context


def build_prompt_from_session(
    session: Session,
    strategy: Union[PromptStrategy, str] = PromptStrategy.MINIMAL,
    max_tokens: Optional[int] = None,
    model: str = "gpt-3.5-turbo",
    include_parent_context: bool = False,
    current_query: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Build a prompt for the next LLM call from a Session.
    
    Args:
        session: The session to build a prompt from
        strategy: Prompt building strategy to use
        max_tokens: Maximum tokens to include (if specified)
        model: Model to use for token counting
        include_parent_context: Whether to include context from parent sessions
        current_query: Current user query for relevance-based context selection
        
    Returns:
        A list of message dictionaries suitable for LLM API calls
    """
    if not session.events:
        return []
    
    # Convert string strategy to enum if needed
    if isinstance(strategy, str):
        try:
            strategy = PromptStrategy(strategy)
        except ValueError:
            logger.warning(f"Unknown strategy '{strategy}', falling back to MINIMAL")
            strategy = PromptStrategy.MINIMAL
    
    # Use the appropriate strategy
    if strategy == PromptStrategy.MINIMAL:
        return _build_minimal_prompt(session)
    elif strategy == PromptStrategy.TASK_FOCUSED:
        return _build_task_focused_prompt(session)
    elif strategy == PromptStrategy.TOOL_FOCUSED:
        return _build_tool_focused_prompt(session)
    elif strategy == PromptStrategy.CONVERSATION:
        return _build_conversation_prompt(session, max_history=5)
    elif strategy == PromptStrategy.HIERARCHICAL:
        return _build_hierarchical_prompt(session, include_parent_context)
    else:
        # Default to minimal
        return _build_minimal_prompt(session)


def _build_minimal_prompt(session: Session) -> List[Dict[str, str]]:
    """
    Build a minimal prompt from a session.
    
    This follows the original implementation's approach:
    - Include the first USER message (task)
    - Include the latest assistant MESSAGE with content set to None
    - Include TOOL_CALL children as tool role messages
    - Fall back to SUMMARY retry note if no TOOL_CALL children exist
    """
    # First USER message
    first_user = next(
        (
            e
            for e in session.events
            if e.type == EventType.MESSAGE and e.source == EventSource.USER
        ),
        None,
    )

    # Latest assistant MESSAGE
    assistant_msg = next(
        (
            ev
            for ev in reversed(session.events)
            if ev.type == EventType.MESSAGE and ev.source != EventSource.USER
        ),
        None,
    )
    
    if assistant_msg is None:
        # Only the user message exists so far
        return [{"role": "user", "content": first_user.message}] if first_user else []

    # Children of that assistant
    children = [
        e
        for e in session.events
        if e.metadata.get("parent_event_id") == assistant_msg.id
    ]
    tool_calls = [c for c in children if c.type == EventType.TOOL_CALL]
    summaries = [c for c in children if c.type == EventType.SUMMARY]

    # Assemble prompt
    prompt: List[Dict[str, str]] = []
    if first_user:
        # Handle both string messages and dict messages
        user_content = first_user.message
        if isinstance(user_content, dict) and "content" in user_content:
            user_content = user_content["content"]
        prompt.append({"role": "user", "content": user_content})

    # ALWAYS add the assistant marker – but strip its free text
    prompt.append({"role": "assistant", "content": None})

    if tool_calls:
        for tc in tool_calls:
            # Extract relevant information from the tool call
            # Handle both new and legacy formats
            if isinstance(tc.message, dict):
                tool_name = tc.message.get("tool_name", tc.message.get("tool", "unknown"))
                tool_result = tc.message.get("result", {})
            else:
                # Legacy format or unexpected type
                tool_name = "unknown"
                tool_result = tc.message

            prompt.append(
                {
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(tool_result, default=str),
                }
            )
    elif summaries:
        # Use the latest summary
        summary = summaries[-1]
        if isinstance(summary.message, dict) and "note" in summary.message:
            prompt.append({"role": "system", "content": summary.message["note"]})
        else:
            # Handle legacy or unexpected format
            prompt.append({"role": "system", "content": str(summary.message)})

    return prompt


def _build_task_focused_prompt(session: Session) -> List[Dict[str, str]]:
    """
    Build a task-focused prompt.
    
    This strategy emphasizes the original task and latest context:
    - Includes the first USER message as the main task
    - Includes the most recent USER message for current context
    - Includes only the most recent and successful tool results
    """
    # Get first and most recent user messages
    user_messages = [
        e for e in session.events
        if e.type == EventType.MESSAGE and e.source == EventSource.USER
    ]
    
    if not user_messages:
        return []
        
    first_user = user_messages[0]
    latest_user = user_messages[-1] if len(user_messages) > 1 else None
    
    # Latest assistant MESSAGE
    assistant_msg = next(
        (
            ev
            for ev in reversed(session.events)
            if ev.type == EventType.MESSAGE and ev.source != EventSource.USER
        ),
        None,
    )
    
    # Build prompt
    prompt = []
    
    # Always include the first user message (the main task)
    first_content = first_user.message
    if isinstance(first_content, dict) and "content" in first_content:
        first_content = first_content["content"]
    prompt.append({"role": "user", "content": first_content})
    
    # Include the latest user message if different from the first
    if latest_user and latest_user.id != first_user.id:
        latest_content = latest_user.message
        if isinstance(latest_content, dict) and "content" in latest_content:
            latest_content = latest_content["content"]
        prompt.append({"role": "user", "content": latest_content})
    
    # Include assistant response placeholder
    if assistant_msg:
        prompt.append({"role": "assistant", "content": None})
        
        # Find successful tool calls
        children = [
            e for e in session.events
            if e.metadata.get("parent_event_id") == assistant_msg.id
        ]
        tool_calls = [c for c in children if c.type == EventType.TOOL_CALL]
        
        # Only include successful tool results
        for tc in tool_calls:
            # Extract and check if result indicates success
            if isinstance(tc.message, dict):
                tool_name = tc.message.get("tool_name", tc.message.get("tool", "unknown"))
                tool_result = tc.message.get("result", {})
                
                # Skip error results
                if isinstance(tool_result, dict) and tool_result.get("status") == "error":
                    continue
                    
                prompt.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(tool_result, default=str),
                })
    
    return prompt


def _build_tool_focused_prompt(session: Session) -> List[Dict[str, str]]:
    """
    Build a tool-focused prompt.
    
    This strategy emphasizes tool usage:
    - Includes the latest user query
    - Includes detailed information about tool calls and results
    - Includes error information from failed tool calls
    """
    # Get the latest user message
    latest_user = next(
        (e for e in reversed(session.events) 
         if e.type == EventType.MESSAGE and e.source == EventSource.USER),
        None
    )
    
    if not latest_user:
        return []
    
    # Get the latest assistant message
    assistant_msg = next(
        (ev for ev in reversed(session.events)
         if ev.type == EventType.MESSAGE and ev.source != EventSource.USER),
        None
    )
    
    # Build prompt
    prompt = []
    
    # Include user message
    user_content = latest_user.message
    if isinstance(user_content, dict) and "content" in user_content:
        user_content = user_content["content"]
    prompt.append({"role": "user", "content": user_content})
    
    # Include assistant placeholder
    if assistant_msg:
        prompt.append({"role": "assistant", "content": None})
        
        # Get all tool calls for this assistant
        children = [
            e for e in session.events
            if e.metadata.get("parent_event_id") == assistant_msg.id
        ]
        tool_calls = [c for c in children if c.type == EventType.TOOL_CALL]
        
        # Add all tool calls with status information
        for tc in tool_calls:
            if isinstance(tc.message, dict):
                tool_name = tc.message.get("tool_name", tc.message.get("tool", "unknown"))
                tool_result = tc.message.get("result", {})
                error = tc.message.get("error", None)
                
                # Include status information in the tool response
                content = tool_result
                if error:
                    content = {"error": error, "details": tool_result}
                
                prompt.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(content, default=str),
                })
    
    return prompt


def _build_conversation_prompt(
    session: Session, 
    max_history: int = 5
) -> List[Dict[str, str]]:
    """
    Build a conversation-style prompt with recent history.
    
    This strategy creates a more natural conversation:
    - Includes up to max_history recent messages in order
    - Preserves conversation flow
    - Still handles tool calls appropriately
    """
    # Get relevant message events
    message_events = [
        e for e in session.events
        if e.type == EventType.MESSAGE
    ]
    
    # Take the most recent messages
    recent_messages = message_events[-max_history:] if len(message_events) > max_history else message_events
    
    # Build the conversation history
    prompt = []
    for msg in recent_messages:
        role = "user" if msg.source == EventSource.USER else "assistant"
        content = msg.message
        
        # Handle different message formats
        if isinstance(content, dict) and "content" in content:
            content = content["content"]
        
        # For the last assistant message, set content to None
        if role == "assistant" and msg == recent_messages[-1] and msg.source != EventSource.USER:
            content = None
            
            # Add tool call results for this assistant message
            tool_calls = [
                e for e in session.events
                if e.type == EventType.TOOL_CALL and e.metadata.get("parent_event_id") == msg.id
            ]
            
            # Add the message first, then tools
            prompt.append({"role": role, "content": content})
            
            # Add tool results
            for tc in tool_calls:
                if isinstance(tc.message, dict):
                    tool_name = tc.message.get("tool_name", tc.message.get("tool", "unknown"))
                    tool_result = tc.message.get("result", {})
                    
                    prompt.append({
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(tool_result, default=str),
                    })
                    
            # Skip adding this message again
            continue
            
        prompt.append({"role": role, "content": content})
    
    return prompt


def _build_hierarchical_prompt(
    session: Session,
    include_parent_context: bool = True
) -> List[Dict[str, str]]:
    """
    Build a prompt that includes hierarchical context.
    
    This strategy leverages the session hierarchy:
    - Starts with the minimal prompt
    - Includes summaries from parent sessions if available
    """
    # Start with the minimal prompt
    prompt = _build_minimal_prompt(session)
    
    # If parent context is enabled and session has a parent
    if include_parent_context and session.parent_id:
        store = SessionStoreProvider.get_store()
        parent = store.get(session.parent_id)
        
        if parent:
            # Find the most recent summary in parent
            summary_event = next(
                (e for e in reversed(parent.events) 
                 if e.type == EventType.SUMMARY),
                None
            )
            
            if summary_event:
                # Extract summary content
                summary_content = summary_event.message
                if isinstance(summary_content, dict) and "note" in summary_content:
                    summary_content = summary_content["note"]
                elif isinstance(summary_content, dict) and "content" in summary_content:
                    summary_content = summary_content["content"]
                    
                # Add parent context at the beginning
                prompt.insert(0, {
                    "role": "system",
                    "content": f"Context from previous conversation: {summary_content}"
                })
    
    return prompt


def truncate_prompt_to_token_limit(
    prompt: List[Dict[str, str]],
    max_tokens: int,
    model: str = "gpt-3.5-turbo"
) -> List[Dict[str, str]]:
    """
    Truncate a prompt to fit within a token limit.
    
    Args:
        prompt: The prompt to truncate
        max_tokens: Maximum tokens to include
        model: Model to use for token counting
        
    Returns:
        Truncated prompt that fits within the token limit
    """
    if not prompt:
        return []
        
    # Convert to text for token counting
    prompt_text = ""
    for msg in prompt:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content is None:
            content = ""
        prompt_text += f"{role}: {content}\n"
    
    # Count tokens
    token_count = TokenUsage.count_tokens(prompt_text, model)
    
    # If we're already under the limit, return as is
    if token_count <= max_tokens:
        return prompt
        
    # We need to truncate - preserve essential elements
    
    # Always keep the first user message (task) and the last few messages
    result = []
    
    # Find the first user message
    first_user_idx = next((i for i, msg in enumerate(prompt) 
                          if msg.get("role") == "user"), None)
    
    # Find the latest assistant message
    latest_assistant_idx = next((i for i, msg in enumerate(reversed(prompt))
                               if msg.get("role") == "assistant"), None)
    if latest_assistant_idx is not None:
        latest_assistant_idx = len(prompt) - 1 - latest_assistant_idx
    
    # Keep the first user message
    if first_user_idx is not None:
        result.append(prompt[first_user_idx])
    
    # Keep the latest assistant and subsequent tool calls
    if latest_assistant_idx is not None:
        # Add all messages from the assistant onwards
        result.extend(prompt[latest_assistant_idx:])
    
    # Create a list of all tool messages in the original prompt
    tool_messages = [msg for msg in prompt if msg.get("role") == "tool"]
    
    # If we're still over the limit, truncate to essentials but keep at least one tool message
    if result and TokenUsage.count_tokens(str(result), model) > max_tokens:
        # Keep only essential non-tool messages
        truncated = [msg for msg in result if msg.get("role") != "tool"]
        
        # If the original prompt had tool messages, keep at least one
        if tool_messages:
            truncated.append(tool_messages[0])
            
            # Try to add more tool messages if we have space
            remaining_tools = [msg for msg in result if msg.get("role") == "tool"][1:]
            for msg in remaining_tools:
                test_prompt = truncated + [msg]
                if TokenUsage.count_tokens(str(test_prompt), model) < max_tokens * 0.9:
                    truncated.append(msg)
        
        result = truncated
    
    return result
