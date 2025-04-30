#!/usr/bin/env python3
# examples/session_example.py
"""
Example script demonstrating basic usage of the A2A Session Manager.

This example shows how to:
1. Create and configure a session store
2. Create a new session
3. Add events to a session
4. Create hierarchical sessions (parent/child)
5. Query and retrieve sessions
"""
import uuid
import logging
from datetime import datetime, timezone

from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.session_run import SessionRun
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_storage():
    """Initialize and configure the session store."""
    # Create an in-memory store for this example
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    return store


def create_simple_session():
    """Create a simple session with a few events."""
    logger.info("Creating a simple session...")
    
    # Create a new session
    session = Session()
    logger.info(f"Created session with ID: {session.id}")
    
    # Add a few events
    session.events.append(
        SessionEvent(
            message="Hello, this is a user message.",
            source=EventSource.USER,
            type=EventType.MESSAGE
        )
    )
    
    session.events.append(
        SessionEvent(
            message="Hello! I'm an AI assistant. How can I help you today?",
            source=EventSource.LLM,
            type=EventType.MESSAGE
        )
    )
    
    session.events.append(
        SessionEvent(
            message="Can you summarize our conversation?",
            source=EventSource.USER,
            type=EventType.MESSAGE
        )
    )
    
    session.events.append(
        SessionEvent(
            message="We've just started our conversation. You greeted me and I introduced myself as an AI assistant.",
            source=EventSource.LLM,
            type=EventType.SUMMARY
        )
    )
    
    # Save the session
    store = SessionStoreProvider.get_store()
    store.save(session)
    
    return session


def create_hierarchical_sessions():
    """Create a parent session with multiple child sessions."""
    logger.info("Creating a hierarchical session structure...")
    
    # Create parent session
    parent_session = Session()
    logger.info(f"Created parent session with ID: {parent_session.id}")
    
    # Add a parent event
    parent_session.events.append(
        SessionEvent(
            message="This is the parent session that will have children.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE
        )
    )
    
    # Save the parent session
    store = SessionStoreProvider.get_store()
    store.save(parent_session)
    
    # Create first child session
    child1 = Session(parent_id=parent_session.id)
    logger.info(f"Created child1 session with ID: {child1.id}")
    
    child1.events.append(
        SessionEvent(
            message="This is child session 1.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE
        )
    )
    
    # Save child1 (this should automatically update the parent's child_ids)
    store.save(child1)
    
    # Create second child session
    child2 = Session(parent_id=parent_session.id)
    logger.info(f"Created child2 session with ID: {child2.id}")
    
    child2.events.append(
        SessionEvent(
            message="This is child session 2.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE
        )
    )
    
    # Save child2
    store.save(child2)
    
    # Create a grandchild session (child of child1)
    grandchild = Session(parent_id=child1.id)
    logger.info(f"Created grandchild session with ID: {grandchild.id}")
    
    grandchild.events.append(
        SessionEvent(
            message="This is a grandchild session.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE
        )
    )
    
    # Save grandchild
    store.save(grandchild)
    
    # Refresh parent to see the updates
    parent_session = store.get(parent_session.id)
    logger.info(f"Parent session now has {len(parent_session.child_ids)} children: {parent_session.child_ids}")
    
    # Refresh child1 to see the updates
    child1 = store.get(child1.id)
    logger.info(f"Child1 session now has {len(child1.child_ids)} children: {child1.child_ids}")
    
    return parent_session


