# chuk_tool_processor/execution/inprocess_strategy.py
import asyncio
import os
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import List, Optional

# tool processor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.tool_registry import ToolRegistryInterface


class InProcessStrategy(ExecutionStrategy):
    """
    Default in-process execution: sequential, with async support and timeouts.
    """
    def __init__(self, registry: ToolRegistryInterface, default_timeout: Optional[float] = None):
        self.registry = registry
        self.default_timeout = default_timeout

    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        results: List[ToolResult] = []
        pid = os.getpid()
        machine = os.uname().nodename
        per_call_timeout = timeout if timeout is not None else self.default_timeout

        for call in calls:
            start_time = datetime.now(timezone.utc)
            impl = self.registry.get_tool(call.tool)

            if not impl:
                end_time = datetime.now(timezone.utc)
                results.append(ToolResult(
                    tool=call.tool,
                    result=None,
                    error="Tool not found",
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid
                ))
                continue

            try:
                raw = impl.execute(**call.arguments)
                # wrap sync calls
                if not asyncio.iscoroutine(raw):
                    raw_coro = asyncio.get_running_loop().run_in_executor(None, lambda: raw)
                else:
                    raw_coro = raw

                if per_call_timeout:
                    result_value = await asyncio.wait_for(raw_coro, per_call_timeout)
                else:
                    result_value = await raw_coro

                end_time = datetime.now(timezone.utc)
                results.append(ToolResult(
                    tool=call.tool,
                    result=result_value,
                    error=None,
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid
                ))

            except asyncio.TimeoutError:
                end_time = datetime.now(timezone.utc)
                results.append(ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Timeout after {per_call_timeout}s",
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid
                ))
            except Exception as e:
                end_time = datetime.now(timezone.utc)
                results.append(ToolResult(
                    tool=call.tool,
                    result=None,
                    error=str(e),
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid
                ))

        return results