#!/usr/bin/env python3
# examples/session_aware_tool_processor.py
"""
Example demonstrating the SessionAwareToolProcessor.

This example shows how to:
1. Create sessions and tools
2. Process LLM responses with tool calls
3. Execute tools and record results in the session
4. Handle retries when tool calls are not found
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from uuid import uuid4

# Import session manager components
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from a2a_session_manager.session_aware_tool_processor import SessionAwareToolProcessor

# Import tool processor components (simulated for this example)
from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.models.tool_result import ToolResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simulated tool definitions
TOOLS = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "args": {
            "location": {
                "type": "string",
                "description": "The city or location to get weather for"
            }
        }
    },
    {
        "name": "calculate",
        "description": "Perform a calculation",
        "args": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate"
            }
        }
    }
]

# Simulated tool execution
async def execute_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool and return results."""
    logger.info(f"Executing tool: {tool_name} with args: {args}")
    
    if tool_name == "get_weather":
        location = args.get("location", "Unknown")
        return {
            "temperature": 72,
            "condition": "Sunny",
            "humidity": 45,
            "location": location
        }
    elif tool_name == "calculate":
        expression = args.get("expression", "0")
        try:
            result = eval(expression)  # Note: eval is used for demonstration only
            return {"result": result}
        except Exception as e:
            return {"error": f"Calculation error: {str(e)}"}
    else:
        return {"error": f"Unknown tool: {tool_name}"}

# Simulate ToolProcessor for the example
# Mock ToolResult class that matches the expected structure
class ToolResult:
    """A mock of the ToolResult class from chuk_tool_processor."""
    
    def __init__(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]):
        self.tool_name = tool_name
        self.arguments = arguments
        self.result = result
        # Add the 'tool' field that seems to be required
        self.tool = tool_name
    
    def model_dump(self) -> Dict[str, Any]:
        """Simulate Pydantic's model_dump method."""
        return {
            "tool_name": self.tool_name,
            "tool": self.tool,
            "arguments": self.arguments,
            "result": self.result
        }


class SimpleToolProcessor(ToolProcessor):
    """A simplified version of ToolProcessor for the example."""
    
    def __init__(self, tools: List[Dict]):
        self.tools = tools
        self.tool_map = {t["name"]: t for t in tools}
    
    async def process_text(self, text: str) -> List[ToolResult]:
        """Process text to extract and execute tool calls."""
        try:
            # Parse the text as JSON to find tool calls
            data = json.loads(text)
            
            # Check for tool_calls in the data
            if "tool_calls" in data:
                results = []
                for tool_call in data["tool_calls"]:
                    if tool_call.get("type") == "function":
                        function = tool_call.get("function", {})
                        tool_name = function.get("name")
                        
                        if tool_name in self.tool_map:
                            # Parse arguments
                            args_str = function.get("arguments", "{}")
                            try:
                                args = json.loads(args_str)
                            except json.JSONDecodeError:
                                args = {}
                            
                            # Execute the tool
                            result = await execute_tool(tool_name, args)
                            
                            # Create a ToolResult
                            tool_result = ToolResult(
                                tool_name=tool_name,
                                arguments=args,
                                result=result
                            )
                            results.append(tool_result)
                
                return results
        except json.JSONDecodeError:
            # If it's not valid JSON, look for tool calls in plain text format
            # This is a simplistic implementation for the example
            if "get_weather" in text and "location" in text:
                # Extract location using a simple pattern (in a real system, use proper parsing)
                import re
                match = re.search(r"location\s*:\s*['\"](.*?)['\"]", text)
                if match:
                    location = match.group(1)
                    result = await execute_tool("get_weather", {"location": location})
                    return [ToolResult(
                        tool_name="get_weather",
                        arguments={"location": location},
                        result=result
                    )]
            
            elif "calculate" in text and "expression" in text:
                match = re.search(r"expression\s*:\s*['\"](.*?)['\"]", text)
                if match:
                    expression = match.group(1)
                    result = await execute_tool("calculate", {"expression": expression})
                    return [ToolResult(
                        tool_name="calculate",
                        arguments={"expression": expression},
                        result=result
                    )]
        
        # If no tool calls found, return empty list
        return []


