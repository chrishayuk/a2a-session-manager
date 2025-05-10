# a2a_session_manager/session_aware_tool_processor.py
"""
Session-aware tool processor that logs tool execution in a session.

This processor handles OpenAI function calling with a hierarchical event structure:
- Creates a parent "batch" event for each processing run
- Creates child events for each tool call, linked via metadata.parent_event_id
- Optionally tracks retries as additional child events
"""

from __future__ import annotations
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Callable, Union, TypeVar, Generic, Tuple
from datetime import datetime, timezone
import hashlib

from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.storage import SessionStoreProvider
from chuk_tool_processor.core.processor import ToolProcessor

# Type for LLM callback function
LLMCallbackAsync = Callable[[str], Dict[str, Any]]

logger = logging.getLogger(__name__)


class SessionAwareToolProcessor:
    """
    Tool processor that logs all tool execution in a session.
    
    This processor creates a hierarchical event structure in the session:
    - Parent "batch" event for each processing run
    - Child tool call events with parent_event_id linking to the batch
    - Child retry events when retries are enabled
    """
    
    def __init__(
        self,
        session_id: str,
        enable_caching: bool = True,
        enable_retries: bool = True,
        max_retries: int = 2,
        retry_delay: float = 1.0
    ):
        """
        Initialize the session-aware tool processor.
        
        Args:
            session_id: ID of the session to log tool execution in
            enable_caching: Whether to cache tool results for identical calls
            enable_retries: Whether to retry failed tool calls
            max_retries: Maximum number of retries per tool call
            retry_delay: Delay in seconds between retries
        """
        self.session_id = session_id
        self.enable_caching = enable_caching
        self.enable_retries = enable_retries
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cache: Dict[str, Any] = {}
    
    @classmethod
    async def create(
        cls,
        session_id: str,
        enable_caching: bool = True,
        enable_retries: bool = True,
        max_retries: int = 2,
        retry_delay: float = 1.0
    ) -> SessionAwareToolProcessor:
        """
        Create a new SessionAwareToolProcessor instance asynchronously.
        
        Args:
            session_id: ID of the session to log tool execution in
            enable_caching: Whether to cache tool results for identical calls
            enable_retries: Whether to retry failed tool calls
            max_retries: Maximum number of retries per tool call
            retry_delay: Delay in seconds between retries
            
        Returns:
            A new SessionAwareToolProcessor instance
        """
        # Verify that the session exists
        store = SessionStoreProvider.get_store()
        session = await store.get(session_id)
        
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        return cls(
            session_id=session_id,
            enable_caching=enable_caching,
            enable_retries=enable_retries,
            max_retries=max_retries,
            retry_delay=retry_delay
        )
    
    async def process_llm_message(
        self,
        llm_message: Dict[str, Any],
        llm_callback: LLMCallbackAsync
    ) -> List[ToolResult]:
        """
        Process an LLM message containing tool calls.
        
        Args:
            llm_message: The message from the LLM with potential tool calls
            llm_callback: Async callback function for follow-up LLM calls
            
        Returns:
            List of tool results
        """
        # Get the store
        store = SessionStoreProvider.get_store()
        
        # Get the session
        session = await store.get(self.session_id)
        if not session:
            raise ValueError(f"Session {self.session_id} not found")
        
        # Create a parent "batch" event for all tool calls in this message
        batch_event = await SessionEvent.create_with_tokens(
            message=llm_message,
            prompt="",
            completion=json.dumps(llm_message, default=str),
            model="gpt-4o-mini",  # Default model, can be overridden
            source=EventSource.LLM,
            type=EventType.MESSAGE
        )
        await batch_event.update_metadata("contains_tool_calls", True)
        await session.add_event_and_save(batch_event)
        
        # Extract tool calls from the message
        tool_calls = llm_message.get("tool_calls", [])
        if not tool_calls:
            return []
        
        # Process each tool call
        results = []
        for call in tool_calls:
            # Extract tool information
            call_id = call.get("id", "unknown")
            function = call.get("function", {})
            tool_name = function.get("name", "unknown")
            arguments = function.get("arguments", "{}")
            
            # Try to parse arguments
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                args = {"raw_arguments": arguments}
            
            # Check cache if enabled
            cache_key = None
            cache_hit = False
            if self.enable_caching:
                cache_key = await self._get_cache_key(tool_name, args)
                if cache_key in self.cache:
                    logger.info(f"Cache hit for tool {tool_name}")
                    result = self.cache[cache_key]
                    cache_hit = True
                    
                    # Create tool call event for cached result
                    tool_event = await SessionEvent.create_with_tokens(
                        message={
                            "tool": tool_name,
                            "arguments": args,
                            "result": result,
                            "cached": True
                        },
                        prompt=f"{tool_name}({json.dumps(args, default=str)})",
                        completion=json.dumps(result, default=str),
                        model="tool-execution",
                        source=EventSource.SYSTEM,
                        type=EventType.TOOL_CALL
                    )
                    await tool_event.update_metadata("parent_event_id", batch_event.id)
                    await tool_event.update_metadata("call_id", call_id)
                    await session.add_event_and_save(tool_event)
                    
                    # Add to results
                    tool_result = ToolResult(
                        tool=tool_name,
                        call_id=call_id,
                        args=args,
                        result=result,
                        error=None
                    )
                    results.append(tool_result)
                    continue
            
            # Execute the tool call with retry logic
            retries = 0
            max_attempts = self.max_retries + 1 if self.enable_retries else 1
            
            while retries < max_attempts:
                try:
                    # Call the tool
                    result = await process_tool_calls(
                        [{"id": call_id, "type": "function", "function": function}],
                        callback=None
                    )
                    
                    if not result:
                        raise ValueError(f"No result returned for tool {tool_name}")
                    
                    tool_result = result[0]
                    
                    # Cache the result if enabled
                    if self.enable_caching and cache_key and not cache_hit:
                        self.cache[cache_key] = tool_result.result
                    
                    # Create tool call event
                    tool_event = await SessionEvent.create_with_tokens(
                        message={
                            "tool": tool_name,
                            "arguments": args,
                            "result": tool_result.result,
                            "error": tool_result.error
                        },
                        prompt=f"{tool_name}({json.dumps(args, default=str)})",
                        completion=json.dumps(tool_result.result, default=str) if tool_result.result else "",
                        model="tool-execution",
                        source=EventSource.SYSTEM,
                        type=EventType.TOOL_CALL
                    )
                    await tool_event.update_metadata("parent_event_id", batch_event.id)
                    await tool_event.update_metadata("call_id", call_id)
                    await tool_event.update_metadata("attempt", retries + 1)
                    await session.add_event_and_save(tool_event)
                    
                    # Add to results
                    results.append(tool_result)
                    break
                
                except Exception as e:
                    # Log the error
                    error_msg = str(e)
                    logger.warning(f"Tool call failed: {error_msg}")
                    
                    # Create retry notice if not the last attempt
                    retries += 1
                    if retries < max_attempts:
                        # Add retry notice
                        retry_event = SessionEvent(
                            message=f"Retry {retries}/{self.max_retries} for tool {tool_name}: {error_msg}",
                            source=EventSource.SYSTEM,
                            type=EventType.SUMMARY,
                            metadata={
                                "parent_event_id": batch_event.id,
                                "call_id": call_id,
                                "attempt": retries,
                                "retry": True
                            }
                        )
                        await session.add_event_and_save(retry_event)
                        
                        # Wait before retrying
                        await asyncio.sleep(self.retry_delay)
                    else:
                        # Last attempt failed, add error event
                        error_event = await SessionEvent.create_with_tokens(
                            message={
                                "tool": tool_name,
                                "arguments": args,
                                "result": None,
                                "error": error_msg
                            },
                            prompt=f"{tool_name}({json.dumps(args, default=str)})",
                            completion=error_msg,
                            model="tool-execution",
                            source=EventSource.SYSTEM,
                            type=EventType.TOOL_CALL
                        )
                        await error_event.update_metadata("parent_event_id", batch_event.id)
                        await error_event.update_metadata("call_id", call_id)
                        await error_event.update_metadata("attempt", retries)
                        await error_event.update_metadata("failed", True)
                        await session.add_event_and_save(error_event)
                        
                        # Add to results
                        tool_result = ToolResult(
                            tool=tool_name,
                            call_id=call_id,
                            args=args,
                            result=None,
                            error=error_msg
                        )
                        results.append(tool_result)
        
        return results
    
    async def _get_cache_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Generate a cache key for a tool call asynchronously.
        
        Args:
            tool_name: Name of the tool
            args: Arguments to the tool
            
        Returns:
            A cache key string
        """
        key_data = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()