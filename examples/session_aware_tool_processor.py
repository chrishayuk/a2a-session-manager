#!/usr/bin/env python3
# examples/session_aware_tool_processor.py
"""
Session-aware tool processor that logs tool execution in a session.

Event hierarchy per LLM message
───────────────────────────────
• one parent MESSAGE (“batch”)
• zero-or-more TOOL_CALL children   (success, cache-hit or error)
• optional SUMMARY children         (retry notices)

The processor also supports:
• result caching
• automatic retries
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from chuk_tool_processor.core.processor import ToolProcessor

from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.storage import SessionStoreProvider

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# helper types
# --------------------------------------------------------------------------- #
@dataclass
class ToolResult:  # noqa: D401
    tool: str = "tool"
    call_id: str = "cid"
    args: Dict[str, Any] | None = None
    result: Any | None = None
    error: str | None = None


LLMCallbackAsync = Any  # placeholder, not required in this file


# --------------------------------------------------------------------------- #
# main class
# --------------------------------------------------------------------------- #
class SessionAwareToolProcessor:
    """Logs, caches and retries tool calls inside a session."""

    def __init__(
        self,
        session_id: str,
        *,
        enable_caching: bool = True,
        enable_retries: bool = True,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> None:
        self.session_id = session_id
        self.enable_caching = enable_caching
        self.enable_retries = enable_retries
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cache: Dict[str, Any] = {}

        # one ToolProcessor instance
        self._tp = ToolProcessor()

    # ------------------------ factory ----------------------------------- #
    @classmethod
    async def create(
        cls,
        session_id: str,
        **kwargs,
    ) -> "SessionAwareToolProcessor":
        store = SessionStoreProvider.get_store()
        if not await store.get(session_id):
            raise ValueError(f"Session {session_id} not found")
        return cls(session_id=session_id, **kwargs)

    # ------------------------------------------------------------------- #
    # internal helper – tests patch this
    # ------------------------------------------------------------------- #
    async def _execute_tool_calls(
        self, calls: List[Dict[str, Any]]
    ) -> List[ToolResult]:
        """
        Execute tool calls with whichever API the installed
        `chuk_tool_processor` exposes.

        • v0.4 ⇒ ToolProcessor.process_tool_calls(...)  (async)
        • v0.5+ ⇒ ToolProcessor.run(...)               (sync or async)
        """
        # pick the real method
        if hasattr(self._tp, "process_tool_calls"):
            raw = await self._tp.process_tool_calls(calls, callback=None)

        elif hasattr(self._tp, "run"):
            maybe = self._tp.run(calls, callback=None)
            if asyncio.iscoroutine(maybe):
                raw = await maybe
            else:  # sync run – off-load to thread-pool
                loop = asyncio.get_running_loop()
                raw = await loop.run_in_executor(None, lambda: maybe)
        else:
            raise AttributeError(
                "ToolProcessor exposes neither 'process_tool_calls' nor 'run'"
            )

        # --- normalise into ToolResult list --------------------------------
        norm: List[ToolResult] = []
        for r in raw:
            if isinstance(r, ToolResult):
                norm.append(r)
            elif isinstance(r, dict):
                norm.append(
                    ToolResult(
                        tool=r.get("tool") or r.get("name", "tool"),
                        call_id=r.get("id", "cid"),
                        args=r.get("args") or r.get("arguments"),
                        result=r.get("result"),
                        error=r.get("error"),
                    )
                )
            else:
                norm.append(ToolResult(result=r))
        return norm

    # ------------------------------------------------------------------- #
    # public entry point
    # ------------------------------------------------------------------- #
    async def process_llm_message(
        self,
        llm_message: Dict[str, Any],
        llm_callback: LLMCallbackAsync,
    ) -> List[ToolResult]:
        store = SessionStoreProvider.get_store()
        session = await store.get(self.session_id)
        if session is None:
            raise ValueError(f"Session {self.session_id} not found")

        batch_event = await SessionEvent.create_with_tokens(
            message=llm_message,
            prompt="",
            completion=json.dumps(llm_message),
            model="gpt-4o-mini",
            source=EventSource.LLM,
            type=EventType.MESSAGE,
        )
        await batch_event.update_metadata("contains_tool_calls", True)
        await session.add_event_and_save(batch_event)

        calls_in_msg = llm_message.get("tool_calls", [])
        if not calls_in_msg:
            return []

        results: List[ToolResult] = []

        for call in calls_in_msg:
            call_id = call.get("id", "unknown")
            fn = call.get("function", {})
            tool_name = fn.get("name", "unknown")
            args_raw = fn.get("arguments", "{}")

            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"raw_arguments": args_raw}

            # -- caching ----------------------------------------------------
            cache_key: Optional[str] = None
            if self.enable_caching:
                cache_key = self._cache_key(tool_name, args)
                if cache_key in self.cache:
                    cached_val = self.cache[cache_key]
                    tr = ToolResult(
                        tool=tool_name,
                        call_id=call_id,
                        args=args,
                        result=cached_val,
                    )
                    results.append(tr)
                    await self._log_tool_event(
                        session, batch_event.id, tr, attempt=1, cached=True
                    )
                    continue

            # -- potentially retry -----------------------------------------
            attempts_allowed = self.max_retries + 1 if self.enable_retries else 1
            attempt = 0
            while attempt < attempts_allowed:
                attempt += 1
                try:
                    tr = (await self._execute_tool_calls(
                        [{"id": call_id, "type": "function", "function": fn}]
                    ))[0]
                    tr.tool, tr.call_id, tr.args = tool_name, call_id, args

                    if cache_key:
                        self.cache[cache_key] = tr.result

                    await self._log_tool_event(
                        session, batch_event.id, tr, attempt=attempt, cached=False
                    )
                    results.append(tr)
                    break

                except Exception as exc:
                    err_msg = str(exc)
                    logger.warning(f"Tool call failed: {err_msg}")

                    if attempt < attempts_allowed:
                        await session.add_event_and_save(
                            SessionEvent(
                                message=(
                                    f"Retry {attempt}/{self.max_retries} "
                                    f"for tool {tool_name}: {err_msg}"
                                ),
                                source=EventSource.SYSTEM,
                                type=EventType.SUMMARY,
                                metadata={
                                    "parent_event_id": batch_event.id,
                                    "call_id": call_id,
                                    "attempt": attempt,
                                    "retry": True,
                                },
                            )
                        )
                        await asyncio.sleep(self.retry_delay)
                    else:
                        tr = ToolResult(
                            tool=tool_name,
                            call_id=call_id,
                            args=args,
                            error=err_msg,
                        )
                        await self._log_tool_event(
                            session,
                            batch_event.id,
                            tr,
                            attempt=attempt,
                            cached=False,
                            failed=True,
                        )
                        results.append(tr)

        return results

    # ------------------------------------------------------------------- #
    # helpers
    # ------------------------------------------------------------------- #
    @staticmethod
    def _cache_key(tool: str, args: Dict[str, Any]) -> str:
        return hashlib.md5(f"{tool}:{json.dumps(args, sort_keys=True)}".encode()).hexdigest()

    async def _log_tool_event(
        self,
        session,
        parent_id: str,
        tr: ToolResult,
        *,
        attempt: int,
        cached: bool,
        failed: bool = False,
    ) -> None:
        ev = await SessionEvent.create_with_tokens(
            message={
                "tool": tr.tool,
                "arguments": tr.args,
                "result": tr.result,
                "error": tr.error,
                "cached": cached,
            },
            prompt=f"{tr.tool}({json.dumps(tr.args, default=str)})",
            completion=json.dumps(tr.result, default=str)
            if tr.result is not None
            else "",
            model="tool-execution",
            source=EventSource.SYSTEM,
            type=EventType.TOOL_CALL,
        )
        await ev.update_metadata("parent_event_id", parent_id)
        await ev.update_metadata("call_id", tr.call_id)
        await ev.update_metadata("attempt", attempt)
        if failed:
            await ev.update_metadata("failed", True)
        await session.add_event_and_save(ev)
