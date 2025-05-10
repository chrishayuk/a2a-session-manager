# tests/test_session_aware_tool_processor.py
"""
Async tests for SessionAwareToolProcessor – slimmed and fixed.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from a2a_session_manager.models.session import Session
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from a2a_session_manager.session_aware_tool_processor import (
    SessionAwareToolProcessor,
    ToolResult,        # ← import the class we just added
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

@pytest_asyncio.fixture
async def sid():
    mem = InMemorySessionStore()
    SessionStoreProvider.set_store(mem)
    s = Session()
    await mem.save(s)
    return s.id


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _dummy_msg():
    return {
        "tool_calls": [
            {
                "id": "cid",
                "type": "function",
                "function": {"name": "t", "arguments": "{}"},
            }
        ]
    }


async def _dummy_cb(_):
    return {}


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_process_tool_calls(sid):
    proc = await SessionAwareToolProcessor.create(session_id=sid)

    with patch.object(
        proc, "_execute_tool_calls",
        AsyncMock(return_value=[ToolResult(result={"ok": True})]),
        create=True,
    ):
        res = await proc.process_llm_message(_dummy_msg(), _dummy_cb)
        assert res[0].result == {"ok": True}


@pytest.mark.asyncio
async def test_cache_behavior(sid):
    proc = await SessionAwareToolProcessor.create(session_id=sid, enable_caching=True)

    with patch.object(
        proc, "_execute_tool_calls",
        AsyncMock(return_value=[ToolResult(result={"v": 1})]),
        create=True,
    ) as first_call:
        await proc.process_llm_message(_dummy_msg(), _dummy_cb)
        first_call.assert_awaited()

    with patch.object(
        proc, "_execute_tool_calls", AsyncMock(return_value=[]), create=True
    ) as second_call:
        out = await proc.process_llm_message(_dummy_msg(), _dummy_cb)
        second_call.assert_not_called()
        assert out[0].result == {"v": 1}


@pytest.mark.asyncio
async def test_retry_behavior(sid):
    proc = await SessionAwareToolProcessor.create(
        session_id=sid, enable_retries=True, max_retries=2, retry_delay=0.001
    )

    with patch.object(
        proc, "_execute_tool_calls",
        AsyncMock(side_effect=[Exception("fail"), [ToolResult(result={"v": 1})]]),
        create=True,
    ):
        out = await proc.process_llm_message(_dummy_msg(), _dummy_cb)
        assert out[0].result == {"v": 1}

    sess = await SessionStoreProvider.get_store().get(sid)
    assert any(e.type == EventType.SUMMARY for e in sess.events)


@pytest.mark.asyncio
async def test_max_retries_exceeded(sid):
    proc = await SessionAwareToolProcessor.create(
        session_id=sid, enable_retries=True, max_retries=1, retry_delay=0.001
    )

    with patch.object(
        proc, "_execute_tool_calls",
        AsyncMock(side_effect=Exception("boom")),
        create=True,
    ):
        out = await proc.process_llm_message(_dummy_msg(), _dummy_cb)
        assert out[0].error
