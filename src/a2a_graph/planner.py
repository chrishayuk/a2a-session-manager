"""a2a_graph.planner
~~~~~~~~~~~~~~~~~~~

Author‑facing *plan* DSL that hides the low‑level graph primitives.  A
plan is a hierarchy of steps (``1``, ``1.2``, ``1.2.1`` …).  Each step
gets a stable UUID and a human‑readable *hierarchical index* so LLMs or
humans can reference it easily.  Only **PlanNode**, **PlanStep** and
structural edges are persisted; tool‑call nodes may be attached later by
another agent, an LLM, or code.

Typical usage
-------------
>>> from a2a_graph.planner import Plan
>>> plan = (Plan("Demo")
...             .step("Check weather")
...                 .step("Look at forecast")
...                 .up()
...             .step("Do calculation")
...             .step("Compile", after=["1", "2"]))
>>> print(plan.outline())
Plan: Demo   (id: 7b58d6e2)
  1     Check weather                    (step_id: 08fd5d22)
  1.1   Look at forecast                 (step_id: e4b9a8f1)
  2     Do calculation                   (step_id: 1d45ca60)
  3     Compile   depends on ['1', '2']  (step_id: 95ba6f77)

Later an LLM can add ToolCall nodes referencing ``step_id``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Optional

from a2a_graph.models import PlanNode, PlanStep
from a2a_graph.models.edges import ParentChildEdge, StepEdge
from a2a_graph.store.base import GraphStore
from a2a_graph.store.memory import InMemoryGraphStore

__all__ = ["Plan"]


def _uid() -> str:  # helper
    return str(uuid.uuid4())


@dataclass
class _Step:
    """Internal mutable step object."""

    title: str
    parent: Optional["_Step"] = None
    after: List[str] = field(default_factory=list)  # dependency indices

    # runtime‑filled fields
    id: str = field(default_factory=_uid)
    index: str = ""  # hierarchical index like "1.2.1"
    children: List["_Step"] = field(default_factory=list)

    # ---- builder helpers --------------------------------------------
    def step(self, title: str, *, after: Sequence[str] = ()) -> "_Step":
        child = _Step(title=title, parent=self, after=list(after))
        self.children.append(child)
        return child

    def up(self) -> "_Step":  # go to parent or stay
        return self.parent or self


class Plan:
    """High‑level Plan façade hiding graph details."""

    def __init__(self, title: str, *, graph: GraphStore | None = None):
        self.title = title
        self.id: str = _uid()
        self._graph: GraphStore = graph or InMemoryGraphStore()

        self._root = _Step("[ROOT]")  # dummy container, not persisted
        self._cursor = self._root
        self._index_map: Dict[str, _Step] = {}

    # ---------------------------------------------------------------- builder DSL
    def step(self, title: str, *, after: Sequence[str] = ()) -> "Plan":
        """Add a child step under the current cursor and descend into it."""
        self._cursor = self._cursor.step(title, after=after)
        return self

    def up(self) -> "Plan":
        """Move cursor one level up (no‑op at root)."""
        self._cursor = self._cursor.up()
        return self

    def add_step(self, title: str, *, parent: str | None = None, after: Sequence[str] = ()) -> str:
        """Add a step *after saving*, possibly at runtime.

        Parameters
        ----------
        title   : str           human description
        parent  : str | None    hierarchical index (e.g. "1.2") to attach under; ``None`` → root
        after   : list[str]     extra dependencies by hierarchical index
        Returns
        -------
        str : hierarchical index assigned to the new step.
        """
        self._ensure_indices()
        parent_step = self._index_map.get(parent) if parent else self._root
        if parent and not parent_step:
            raise ValueError(f"parent index {parent!r} does not exist")
        new_idx_num = len(parent_step.children) + 1
        hindex = f"{parent_step.index}.{new_idx_num}" if parent_step.index else str(new_idx_num)

        step = _Step(title=title, parent=parent_step, after=list(after))
        step.index = hindex
        parent_step.children.append(step)
        self._index_map[hindex] = step

        # persist immediately
        self._persist_step(step, parent_step)
        return hindex

    # ---------------------------------------------------------------- outline & numbering
    def _ensure_indices(self):
        if self._index_map:
            return  # already assigned
        self._assign_indices()

    def _assign_indices(self):
        """Depth‑first numbering; fills .index & _index_map."""
        stack: List[tuple[_Step, str]] = [(self._root, "")]
        while stack:
            node, prefix = stack.pop()
            for i, child in reversed(list(enumerate(node.children, 1))):
                child.index = f"{prefix}{i}" if prefix else str(i)
                self._index_map[child.index] = child
                stack.append((child, f"{child.index}."))

    def outline(self) -> str:
        """Return a numbered plain‑text outline (for humans/LLMs)."""
        self._ensure_indices()
        lines = [f"Plan: {self.title}   (id: {self.id[:8]})"]

        def walk(st: _Step):
            for ch in st.children:
                dep = f"  depends on {ch.after}" if ch.after else ""
                lines.append(f"  {ch.index:<6} {ch.title:<35} (step_id: {ch.id[:8]}){dep}")
                walk(ch)
        walk(self._root)
        return "\n".join(lines)

    # ---------------------------------------------------------------- persistence
    def save(self, session) -> str:
        """Persist plan structure (no tools) into the graph store."""
        self._ensure_indices()

        plan_node = PlanNode(id=self.id, data={"description": self.title})
        self._graph.add_node(plan_node)

        # link to session's root graph node if you have one
        # (omitted here—caller can do it if needed)

        for st in self._index_map.values():
            parent = st.parent or self._root
            plan_step = PlanStep(id=st.id, data={"description": st.title, "index": st.index})
            self._graph.add_node(plan_step)
            self._graph.add_edge(ParentChildEdge(src=plan_node.id, dst=plan_step.id))
            if parent is not self._root:
                self._graph.add_edge(ParentChildEdge(src=parent.id, dst=plan_step.id))

        for st in self._index_map.values():
            for dep_idx in st.after:
                dep = self._index_map.get(dep_idx)
                if dep:
                    self._graph.add_edge(StepEdge(src=dep.id, dst=st.id))

        return plan_node.id

    # ---------------------------------------------------------------- helper
    def _persist_step(self, st: _Step, parent: _Step):
        """Persist a *new* step that was added after save()."""
        ps = PlanStep(id=st.id, data={"description": st.title, "index": st.index})
        self._graph.add_node(ps)
        self._graph.add_edge(ParentChildEdge(src=self.id, dst=ps.id))
        if parent is not self._root:
            self._graph.add_edge(ParentChildEdge(src=parent.id, dst=ps.id))
        for dep in st.after:
            dep_step = self._index_map.get(dep)
            if dep_step:
                self._graph.add_edge(StepEdge(src=dep_step.id, dst=st.id))

    # expose graph to caller for enrichment or execution
    @property
    def graph(self) -> GraphStore:
        return self._graph
