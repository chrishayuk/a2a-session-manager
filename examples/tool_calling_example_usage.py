"""
Demonstrates tool registration, parsing with JSON/XML/function-call plugins,
executing with in-process and subprocess strategies, timeouts, sequential and parallel tasks,
and printing colorized results including durations, host info, process IDs, and timeout handling.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, List

# ANSI colors
from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)

# tool processor imports
from chuk_tool_processor.tool_registry import InMemoryToolRegistry
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.subprocess_strategy import SubprocessStrategy

from chuk_tool_processor.plugins.json_tool import JsonToolPlugin
from chuk_tool_processor.plugins.xml_tool import XmlToolPlugin
from chuk_tool_processor.plugins.function_call_tool import FunctionCallPlugin
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# --- Dummy tools ---
class EchoTool:
    def execute(self, **kwargs: Any) -> str:
        return f"Echo: {kwargs}"

class AsyncComputeTool:
    async def execute(self, **kwargs: Any) -> str:
        await asyncio.sleep(0.1)
        total = sum(v for v in kwargs.values() if isinstance(v, (int, float)))
        return f"Sum: {total}"

class SlowTool:
    async def execute(self, **kwargs: Any) -> str:
        await asyncio.sleep(2)
        return "Done"

class ErrorTool:
    def execute(self, **kwargs: Any) -> Any:
        raise RuntimeError("Tool failure occurred")

# --- Common plugins and calls ---
plugins = [
    ("JSON Plugin", JsonToolPlugin(), json.dumps({
        "tool_calls": [{"tool": "echo", "arguments": {"msg": "Hello JSON"}}]
    })),
    ("XML Plugin", XmlToolPlugin(), '<tool name="compute" args=\'{"a":5,"b":7}\'/>' ),
    ("FunctionCall Plugin", FunctionCallPlugin(), json.dumps({
        "function_call": {"name": "echo", "arguments": {"user": "Alice", "action": "login"}}
    })),
    ("Slow Tool Plugin", JsonToolPlugin(), json.dumps({
        "tool_calls": [{"tool": "slow", "arguments": {}}]
    })),
    ("Error Tool Plugin", JsonToolPlugin(), json.dumps({
        "tool_calls": [{"tool": "error", "arguments": {}}]
    })),
]

# --- Helper to format and print results ---
def print_results(title: str, calls: List[ToolCall], results: List[ToolResult]):
    print(Fore.CYAN + f"\n=== {title} ===")
    for call, r in zip(calls, results):
        duration = (r.end_time - r.start_time).total_seconds()
        color = Fore.GREEN if not r.error else Fore.RED
        header = color + f"{r.tool} ({duration:.3f}s) [pid:{r.pid}]"
        print(header + Style.RESET_ALL)
        print(f"  {Fore.YELLOW}Args:{Style.RESET_ALL}    {call.arguments}")
        if r.error and r.error.startswith("Timeout"):
            print(f"  {Fore.RED}Timeout:{Style.RESET_ALL}  {r.error}")
        else:
            print(f"  {Fore.MAGENTA}Result:{Style.RESET_ALL}  {r.result!r}")
            if r.error:
                print(f"  {Fore.RED}Error:{Style.RESET_ALL}   {r.error!r}")
        print(f"  Started: {r.start_time.isoformat()}")
        print(f"  Finished:{r.end_time.isoformat()}")
        print(f"  Host:    {r.machine}")
        print(Style.DIM + "-" * 60)

# --- Runner helper ---
async def run_all(executor: ToolExecutor):
    # Sequential
    for title, plugin, raw in plugins:
        calls = plugin.try_parse(raw)
        timeout = 0.5 if "Slow Tool Plugin" in title else None
        results = await executor.execute(calls, timeout=timeout)
        print_results(f"{title} (sequential)", calls, results)
        await asyncio.sleep(0.1)

    # Parallel
    print(Fore.CYAN + "\n=== Parallel Echo Tasks ===")
    parallel_calls = [ToolCall(tool="echo", arguments={"i": i}) for i in range(5)]
    tasks = [
        (call, asyncio.create_task(executor.execute([call]), name=f"echo-{i}"))
        for i, call in enumerate(parallel_calls)
    ]
    for call, task in tasks:
        try:
            results = await asyncio.wait_for(task, timeout=2.0)
            print(Fore.YELLOW + f"Task {task.get_name()} completed")
            print_results("Parallel echo result", [call], results)
        except asyncio.TimeoutError:
            print(Fore.RED + f"Task {task.get_name()} timed out")

# --- Main ---
async def main():
    registry = InMemoryToolRegistry()
    registry.register_tool(EchoTool(), name="echo")
    registry.register_tool(AsyncComputeTool(), name="compute")
    registry.register_tool(SlowTool(), name="slow")
    registry.register_tool(ErrorTool(), name="error")

    print(Fore.BLUE + "\n--- Using InProcessStrategy ---")
    executor_ip = ToolExecutor(
        registry,
        strategy=InProcessStrategy(registry, default_timeout=1.0)
    )
    await run_all(executor_ip)

    print(Fore.BLUE + "\n--- Using SubprocessStrategy ---")
    try:
        executor_sp = ToolExecutor(
            registry,
            strategy=SubprocessStrategy(registry, max_workers=4, default_timeout=1.0)
        )
        await run_all(executor_sp)
    except Exception as e:
        print(Fore.RED + "SubprocessStrategy demo skipped due to error:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
