#!/usr/bin/env python
# examples/run_plan_executor.py
"""
run_plan_executor.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A polished demonstration of PlanExecutor with a human-readable log.

Plan hierarchy
--------------
  1     Make coffee
        1.1  Grind beans
  2     Read news  (depends on 1)

Each step owns a ToolCall invoking the dummy async `echo` tool.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Callable, Awaitable

from a2a_graph.planner.plan_executor import PlanExecutor
from a2a_graph.store.memory import InMemoryGraphStore
from a2a_graph.models import GraphNode, NodeKind
from a2a_graph.models.edges import EdgeKind, GraphEdge, ParentChildEdge
from a2a_graph.utils.pretty import PlanRunLogger, clr, pretty_print_plan
from a2a_session_manager.models.event_type import EventType

# ───────────────────────────── build tiny graph ──────────────────────────
print(clr("🟢  BUILD GRAPH", "1;32"))
graph = InMemoryGraphStore()

plan = GraphNode(kind=NodeKind.PLAN, data={"description": "Morning routine"})
graph.add_node(plan)

s1   = GraphNode(kind=NodeKind.PLAN_STEP, data={"description": "Make coffee", "index": "1"})
s11  = GraphNode(kind=NodeKind.PLAN_STEP, data={"description": "Grind beans", "index": "1.1"})
s2   = GraphNode(kind=NodeKind.PLAN_STEP, data={"description": "Read news",  "index": "2"})
for n in (s1, s11, s2): graph.add_node(n)

graph.add_edge(ParentChildEdge(src=plan.id, dst=s1.id))
graph.add_edge(ParentChildEdge(src=s1.id,   dst=s11.id))
graph.add_edge(ParentChildEdge(src=plan.id, dst=s2.id))
graph.add_edge(GraphEdge(kind=EdgeKind.STEP_ORDER, src=s1.id, dst=s2.id))

# tool-call helper
def attach(step: GraphNode, msg: str):
    tc = GraphNode(kind=NodeKind.TOOL_CALL, data={"name": "echo", "args": {"msg": msg}})
    graph.add_node(tc)
    graph.add_edge(GraphEdge(kind=EdgeKind.PLAN_LINK, src=step.id, dst=tc.id))

attach(s11, "Grinding…")
attach(s1,  "Brewing ☕")
attach(s2,  "Good morning headlines")

pretty_print_plan(graph, plan)
print()

# ───────────────────────────── stub echo tool ────────────────────────────
async def echo_tool(args: Dict[str, Any]): return {"echo": args}
async def real_process(tc, evt_id, aid):
    return await echo_tool(json.loads(tc["function"]["arguments"] or "{}"))

# wrapper logger
logger = PlanRunLogger(graph, plan.id)

# ──────────────────────────────── execute ────────────────────────────────
async def main():
    print(clr("🛠  EXECUTE", "1;34"))
    px = PlanExecutor(graph)

    results: List[Any] = []
    steps   = px.get_plan_steps(plan.id)
    batches = px.determine_execution_order(steps)

    for batch in batches:
        coros = [
            px.execute_step(
                sid,
                assistant_node_id="assistant",
                parent_event_id="root",
                create_child_event=logger.evt,
                process_tool_call=lambda tc, e, a, _sid=sid: logger.proc(tc, e, a, real_proc=real_process),
            )
            for sid in batch
        ]
        for r in await asyncio.gather(*coros):
            results.extend(r)

    print(clr("\n🎉  RESULTS", "1;32"))
    for r in results:
        print(json.dumps(r, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
