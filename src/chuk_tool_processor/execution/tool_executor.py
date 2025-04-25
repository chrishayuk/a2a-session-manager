# chuk_tool_processor/execution/tool_executor.py
from typing import List, Optional

# tool processor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.execution.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.tool_registry import ToolRegistryInterface

class ToolExecutor:
    """
    Wraps an ExecutionStrategy (in‐process or subprocess) and provides
    a default_timeout shortcut for convenience.
    """
    def __init__(
        self,
        registry: ToolRegistryInterface,
        default_timeout: float = 1.0,
        strategy: Optional[ExecutionStrategy] = None,
        # allow passing through to SubprocessStrategy if needed:
        strategy_kwargs: dict = {}
    ):
        # If user supplied a strategy, use it; otherwise default to in-process
        if strategy is not None:
            self.strategy = strategy
        else:
            self.strategy = InProcessStrategy(
                registry=registry,
                default_timeout=default_timeout
            )
        self.registry = registry

    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        """
        Execute the list of calls with the underlying strategy.
        `timeout` here overrides the strategy's default_timeout.
        """
        return await self.strategy.run(calls, timeout=timeout)
