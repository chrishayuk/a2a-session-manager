#!/usr/bin/env python3
# examples/openai_tool_demo.py
"""
Async-native OpenAI tools demo using the chuk session manager.

Highlights
----------
* Fully asynchronous from top to bottom - no blocking calls.
* Uses **AsyncOpenAI** client and the **SessionAwareToolProcessor** to
  capture and persist tool-call hierarchies inside an in-memory session store.
* Pretty-prints the resulting event tree and basic token/cost stats.

Prerequisites::

    pip install openai "python-dotenv>=1.0"  # loads OPENAI_API_KEY
    export OPENAI_API_KEY="sk-..."

Run it::

    python examples/openai_tool_demo_async.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import pprint
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Session-manager imports
from chuk_session_manager.storage.providers.memory import InMemorySessionStore
from chuk_session_manager.storage import SessionStoreProvider
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_type import EventType
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.session_aware_tool_processor import (
    SessionAwareToolProcessor,
)

# Tools auto-register with chuk_tool_processor when imported
from chuk_tool_processor.registry.tool_export import openai_functions
from sample_tools import WeatherTool, SearchTool, CalculatorTool  # noqa: F401  pylint: disable=unused-import

###############################################################################
# Logging
###############################################################################
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

###############################################################################
# Helpers
###############################################################################
async def get_openai_client() -> AsyncOpenAI:
    """Return an :class:`AsyncOpenAI` client after a quick sanity ping."""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set (env or .env file)")

    client = AsyncOpenAI(api_key=api_key)

    # Cheap 1-token call just to fail fast if the key / networking is wrong
    await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
    )
    return client


async def pretty_event_tree(session: Session) -> None:
    """Walk the session's events and print them as an indented tree."""

    # Map event-id → list[child events]
    children: dict[str, list[SessionEvent]] = {}
    for evt in session.events:
        parent = await evt.get_metadata("parent_event_id")
        if parent:
            children.setdefault(parent, []).append(evt)

    async def _dump(evt: SessionEvent, depth: int = 0) -> None:
        pad = "  " * depth
        print(f"{pad}• {evt.type.value:10} id={evt.id}")
        if evt.type == EventType.TOOL_CALL:
            msg = evt.message or {}
            print(f"{pad}  ↳ {msg.get('tool')} | error={msg.get('error')}")
        for child in sorted(children.get(evt.id, []), key=lambda e: e.timestamp):
            await _dump(child, depth + 1)

    roots = [e for e in session.events if not await e.get_metadata("parent_event_id")]
    for root in sorted(roots, key=lambda e: e.timestamp):
        await _dump(root)


async def call_llm(client: AsyncOpenAI, prompt: str) -> dict:
    """Query the LLM with our tools, returning the raw assistant message dict."""
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        tools=openai_functions(),
        tool_choice="auto",
        temperature=0.7,
    )
    return response.choices[0].message.model_dump()


###############################################################################
# Main flow
###############################################################################
async def main() -> None:
    client = await get_openai_client()

    # In-memory store so the demo is completely self-contained
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)

    session = await Session.create()

    # Processor that will run/record tool calls for this session
    processor = await SessionAwareToolProcessor.create(session_id=session.id)

    user_prompt = (
        "I need to know if I should wear a jacket today in New York.\n"
        "Also, how much is 235.5 × 18.75?\n"
        "Finally, find a couple of pages on climate-change adaptation."
    )

    # Record the USER event (with token accounting)
    user_event = await SessionEvent.create_with_tokens(
        message=user_prompt,
        prompt=user_prompt,
        model="gpt-4o-mini",
        source=EventSource.USER,
    )
    await session.add_event_and_save(user_event)

    # Ask the model (tools will be suggested/run automatically)
    assistant_msg = await call_llm(client, user_prompt)

    # Execute + log tool calls
    tool_results = await processor.process_llm_message(assistant_msg, lambda _: call_llm(client, _))

    # Refresh session from store to include new events
    session = await store.get(session.id)

    # --- Display ------------------------------------------------------------------ #
    print(f"\nExecuted {len(tool_results)} tool calls")
    for r in tool_results:
        print(f"\n→ {r.tool}")
        pprint.pp(r.result)

    print("\nSession event tree:")
    await pretty_event_tree(session)

    # Simple token/cost overview if the tracking is available
    if session.total_tokens:
        print(
            f"\nToken usage: {session.total_tokens} tokens – "
            f"estimated cost ${session.total_cost:.6f}"
        )
        for model, usage in session.token_summary.usage_by_model.items():
            print(f"  {model}: {usage.total_tokens} tokens (${usage.estimated_cost_usd:.6f})")


if __name__ == "__main__":
    asyncio.run(main())
