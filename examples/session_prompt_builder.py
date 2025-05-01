#!/usr/bin/env python3
# examples/session_prompt_builder.py
"""
Example script demonstrating the use of the Session Prompt Builder.

This example shows how to:
1. Create and manipulate sessions
2. Use different prompt building strategies
3. Generate LLM-ready prompts from sessions
4. Integrate with a simple LLM client
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

# Import session manager components
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from a2a_session_manager.session_prompt_builder import build_prompt_from_session, PromptStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simulated LLM client for demonstration purposes
async def call_llm(messages: List[Dict[str, Any]], model: str = "gpt-3.5-turbo") -> Dict[str, Any]:
    """Simulate calling an LLM API."""
    logger.info(f"Calling LLM with {len(messages)} messages")
    
    # In a real implementation, this would make an API call
    # For demonstration, we'll just return a simulated response
    prompt_str = "\n".join(f"{msg.get('role')}: {msg.get('content')}" for msg in messages)
    logger.info(f"Prompt:\n{prompt_str[:500]}...")
    
    # Simulate tool call if we detect certain keywords
    if "weather" in prompt_str.lower():
        return {
            "role": "assistant",
            "content": "I'll check the weather for you.",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"location": "New York"})
                    }
                }
            ]
        }
    
    # Otherwise, return a normal message
    return {
        "role": "assistant",
        "content": "I'm a simulated LLM response. I would respond to your query here."
    }

# Simulated tool execution
async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate executing a tool."""
    logger.info(f"Executing tool: {tool_name} with arguments: {arguments}")
    
    if tool_name == "get_weather":
        return {
            "temperature": 72,
            "condition": "Sunny",
            "humidity": 45,
            "location": arguments.get("location", "Unknown")
        }
    
    return {"error": "Unknown tool"}

