# chuk_tool_processor/tool_registry.py
from typing import Protocol, Any, Dict, List, Optional


class ToolRegistryInterface(Protocol):
    """
    Protocol for a tool registry. Implementations should allow registering tools
    and retrieving them by name.
    """
    def register_tool(self, tool: Any, name: Optional[str] = None) -> None:
        ...

    def get_tool(self, name: str) -> Optional[Any]:
        ...

    def list_tools(self) -> List[str]:
        ...


class InMemoryToolRegistry:
    """
    In-memory implementation of ToolRegistryInterface.
    """
    def __init__(self):
        self._tools: Dict[str, Any] = {}

    def register_tool(self, tool: Any, name: Optional[str] = None) -> None:
        """
        Register a tool implementation.

        Args:
            tool: The tool class or instance with an `execute` method.
            name: Optional explicit name; if omitted, uses tool.__name__.
        """
        key = name or getattr(tool, "__name__", None) or repr(tool)
        self._tools[key] = tool

    def get_tool(self, name: str) -> Optional[Any]:
        """
        Retrieve a registered tool by name.
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """
        List all registered tool names.
        """
        return list(self._tools.keys())


class ToolRegistryProvider:
    """
    Global provider for a ToolRegistryInterface implementation.
    Use `set_registry` to override (e.g., for testing).
    """
    _registry: ToolRegistryInterface = InMemoryToolRegistry()

    @classmethod
    def get_registry(cls) -> ToolRegistryInterface:
        return cls._registry

    @classmethod
    def set_registry(cls, registry: ToolRegistryInterface) -> None:
        cls._registry = registry
