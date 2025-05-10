#!/usr/bin/env python3
"""
examples/retry_prompt_demo.py
─────────────────────────────
Illustrates:

• How you might retry an LLM call until it proposes a tool-call.
• SessionAwareToolProcessor execution / event logging.
• Prompt pruning with build_prompt_from_session().
"""

from __future__ import annotations

import asyncio
import json
import logging
import pprint
from typing import Dict, List

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

# ── sample tool (self-registers) ────────────────────────────────────────────
from sample_tools import WeatherTool  # noqa: F401

# ── A2A imports ─────────────────────────────────────────────────────────────
from a2a_session_manager.storage.providers.memory import InMemorySessionStore
from a2a_session_manager.storage import SessionStoreProvider
from a2a_session_manager.models.session import Session, SessionEvent
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.session_aware_tool_processor import SessionAwareToolProcessor
from a2a_session_manager.session_prompt_builder import build_prompt_from_session

##############################################################################
# Fake LLM: fails once, succeeds on the second call
##############################################################################
ATTEMPTS = 0


async def fake_llm(_: List[Dict] | str) -> Dict:
    """Return a plain assistant answer first, a valid tool-call next."""
    global ATTEMPTS  # noqa: PLW0603
    ATTEMPTS += 1

    if ATTEMPTS == 1:
        # Invalid assistant reply (no tool_calls) – forces a retry loop below
        return {"role": "assistant", "content": "Weather is nice!", "tool_calls": []}

    # Second attempt – proper function call
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "weather",
                    "arguments": '{"location": "London"}',
                },
            }
        ],
    }


##############################################################################
# Pretty-printing helpers
##############################################################################
async def print_event_tree(sess: Session) -> None:
    """Indented tree by parent_event_id metadata."""
    children: dict[str, list[SessionEvent]] = {}
    for e in sess.events:
        parent = await e.get_metadata("parent_event_id")
        if parent:
            children.setdefault(parent, []).append(e)

    async def _dump(evt: SessionEvent, depth: int = 0) -> None:
        pad = "  " * depth
        print(f"{pad}• {evt.type.value:9} id={evt.id}")
        for ch in sorted(children.get(evt.id, []), key=lambda x: x.timestamp):
            await _dump(ch, depth + 1)

    roots = [e for e in sess.events if not await e.get_metadata("parent_event_id")]
    for r in sorted(roots, key=lambda x: x.timestamp):
        await _dump(r)


##############################################################################
# Main demo flow
##############################################################################
async def main() -> None:
    # 1) Session bootstrap
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    session = await Session.create()

    user_prompt = "Tell me the weather in London."
    await session.add_event_and_save(
        SessionEvent(
            message={"content": user_prompt},
            type=EventType.MESSAGE,
            source=EventSource.USER,
        )
    )

    # 2) Session-aware processor (no internal LLM retries – we handle them below)
    processor = await SessionAwareToolProcessor.create(
        session_id=session.id,
        max_retries=1,          # tool-call retries
        enable_caching=False,
    )

    # 3) Retry loop: keep asking fake_llm until we get tool_calls
    while True:
        assistant_msg = await fake_llm("prompt")
        if assistant_msg.get("tool_calls"):
            break   # got a callable answer

        # Log the “plain” assistant message so the history looks realistic
        await session.add_event_and_save(
            SessionEvent(
                message=assistant_msg,
                type=EventType.MESSAGE,
                source=EventSource.LLM,
            )
        )

    # 4) Execute the tool calls + log
    tool_results = await processor.process_llm_message(assistant_msg, fake_llm)

    # Reload session (new events were added)
    session = await store.get(session.id)

    # 5) Outputs
    print("\nTool execution results:")
    for res in tool_results:
        print(json.dumps(getattr(res, "result", None), default=str, indent=2))

    print("\nHierarchical Session Events:")
    await print_event_tree(session)

    next_prompt = await build_prompt_from_session(session)
    print("\nNext-turn prompt that would be sent to the LLM:")
    pprint.pp(next_prompt)


if __name__ == "__main__":
    asyncio.run(main())
