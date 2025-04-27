# a2a_graph/models/edges/base.py
from __future__ import annotations
from enum import Enum
from typing import Any, Dict
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# all
__all__ = ["EdgeKind", "GraphEdge"]


class EdgeKind(str, Enum):
    """Canonical edge semantics."""
    PARENT_CHILD = "parent_child"   # hierarchy
    NEXT = "next"                   # temporal / sequential
    PLAN_LINK = "plan_link"         # plan-to-task / step
    STEP_ORDER = "step_order"       # step-1 → step-2
    CUSTOM = "custom"               # catch-all


class _FrozenMixin:
    def __setattr__(self, name: str, value: Any) -> None:  # noqa: D401
        try:
            super().__setattr__(name, value)  # type: ignore[misc]
        except ValidationError as exc:
            raise TypeError(str(exc)) from None


class GraphEdge(_FrozenMixin, BaseModel):
    """Directed edge between two GraphNode ids."""
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: EdgeKind
    src: str
    dst: str
    data: Dict[str, Any] = Field(default_factory=dict)

    def __repr__(self) -> str:  # noqa: D401
        return f"<{self.kind.value}:{self.src[:6]}→{self.dst[:6]}>"
