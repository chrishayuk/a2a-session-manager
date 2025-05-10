#!/usr/bin/env python3
# examples/session_example.py
"""
session_example.py
~~~~~~~~~~~~~~~~~~~~~~~

Demonstrates the async API of A2A Session Manager:

* initialize an in-memory async store
* create a simple session with events
* build a parent → child → grand-child hierarchy 
* traverse ancestors / descendants asynchronously
* pretty-print a summary of sessions

Run:
```bash
uv run examples/async_session_example.py
```
"""

import asyncio
import logging
from typing import List

from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.session import Session, SessionEvent
from a2a_session_manager.models.session_run import SessionRun
from a2a_session_manager.storage import SessionStoreProvider
from a2a_session_manager.storage.providers.memory import InMemorySessionStore
from a2a_session_manager.session_prompt_builder import build_prompt_from_session, PromptStrategy

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# Helper functions
async def describe_session(session: Session):
    """Print a description of a session."""
    log.info("\n=== Session %s ===", session.id)
    log.info("events=%d | runs=%d | children=%d", len(session.events), len(session.runs), len(session.child_ids))
    
    for evt in session.events:
        log.info("  [%s/%s] %s", evt.source.value, evt.type.value, str(evt.message)[:60])
    
    for run in session.runs:
        log.info("  run %s ⇒ %s", run.id, run.status.value)
    
    # Show ancestors if any
    ancestors = await session.ancestors()
    if ancestors:
        log.info("  ancestors: %s", [a.id for a in ancestors])
    
    # Show descendants if any
    descendants = await session.descendants()
    if descendants:
        log.info("  descendants: %s", [d.id for d in descendants])


async def main():
    """Main example demonstrating async session operations."""
    log.info("Starting A2A Session Manager async example")
    
    # 1. Initialize the async in-memory store
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    log.info("Initialized async in-memory session store")
    
    # 2. Create a simple session with messages
    log.info("\n=== Creating a simple session ===")
    
    # Create using the async factory method
    simple = await Session.create()
    
    # Add events
    simple.add_event(SessionEvent(
        message="Hello! I have a question about quantum computing.", 
        source=EventSource.USER
    ))
    
    simple.add_event(SessionEvent(
        message="I'd be happy to help with your quantum computing question. What would you like to know?", 
        source=EventSource.LLM
    ))
    
    simple.add_event(SessionEvent(
        message="Can you explain quantum entanglement in simple terms?", 
        source=EventSource.USER
    ))
    
    # Add a summary event
    simple.add_event(SessionEvent(
        message="The user asked about quantum computing and specifically quantum entanglement.", 
        source=EventSource.LLM, 
        type=EventType.SUMMARY
    ))
    
    # Save asynchronously
    await store.save(simple)
    
    # Show the session details
    await describe_session(simple)
    
    # 3. Create a session hierarchy (parent → child → grandchild)
    log.info("\n=== Creating a session hierarchy ===")
    
    # Create parent session
    parent = await Session.create()
    parent.add_event(SessionEvent(
        message="Let's discuss AI capabilities.",
        source=EventSource.USER
    ))
    await store.save(parent)
    log.info(f"Created parent session: {parent.id}")
    
    # Create first child session
    child_a = await Session.create(parent_id=parent.id)
    child_a.add_event(SessionEvent(
        message="Tell me about language models.",
        source=EventSource.USER
    ))
    await store.save(child_a)
    log.info(f"Created child session A: {child_a.id}")
    
    # Create second child session
    child_b = await Session.create(parent_id=parent.id)
    child_b.add_event(SessionEvent(
        message="Tell me about computer vision.",
        source=EventSource.USER
    ))
    await store.save(child_b)
    log.info(f"Created child session B: {child_b.id}")
    
    # Create grandchild session
    grandchild = await Session.create(parent_id=child_a.id)
    grandchild.add_event(SessionEvent(
        message="How do transformer models work?",
        source=EventSource.USER
    ))
    await store.save(grandchild)
    log.info(f"Created grandchild session: {grandchild.id}")
    
    # Navigate hierarchy
    log.info("\nNavigating hierarchy:")
    
    # Get ancestors of grandchild
    grandchild_ancestors = await grandchild.ancestors()
    log.info(f"Grandchild ancestors: {[a.id for a in grandchild_ancestors]}")
    
    # Get descendants of parent
    parent_descendants = await parent.descendants()
    log.info(f"Parent descendants: {[d.id for d in parent_descendants]}")
    
    # 4. Create a session with runs
    log.info("\n=== Creating a session with runs ===")
    
    # Create session
    run_session = await Session.create()
    run_session.add_event(SessionEvent(
        message="Can you analyze this data for me?",
        source=EventSource.USER
    ))
    
    # Create three runs with different states
    run1 = SessionRun()
    run1.mark_running()
    run1.mark_completed()
    
    run2 = SessionRun()
    run2.mark_running()
    run2.mark_failed()
    
    run3 = SessionRun()
    run3.mark_running()
    
    # Add runs to session
    run_session.runs.extend([run1, run2, run3])
    
    # Add events associated with runs
    run_session.add_event(SessionEvent(
        message="Processing first dataset",
        source=EventSource.SYSTEM,
        task_id=run1.id
    ))
    
    run_session.add_event(SessionEvent(
        message="Error processing second dataset",
        source=EventSource.SYSTEM,
        task_id=run2.id
    ))
    
    run_session.add_event(SessionEvent(
        message="Currently processing third dataset",
        source=EventSource.SYSTEM,
        task_id=run3.id
    ))
    
    # Save the session
    await store.save(run_session)
    
    # Describe the session with runs
    await describe_session(run_session)
    
    # 5. Build prompts from a session
    log.info("\n=== Building LLM prompts from sessions ===")
    
    # Create a session with a tool call
    tool_session = await Session.create()
    
    # Add a conversation with tool usage
    tool_session.add_event(SessionEvent(
        message="What's the weather in New York?",
        source=EventSource.USER
    ))
    
    assistant_msg = SessionEvent(
        message="I'll check the weather for you.",
        source=EventSource.LLM
    )
    tool_session.add_event(assistant_msg)
    
    # Add a tool call as a child of the assistant message
    tool_session.add_event(SessionEvent(
        message={
            "tool_name": "get_weather",
            "result": {"temperature": 72, "condition": "Sunny", "location": "New York"}
        },
        source=EventSource.SYSTEM,
        type=EventType.TOOL_CALL,
        metadata={"parent_event_id": assistant_msg.id}
    ))
    
    await store.save(tool_session)
    
    # Build prompts using different strategies
    log.info("\nPrompt with MINIMAL strategy:")
    minimal_prompt = await build_prompt_from_session(tool_session, PromptStrategy.MINIMAL)
    for msg in minimal_prompt:
        log.info(f"  {msg['role']}: {msg.get('content')}")
    
    log.info("\nPrompt with TOOL_FOCUSED strategy:")
    tool_prompt = await build_prompt_from_session(tool_session, PromptStrategy.TOOL_FOCUSED)
    for msg in tool_prompt:
        if msg.get('role') == 'tool':
            log.info(f"  {msg['role']} ({msg.get('name')}): {msg.get('content')}")
        else:
            log.info(f"  {msg['role']}: {msg.get('content')}")
    
    # 6. List all sessions
    log.info("\n=== Listing all sessions ===")
    session_ids = await store.list_sessions()
    log.info(f"Found {len(session_ids)} sessions in the store:")
    for sid in session_ids:
        log.info(f"  • {sid}")
    
    log.info("\nAsync Session Manager example completed")


if __name__ == "__main__":
    asyncio.run(main())