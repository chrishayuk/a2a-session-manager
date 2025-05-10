# examples/session_example_usage.py
#!/usr/bin/env python3
"""
async_session_example_usage.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Demonstration script for managing **Accounts → Projects → Sessions** with an
*in-memory* store using the async API. It shows:

1.  Creating an `Account` owned by a user.
2.  Adding a **shared** `Project` (visible to selected users).
3.  Creating a *root* `Session`, appending chat events, and running a
   `SessionRun`.
4.  Forking a *child* session to demonstrate hierarchy handling.
5.  Performing simple ACL queries.

Running the file prints a concise audit log **and** returns a dictionary with
references to the key objects (handy for notebooks/tests).
"""

from __future__ import annotations
import asyncio

# ── Storage providers ────────────────────────────────────────────────
from chuk_session_manager.storage import InMemorySessionStore, SessionStoreProvider

# ── Account & Project layer ──────────────────────────────────────────
from a2a_accounts.models.project import Project
from a2a_accounts.models.account import Account
from a2a_accounts.models.access_levels import AccessLevel

# ── Session layer ────────────────────────────────────────────────────
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_type import EventType
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.models.session_run import SessionRun


async def print_event_tree(sess: Session, indent: int = 0) -> None:  # helper
    """Pretty-print a Session hierarchy for quick inspection."""
    pad = "  " * indent
    print(f"{pad}• session {sess.id}")
    for child_id in sess.child_ids:
        store = SessionStoreProvider.get_store()
        child = await store.get(child_id)
        if child:
            await print_event_tree(child, indent + 1)


async def main():  # async demo script
    # 1) Set up an in-memory session store ----------------------------------
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    print("🗄️  Initialized in-memory session store.")

    # 2) Create an Account ---------------------------------------------------
    acct = Account(name="Demo Corp", owner_user_id="alice")
    print(f"👤 Created Account: {acct.id} (owner_user_id={acct.owner_user_id})")

    # 3) Create a shared Project under that Account -------------------------
    proj = Project(
        name="Alpha Project",
        account_id=acct.id,
        access_level=AccessLevel.SHARED,
        shared_with={acct.id, "bob"},
    )
    acct.add_project(proj)
    print(f"📁 Created Project: {proj.id} (access_level={proj.access_level.value})")
    print(f"   → Account {acct.id} now owns projects: {acct.project_ids}")

    # 4) Create a root Session using async factory method ---------------------------------------------
    root = await Session.create()
    proj.add_session(root)
    print(f"💬 Created root Session: {root.id}")
    print(f"   → Project {proj.id} now has sessions: {proj.session_ids}")

    # 5) Record a couple of chat events and save -------------------------------------
    await root.add_event_and_save(SessionEvent(
        message="Hey, how are you?",
        source=EventSource.USER,
        type=EventType.MESSAGE,
    ))
    
    await root.add_event_and_save(SessionEvent(
        message="I'm fine, thanks!",
        source=EventSource.LLM,
        type=EventType.MESSAGE,
    ))
    
    print(f"   • Recorded {len(root.events)} events; last at {root.last_update_time}")

    # 6) Start and complete a run ------------------------------------------
    run = SessionRun()
    run.mark_running()
    root.runs.append(run)
    await store.save(root)
    print(f"   • Started run {run.id} at {run.started_at} (status={run.status.value})")

    run.mark_completed()
    await store.save(root)
    print(f"   • Completed run {run.id} at {run.ended_at} (status={run.status.value})")

    # 7) Fork a child Session ----------------------------------------------
    child = await Session.create(parent_id=root.id)
    print(f"🧒 Created child Session: {child.id}")
    
    # Display hierarchy
    await print_event_tree(root)

    # 8) Check ACL at the project level ------------------------------------
    print(f"🔒 Is project public? {proj.is_public}")
    print(f"🔑 Does '{acct.id}' have access? {proj.has_access(acct.id)}")
    print(f"🔑 Does 'eve' have access? {proj.has_access('eve')}")

    # Return objects for interactive use / testing -------------------------
    return {
        "account": acct,
        "project": proj,
        "root_session": root,
        "child_session": child,
    }


if __name__ == "__main__":
    asyncio.run(main())