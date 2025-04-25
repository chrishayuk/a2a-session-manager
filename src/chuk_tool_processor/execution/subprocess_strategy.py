# chuk_tool_processor/execution/subprocess_strategy.py
import asyncio
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import List, Optional

# tool processor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.tool_registry import ToolRegistryInterface

class SubprocessStrategy(ExecutionStrategy):
    """
    Executes each call in a separate process pool worker for isolation.
    """
    def __init__(self, registry: ToolRegistryInterface, max_workers: int = 4, default_timeout: Optional[float] = None):
        self.registry = registry
        self.default_timeout = default_timeout
        self.pool = ProcessPoolExecutor(max_workers=max_workers)

    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        loop = asyncio.get_running_loop()
        tasks: List[asyncio.Future] = []
        for call in calls:
            # schedule each tool execution in process pool
            tasks.append(
                loop.run_in_executor(self.pool, self._run_sync, call)
            )

        # gather with timeouts
        results: List[ToolResult] = []
        for task in asyncio.as_completed(tasks):
            try:
                res = await asyncio.wait_for(task, timeout or self.default_timeout)
            except asyncio.TimeoutError:
                # build a generic timeout result
                res = ToolResult(
                    tool="unknown",
                    result=None,
                    error="Timeout",
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    machine=os.uname().nodename,
                    pid=os.getpid()
                )
            results.append(res)

        return results

    def _run_sync(self, call: ToolCall) -> ToolResult:
        """
        Sync helper to execute a single call and capture result metadata.
        """
        pid = os.getpid()
        machine = os.uname().nodename
        start_time = datetime.now(timezone.utc)
        impl = self.registry.get_tool(call.tool)

        if not impl:
            return ToolResult(
                tool=call.tool,
                result=None,
                error="Tool not found",
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid
            )

        try:
            result_value = impl.execute(**call.arguments)
            return ToolResult(
                tool=call.tool,
                result=result_value,
                error=None,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid
            )
        except Exception as e:
            return ToolResult(
                tool=call.tool,
                result=None,
                error=str(e),
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid
            )
