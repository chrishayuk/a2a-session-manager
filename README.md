# chuk session manager

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, flexible session management system for AI applications.

## Overview

chuk session manager provides a comprehensive solution for tracking, persisting, and analyzing AI-based conversations and interactions. Whether you're building a simple chatbot or a complex agent-to-agent system, this library offers the building blocks to manage conversation state, hierarchy, and token usage.

## Features

- **Async-First Design**: Full async support for modern web applications and non-blocking I/O
- **Multiple Storage Backends**: Choose from in-memory, file-based, or Redis storage
- **Hierarchical Sessions**: Create parent-child relationships between sessions
- **Event Tracking**: Record all interactions with detailed metadata
- **Token Usage Monitoring**: Track token consumption and estimate costs
- **Run Management**: Organize sessions into logical execution runs
- **Prompt Building**: Generate optimized prompts from session data using multiple strategies
- **Tool Integration**: Track tool execution with parent-child event relationships
- **Infinite Conversations**: Support for infinitely long conversations through automatic segmentation
- **Extensible Design**: Easily extend with custom storage providers or event types

## Installation

```bash
# Basic installation
pip install chuk-session-manager

# With Redis support
pip install chuk-session-manager[redis]

# With tool processor integration
pip install chuk-session-manager[tools]

# With development tools
pip install chuk-session-manager[dev]

# Full installation with all dependencies
pip install chuk-session-manager[full]
```

## Quick Start

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

async def main():
    # Configure storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)

    # Create a session
    session = await Session.create()

    # Add an event
    session.add_event(SessionEvent(
        message="Hello, this is a user message.",
        source=EventSource.USER
    ))

    # Save session
    await store.save(session)

    # Retrieve session
    retrieved_session = await store.get(session.id)
    print(f"Retrieved session with ID: {retrieved_session.id}")
    
    # Work with hierarchical sessions
    child = await Session.create(parent_id=session.id)
    
    # Navigate hierarchy
    ancestors = await child.ancestors()
    print(f"Child's ancestors: {[a.id for a in ancestors]}")

# Run the async code
asyncio.run(main())
```

## Storage Providers

### In-Memory Storage

Ideal for testing and temporary applications:

```python
import asyncio
from chuk_session_manager.storage import InMemorySessionStore, SessionStoreProvider

async def example():
    # Configure store
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create and save a session
    session = await Session.create()
    await store.save(session)
    
    # List all sessions
    all_sessions = await store.list_sessions()
    print(f"All sessions: {all_sessions}")

# Run the example
asyncio.run(example())
```

### File-Based Storage

Persists sessions to JSON files with async I/O:

```python
import asyncio
from chuk_session_manager.storage.providers.file import FileSessionStore, create_file_session_store
from chuk_session_manager.storage import SessionStoreProvider

async def example():
    # Create file store
    store = FileSessionStore(directory="./sessions")
    SessionStoreProvider.set_store(store)
    
    # Create and save a session
    session = await Session.create()
    session.add_event(SessionEvent(
        message="This is saved to a file asynchronously!",
        source=EventSource.USER
    ))
    await store.save(session)
    
    # Retrieve the session
    retrieved = await store.get(session.id)
    print(f"Retrieved session with {len(retrieved.events)} events")

# Run the example
asyncio.run(example())
```

### Redis Storage

Distributed storage for production applications:

```python
import asyncio
from chuk_session_manager.storage.providers.redis import RedisSessionStore, create_redis_session_store
from chuk_session_manager.storage import SessionStoreProvider

async def example():
    # Create Redis store
    store = await create_redis_session_store(
        host="localhost",
        port=6379,
        db=0,
        key_prefix="session:",
        expiration_seconds=86400  # 24 hours
    )
    SessionStoreProvider.set_store(store)
    
    # Create and save a session
    session = await Session.create()
    await store.save(session)
    
    # Set expiration
    await store.set_expiration(session.id, 3600)  # 1 hour

