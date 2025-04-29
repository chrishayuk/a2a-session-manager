#!/usr/bin/env python
"""
cli/demo_cli.py – iterative planning CLI
========================================
$ uv run cli/demo_cli.py \
    "Where is the best place to buy cheese in the UK?"
"""

from __future__ import annotations

import argparse, asyncio, json, os, uuid
import traceback
import warnings
from typing import Any, Dict, Tuple
from urllib.parse import urlparse, parse_qs, unquote

from dotenv import load_dotenv
load_dotenv()                        # ← OPENAI_API_KEY

# ── demo tools (auto-register on import) ────────────────────────────
from sample_tools import WeatherTool, SearchTool, VisitURL  # noqa: F401

# ── A2A plumbing ────────────────────────────────────────────────────
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider
from a2a_session_manager.models.session import Session
from a2a_graph.store.memory import InMemoryGraphStore
from a2a_graph.planner import Plan
from a2a_graph.models import ToolCall
from a2a_graph.models.edges import GraphEdge, EdgeKind
from a2a_graph.processor import GraphAwareToolProcessor
from a2a_graph.utils.visualization import print_session_events, print_graph_structure
from a2a_graph.utils.registry_helpers import execute_tool

# ── planning agent ---------------------------------------------------
from a2a_graph.agents.plan_agent import PlanAgent

# ╭──────────────────────────────────────────────────────────────────╮
# │ 1.  TOOL ALLOW-LIST & VALIDATION                                │
# ╰──────────────────────────────────────────────────────────────────╯
ALLOWED_TOOLS: set[str] = {"weather", "search", "visit_url"}

TOOL_SCHEMA: dict[str, dict[str, Any]] = {
    "weather": {"location": lambda v: isinstance(v, str) and v.strip()},
    "search": {"query": lambda v: isinstance(v, str) and v.strip()},
    # Accept any non-empty URL string
    "visit_url": {"url": lambda v: isinstance(v, str) and v.strip()},
}

def _tool_sig(name: str, spec: dict[str, Any]) -> str:
    inner = ", ".join(f"{k}:str" for k in spec)
    return f"  – {name}  {{{inner}}}"

SYS_MSG = (
    "You are an assistant that writes a JSON *plan* using only these tools:\n"
    + "\n".join(_tool_sig(n, TOOL_SCHEMA[n]) for n in ALLOWED_TOOLS)
    + "\nReturn ONLY a JSON object of the form\n"
    "{\n"
    '  "title": str,\n'
    '  "steps": [ { "title": str, "tool": str, "args": object, "depends_on": [] } ]\n'
    "}"
)

def validate_step(step: Dict[str, Any]) -> Tuple[bool, str]:
    tool = step.get("tool")
    if tool not in ALLOWED_TOOLS:
        return False, f"{tool!r} not allowed"
    spec, args = TOOL_SCHEMA[tool], step.get("args", {})
    miss  = [k for k in spec if k not in args]
    extra = [k for k in args if k not in spec]
    bad   = [k for k, fn in spec.items() if k in args and not fn(args[k])]
    if miss:  return False, f"{tool}: missing {miss}"
    if extra: return False, f"{tool}: unknown {extra}"
    if bad:   return False, f"{tool}: invalid {bad}"
    return True, ""

# ╭──────────────────────────────────────────────────────────────────╮
# │ 2.  TOOL-EXECUTION ADAPTER                                     │
# ╰──────────────────────────────────────────────────────────────────╯
async def _adapter(name: str, args: Dict[str, Any]) -> Any:
    """
    Enhanced adapter with improved error handling and URL preprocessing.
    """
    # Special handling for visit_url to preprocess DuckDuckGo URLs
    if name == "visit_url" and "url" in args:
        url = args["url"]
        
        # Extract the target URL from DuckDuckGo redirects before passing to tool
        if "duckduckgo.com/l/" in url:
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if "uddg" in params and params["uddg"]:
                    args["url"] = unquote(params["uddg"][0])
            except Exception:
                pass
    
    # Create the tool call object with updated arguments
    tc = {
        "id": uuid.uuid4().hex,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)}
    }
    
    # Execute the tool with error handling
    try:
        result = await execute_tool(tc, None, None)
        return result
    except Exception as e:
        # Return a structured error response instead of raising
        return {"error": str(e)}

# ── replace current register_tools -----------------------------------
def register_tools(proc: GraphAwareToolProcessor) -> None:
    """
    Register tools with improved error handling.
    """
    from chuk_tool_processor.registry import default_registry
    
    # Suppress warnings that might interfere with tool execution
    warnings.filterwarnings("ignore", category=UserWarning)

    for t in ALLOWED_TOOLS:
        try:
            tool = default_registry.get_tool(t)
            # Bind *t* at definition-time with a default arg
            proc.register_tool(t, lambda a, _n=t: _adapter(_n, a))
        except KeyError:
            raise RuntimeError(f"Tool {t!r} not found in chuk registry")
        except Exception as e:
            raise RuntimeError(f"Error registering tool {t!r}: {e}")