async def simulate_llm_call(prompt: str, retry_prompt: Optional[str] = None) -> Dict[str, Any]:
    """Simulate an LLM call that returns tool calls."""
    logger.info(f"LLM Call with prompt: {prompt[:100]}...")
    
    # If this is a retry, generate a different response
    if retry_prompt:
        logger.info(f"Using retry prompt: {retry_prompt}")
        
        # For retries, generate a proper tool call
        return {
            "role": "assistant",
            "content": "Let me fix my response.",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "New York"}'
                    }
                }
            ]
        }
    
    # Check if prompt contains certain keywords to determine response
    if "weather" in prompt.lower():
        if "invalid" in prompt.lower():
            # Generate an invalid response to test retry logic
            return {
                "role": "assistant",
                "content": "I'll check the weather for you, but I need to use a tool for that."
                # No tool_calls field to test retry logic
            }
        else:
            # Normal weather query
            return {
                "role": "assistant",
                "content": "I'll check the weather for you.",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "New York"}'
                        }
                    }
                ]
            }
    elif "calculate" in prompt.lower():
        return {
            "role": "assistant",
            "content": "I'll calculate that for you.",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "calculate",
                        "arguments": '{"expression": "42 * 2"}'
                    }
                }
            ]
        }
    else:
        # Generic response with no tool calls
        return {
            "role": "assistant",
            "content": "I'm an AI assistant. How can I help you today?"
        }


