# A2A Session Manager

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, flexible session management system for AI applications.

## Overview

A2A Session Manager provides a comprehensive solution for tracking, persisting, and analyzing AI-based conversations and interactions. Whether you're building a simple chatbot or a complex agent-to-agent system, this library offers the building blocks to manage conversation state, hierarchy, and token usage.

## Features

- **Multiple Storage Backends**: Choose from in-memory, file-based, or Redis storage
- **Hierarchical Sessions**: Create parent-child relationships between sessions
- **Event Tracking**: Record all interactions with detailed metadata
- **Token Usage Monitoring**: Track token consumption and estimate costs
- **Run Management**: Organize sessions into logical execution runs
- **Prompt Building**: Generate optimized prompts from session data using multiple strategies
- **Tool Integration**: Track tool execution with parent-child event relationships
- **Extensible Design**: Easily extend with custom storage providers or event types

## Installation

```bash
# Basic installation
pip install a2a-session-manager

# With Redis support
pip install a2a-session-manager[redis]

# With tool processor integration
pip install a2a-session-manager[tools]

# With development tools
pip install a2a-session-manager[dev]

# Full installation with all dependencies
pip install a2a-session-manager[full]
```

## Quick Start

```python
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore

# Configure storage
store = InMemorySessionStore()
SessionStoreProvider.set_store(store)

# Create a session
session = Session()

# Add an event
session.add_event(SessionEvent(
    message="Hello, this is a user message",
    source=EventSource.USER
))

# Track token usage
llm_response = "Hello! I'm an AI assistant. How can I help you today?"
llm_event = SessionEvent.create_with_tokens(
    message=llm_response,
    prompt="Hello, this is a user message",
    completion=llm_response,
    model="gpt-3.5-turbo",
    source=EventSource.LLM
)
session.add_event(llm_event)

# Save session
store.save(session)

# Retrieve session
retrieved_session = store.get(session.id)
```

## Storage Providers

### In-Memory Storage

Ideal for testing and temporary applications:

```python
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider

store = InMemorySessionStore()
SessionStoreProvider.set_store(store)
```

### File-Based Storage

Persists sessions to JSON files:

```python
from a2a_session_manager.storage import create_file_session_store, SessionStoreProvider

store = create_file_session_store(directory="./sessions")
SessionStoreProvider.set_store(store)
```

### Redis Storage

Distributed storage for production applications:

```python
from a2a_session_manager.storage import create_redis_session_store, SessionStoreProvider

store = create_redis_session_store(
    host="localhost",
    port=6379,
    db=0,
    key_prefix="session:",
    expiration_seconds=86400  # 24 hours
)
SessionStoreProvider.set_store(store)
```

## Token Usage Tracking

```python
# Create an event with automatic token counting
event = SessionEvent.create_with_tokens(
    message="This is the assistant's response",
    prompt="What is the weather?",
    completion="This is the assistant's response",
    model="gpt-4-turbo"
)

# Get token usage
print(f"Prompt tokens: {event.token_usage.prompt_tokens}")
print(f"Completion tokens: {event.token_usage.completion_tokens}")
print(f"Total tokens: {event.token_usage.total_tokens}")
print(f"Estimated cost: ${event.token_usage.estimated_cost_usd:.6f}")
```

## Hierarchical Sessions

```python
# Create a parent session
parent = Session()
store.save(parent)

# Create child sessions
child1 = Session(parent_id=parent.id)
store.save(child1)

child2 = Session(parent_id=parent.id)
store.save(child2)

# Navigate hierarchy
ancestors = child1.ancestors()
descendants = parent.descendants()
```

## Session Runs

```python
# Create a session
session = Session()

# Start a run
run = SessionRun()
session.runs.append(run)
run.mark_running()

# Add events to the run
session.events.append(
    SessionEvent(
        message="Processing your request...",
        task_id=run.id
    )
)

# Complete the run
run.mark_completed()
```

## Prompt Builder

Generate optimized prompts from session data for LLM calls using various strategies:

```python
from a2a_session_manager.prompts import build_prompt_from_session, PromptStrategy

# Get a session
session = store.get(session_id)

# Build a prompt using different strategies
minimal_prompt = build_prompt_from_session(session, PromptStrategy.MINIMAL)
conversation_prompt = build_prompt_from_session(session, PromptStrategy.CONVERSATION)
tool_focused_prompt = build_prompt_from_session(session, PromptStrategy.TOOL_FOCUSED)
hierarchical_prompt = build_prompt_from_session(
    session, 
    PromptStrategy.HIERARCHICAL,
    include_parent_context=True
)

# Token-aware prompt building
from a2a_session_manager.prompts import truncate_prompt_to_token_limit

# Ensure the prompt fits within token limits
truncated_prompt = truncate_prompt_to_token_limit(
    conversation_prompt, 
    max_tokens=4000,
    model="gpt-4-turbo"
)
```

### Prompt Strategies

- **MINIMAL**: Includes only essential context (first user message, latest assistant response, and tool results)
- **TASK_FOCUSED**: Emphasizes the original task with minimal context
- **TOOL_FOCUSED**: Prioritizes tool usage information
- **CONVERSATION**: Includes more conversation history for a natural flow
- **HIERARCHICAL**: Leverages parent session context for multi-session conversations

## Session-Aware Tool Processing

Track tool execution within your sessions using the SessionAwareToolProcessor:

```python
from a2a_session_manager.session_aware_tool_processor import SessionAwareToolProcessor
from your_tool_package import ToolProcessor  # Your tool execution framework

# Create a session-aware tool processor
processor = SessionAwareToolProcessor(
    session_id="your_session_id",
    max_llm_retries=2,
    llm_retry_prompt="Please provide a valid tool call."
)

# Process LLM response with tool calls
async def llm_call_fn(retry_prompt):
    # Your LLM call implementation
    return await call_llm_with_prompt(retry_prompt)

# Process the LLM response
llm_response = {
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

# Tool results will be automatically added to the session
results = await processor.process_llm_message(llm_response, llm_call_fn)
```

The SessionAwareToolProcessor:
- Wraps tool execution in a session run
- Records the original LLM response
- Creates child events for each tool call
- Handles retries when needed
- Properly marks success and failure states

## Examples

See the `examples/` directory for complete usage examples:

- `session_example.py`: Basic session management
- `token_tracking_example.py`: Token usage monitoring
- `session_prompt_builder.py`: Building LLM prompts from sessions
- `session_aware_tool_processor.py`: Integrating tool execution with sessions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.