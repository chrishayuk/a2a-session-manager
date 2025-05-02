# a2a_session_manager/infinite_conversation.py
"""
InfiniteConversationManager for a2a_session_manager.

This module provides a solution for managing conversations that can
extend indefinitely without hitting token limits, using hierarchical
sessions and automatic summarization.

Features:
- Automatic session segmentation based on token thresholds
- Summary generation for conversation segments
- Context bridges between parent and child sessions
- Hierarchical context building for LLM calls
- Support for multiple summarization strategies
"""

from typing import List, Dict, Any, Optional, Callable, Union, TypeVar, Generic, Protocol, Tuple
from datetime import datetime, timezone
import logging
import asyncio
from enum import Enum  # Import Enum at the top of the file

from a2a_session_manager.models.session import Session, MessageT
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.token_usage import TokenUsage
from a2a_session_manager.storage import SessionStoreProvider

# Set up logging
logger = logging.getLogger(__name__)

# Type for LLM callback
T = TypeVar('T')


class SummarizationStrategy(str, Enum):
    """Strategies for summarizing conversation segments."""
    BASIC = "basic"             # Simple summary of the entire conversation
    KEY_POINTS = "key_points"   # Extracts key points from the conversation
    QUERY_FOCUSED = "query"     # Focuses summary on recent user queries
    TOPIC_BASED = "topic"       # Organizes summary by conversation topics


class LLMCallbackProtocol(Protocol):
    """Protocol for LLM callback functions."""
    async def __call__(self, messages: List[Dict[str, Any]], model: str) -> str: ...


