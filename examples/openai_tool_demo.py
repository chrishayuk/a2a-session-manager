#!/usr/bin/env python3
# examples/openai_tool_demo.py
"""
OpenAI-tools demo with session logging and hierarchical event
printing using the async API. The SessionAwareToolProcessor stores:

   • one parent "batch" event
   • retry notices (if any)   → metadata.parent_event_id = <batch-id>
   • TOOL_CALL results        → metadata.parent_event_id = <batch-id>

This script renders that hierarchy in an indented tree.
"""

from __future__ import annotations

# ── quiet logging by default ───────────────────────────────────────
import logging, sys, asyncio, json, os, pprint
logging.basicConfig(level=logging.WARNING,
                    stream=sys.stdout,
                    format="%(levelname)s | %(message)s")
import chuk_tool_processor            # silence its handler
logging.getLogger("chuk_tool_processor").setLevel(logging.WARNING)

# ── OpenAI + env ───────────────────────────────────────────────────
from dotenv import load_dotenv
from openai import AsyncOpenAI

# ── session & processor bits ───────────────────────────────────────
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.session_aware_tool_processor import SessionAwareToolProcessor
from chuk_tool_processor.registry.tool_export import openai_functions

# tools self-register
from sample_tools import WeatherTool, SearchTool, CalculatorTool  # noqa: F401

load_dotenv()


async def ensure_openai_ok() -> AsyncOpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY in environment or .env")
    client = AsyncOpenAI(api_key=key)
    await client.chat.completions.create(
        model="gpt-3.5-turbo", messages=[{"role": "user", "content": "ping"}]
    )
    return client


# ── tiny helper to pretty-print hierarchy ──────────────────────────
async def print_event_tree(events: list[SessionEvent]) -> None:
    ids = {evt.id: evt for evt in events}
    children: dict[str, list[SessionEvent]] = {}
    for evt in events:
        # Try to get parent_id, fallback to direct metadata access if needed
        try:
            if hasattr(evt, "get_metadata"):
                parent_id = await evt.get_metadata("parent_event_id")
            else:
                parent_id = evt.metadata.get("parent_event_id")
                
            if parent_id:
                children.setdefault(parent_id, []).append(evt)
        except Exception as e:
            # Fallback if any error occurs
            parent_id = evt.metadata.get("parent_event_id")
            if parent_id:
                children.setdefault(parent_id, []).append(evt)

    async def _dump(evt: SessionEvent, indent: int = 0):
        pad = "  " * indent
        print(f"{pad}• {evt.type.value:10}  id={evt.id}")
        if evt.type == EventType.TOOL_CALL:
            msg = evt.message or {}
            print(f"{pad}  ⇒ {msg.get('tool')}   "
                  f"error={msg.get('error')}")
        for ch in sorted(children.get(evt.id, []), key=lambda e: e.timestamp):
            await _dump(ch, indent + 1)

    # roots = events without parent_event_id
    roots = []
    for evt in events:
        # Try to check for parent_id, fallback to direct metadata access if needed
        try:
            if hasattr(evt, "get_metadata"):
                parent_id = await evt.get_metadata("parent_event_id")
            else:
                parent_id = evt.metadata.get("parent_event_id")
                
            if not parent_id:
                roots.append(evt)
        except Exception as e:
            # Fallback if any error occurs
            parent_id = evt.metadata.get("parent_event_id")
            if not parent_id:
                roots.append(evt)
            
    for root in sorted(roots, key=lambda e: e.timestamp):
        await _dump(root)


# ── main flow ───────────────────────────────────────────────────────
async def main() -> None:
    client = await ensure_openai_ok()

    # Session & in-memory store with async
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create session using async factory method
    session = await Session.create()
    
    # Create processor for session - use the create method if available, otherwise use constructor
    if hasattr(SessionAwareToolProcessor, "create"):
        processor = await SessionAwareToolProcessor.create(
            session_id=session.id,
            enable_caching=True,
            enable_retries=True
        )
    else:
        processor = SessionAwareToolProcessor(
            session_id=session.id,
            enable_caching=True,
            enable_retries=True
        )

    # Add a user message to the session
    user_prompt = (
        "I need to know if I should wear a jacket today in New York.\n"
        "Also, how much is 235.5 × 18.75?\n"
        "Finally, find a couple of pages on climate-change adaptation."
    )
    
    # Add the user message to the session - safely handle both sync and async approaches
    try:
        # Try the newer async approach with token tracking
        user_event = await SessionEvent.create_with_tokens(
            message=user_prompt,
            prompt=user_prompt,
            completion="",
            model="gpt-4o-mini",
            source=EventSource.USER,
            type=EventType.MESSAGE
        )
    except Exception as e:
        # Fallback to the old approach
        user_event = SessionEvent(
            message=user_prompt,
            source=EventSource.USER,
            type=EventType.MESSAGE
        )
        
    await session.add_event_and_save(user_event)

    # LLM callback function
    async def ask_llm(prompt_text: str):
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_text}],
            tools=openai_functions(),
            tool_choice="auto",
            temperature=0.7,
        )
        return resp.choices[0].message.model_dump()

    # Get assistant message
    assistant_msg = await ask_llm(user_prompt)
    
    # Process LLM message with tool processor
    results = await processor.process_llm_message(assistant_msg, ask_llm)

    # Get the updated session
    session = await store.get(session.id)

    # Calculate total token usage if available
    total_tokens = getattr(session, "total_tokens", 0)
    total_cost = getattr(session, "total_cost", 0)

    # ── show tool results ───────────────────────────────────────────
    print(f"\nExecuted {len(results)} tool calls")
    for r in results:
        print(f"\n⮑  {r.tool}")
        # Safely handle result printing
        if hasattr(r.result, "model_dump"):
            pprint.pp(r.result.model_dump())
        else:
            pprint.pp(r.result)

    # ── show hierarchical events ───────────────────────────────────
    print("\nSession event tree:")
    await print_event_tree(session.events)
    
    # ── show token usage if available ─────────────────────────────────
    if total_tokens > 0:
        print(f"\nToken usage: {total_tokens} tokens (estimated cost: ${total_cost:.6f})")
        
        # Show token usage by model if available
        if hasattr(session, "token_summary") and hasattr(session.token_summary, "usage_by_model"):
            print("\nUsage by model:")
            for model, usage in session.token_summary.usage_by_model.items():
                print(f"  {model}: {usage.total_tokens} tokens (${usage.estimated_cost_usd:.6f})")


if __name__ == "__main__":
    asyncio.run(main())