# ╭──────────────────────────────────────────────────────────────────╮
# │ 3.  FOLLOW-UP PLANNING                                         │
# ╰──────────────────────────────────────────────────────────────────╯
async def gen_subplan(agent: PlanAgent, goal: str, snippet: str) -> dict | None:
    """Ask GPT if more steps are useful given fresh data."""
    prompt = (
        f"User goal: {goal!r}\n\nNew data:\n{snippet}\n\n"
        "If more tool calls help, return a JSON plan (same schema). "
        "Else reply with DONE."
    )
    raw = await agent._chat(
        [{"role": "system", "content": agent.system_prompt},
         {"role": "user",   "content": prompt}]
    )
    return None if raw.strip().upper() == "DONE" else json.loads(raw)

def attach_subplan(plan: Plan, parent_ix: str, sub: dict) -> None:
    """Add sub-plan steps under *parent_ix* and persist links."""
    for st in sub["steps"]:
        child_ix = plan.add_step(st["title"], parent=parent_ix)
        tc = ToolCall(data={"name": st["tool"], "args": st["args"]})
        plan.graph.add_node(tc)
        plan.graph.add_edge(GraphEdge(kind=EdgeKind.PLAN_LINK,
                                      src=plan._by_index[child_ix].id,
                                      dst=tc.id))

# ╭──────────────────────────────────────────────────────────────────╮
# │ 4.  GPT SUMMARY                                                │
# ╰──────────────────────────────────────────────────────────────────╯
async def summarise(results: list[dict[str, Any]], goal: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    rsp = await client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[{"role": "user",
                   "content": f"Task: {goal}\n"
                              f"Tool results JSON:\n{json.dumps(results,indent=2)}\n"
                              "Reply in ≤1 sentence."}],
    )
    return rsp.choices[0].message.content.strip()

# ╭──────────────────────────────────────────────────────────────────╮
# │ 5.  MAIN LOOP                                                  │
# ╰──────────────────────────────────────────────────────────────────╯
async def run(user_prompt: str) -> None:
    # 5-1  initial plan
    agent     = PlanAgent(system_prompt=SYS_MSG, validate_step=validate_step)
    plan_json = await agent.plan(user_prompt)

    plan = Plan(plan_json["title"])
    for s in plan_json["steps"]:
        plan.step(s["title"]).up()
    plan_id = plan.save()

    idx2step = {n.data["index"]: n.id
                for n in plan.graph.nodes.values()
                if n.__class__.__name__ == "PlanStep"}
    # ── inside run(), section 5-1 / 5-2 – replace the small for-loop -------
    for i, s in enumerate(plan_json["steps"], 1):
        tc = ToolCall(data={"name": s["tool"], "args": s["args"]})
        plan.graph.add_node(tc)
        plan.graph.add_edge(
            GraphEdge(kind=EdgeKind.PLAN_LINK, src=idx2step[str(i)], dst=tc.id)
        )


    # 5-2  session + processor
    SessionStoreProvider.set_store(InMemorySessionStore())
    session = Session(); SessionStoreProvider.get_store().save(session)
    proc = GraphAwareToolProcessor(session.id, plan.graph)
    register_tools(proc)

    print("\n📋  LLM-GENERATED PLAN (validated)\n")
    print(plan.outline(), "\n")

    # 5-3  execute first batch & collect
    first_batch: list[tuple[str, list]] = []
    def on_step(step_id: str, results: list) -> bool:
        first_batch.append((step_id, results)); return True
    await proc.process_plan(plan_id, "assistant", lambda _: None, on_step=on_step)

    # 5-4  look at *search* results → maybe sub-plan
    changed = False
    for step_id, results in first_batch:
        for tr in results:
            if tr.tool != "search" or not tr.result:
                continue
            snippet   = json.dumps(tr.result["results"][:3], indent=2)
            parent_ix = plan.graph.get_node(step_id).data["index"]
            sub       = await gen_subplan(agent, user_prompt, snippet)
            if sub:
                attach_subplan(plan, parent_ix, sub)
                changed = True

    # 5-5  finish plan execution
    final_results = (
        await proc.process_plan(plan_id, "assistant", lambda _: None)
        if changed else [tr for _, lst in first_batch for tr in lst]
    )

    # 5-6  output
    print("✅  TOOL RESULTS\n")
    for r in final_results:
        print(json.dumps(r.result, indent=2), "\n")

    print("🤔  LLM SUMMARY\n")
    print(await summarise([r.result for r in final_results], user_prompt), "\n")

    print_session_events(session)
    print_graph_structure(plan.graph)

# ╭──────────────────────────────────────────────────────────────────╮
# │ 6.  CLI ENTRY-POINT                                            │
# ╰──────────────────────────────────────────────────────────────────╯
def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="user question / task")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY missing")

    asyncio.run(run(args.query))

if __name__ == "__main__":
    cli()