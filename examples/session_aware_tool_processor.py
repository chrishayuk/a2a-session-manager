#!/usr/bin/env python3
# examples/session_aware_tool_processor.py
"""
session_aware_tool_processor_demo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A self-contained showcase for **SessionAwareToolProcessor** covering four
scenarios:

1. **Successful tool call** - LLM reply already includes a valid call.
2. **Retry logic** - first reply is missing a call, second succeeds.
3. **Failed retry** - even after the allowed retries, no call appears.
4. **Multiple tools** - one LLM reply includes *two* function calls.

Key points
----------
* Uses an **in-memory** `SessionStore` → no external services.
* Demonstrates how events, runs, and summaries are recorded.
* Uses a tiny `SimpleToolProcessor` that extracts tool calls from the
  assistant JSON and executes them via the mock `execute_tool`.

Run directly:

```bash
uv run examples/session_aware_tool_processor_demo.py
```
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

# ── Logging setup ────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ── Session-manager imports ─────────────────────────────────────────
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.session import Session, SessionEvent
from a2a_session_manager.session_aware_tool_processor import SessionAwareToolProcessor
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider

# ── Mock tool layer ────────────────────────────────────────────────
TOOLS: List[Dict[str, Any]] = [
    {"name": "get_weather", "args": {"location": {"type": "string"}}},
    {"name": "calculate", "args": {"expression": {"type": "string"}}},
]


async def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Tiny mock backend for the demo tools."""
    log.info("Executing %s with %s", name, args)
    if name == "get_weather":
        return {
            "temperature": 72,
            "condition": "Sunny",
            "humidity": 45,
            "location": args.get("location", "Unknown"),
        }
    if name == "calculate":
        expr = args.get("expression", "0")
        try:
            return {"result": eval(expr)}  # noqa: S307 (demo only)
        except Exception as exc:  # pragma: no cover
            return {"error": str(exc)}
    return {"error": f"Unknown tool: {name}"}


class ToolResult:  # simple stand-in for real model
    def __init__(self, tool: str, arguments: Dict[str, Any], result: Dict[str, Any]):
        self.tool = tool
        self.arguments = arguments
        self.result = result

    def model_dump(self):
        return {"tool": self.tool, "arguments": self.arguments, "result": self.result}


class SimpleToolProcessor:
    """Extracts `tool_calls` JSON, executes mock tools."""

    def __init__(self, tools: List[Dict[str, Any]]):
        self.tool_map = {t["name"]: t for t in tools}

    async def process_text(self, text: str):  # noqa: D401
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        results: List[ToolResult] = []
        for call in data.get("tool_calls", []):
            fn = call.get("function", {})
            name = fn.get("name")
            if name not in self.tool_map:
                continue
            args = json.loads(fn.get("arguments", "{}"))
            res = await execute_tool(name, args)
            results.append(ToolResult(name, args, res))
        return results


# ── Fake LLM helper ────────────────────────────────────────────────
async def fake_llm(prompt: str, *, include_tool: bool) -> Dict[str, Any]:
    log.info("LLM >>> %s", prompt)
    if "weather" in prompt.lower():
        if include_tool:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "get_weather", "arguments": json.dumps({"location": "New York"})}},
                ],
            }
        return {"role": "assistant", "content": "Sure, let me check…"}
    if "calculate" in prompt.lower():
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"type": "function", "function": {"name": "calculate", "arguments": json.dumps({"expression": "42 * 2"})}},
            ],
        }
    return {"role": "assistant", "content": "How can I help?"}


# ── Shared scenario runner ─────────────────────────────────────────
async def run_scenario(label: str, prompt: str, include_tool: bool, max_retries: int = 2):
    log.info("\n=== %s ===", label)

    SessionStoreProvider.set_store(InMemorySessionStore())
    store = SessionStoreProvider.get_store()
    sess = Session()
    store.save(sess)  # ← FIX: ensure processor can load the session

    sess.events.append(SessionEvent(message=prompt, type=EventType.MESSAGE, source=EventSource.USER))

    proc = SessionAwareToolProcessor(session_id=sess.id, max_llm_retries=max_retries)
    proc.process_text = SimpleToolProcessor(TOOLS).process_text  # monkey-patch

    assistant_msg = await fake_llm(prompt, include_tool=include_tool)

    async def retry_fn(_):
        return await fake_llm(prompt, include_tool=True)

    try:
        results = await proc.process_llm_message(assistant_msg, retry_fn)
        log.info("Tool results:\n%s", json.dumps([r.model_dump() for r in results], indent=2))
    except RuntimeError as exc:
        log.info("Expected failure: %s", exc)

    log.info("Session events: %d | runs: %d", len(sess.events), len(sess.runs))


# ── Main entry ─────────────────────────────────────────────────────
async def main():
    await run_scenario("Successful tool call", "What's the weather like in New York?", include_tool=True)
    await run_scenario("Retry mechanism", "Check the invalid weather format please", include_tool=False, max_retries=2)
    await run_scenario("Failed retry", "This is a generic query with no tool call", include_tool=False, max_retries=1)

    # Multiple tools -----------------------------------------------
    log.info("\n=== Multiple tools ===")
    SessionStoreProvider.set_store(InMemorySessionStore())
    store = SessionStoreProvider.get_store()
    sess = Session()
    store.save(sess)  # ← FIX

    sess.events.append(SessionEvent(message="Weather and 42*2", type=EventType.MESSAGE, source=EventSource.USER))

    proc = SessionAwareToolProcessor(session_id=sess.id)
    proc.process_text = SimpleToolProcessor(TOOLS).process_text

    llm_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"type": "function", "function": {"name": "get_weather", "arguments": json.dumps({"location": "New York"})}},
            {"type": "function", "function": {"name": "calculate", "arguments": json.dumps({"expression": "42 * 2"})}},
        ],
    }

    results = await proc.process_llm_message(llm_msg, lambda _: llm_msg)
    log.info("Tool results (multi):\n%s", json.dumps([r.model_dump() for r in results], indent=2))
    log.info("Session events: %d | runs: %d", len(sess.events), len(sess.runs))


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
