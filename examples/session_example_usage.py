# examples/session_example_usage.py
"""
Demonstration script for creating and managing sessions, events, runs, and hierarchy
using the a2a_session_manager models and in-memory store.
"""
from datetime import datetime

# Import provider and in-memory store
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider

# Import models and enums
from a2a_session_manager.models.access_control import AccessControlled
from a2a_session_manager.models.project import Project
from a2a_session_manager.models.access_levels import AccessLevel
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.session_run import SessionRun, RunStatus

def main():
    # Initialize in-memory store and register it
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    print("Initialized in-memory session store.")

    # Create a project (public)
    project = Project(
        name="Demo Project",
        account_id="acct_demo",
        access_level=AccessLevel.PUBLIC
    )
    print(f"Created project: {project.id} (access_level={project.access_level.value})")

    # Create a root session
    root_sess = Session(
        account_id="acct_demo",
        project_id=project.id
    )
    store.save(root_sess)
    print(f"Root session created: {root_sess.id}")

    # Add events to the root session
    evt1 = SessionEvent(
        message="User said hello",
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    evt2 = SessionEvent(
        message="LLM responded",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    root_sess.events.extend([evt1, evt2])
    print(f"Root session has {len(root_sess.events)} events; last update at {root_sess.last_update_time}")

    # Start a new run
    run = SessionRun()
    run.mark_running()
    root_sess.runs.append(run)
    print(f"Started run {run.id} at {run.started_at} (status={run.status.value})")

    # Complete the run
    run.mark_completed()
    print(f"Completed run {run.id} at {run.ended_at} (status={run.status.value})")

    # Create a child session
    child = Session(
        account_id="acct_demo",
        project_id=project.id,
        parent_id=root_sess.id
    )
    store.save(child)
    print(f"Child session created: {child.id} (parent={child.parent_id})")

    # Show hierarchy
    print("Root children:", root_sess.child_ids)
    print("Child ancestors:", [s.id for s in child.ancestors()])

    # Access control
    print("Project is public?", project.is_public)
    print("Does acct_demo have access to root?", root_sess.has_access("acct_demo"))

if __name__ == "__main__":
    main()
