# a2a_graph/models/edges/__init__.py
"""
Unified import surface for edge types:

    from a2a_graph.models.edges import ParentChildEdge, EdgeKind, …
"""
from .base      import EdgeKind, GraphEdge
from .hierarchy import ParentChildEdge
from .ordering  import NextEdge
from .planning  import PlanEdge, StepEdge

__all__ = (
    "EdgeKind",
    "GraphEdge",
    "ParentChildEdge",
    "NextEdge",
    "PlanEdge",
    "StepEdge",
)
