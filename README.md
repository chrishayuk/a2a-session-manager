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
- **Extensible Design**: Easily extend with custom storage providers or event types

## Installation

```bash
# Basic installation
pip install a2a-session-manager

# With Redis support
pip install a2a-session-manager[redis]

# With development tools
pip install a2a-session-manager[dev]
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

## Examples

See the `examples/` directory for complete usage examples:

- `session_example.py`: Basic session management
- `token_tracking_example.py`: Token usage monitoring

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.