# a2a_graph/demo/__init__.py
"""
Demo helpers for a2a_graph

• simulate_llm_call – tiny fake-LLM utility used by the demo scripts
"""

from __future__ import annotations

# keep the simulator (still useful for demos / tests)
from .llm_simulator import simulate_llm_call

__all__: list[str] = ["simulate_llm_call"]
