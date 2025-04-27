# src/a2a_graph/demo/demo_graph_processor.py
"""
Fully-wired GraphAwareToolProcessor demo

Plan steps → tool mapping
  1. Check weather  → weather(location="New York")
  2. Calculate      → calculator(a=235.5, b=18.75, op="*")
  3. Search         → web_search(q="climate change adaptation")
  4. Compile report → compile_report(inputs={weather, calculation, search})

If web_search or compile_report aren’t in TOOL_REGISTRY the demo supplies stubs.
"""

import asyncio
from typing import List

# ── Session-manager imports ────────────────────────────────────────────
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource

# ── Graph-model imports ────────────────────────────────────────────────
from a2a_graph.models import (
    SessionNode, UserMessage, AssistantMessage,
    PlanNode, PlanStep, ToolCall
)
from a2a_graph.models.edges import (
    ParentChildEdge, NextEdge, StepEdge,
    GraphEdge, EdgeKind
)

# ── Local library imports ─────────────────────────────────────────────
from a2a_graph.processor import GraphAwareToolProcessor
from a2a_graph.store.memory import InMemoryGraphStore
from a2a_graph.utils.visualization import print_session_events, print_graph_structure
from a2a_graph.demo.tools import TOOL_REGISTRY
from a2a_graph.demo.llm_simulator import simulate_llm_call


async def main() -> None:
    print("🚀  demo start")

    # ------------------------------------------------------------------ 1
    SessionStoreProvider.set_store(InMemorySessionStore())
    g = InMemoryGraphStore()

    session = Session()
    SessionStoreProvider.get_store().save(session)
    s_node = SessionNode(data={"session_manager_id": session.id})
    g.add_node(s_node)

    # ------------------------------------------------------------------ 2
    user_txt = (
        "What's the weather like in New York, calculate 235.5×18.75, "
        "and search for climate-change adaptation."
    )
    session.events.append(SessionEvent(
        message=user_txt, type=EventType.MESSAGE, source=EventSource.USER
    ))

    u_node = UserMessage(data={"content": user_txt}); g.add_node(u_node)
    a_node = AssistantMessage(data={"content": None}); g.add_node(a_node)

    g.add_edge(ParentChildEdge(src=s_node.id, dst=u_node.id))
    g.add_edge(ParentChildEdge(src=s_node.id, dst=a_node.id))
    g.add_edge(NextEdge(src=u_node.id, dst=a_node.id))

    # ------------------------------------------------------------------ 3
    plan = PlanNode(data={"description": "weather + calc + search + compile"}); g.add_node(plan)
    g.add_edge(ParentChildEdge(src=s_node.id, dst=plan.id))
    g.add_edge(ParentChildEdge(src=a_node.id, dst=plan.id))

    step_specs = [
        ("Check the weather in New York",                    1),
        ("Calculate 235.5 × 18.75",                          2),
        ("Search for climate change adaptation information", 3),
        ("Compile and present all information",              4),
    ]
    steps: List[PlanStep] = []
    for desc, idx in step_specs:
        s = PlanStep(data={"description": desc, "index": idx})
        steps.append(s); g.add_node(s)
        g.add_edge(ParentChildEdge(src=plan.id, dst=s.id))

    for s in steps[:3]:  # step-4 depends on 1-3
        g.add_edge(StepEdge(src=s.id, dst=steps[3].id))

    # ------------------------------------------------------------------ 4
    # TOOL_CALL nodes + PLAN_LINK
    def link_tool(step, name, args):
        tc = ToolCall(data={"name": name, "args": args})
        g.add_node(tc)
        g.add_edge(GraphEdge(kind=EdgeKind.PLAN_LINK, src=step.id, dst=tc.id))
        return tc

    link_tool(steps[0], "weather",     {"location": "New York"})
    link_tool(steps[1], "calculator",  {"a": 235.5, "b": 18.75, "op": "*"})
    link_tool(steps[2], "web_search",  {"q": "climate change adaptation"})

    # Stub tools if missing
    if "web_search" not in TOOL_REGISTRY:
        async def _stub_search(args): return {"top_result": f"Dummy for '{args.get('q')}'"}
        TOOL_REGISTRY["web_search"] = _stub_search
    if "compile_report" not in TOOL_REGISTRY:
        async def _stub_compile(args): return {"summary": "Compiled report", **args}
        TOOL_REGISTRY["compile_report"] = _stub_compile

    # compile_report gets IDs of previous tool calls (just placeholders here)
    link_tool(steps[3], "compile_report", {
        "inputs": {
            "weather":   "<<weather-id>>",
            "calculation": "<<calc-id>>",
            "search":   "<<search-id>>"
        }
    })

    # ------------------------------------------------------------------ 5
    proc = GraphAwareToolProcessor(session_id=session.id, graph_store=g)
    for name, fn in TOOL_REGISTRY.items():
        proc.register_tool(name, fn)

    batches = proc.plan_executor.determine_execution_order(
        proc.plan_executor.get_plan_steps(plan.id)
    )
    print("🔍 batches", batches)

    # ------------------------------------------------------------------ 6
    print("\n==== EXECUTING PLAN ====")
    results = await proc.process_plan(plan_node_id=plan.id,
                                      assistant_node_id=a_node.id,
                                      llm_call_fn=simulate_llm_call)
    print(f"✅ plan produced {len(results)} results")
    for r in results:
        print("⮑", r.tool, "->", r.result)

    # ------------------------------------------------------------------ 7
    print_session_events(session)
    print_graph_structure(g)
    print("✨ finished")


if __name__ == "__main__":
    asyncio.run(main())
