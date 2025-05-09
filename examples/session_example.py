#!/usr/bin/env python3
# examples/session_example.py
"""
session_example.py
~~~~~~~~~~~~~~~~~~~~~~~

Minimal yet complete walk-through of the core **A2A Session Manager** API:

* initialise an in-memory store
* create a simple session (events only)
* build a parent → child → grand-child hierarchy
* attach multiple runs with different outcomes
* traverse ancestors / descendants
* pretty-print a compact summary of every session in the store

Run:

```bash
uv run examples/session_example_clean.py
```
"""

from __future__ import annotations

import logging
from typing import List

from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.session import Session, SessionEvent
from a2a_session_manager.models.session_run import SessionRun
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider

# ── logging ───────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────

def save(obj):
    SessionStoreProvider.get_store().save(obj)


def add_event(sess: Session, msg: str, source: EventSource, etype: EventType = EventType.MESSAGE, **kw):
    sess.events.append(SessionEvent(message=msg, source=source, type=etype, **kw))


def describe(sess: Session):
    log.info("\n=== Session %s ===", sess.id)
    log.info("events=%d | runs=%d | children=%d", len(sess.events), len(sess.runs), len(sess.child_ids))
    for evt in sess.events:
        log.info("  [%s/%s] %s", evt.source.value, evt.type.value, evt.message[:60])
    for run in sess.runs:
        log.info("  run %s ⇒ %s", run.id, run.status.value)


# ── demo steps ────────────────────────────────────────────────────────────

def main():  # noqa: D401 – imperative demo
    SessionStoreProvider.set_store(InMemorySessionStore())

    # 1) simple session ----------------------------------------------------
    simple = Session()
    add_event(simple, "Hello!", EventSource.USER)
    add_event(simple, "Hi, how can I help?", EventSource.LLM)
    add_event(simple, "Summarise please", EventSource.USER)
    add_event(simple, "You greeted me; I offered help.", EventSource.LLM, EventType.SUMMARY)
    save(simple)
    describe(simple)

    # 2) parent / child / grand-child -------------------------------------
    parent = Session(); save(parent)
    add_event(parent, "Root session", EventSource.SYSTEM)

    child_a = Session(parent_id=parent.id); save(child_a)
    add_event(child_a, "first child", EventSource.SYSTEM)

    child_b = Session(parent_id=parent.id); save(child_b)
    add_event(child_b, "second child", EventSource.SYSTEM)

    grand = Session(parent_id=child_a.id); save(grand)
    add_event(grand, "grand-child", EventSource.SYSTEM)

    log.info("parent → children: %s", parent.child_ids)
    log.info("child_a → children: %s", child_a.child_ids)

    # 3) session with runs -------------------------------------------------
    runner = Session(); save(runner)
    add_event(runner, "multi-run session", EventSource.SYSTEM)

    def new_run(status: str):
        run = SessionRun(); run.mark_running();
        if status == "completed":
            run.mark_completed()
        elif status == "failed":
            run.mark_failed()
        return run

    runner.runs.extend([new_run("completed"), new_run("failed"), new_run("completed")])
    add_event(runner, "event for run 1", EventSource.SYSTEM, task_id=runner.runs[0].id)
    add_event(runner, "event for run 2", EventSource.SYSTEM, task_id=runner.runs[1].id)
    add_event(runner, "event for run 3", EventSource.SYSTEM, task_id=runner.runs[2].id)

    describe(runner)

    # 4) list everything ---------------------------------------------------
    store = SessionStoreProvider.get_store()
    log.info("\n--- All sessions in store (%d) ---", len(store.list_sessions()))
    for s_id in store.list_sessions():
        log.info("  • %s", s_id)


if __name__ == "__main__":  # pragma: no cover
    main()
