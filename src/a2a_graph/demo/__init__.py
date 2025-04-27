# a2a_graph/demo/__init__.py
"""
Demo components for showcasing a2a_graph functionality.

This package contains demonstration scripts, sample tools,
and a simulated LLM for testing the GraphAwareToolProcessor.
"""

from .tools import TOOL_REGISTRY, weather_tool, calculator_tool, search_tool
from .llm_simulator import simulate_llm_call

__all__ = [
    "TOOL_REGISTRY",
    "weather_tool",
    "calculator_tool", 
    "search_tool",
    "simulate_llm_call"
]