class InfiniteConversationManager(Generic[MessageT]):
    """
    Manages infinitely long conversations using hierarchical sessions.
    
    Uses session hierarchy and summarization to enable conversations
    that can continue indefinitely without hitting token limits.
    """
    
    def __init__(
        self,
        token_threshold: int = 6000,
        summary_model: str = "gpt-3.5-turbo",
        max_context_depth: int = 3,
        summarization_strategy: SummarizationStrategy = SummarizationStrategy.BASIC,
        session_class: Optional[type] = None,
        store_provider = None
    ):
        """
        Initialize the InfiniteConversationManager.
        
        Args:
            token_threshold: Maximum tokens before creating a new segment
            summary_model: Model to use for generating summaries
            max_context_depth: Maximum number of ancestor sessions to include
            summarization_strategy: Strategy for generating summaries
            session_class: Optional custom Session class
            store_provider: Optional custom store provider
        """
        self.token_threshold = token_threshold
        self.summary_model = summary_model
        self.max_context_depth = max_context_depth
        self.summarization_strategy = summarization_strategy
        self.session_class = session_class or Session
        
        # Get the store from the provider
        self.store_provider = store_provider or SessionStoreProvider
        self.store = self.store_provider.get_store()
    
    async def process_message(
        self,
        session_id: str,
        message: Union[str, Dict[str, Any], MessageT],
        source: EventSource,
        llm_callback: LLMCallbackProtocol,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Process a message, creating new session segments as needed.
        
        Args:
            session_id: Current session ID
            message: Message content
            source: Message source (USER or LLM)
            llm_callback: Callback for LLM operations (summarization)
            metadata: Optional metadata for the event
            
        Returns:
            The session ID to use (may be a new child session)
        """
        # Get the current session
        session = self.store.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Add the message to the current session
        event = SessionEvent(
            message=message,
            source=source,
            type=EventType.MESSAGE,
            metadata=metadata or {}
        )
        session.add_event(event)
        self.store.save(session)
        
        # Check if we need to create a new segment
        token_count = self._get_session_token_count(session)
        logger.debug(f"Session {session_id} token count: {token_count}/{self.token_threshold}")
        
        if token_count >= self.token_threshold:
            logger.info(f"Token threshold reached: {token_count} >= {self.token_threshold}")
            logger.info(f"Creating a new session segment for session {session_id}")
            
            # Create a summary of the current session
            summary = await self._create_summary(session, llm_callback)
            
            # Add summary to the current session
            summary_event = SessionEvent(
                message=summary,
                source=EventSource.SYSTEM,
                type=EventType.SUMMARY,
                metadata={"auto_generated": True, "summarization_strategy": self.summarization_strategy}
            )
            session.add_event(summary_event)
            self.store.save(session)
            
            # Create a new child session
            child = self.session_class(parent_id=session.id)
            
            # Add context bridge event to the new session
            bridge_event = SessionEvent(
                message=f"Continuation from previous conversation. Summary: {summary}",
                source=EventSource.SYSTEM,
                type=EventType.REFERENCE,  # Using REFERENCE type for context bridges
                metadata={
                    "parent_session_id": session.id,
                    "context_bridge": True,
                    "summary_reference": True
                }
            )
            child.add_event(bridge_event)
            
            # Save the new child session
            self.store.save(child)
            
            logger.info(f"Created new child session: {child.id}")
            return child.id
        
        # If no branching needed, return the current session ID
        return session_id
    
    def _get_session_token_count(self, session: Session) -> int:
        """
        Get the token count for a session.
        
        Uses the session's built-in token tracking if available,
        or estimates based on event content.
        
        Args:
            session: The session to count tokens for
            
        Returns:
            Estimated token count
        """
        # If session has total_tokens property, use it
        if hasattr(session, 'total_tokens') and session.total_tokens > 0:
            return session.total_tokens
        
        # Otherwise estimate based on event content
        total_tokens = 0
        for event in session.events:
            # If event has token usage info, use it
            if hasattr(event, 'token_usage') and event.token_usage:
                total_tokens += event.token_usage.total_tokens
                continue
                
            # Otherwise estimate based on content
            message = event.message
            if isinstance(message, str):
                # Rough approximation: 4 chars ≈ 1 token
                total_tokens += len(message) // 4
            elif isinstance(message, dict):
                # For dict messages, estimate based on string representation
                total_tokens += len(str(message)) // 4
            else:
                # For other types, use a conservative estimate
                total_tokens += 10  # Minimal token count for structural elements
        
        return total_tokens
    
    async def _create_summary(
        self,
        session: Session,
        llm_callback: LLMCallbackProtocol
    ) -> str:
        """
        Create a summary of the session content using the selected strategy.
        
        Args:
            session: The session to summarize
            llm_callback: Function to call the LLM for summarization
            
        Returns:
            A summary of the session content
        """
        # Use different prompt templates based on strategy
        if self.summarization_strategy == SummarizationStrategy.KEY_POINTS:
            return await self._create_key_points_summary(session, llm_callback)
        elif self.summarization_strategy == SummarizationStrategy.QUERY_FOCUSED:
            return await self._create_query_focused_summary(session, llm_callback)
        elif self.summarization_strategy == SummarizationStrategy.TOPIC_BASED:
            return await self._create_topic_based_summary(session, llm_callback)
        else:
            # Default to basic summary
            return await self._create_basic_summary(session, llm_callback)
    
    async def _create_basic_summary(
        self,
        session: Session,
        llm_callback: LLMCallbackProtocol
    ) -> str:
        """Create a basic summary of the entire conversation."""
        # Format conversation for summarization
        formatted_messages = self._format_conversation_for_summary(session)
        
        # Create summarization prompt
        system_message = {
            "role": "system",
            "content": "Create a concise summary of this conversation that captures key information, main topics discussed, and important points raised. This summary will be used as context for continuing the conversation."
        }
        
        # Build prompt and call LLM
        prompt = [system_message] + formatted_messages
        return await llm_callback(prompt, self.summary_model)
    
    async def _create_key_points_summary(
        self,
        session: Session,
        llm_callback: LLMCallbackProtocol
    ) -> str:
        """Create a summary focused on extracting key points."""
        # Format conversation for summarization
        formatted_messages = self._format_conversation_for_summary(session)
        
        # Create summarization prompt
        system_message = {
            "role": "system",
            "content": "Extract the key points and important information from this conversation. Focus on facts, decisions, questions, and conclusions rather than summarizing the entire conversation flow. This extraction will be used as context for continuing the conversation."
        }
        
        # Build prompt and call LLM
        prompt = [system_message] + formatted_messages
        return await llm_callback(prompt, self.summary_model)
    
    async def _create_query_focused_summary(
        self,
        session: Session,
        llm_callback: LLMCallbackProtocol
    ) -> str:
        """Create a summary focused on recent user queries and concerns."""
        # Format conversation for summarization
        formatted_messages = self._format_conversation_for_summary(session)
        
        # Create summarization prompt
        system_message = {
            "role": "system",
            "content": "Summarize this conversation with a focus on the user's main questions, concerns, and interests. Prioritize capturing what matters most to the user and the key information they're seeking. This summary will be used as context for continuing the conversation."
        }
        
        # Build prompt and call LLM
        prompt = [system_message] + formatted_messages
        return await llm_callback(prompt, self.summary_model)
    
    async def _create_topic_based_summary(
        self,
        session: Session,
        llm_callback: LLMCallbackProtocol
    ) -> str:
        """Create a summary organized by conversation topics."""
        # Format conversation for summarization
        formatted_messages = self._format_conversation_for_summary(session)
        
        # Create summarization prompt
        system_message = {
            "role": "system",
            "content": "Identify the main topics discussed in this conversation and create a summary organized by these topics. For each topic, capture the key points and relevant information. This organized summary will be used as context for continuing the conversation."
        }
        
        # Build prompt and call LLM
        prompt = [system_message] + formatted_messages
        return await llm_callback(prompt, self.summary_model)
    
    def _format_conversation_for_summary(self, session: Session) -> List[Dict[str, Any]]:
        """Format session events as a conversation for summarization."""
        formatted_messages = []
        
        for event in session.events:
            if event.type == EventType.MESSAGE:
                # Determine role
                role = "user" if event.source == EventSource.USER else "assistant"
                
                # Extract message content
                content = event.message
                if isinstance(content, dict) and "content" in content:
                    content = content["content"]
                elif not isinstance(content, str):
                    content = str(content)
                
                # Add to formatted messages
                formatted_messages.append({"role": role, "content": content})
        
        return formatted_messages
    
    def build_context_for_llm(
        self,
        session_id: str,
        max_tokens: Optional[int] = None,
        include_summaries: bool = True,
        context_message_limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Build context for an LLM call using the session and its ancestors.
        
        Args:
            session_id: The ID of the session to build context from
            max_tokens: Optional maximum tokens to include
            include_summaries: Whether to include summaries from ancestors
            context_message_limit: Optional limit on number of messages to include
            
        Returns:
            List of messages formatted for LLM API calls
        """
        session = self.store.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Start with messages from current session
        messages = self._extract_messages_from_session(session, context_message_limit)
        
        # Add context from ancestors if summaries are enabled
        if include_summaries:
            # Get ancestors up to max depth
            ancestors = session.ancestors()
            ancestors = ancestors[:self.max_context_depth]
            
            # Add summaries in reverse order (oldest first)
            summary_contexts = []
            for ancestor in reversed(ancestors):
                summary = self._get_latest_summary(ancestor)
                if summary:
                    summary_contexts.append({
                        "role": "system", 
                        "content": f"Previous conversation context: {summary}"
                    })
            
            # Add summaries at the beginning
            messages = summary_contexts + messages
        
        # Apply token limit if specified
        if max_tokens:
            messages = self._limit_context_tokens(messages, max_tokens)
        
        return messages
    
    def _extract_messages_from_session(
        self,
        session: Session,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Extract messages from a session in the format needed for LLM calls."""
        # Get message events
        message_events = [e for e in session.events if e.type == EventType.MESSAGE]
        
        # Apply limit if specified (take most recent messages)
        if limit and len(message_events) > limit:
            message_events = message_events[-limit:]
        
        # Format as LLM messages
        messages = []
        for event in message_events:
            # Determine role
            role = "user" if event.source == EventSource.USER else "assistant"
            
            # Extract content
            content = event.message
            if isinstance(content, dict) and "content" in content:
                content = content["content"]
            elif not isinstance(content, str):
                content = str(content)
            
            messages.append({"role": role, "content": content})
        
        # Also include context bridge events as system messages
        for event in session.events:
            if (event.type == EventType.REFERENCE and 
                event.metadata and 
                event.metadata.get("context_bridge")):
                messages.insert(0, {"role": "system", "content": event.message})
        
        return messages
    
    def _get_latest_summary(self, session: Session) -> Optional[str]:
        """Get the latest summary from a session."""
        summary_events = [e for e in session.events if e.type == EventType.SUMMARY]
        if not summary_events:
            return None
        
        latest_summary = summary_events[-1]
        content = latest_summary.message
        
        # Extract content if needed
        if isinstance(content, dict) and "content" in content:
            content = content["content"]
        elif not isinstance(content, str):
            content = str(content)
            
        return content
    
    def _limit_context_tokens(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int
    ) -> List[Dict[str, Any]]:
        """Limit context to stay under token limit."""
        if not messages:
            return []
            
        # Ensure we have the first few system messages and the most recent messages
        # Start by separating system messages from regular conversation
        system_messages = [m for m in messages if m.get("role") == "system"]
        conversation = [m for m in messages if m.get("role") != "system"]
        
        # Count tokens for system messages
        system_token_count = sum(len(m.get("content", "")) // 4 for m in system_messages)
        
        # Calculate remaining tokens for conversation
        remaining_tokens = max_tokens - system_token_count
        
        # If we don't have enough tokens for conversation, prioritize most recent messages
        if remaining_tokens <= 0:
            # Keep at least one recent message
            return system_messages + [conversation[-1]] if conversation else []
        
        # Start with the most recent message
        included_conversation = []
        token_count = 0
        
        # Add messages from most recent to oldest until we hit the limit
        for msg in reversed(conversation):
            # Estimate tokens for this message
            content = msg.get("content", "")
            msg_tokens = len(content) // 4 if isinstance(content, str) else len(str(content)) // 4
            
            # If adding this message would exceed the limit, stop
            if token_count + msg_tokens > remaining_tokens and included_conversation:
                break
                
            # Add this message
            included_conversation.append(msg)
            token_count += msg_tokens
        
        # Reverse to get chronological order
        included_conversation.reverse()
        
        # Combine system messages with included conversation
        return system_messages + included_conversation
    
    def get_session_chain(self, session_id: str) -> List[Session]:
        """
        Get the complete chain of sessions from root to the specified session.
        
        Args:
            session_id: The ID of the session to get the chain for
            
        Returns:
            List of sessions in the chain, from root to the specified session
        """
        session = self.store.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Get ancestors
        ancestors = session.ancestors()
        
        # Build chain in order from root to current
        chain = list(reversed(ancestors))
        chain.append(session)
        
        return chain
    
    def get_full_conversation_history(
        self,
        session_id: str,
        include_system_events: bool = False
    ) -> List[Tuple[str, str, Any]]:
        """
        Get the complete conversation history across all session segments.
        
        Args:
            session_id: The ID of the session to get history for
            include_system_events: Whether to include system events
            
        Returns:
            List of (role, source, content) tuples in chronological order
        """
        # Get the chain of sessions
        chain = self.get_session_chain(session_id)
        
        # Extract messages from each session
        history = []
        for session in chain:
            for event in session.events:
                # Skip non-message events unless include_system_events is True
                if event.type != EventType.MESSAGE:
                    if not include_system_events:
                        continue
                    
                    # For system events we want to include
                    if event.type == EventType.SUMMARY:
                        history.append(("system", "SUMMARY", event.message))
                    elif event.type == EventType.REFERENCE and event.metadata.get("context_bridge"):
                        history.append(("system", "CONTEXT_BRIDGE", event.message))
                    
                    # Skip other system events
                    continue
                
                # For message events
                role = "user" if event.source == EventSource.USER else "assistant"
                history.append((role, event.source.value, event.message))
        
        return history