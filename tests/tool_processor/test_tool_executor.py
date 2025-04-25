# tests/tool_processor/test_tool_executor
import pytest
import asyncio
import os
from datetime import datetime, timezone

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.tool_registry import InMemoryToolRegistry

# Dummy tool implementations

def sync_tool(**kwargs):
    return f"sync:{kwargs}"

class AsyncTool:
    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        return f"async:{kwargs}"

class FailingTool:
    def execute(self, **kwargs):
        raise RuntimeError("expected failure")

class SlowTool:
    async def execute(self, **kwargs):
        # Sleep longer than timeout to trigger timeout
        await asyncio.sleep(0.1)
        return "slow result"

@pytest.mark.asyncio
async def test_execute_empty_calls():
    registry = InMemoryToolRegistry()
    executor = ToolExecutor(registry)
    results = await executor.execute([])
    assert results == []

@pytest.mark.asyncio
async def test_execute_unknown_tool():
    registry = InMemoryToolRegistry()
    executor = ToolExecutor(registry)
    call = ToolCall(tool="missing", arguments={"a": 1})
    results = await executor.execute([call])
    assert len(results) == 1
    res = results[0]
    assert isinstance(res, ToolResult)
    assert res.tool == "missing"
    assert res.result is None
    assert res.error == "Tool not found"
    # Metadata fields
    assert isinstance(res.start_time, datetime)
    assert isinstance(res.end_time, datetime)
    assert res.start_time <= res.end_time
    assert isinstance(res.machine, str) and res.machine
    assert isinstance(res.pid, int)

@pytest.mark.asyncio
async def test_execute_sync_and_async_tool_success():
    registry = InMemoryToolRegistry()
    # register sync tool under name 'sync'
    registry.register_tool(tool=type("T", (), {"__name__": "sync", "execute": staticmethod(sync_tool)}), name='sync')
    registry.register_tool(tool=AsyncTool(), name='async')
    executor = ToolExecutor(registry)

    # Sync tool
    call_sync = ToolCall(tool='sync', arguments={'x': 42})
    # Async tool
    call_async = ToolCall(tool='async', arguments={'y': 'test'})

    results = await executor.execute([call_sync, call_async])
    assert len(results) == 2

    # Test sync result
    res_sync = results[0]
    assert res_sync.tool == 'sync'
    assert res_sync.result == "sync:{'x': 42}"
    assert res_sync.error is None

    # Test async result
    res_async = results[1]
    assert res_async.tool == 'async'
    assert res_async.result == "async:{'y': 'test'}"
    assert res_async.error is None

@pytest.mark.asyncio
async def test_execute_tool_raises_and_timeout():
    registry = InMemoryToolRegistry()
    registry.register_tool(tool=FailingTool(), name='fail')
    registry.register_tool(tool=SlowTool(), name='slow')
    # default timeout overridden via constructor
    executor = ToolExecutor(registry, default_timeout=0.05)

    # Failing tool
    call_fail = ToolCall(tool='fail', arguments={'z': True})
    # Slow tool should timeout
    call_slow = ToolCall(tool='slow', arguments={})

    results = await executor.execute([call_fail, call_slow])
    assert len(results) == 2

    # Failing tool
    res_fail = results[0]
    assert res_fail.tool == 'fail'
    assert res_fail.result is None
    assert 'expected failure' in res_fail.error

    # Slow tool timeout
    res_slow = results[1]
    assert res_slow.tool == 'slow'
    assert res_slow.result is None
    assert 'Timeout' in res_slow.error

    # Metadata also present
    for res in results:
        assert isinstance(res.start_time, datetime)
        assert isinstance(res.end_time, datetime)
        assert res.start_time <= res.end_time
        assert isinstance(res.pid, int)
        assert isinstance(res.machine, str) and res.machine