# Run the example
asyncio.run(example())
```

## Token Usage Tracking

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

async def example():
    # Setup
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    session = await Session.create()
    
    # Add user message (no token tracking needed)
    user_message = "Explain quantum computing in simple terms"
    session.add_event(SessionEvent(
        message=user_message,
        source=EventSource.USER
    ))
    
    # Assistant response with token tracking
    assistant_response = "Quantum computing uses qubits that can be both 0 and 1 simultaneously, unlike classical bits."
    
    # Create event with automatic token counting
    assistant_event = SessionEvent.create_with_tokens(
        message=assistant_response,
        prompt=user_message,
        completion=assistant_response,
        model="gpt-4",
        source=EventSource.LLM
    )
    session.add_event(assistant_event)
    
    # Save the session
    await store.save(session)
    
    # Get token usage information
    print(f"Total tokens: {session.total_tokens}")
    print(f"Estimated cost: ${session.total_cost:.6f}")
    print(f"Prompt tokens: {assistant_event.token_usage.prompt_tokens}")
    print(f"Completion tokens: {assistant_event.token_usage.completion_tokens}")

# Run the example
asyncio.run(example())
```

## Hierarchical Sessions

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

async def example():
    # Setup
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a parent session
    parent = await Session.create()
    
    # Create child sessions
    child1 = await Session.create(parent_id=parent.id)
    child2 = await Session.create(parent_id=parent.id)
    
    # Create a grandchild session
    grandchild = await Session.create(parent_id=child1.id)
    
    # Navigate hierarchy
    ancestors = await grandchild.ancestors()
    print(f"Grandchild ancestors: {[a.id for a in ancestors]}")
    
    descendants = await parent.descendants()
    print(f"Parent descendants: {[d.id for d in descendants]}")

# Run the example
asyncio.run(example())
```

## Session Runs

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.session_run import SessionRun
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

async def example():
    # Setup
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    session = await Session.create()
    
    # Start a run
    run = SessionRun()
    run.mark_running()
    session.runs.append(run)
    
    # Add events to the run
    session.add_event(SessionEvent(
        message="Processing your request...",
        source=EventSource.SYSTEM,
        task_id=run.id
    ))
    
    # Complete the run
    run.mark_completed()
    
    # Save the session
    await store.save(session)
    
    # Check run information
    active_run = session.active_run
    print(f"Active run: {active_run.id if active_run else 'None'}")

# Run the example
asyncio.run(example())
```

## Prompt Builder

Generate optimized prompts from session data for LLM calls using various strategies:

```python
import asyncio
import json
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.models.event_type import EventType
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from chuk_session_manager.session_prompt_builder import build_prompt_from_session, PromptStrategy

async def example():
    # Setup
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    session = await Session.create()
    
    # Add a conversation with tool usage
    session.add_event(SessionEvent(
        message="What's the weather in New York?",
        source=EventSource.USER
    ))
    
    assistant_msg = SessionEvent(
        message="I'll check the weather for you.",
        source=EventSource.LLM
    )
    session.add_event(assistant_msg)
    
    # Add a tool call as a child of the assistant message
    tool_event = SessionEvent(
        message={
            "tool_name": "get_weather",
            "result": {"temperature": 72, "condition": "Sunny", "location": "New York"}
        },
        source=EventSource.SYSTEM,
        type=EventType.TOOL_CALL,
        metadata={"parent_event_id": assistant_msg.id}
    )
    session.add_event(tool_event)
    
    # Save the session
    await store.save(session)
    
    # Build prompts with different strategies
    minimal_prompt = await build_prompt_from_session(session, PromptStrategy.MINIMAL)
    conversation_prompt = await build_prompt_from_session(session, PromptStrategy.CONVERSATION)
    tool_prompt = await build_prompt_from_session(session, PromptStrategy.TOOL_FOCUSED)
    
    # Print one of the prompts
    print(json.dumps(tool_prompt, indent=2))

# Run the example
asyncio.run(example())
```

