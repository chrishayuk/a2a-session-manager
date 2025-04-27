# a2a_graph/plan_executor.py
from typing import List, Dict, Set, Callable, Any, Awaitable, Optional
import json

from a2a_graph.models import GraphNode, NodeKind
from a2a_graph.models.edges import EdgeKind
from a2a_session_manager.models.event_type import EventType

from .store.base import GraphStore


class PlanExecutor:
    """
    Extract plan steps, compute execution batches, and execute individual steps.
    """
    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store

    # ------------------------------------------------------------------ steps
    def get_plan_steps(self, plan_id: str) -> List[GraphNode]:
        edges = self.graph_store.get_edges(src=plan_id, kind=EdgeKind.PARENT_CHILD)
        steps: List[GraphNode] = [
            self.graph_store.get_node(e.dst)
            for e in edges
            if (self.graph_store.get_node(e.dst) and
                self.graph_store.get_node(e.dst).kind == NodeKind.PLAN_STEP)
        ]
        return sorted(steps, key=lambda s: s.data.get("index", 0))

    # ------------------------------------------------------------------ batches
    def determine_execution_order(self, steps: List[GraphNode]) -> List[List[str]]:
        """
        Returns a list of batches; each batch is a list of step-IDs that can
        execute in parallel. An edge STEP_ORDER(src → dst) means **dst depends
        on src**.
        """
        dependencies: Dict[str, Set[str]] = {s.id: set() for s in steps}
        dependents:   Dict[str, Set[str]] = {s.id: set() for s in steps}

        for step in steps:
            outs = self.graph_store.get_edges(src=step.id, kind=EdgeKind.STEP_ORDER)
            for e in outs:
                # dst is blocked on src
                dependencies[e.dst].add(step.id)
                dependents[step.id].add(e.dst)          # <-- fixed line

        # first batch: steps with no unmet deps
        ready = [sid for sid, deps in dependencies.items() if not deps]
        if not ready and steps:
            ready = [steps[0].id]

        batches: List[List[str]] = []
        while ready:
            batches.append(ready)
            next_ready: List[str] = []

            for sid in ready:
                for dependent in list(dependents[sid]):
                    dependencies[dependent].discard(sid)
                    if not dependencies[dependent]:
                        next_ready.append(dependent)

            ready = next_ready

        return batches

    # ------------------------------------------------------------------ execute
    async def execute_step(
        self,
        step_id: str,
        assistant_node_id: str,
        parent_event_id: str,
        create_child_event: Callable[[EventType, Dict[str, Any], str], Any],
        process_tool_call: Callable[[Dict[str, Any], str, Optional[str]], Awaitable[Any]]
    ) -> List[Any]:
        step_node = self.graph_store.get_node(step_id)
        if not step_node or step_node.kind != NodeKind.PLAN_STEP:
            raise ValueError(f"Invalid plan step: {step_id}")

        start_evt = create_child_event(
            EventType.SUMMARY,
            {
                "step_id": step_id,
                "description": step_node.data.get("description", "Unknown step"),
                "status": "started",
            },
            parent_event_id,
        )

        results: List[Any] = []
        tool_edges = self.graph_store.get_edges(src=step_id, kind=EdgeKind.PLAN_LINK)

        for edge in tool_edges:
            tool_node = self.graph_store.get_node(edge.dst)
            if not tool_node or tool_node.kind != NodeKind.TOOL_CALL:
                continue

            tool_call = {
                "id": tool_node.id,
                "type": "function",
                "function": {
                    "name": tool_node.data.get("name"),
                    "arguments": json.dumps(tool_node.data.get("args", {})),
                },
            }
            res = await process_tool_call(tool_call, start_evt.id, assistant_node_id)
            results.append(res)

        create_child_event(
            EventType.SUMMARY,
            {"step_id": step_id, "status": "completed", "tools_executed": len(results)},
            parent_event_id,
        )
        return results