async def demonstrate_successful_tool_call():
    """Demonstrate a successful tool call."""
    logger.info("\n=== Demonstrating Successful Tool Call ===")
    
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a new session
    session = Session()
    store.save(session)
    session_id = session.id
    logger.info(f"Created session with ID: {session_id}")
    
    # Add a user message
    user_msg = SessionEvent(
        message="What's the weather like in New York?",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    store.save(session)
    
    # Create the session-aware tool processor
    tool_processor = SimpleToolProcessor(TOOLS)
    session_processor = SessionAwareToolProcessor(
        session_id=session_id,
        max_llm_retries=2
    )
    
    # Monkey-patch the process_text method (in a real application, you'd properly subclass)
    session_processor.process_text = tool_processor.process_text
    
    # Simulate LLM call
    prompt = "What's the weather like in New York?"
    llm_response = await simulate_llm_call(prompt)
    
    # Process the LLM response through the session-aware processor
    async def llm_call_fn(retry_prompt):
        return await simulate_llm_call(prompt, retry_prompt)
    
    results = await session_processor.process_llm_message(llm_response, llm_call_fn)
    
    # Print results
    logger.info(f"Tool results: {json.dumps([r.model_dump() for r in results], indent=2)}")
    
    # Check the session for recorded events
    session = store.get(session_id)
    logger.info(f"Session now has {len(session.events)} events and {len(session.runs)} runs")
    
    # Print event types to see what was recorded
    event_types = [e.type.value for e in session.events]
    logger.info(f"Event types in session: {event_types}")
    
    return session


async def demonstrate_retry_mechanism():
    """Demonstrate the retry mechanism when no tool calls are found."""
    logger.info("\n=== Demonstrating Retry Mechanism ===")
    
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a new session
    session = Session()
    store.save(session)
    session_id = session.id
    logger.info(f"Created session with ID: {session_id}")
    
    # Add a user message
    user_msg = SessionEvent(
        message="Check the invalid weather format please",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    store.save(session)
    
    # Create the session-aware tool processor
    tool_processor = SimpleToolProcessor(TOOLS)
    session_processor = SessionAwareToolProcessor(
        session_id=session_id,
        max_llm_retries=2,
        llm_retry_prompt="Your previous response didn't contain a valid tool call. Please try again with a proper tool_call."
    )
    
    # Monkey-patch the process_text method (in a real application, you'd properly subclass)
    session_processor.process_text = tool_processor.process_text
    
    # Simulate LLM call that will require a retry
    prompt = "Check the invalid weather format please"
    llm_response = await simulate_llm_call(prompt)
    
    # Process the LLM response through the session-aware processor
    async def llm_call_fn(retry_prompt):
        return await simulate_llm_call(prompt, retry_prompt)
    
    results = await session_processor.process_llm_message(llm_response, llm_call_fn)
    
    # Print results
    logger.info(f"Tool results after retry: {json.dumps([r.model_dump() for r in results], indent=2)}")
    
    # Check the session for recorded events
    session = store.get(session_id)
    logger.info(f"Session now has {len(session.events)} events and {len(session.runs)} runs")
    
    # Print event types to see what was recorded
    event_types = [e.type.value for e in session.events]
    logger.info(f"Event types in session: {event_types}")
    
    # Check for summary events (retries)
    summary_events = [e for e in session.events if e.type == EventType.SUMMARY]
    if summary_events:
        logger.info(f"Found {len(summary_events)} summary events (retries)")
        for i, evt in enumerate(summary_events):
            logger.info(f"  Summary {i+1}: {evt.message}")
    
    return session


async def demonstrate_failed_retry():
    """Demonstrate what happens when max retries is exceeded."""
    logger.info("\n=== Demonstrating Failed Retry ===")
    
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a new session
    session = Session()
    store.save(session)
    session_id = session.id
    logger.info(f"Created session with ID: {session_id}")
    
    # Add a user message
    user_msg = SessionEvent(
        message="This is a generic query with no tool call",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    store.save(session)
    
    # Create the session-aware tool processor with only 1 retry
    tool_processor = SimpleToolProcessor(TOOLS)
    session_processor = SessionAwareToolProcessor(
        session_id=session_id,
        max_llm_retries=1  # Only allow 1 retry
    )
    
    # Override process_text to always return empty results (forcing retry failure)
    async def always_empty_process_text(text):
        return []
    
    # Monkey-patch the process_text method
    session_processor.process_text = always_empty_process_text
    
    # Simulate LLM call
    prompt = "This is a generic query with no tool call"
    llm_response = await simulate_llm_call(prompt)
    
    # Process the LLM response through the session-aware processor
    async def llm_call_fn(retry_prompt):
        # Even on retry, we'll get a response that process_text can't extract tools from
        return await simulate_llm_call(prompt, retry_prompt)
    
    try:
        results = await session_processor.process_llm_message(llm_response, llm_call_fn)
        logger.info("Unexpectedly succeeded when failure was expected")
    except RuntimeError as e:
        logger.info(f"Expected error occurred: {str(e)}")
    
    # Check the session for recorded events
    session = store.get(session_id)
    logger.info(f"Session now has {len(session.events)} events and {len(session.runs)} runs")
    
    # Check run status
    if session.runs:
        logger.info(f"Run status: {session.runs[0].status.value}")
    
    return session


async def demonstrate_multiple_tools():
    """Demonstrate processing multiple tool calls in one response."""
    logger.info("\n=== Demonstrating Multiple Tools ===")
    
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a new session
    session = Session()
    store.save(session)
    session_id = session.id
    logger.info(f"Created session with ID: {session_id}")
    
    # Add a user message
    user_msg = SessionEvent(
        message="What's the weather in New York and calculate 42 * 2",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_msg)
    store.save(session)
    
    # Create the session-aware tool processor
    tool_processor = SimpleToolProcessor(TOOLS)
    session_processor = SessionAwareToolProcessor(
        session_id=session_id
    )
    
    # Monkey-patch for demo
    session_processor.process_text = tool_processor.process_text
    
    # Create an LLM response with multiple tool calls
    llm_response = {
        "role": "assistant",
        "content": "I'll check both the weather and do that calculation for you.",
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"location": "New York"}'
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "arguments": '{"expression": "42 * 2"}'
                }
            }
        ]
    }
    
    # Process the LLM response
    async def llm_call_fn(retry_prompt):
        return llm_response  # No need to change on retry for this example
    
    results = await session_processor.process_llm_message(llm_response, llm_call_fn)
    
    # Print results
    logger.info(f"Multiple tool results: {json.dumps([r.model_dump() for r in results], indent=2)}")
    
    # Check the session for recorded events
    session = store.get(session_id)
    logger.info(f"Session now has {len(session.events)} events and {len(session.runs)} runs")
    
    # Count tool call events
    tool_calls = [e for e in session.events if e.type == EventType.TOOL_CALL]
    logger.info(f"Found {len(tool_calls)} tool call events")
    
    return session


async def main():
    """Run all demonstrations."""
    logger.info("Starting SessionAwareToolProcessor demonstrations")
    
    # Demonstrate the different scenarios
    await demonstrate_successful_tool_call()
    await demonstrate_retry_mechanism()
    try:
        await demonstrate_failed_retry()
    except Exception as e:
        logger.info(f"Failed retry demonstration completed with: {str(e)}")
    await demonstrate_multiple_tools()
    
    logger.info("All demonstrations completed")


if __name__ == "__main__":
    asyncio.run(main())