### Prompt Strategies

- **MINIMAL**: Includes only essential context (first user message, latest assistant response, and tool results)
- **TASK_FOCUSED**: Emphasizes the original task with minimal context
- **TOOL_FOCUSED**: Prioritizes tool usage information
- **CONVERSATION**: Includes more conversation history for a natural flow
- **HIERARCHICAL**: Leverages parent session context for multi-session conversations

## Session-Aware Tool Processor

Track tool execution within your sessions using the SessionAwareToolProcessor:

```python
import asyncio
import json
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from chuk_session_manager.session_aware_tool_processor import SessionAwareToolProcessor

# Example tool result class
class ToolResult:
    def __init__(self, tool, arguments, result):
        self.tool = tool
        self.arguments = arguments
        self.result = result
    
    def model_dump(self):
        return {"tool": self.tool, "arguments": self.arguments, "result": self.result}

async def example():
    # Setup
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    session = await Session.create()
    
    # Add initial user message
    session.add_event(SessionEvent(
        message="What's the weather in New York?",
        source=EventSource.USER
    ))
    await store.save(session)
    
    # Create tool processor
    processor = SessionAwareToolProcessor(session_id=session.id)
    
    # Simple process_text implementation
    async def process_text(text):
        data = json.loads(text)
        results = []
        for call in data.get("tool_calls", []):
            fn = call.get("function", {})
            name = fn.get("name")
            if name == "get_weather":
                args = json.loads(fn.get("arguments", "{}"))
                result = {"temperature": 72, "condition": "Sunny", "location": args.get("location")}
                results.append(ToolResult("get_weather", args, result))
        return results
    
    # Monkey patch for demo
    processor.process_text = process_text
    
    # LLM response with tool calls
    assistant_msg = {
        "role": "assistant",
        "content": "I'll check the weather for you",
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
    
    # Simple LLM callback
    async def llm_callback(prompt):
        return assistant_msg
    
    # Process the message
    results = await processor.process_llm_message(assistant_msg, llm_callback)
    
    # Check results
    print(f"Processed {len(results)} tool calls")
    
    # Check session events
    updated_session = await store.get(session.id)
    print(f"Session now has {len(updated_session.events)} events")
    
    # Get the tool call event
    tool_events = [e for e in updated_session.events if e.type == EventType.TOOL_CALL]
    if tool_events:
        print(f"Tool result: {tool_events[0].message}")

# Run the example
asyncio.run(example())
```

## Web Framework Integration

chuk session manager works seamlessly with modern web frameworks like FastAPI, Starlette, and ASGI-based Django:

```python
from fastapi import FastAPI, HTTPException
from chuk_session_manager.models.session import Session
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

# Initialize FastAPI app
app = FastAPI()

# Configure storage at startup
@app.on_event("startup")
async def startup():
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)

# Session API endpoints
@app.post("/sessions")
async def create_session():
    session = await Session.create()
    return {"id": session.id}

@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    store = SessionStoreProvider.get_store()
    session = await store.get(session_id)
    
    if not session:
        raise HTTPException(404, "Session not found")
        
    return {
        "id": session.id,
        "events_count": len(session.events),
        "runs_count": len(session.runs),
        "child_ids": session.child_ids
    }
```

## Examples

See the `examples/` directory for complete usage examples:

- `async_session_example.py`: Basic async session management
- `fastapi_session_example.py`: Integration with FastAPI
- `session_token_usage_example.py`: Token usage monitoring
- `session_prompt_builder.py`: Building LLM prompts from sessions
- `session_aware_tool_processor.py`: Integrating tool execution with sessions
- `example_infinite_conversation.py`: Managing infinitely long conversations

Run examples with:

```bash
uv run examples/async_session_example.py
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.