def create_session_with_runs():
    """Create a session with multiple runs."""
    logger.info("Creating a session with runs...")
    
    # Create a new session
    session = Session()
    logger.info(f"Created session with ID: {session.id}")
    
    # Add a message
    session.events.append(
        SessionEvent(
            message="Starting a session with multiple runs.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE
        )
    )
    
    # Create and start a run
    run1 = SessionRun()
    session.runs.append(run1)
    run1.mark_running()
    logger.info(f"Started run {run1.id}")
    
    # Add events associated with this run
    session.events.append(
        SessionEvent(
            message="This event is part of the first run.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE,
            task_id=run1.id
        )
    )
    
    # Mark the run as completed
    run1.mark_completed()
    logger.info(f"Completed run {run1.id}")
    
    # Start a second run
    run2 = SessionRun()
    session.runs.append(run2)
    run2.mark_running()
    logger.info(f"Started run {run2.id}")
    
    # Add events for the second run
    session.events.append(
        SessionEvent(
            message="This event is part of the second run.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE,
            task_id=run2.id
        )
    )
    
    # Oops, something went wrong with this run
    run2.mark_failed()
    logger.info(f"Run {run2.id} failed")
    
    # Start a third run
    run3 = SessionRun()
    session.runs.append(run3)
    run3.mark_running()
    logger.info(f"Started run {run3.id}")
    
    # Add events for the third run
    session.events.append(
        SessionEvent(
            message="This event is part of the third run.",
            source=EventSource.SYSTEM,
            type=EventType.MESSAGE,
            task_id=run3.id
        )
    )
    
    # Successfully complete this run
    run3.mark_completed()
    logger.info(f"Completed run {run3.id}")
    
    # Save the session
    store = SessionStoreProvider.get_store()
    store.save(session)
    
    return session


def print_session_details(session):
    """Print detailed information about a session."""
    logger.info(f"=== Session Details: {session.id} ===")
    logger.info(f"Created: {session.metadata.created_at}")
    logger.info(f"Last update: {session.last_update_time}")
    logger.info(f"Parent ID: {session.parent_id}")
    logger.info(f"Child IDs: {session.child_ids}")
    logger.info(f"Number of events: {len(session.events)}")
    
    # Print events
    logger.info("Events:")
    for i, event in enumerate(session.events):
        logger.info(f"  {i+1}. [{event.source.value}] [{event.type.value}] {event.message[:50]}...")
    
    # Print runs
    logger.info(f"Number of runs: {len(session.runs)}")
    for i, run in enumerate(session.runs):
        logger.info(f"  Run {i+1}: {run.id} - Status: {run.status.value}, Started: {run.started_at}, Ended: {run.ended_at or 'N/A'}")


def navigate_session_hierarchy(session_id):
    """Navigate through a session hierarchy, demonstrating ancestors/descendants methods."""
    logger.info(f"Navigating hierarchy for session: {session_id}")
    
    # Get the store
    store = SessionStoreProvider.get_store()
    
    # Get the session
    session = store.get(session_id)
    if not session:
        logger.error(f"Session {session_id} not found")
        return
    
    # Get ancestors
    ancestors = session.ancestors()
    logger.info(f"Session has {len(ancestors)} ancestors:")
    for i, ancestor in enumerate(ancestors):
        logger.info(f"  Ancestor {i+1}: {ancestor.id}")
    
    # Get descendants
    descendants = session.descendants()
    logger.info(f"Session has {len(descendants)} descendants:")
    for i, descendant in enumerate(descendants):
        logger.info(f"  Descendant {i+1}: {descendant.id}")


def main():
    """Main function demonstrating the session manager functionality."""
    logger.info("Starting A2A Session Manager example")
    
    # Setup storage
    store = setup_storage()
    
    # Create a simple session
    simple_session = create_simple_session()
    print_session_details(simple_session)
    
    # Create hierarchical sessions
    parent_session = create_hierarchical_sessions()
    
    # Navigate through the hierarchy
    navigate_session_hierarchy(parent_session.id)
    
    # Create a session with runs
    run_session = create_session_with_runs()
    print_session_details(run_session)
    
    # List all sessions
    all_sessions = store.list_sessions()
    logger.info(f"Total sessions in store: {len(all_sessions)}")
    logger.info(f"Session IDs: {all_sessions}")
    
    logger.info("A2A Session Manager example completed")


if __name__ == "__main__":
    main()