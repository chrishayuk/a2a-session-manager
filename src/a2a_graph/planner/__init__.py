# src/a2a_graph/planner/__init__.py
"""
a2a_graph.planner package
=========================

Re-exports the public surface of the *planner* subsystem so callers can
simply write:

    from a2a_graph.planner import Plan, PlanExecutor
"""

from .plan import Plan                 # high-level author DSL
from .plan_executor import PlanExecutor  # low-level internal helper

__all__ = ["Plan", "PlanExecutor"]