async def demonstrate_minimal_strategy():
    """Demonstrate the minimal prompt strategy."""
    logger.info("\n=== Demonstrating MINIMAL Prompt Strategy ===")
    
    # Create a new session
    session = Session()
    
    # Add a user message
    user_msg = SessionEvent(
        message="What's the weather like in New York?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    
    # Build prompt with minimal strategy
    prompt = build_prompt_from_session(session, PromptStrategy.MINIMAL)
    logger.info(f"Minimal prompt with only user message:\n{json.dumps(prompt, indent=2)}")
    
    # Call LLM
    llm_response = await call_llm(prompt)
    
    # Add LLM response to session
    assistant_msg = SessionEvent(
        message=llm_response,
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(assistant_msg)
    
    # Execute tool call if present
    if "tool_calls" in llm_response:
        for tool_call in llm_response.get("tool_calls", []):
            if tool_call.get("type") == "function":
                func = tool_call.get("function", {})
                tool_name = func.get("name")
                arguments = json.loads(func.get("arguments", "{}"))
                
                # Execute the tool
                result = await execute_tool(tool_name, arguments)
                
                # Add tool result as a child of the assistant message
                tool_event = SessionEvent(
                    message={
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "result": result
                    },
                    source=EventSource.SYSTEM,
                    type=EventType.TOOL_CALL,
                    metadata={"parent_event_id": assistant_msg.id}
                )
                session.add_event(tool_event)
    
    # Build prompt again with the updated session
    prompt = build_prompt_from_session(session, PromptStrategy.MINIMAL)
    logger.info(f"Minimal prompt after tool execution:\n{json.dumps(prompt, indent=2)}")
    
    return session

async def demonstrate_conversation_strategy():
    """Demonstrate the conversation prompt strategy with a multi-turn dialog."""
    logger.info("\n=== Demonstrating CONVERSATION Prompt Strategy ===")
    
    # Create a new session
    session = Session()
    
    # Simulate a 3-turn conversation
    conversation = [
        {"role": "user", "content": "Tell me about quantum computing."},
        {"role": "assistant", "content": "Quantum computing uses quantum bits or qubits that can exist in multiple states simultaneously, unlike classical bits."},
        {"role": "user", "content": "How is that different from classical computing?"},
        {"role": "assistant", "content": "Classical computing uses bits that are either 0 or 1, while quantum computing uses qubits that can be in a superposition of states."},
        {"role": "user", "content": "What practical applications does it have?"}
    ]
    
    # Add conversation to session
    for msg in conversation:
        event = SessionEvent(
            message=msg["content"],
            source=EventSource.USER if msg["role"] == "user" else EventSource.LLM,
            type=EventType.MESSAGE
        )
        session.add_event(event)
    
    # Build prompt with conversation strategy
    prompt = build_prompt_from_session(session, PromptStrategy.CONVERSATION)
    logger.info(f"Conversation prompt:\n{json.dumps(prompt, indent=2)}")
    
    return session

async def demonstrate_hierarchical_strategy():
    """Demonstrate the hierarchical prompt strategy with parent-child sessions."""
    logger.info("\n=== Demonstrating HIERARCHICAL Prompt Strategy ===")
    
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create parent session
    parent = Session()
    
    # Add messages to parent
    parent.add_event(SessionEvent(
        message="I want to plan a trip to Japan.",
        source=EventSource.USER,
        type=EventType.MESSAGE
    ))
    
    parent.add_event(SessionEvent(
        message="Great! Japan is a wonderful destination. What kind of activities are you interested in?",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    ))
    
    parent.add_event(SessionEvent(
        message="I'm interested in both historical sites and nature.",
        source=EventSource.USER,
        type=EventType.MESSAGE
    ))
    
    # Add a summary to parent
    parent.add_event(SessionEvent(
        message="User is planning a trip to Japan and is interested in historical sites and nature.",
        source=EventSource.SYSTEM,
        type=EventType.SUMMARY
    ))
    
    # Save parent
    store.save(parent)
    
    # Create child session
    child = Session(parent_id=parent.id)
    
    # Add message to child
    child.add_event(SessionEvent(
        message="Can you suggest an itinerary for 7 days?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    ))
    
    # Save child
    store.save(child)
    
    # Build prompt with hierarchical strategy
    prompt = build_prompt_from_session(
        child, 
        PromptStrategy.HIERARCHICAL,
        include_parent_context=True
    )
    logger.info(f"Hierarchical prompt:\n{json.dumps(prompt, indent=2)}")
    
    return child

async def demonstrate_tool_focused_strategy():
    """Demonstrate the tool-focused prompt strategy."""
    logger.info("\n=== Demonstrating TOOL_FOCUSED Prompt Strategy ===")
    
    # Create a session with tool calls
    session = Session()
    
    # Add user message
    session.add_event(SessionEvent(
        message="What's the weather in New York, Tokyo, and London?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    ))
    
    # Add assistant message
    assistant_msg = SessionEvent(
        message="I'll check the weather for these cities.",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(assistant_msg)
    
    # Add multiple tool calls
    cities = ["New York", "Tokyo", "London"]
    weather = [
        {"temperature": 72, "condition": "Sunny"},
        {"temperature": 68, "condition": "Rainy"},
        {"temperature": 60, "condition": "Cloudy"}
    ]
    
    for i, city in enumerate(cities):
        tool_event = SessionEvent(
            message={
                "tool_name": "get_weather",
                "arguments": {"location": city},
                "result": weather[i]
            },
            source=EventSource.SYSTEM,
            type=EventType.TOOL_CALL,
            metadata={"parent_event_id": assistant_msg.id}
        )
        session.add_event(tool_event)
    
    # Build prompt with tool-focused strategy
    prompt = build_prompt_from_session(session, PromptStrategy.TOOL_FOCUSED)
    logger.info(f"Tool-focused prompt:\n{json.dumps(prompt, indent=2)}")
    
    return session

async def demonstrate_token_management():
    """Demonstrate prompt truncation to manage token limits."""
    logger.info("\n=== Demonstrating Token Management ===")
    
    # Create a session with many messages
    session = Session()
    
    # Add a long conversation
    for i in range(20):
        # Add user message
        session.add_event(SessionEvent(
            message=f"This is user message #{i+1}. It contains some text to increase token count.",
            source=EventSource.USER,
            type=EventType.MESSAGE
        ))
        
        # Add assistant message
        session.add_event(SessionEvent(
            message=f"This is assistant response #{i+1}. It also contains extra text to make the prompt longer.",
            source=EventSource.LLM,
            type=EventType.MESSAGE
        ))
    
    # Build prompt with conversation strategy and token limit
    from a2a_session_manager.session_prompt_builder import truncate_prompt_to_token_limit
    
    # First get the full prompt
    full_prompt = build_prompt_from_session(session, PromptStrategy.CONVERSATION)
    logger.info(f"Full prompt length: {len(full_prompt)} messages")
    
    # Then truncate it
    truncated_prompt = truncate_prompt_to_token_limit(full_prompt, max_tokens=500)
    logger.info(f"Truncated prompt length: {len(truncated_prompt)} messages")
    
    # Show the difference
    logger.info(f"Truncated prompt preview:\n{json.dumps(truncated_prompt[:5], indent=2)}")
    
    return session

async def main():
    """Run all demonstrations."""
    logger.info("Starting Session Prompt Builder demonstrations")
    
    # Demonstrate different strategies
    await demonstrate_minimal_strategy()
    await demonstrate_conversation_strategy()
    await demonstrate_hierarchical_strategy()
    await demonstrate_tool_focused_strategy()
    await demonstrate_token_management()
    
    logger.info("All demonstrations completed")

if __name__ == "__main__":
    asyncio.run(main())