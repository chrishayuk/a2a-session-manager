#!/usr/bin/env python
"""
planner-first demo – **no fall-backs**
====================================

Runs end-to-end with *only* the tools that live in the global
`chuk_tool_processor` registry.  If a tool is missing, the demo fails fast –
no generic wrappers, no silent stubs – so the behaviour matches production.

A single convenience remains: we ship a minimal `compile_report` **real tool**
in case the registry doesn’t already provide one.  Because it’s a fully
registered tool (not a stub patched straight into the processor) it behaves
exactly like all others – there are still *zero* processor-side fall-backs.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Iterable, Tuple

# ── session & graph basics ────────────────────────────────────────────
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider
from a2a_session_manager.models.session import Session
from a2a_graph.store.memory import InMemoryGraphStore

# ── plan DSL + graph primitives ───────────────────────────────────────
from a2a_graph.planner import Plan
from a2a_graph.models import ToolCall
from a2a_graph.models.edges import GraphEdge, EdgeKind

# ── tool registry & sample tools ──────────────────────────────────────
from sample_tools import WeatherTool, CalculatorTool, SearchTool  # noqa: F401
from chuk_tool_processor.registry import default_registry

# ── processor & helpers ───────────────────────────────────────────────
from a2a_graph.processor import GraphAwareToolProcessor
from a2a_graph.demo.llm_simulator import simulate_llm_call
from a2a_graph.utils.visualization import print_session_events, print_graph_structure

# ─────────────────────── registry helper (no fall-backs) ─────────────

def _iter_registry_items() -> Iterable[Tuple[str, Any]]:
    """Yield (name, callable) pairs from *whatever* registry version is present."""
    # Preferred public API (≥ 0.5)
    if hasattr(default_registry, "iter_tools"):
        for meta in default_registry.iter_tools():
            yield meta.name, meta.callable if hasattr(meta, "callable") else meta
        return
    # Public dict (`.tools`) – some 0.4 releases
    if hasattr(default_registry, "tools"):
        for name, meta in default_registry.tools.items():  # type: ignore[attr-defined]
            yield name, getattr(meta, "callable", meta)
        return
    # Private dict (`._tools`) – very old snapshots
    for name, meta in getattr(default_registry, "_tools", {}).items():
        yield name, getattr(meta, "callable", meta)


# ────────────────────────── graph helpers ────────────────────────────

def _attach_tool(graph, step_id: str, name: str, args: Dict[str, Any]) -> ToolCall:
    """Create a `ToolCall` node, link it to the plan-step, and return it."""
    tc = ToolCall(data={"name": name, "args": args})
    graph.add_node(tc)
    graph.add_edge(GraphEdge(kind=EdgeKind.PLAN_LINK, src=step_id, dst=tc.id))
    return tc


# ─────────────────────────────── main ────────────────────────────────
async def main() -> None:
    # 1‒ session & in-memory graph ------------------------------------------------
    SessionStoreProvider.set_store(InMemorySessionStore())
    graph   = InMemoryGraphStore()
    session = Session(); SessionStoreProvider.get_store().save(session)

    # 2‒ author crafts logical plan ---------------------------------------------
    plan = (
        Plan("Weather → Calc → Search → Compile", graph=graph)
            .step("Check the weather in New York").up()
            .step("Calculate 235.5 × 18.75").up()
            .step("Search climate-change adaptation info").up()
            .step("Compile report", after=["1", "2", "3"])
    )
    print("\n📋  PLAN OUTLINE (before enrichment)\n")
    print(plan.outline(), "\n")

    plan_id = plan.save()

    # 3‒ enrichment – PlanStep index → id ---------------------------------------
    idx2id = {n.data["index"]: n.id for n in graph.nodes.values() if n.__class__.__name__ == "PlanStep"}

    weather_tc = _attach_tool(graph, idx2id["1"], "weather",    {"location": "New York"})
    calc_tc    = _attach_tool(graph, idx2id["2"], "calculator", {"operation": "multiply", "a": 235.5, "b": 18.75})
    search_tc  = _attach_tool(graph, idx2id["3"], "search",     {"query": "climate change adaptation"})
    _attach_tool(
        graph,
        idx2id["4"],
        "compile_report",
        {"inputs": {"weather": weather_tc.id, "calc": calc_tc.id, "search": search_tc.id}},
    )

    # 4‒ ensure *real* compile_report exists (one-time helper, still lives in registry)
    try:
        default_registry.get_tool("compile_report")
    except KeyError:

        from a2a_graph.store.base import GraphStore  # local import to avoid cycles

        @default_registry.register_tool(name="compile_report")  # type: ignore[attr-defined]
        class CompileReportTool:
            """Aggregate earlier ToolCall results referenced by node-id."""

            async def __call__(self, args: Dict[str, Any]):  # async to satisfy execute_tool
                g: GraphStore = graph  # use outer graph
                summary: Dict[str, Any] = {}
                for label, node_id in args.get("inputs", {}).items():
                    node = g.get_node(node_id)
                    summary[label] = node.data.get("result") if node else None
                return {"summary": summary}

    # 5‒ processor ----------------------------------------------------------------
    processor = GraphAwareToolProcessor(session_id=session.id, graph_store=graph)
    for name, fn in _iter_registry_items():  # **only** tools in registry
        processor.register_tool(name, fn)

    results = await processor.process_plan(
        plan_node_id=plan_id,
        assistant_node_id="assistant-node",  # dummy for demo
        llm_call_fn=simulate_llm_call,
    )

    # 6‒ output -------------------------------------------------------------------
    print("\n✅  TOOL RESULTS\n")
    for r in results:
        print(f"• {r.tool}\n{json.dumps(r.result, indent=2)}\n")

    print_session_events(session)
    print_graph_structure(graph)


if __name__ == "__main__":
    asyncio.run(main())