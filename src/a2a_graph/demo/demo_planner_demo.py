# src/a2a_graph/demo/demo_planner_demo.py
"""
Planner-first demo

1. Build a hierarchical plan with the high-level Plan DSL (no graph calls).
2. Persist it (PlanNode + PlanStep only).
3. **Enrichment phase:** attach ToolCall nodes to selected steps.
4. Run with GraphAwareToolProcessor.
"""

import asyncio
import json
from typing import Dict, Any

# Session manager
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider
from a2a_session_manager.models.session import Session

# Graph & processor
from a2a_graph.planner import Plan
from a2a_graph.models import ToolCall
from a2a_graph.models.edges import GraphEdge, EdgeKind
from a2a_graph.processor import GraphAwareToolProcessor
from a2a_graph.demo.tools import TOOL_REGISTRY
from a2a_graph.demo.llm_simulator import simulate_llm_call
from a2a_graph.utils.visualization import print_session_events, print_graph_structure
from a2a_graph.store.memory import InMemoryGraphStore


# -------------------------------------------------------------------- helpers
def attach_tool(
    graph, step_id: str, name: str, args: Dict[str, Any]
) -> None:
    """Create a ToolCall node + PLAN_LINK edge pointing to `step_id`."""
    tc = ToolCall(data={"name": name, "args": args})
    graph.add_node(tc)
    graph.add_edge(GraphEdge(kind=EdgeKind.PLAN_LINK, src=step_id, dst=tc.id))


async def main() -> None:
    # ---------------------------------------------------------------- 1  session + shared graph
    SessionStoreProvider.set_store(InMemorySessionStore())
    graph = InMemoryGraphStore()

    session = Session()
    SessionStoreProvider.get_store().save(session)

    # ---------------------------------------------------------------- 2  build plan (only titles & deps)
    plan = (
        Plan("Weather + Calc + Search + Compile", graph=graph)
          .step("Check the weather in New York")                       # index 1
          .up()
          .step("Calculate 235.5 × 18.75")                             # index 2
          .up()
          .step("Search for climate change adaptation information")    # index 3
          .up()
          .step("Compile and present all information", after=["1", "2", "3"])  # index 4
    )

    print("📋 Plan outline before enrichment:\n")
    print(plan.outline(), "\n")

    plan_id = plan.save(session)      # Only PlanNode + PlanStep now exist

    # ---------------------------------------------------------------- 3  enrichment (simulate LLM attaching tools)
    # Find helper: step index → step_id
    index_to_id = {
        n.data["index"]: n.id
        for n in graph.nodes.values()
        if n.__class__.__name__ == "PlanStep"
    }

    attach_tool(graph, index_to_id["1"], "weather",
                {"location": "New York"})
    attach_tool(graph, index_to_id["2"], "calculator",
                {"a": 235.5, "b": 18.75, "op": "*"})
    attach_tool(graph, index_to_id["3"], "web_search",
                {"q": "climate change adaptation"})
    attach_tool(graph, index_to_id["4"], "compile_report",
                {"inputs": {"weather": "<<weather>>",
                            "calc": "<<calc>>",
                            "search": "<<search>>"}})

    # Provide stub tools if missing
    if "web_search" not in TOOL_REGISTRY:
        async def _stub_search(args): return {"top_result": f"Dummy for {args['q']}"}
        TOOL_REGISTRY["web_search"] = _stub_search
    if "compile_report" not in TOOL_REGISTRY:
        async def _stub_compile(args): return {"summary": "Compiled", **args}
        TOOL_REGISTRY["compile_report"] = _stub_compile

    # ---------------------------------------------------------------- 4  run via processor
    processor = GraphAwareToolProcessor(session_id=session.id, graph_store=graph)
    for n, fn in TOOL_REGISTRY.items():
        processor.register_tool(n, fn)

    results = await processor.process_plan(
        plan_node_id=plan_id,
        assistant_node_id=None,
        llm_call_fn=simulate_llm_call
    )

    print("✅ Tool results:")
    for r in results:
        print("  ", r.tool, "->", json.dumps(r.result, indent=2))

    # ---------------------------------------------------------------- 5  visualize
    print_session_events(session)
    print_graph_structure(graph)


if __name__ == "__main__":
    asyncio.run(main())
