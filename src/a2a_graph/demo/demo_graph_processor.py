# a2a_graph/demo/demo_graph_processor   .py
"""
Main demonstration of the GraphAwareToolProcessor.

This script shows:
1. Setting up the graph and session structures
2. Defining a plan with steps and dependencies
3. Executing tools based on the plan structure with parallel execution
4. Proper logging of results in both graph and session
"""

import asyncio
import pprint
from typing import Dict, Any, List

# Session Manager imports
from a2a_session_manager.storage import InMemorySessionStore, SessionStoreProvider
from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource

# Graph Model imports
from a2a_graph.models import (
    NodeKind, 
    SessionNode, 
    UserMessage, 
    AssistantMessage,
    PlanNode, 
    PlanStep
)
from a2a_graph.models.edges import (
    EdgeKind, 
    ParentChildEdge, 
    NextEdge, 
    StepEdge
)

# Local imports
from a2a_graph import (
    GraphAwareToolProcessor,
    InMemoryGraphStore,
    print_session_events,
    print_graph_structure
)
from a2a_graph.demo.tools import TOOL_REGISTRY
from a2a_graph.demo.llm_simulator import simulate_llm_call


async def main():
    """Main demonstration of the GraphAwareToolProcessor."""
    print("🚀 Starting GraphAwareToolProcessor demo")
    
    # 1. Initialize session store
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    print("🗄️  Initialized in-memory session store")
    
    # 2. Initialize graph store
    graph_store = InMemoryGraphStore()
    print("📊 Initialized simple graph store")
    
    # 3. Create a session
    session = Session()
    store.save(session)
    print(f"💬 Created session {session.id}")
    
    # 4. Create session node in graph
    session_node = SessionNode(
        data={"session_manager_id": session.id}
    )
    graph_store.add_node(session_node)
    print(f"📊 Created graph session node {session_node.id}")
    
    # 5. Add user message
    user_content = "What's the weather like in New York, and can you calculate 235.5 × 18.75? Also search for climate change adaptation."
    
    # Add to session
    user_event = SessionEvent(
        message=user_content,
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.events.append(user_event)
    store.save(session)
    
    # Add to graph
    user_msg_node = UserMessage(
        data={"content": user_content}
    )
    graph_store.add_node(user_msg_node)
    
    # Connect user message to session
    session_to_user = ParentChildEdge(
        src=session_node.id,
        dst=user_msg_node.id
    )
    graph_store.add_edge(session_to_user)
    print(f"✏️  Added user message to session and graph")
    
    # 6. Add assistant message (initial)
    assistant_msg_node = AssistantMessage(
        data={"content": None}  # Will be filled later
    )
    graph_store.add_node(assistant_msg_node)
    
    # Connect assistant message
    session_to_assistant = ParentChildEdge(
        src=session_node.id,
        dst=assistant_msg_node.id
    )
    user_to_assistant = NextEdge(
        src=user_msg_node.id,
        dst=assistant_msg_node.id
    )
    graph_store.add_edge(session_to_assistant)
    graph_store.add_edge(user_to_assistant)
    
    # 7. Create a plan
    plan_node = PlanNode(
        data={
            "description": "Answer about weather, perform calculation, and search for climate info"
        }
    )
    graph_store.add_node(plan_node)
    
    # Connect plan to session and assistant
    session_to_plan = ParentChildEdge(
        src=session_node.id,
        dst=plan_node.id
    )
    assistant_to_plan = ParentChildEdge(
        src=assistant_msg_node.id,
        dst=plan_node.id
    )
    graph_store.add_edge(session_to_plan)
    graph_store.add_edge(assistant_to_plan)
    
    # 8. Create plan steps with dependencies
    steps = [
        PlanStep(
            data={
                "description": "Check the weather in New York",
                "index": 1
            }
        ),
        PlanStep(
            data={
                "description": "Calculate 235.5 × 18.75",
                "index": 2
            }
        ),
        PlanStep(
            data={
                "description": "Search for climate change adaptation information",
                "index": 3
            }
        ),
        PlanStep(
            data={
                "description": "Compile and present all information",
                "index": 4
            }
        )
    ]
    
    # Add steps to graph and connect to plan
    for step in steps:
        graph_store.add_node(step)
        
        # Connect step to plan
        plan_to_step = ParentChildEdge(
            src=plan_node.id,
            dst=step.id
        )
        graph_store.add_edge(plan_to_step)
    
    # Add dependencies - Step 4 depends on steps 1, 2, and 3
    # These are independent and can run in parallel
    for i in range(3):
        step_to_step = StepEdge(
            src=steps[i].id,
            dst=steps[3].id
        )
        graph_store.add_edge(step_to_step)
    
    print(f"📝 Created plan with {len(steps)} steps and dependencies")
    
    # 9. Initialize the graph-aware tool processor
    processor = GraphAwareToolProcessor(
        session_id=session.id,
        graph_store=graph_store,
        enable_caching=True,
        enable_retries=True
    )
    
    # Register tools
    for name, tool_fn in TOOL_REGISTRY.items():
        processor.register_tool(name, tool_fn)
    print("🔧 Registered tools with the processor")
    
    # 10. Execute the plan
    print("\n==== EXECUTING PLAN ====")
    try:
        results = await processor.process_plan(
            plan_node_id=plan_node.id,
            assistant_node_id=assistant_msg_node.id,
            llm_call_fn=simulate_llm_call
        )
        print(f"✅ Plan execution completed with {len(results)} results")
        
        # Print tool results
        print("\nTool Results:")
        for i, result in enumerate(results):
            print(f"\n⮑  {result.tool}")
            pprint.pprint(result.result)
        
    except Exception as e:
        print(f"❌ Plan execution failed: {e}")
    
    # 11. Process an LLM message directly (simulates a normal flow)
    print("\n==== PROCESSING LLM MESSAGE ====")
    assistant_msg = await simulate_llm_call("Tell me about the weather and calculate something")
    
    try:
        results = await processor.process_llm_message(
            assistant_msg=assistant_msg,
            llm_call_fn=simulate_llm_call,
            assistant_node_id=assistant_msg_node.id
        )
        print(f"✅ Processed LLM message with {len(results)} tool calls")
        
    except Exception as e:
        print(f"❌ LLM message processing failed: {e}")
    
    # 12. Print session events in hierarchical view
    print_session_events(session)
    
    # 13. Print graph structure
    print_graph_structure(graph_store)
    
    print("\n✨ Demo completed!")

if __name__ == "__main__":
    asyncio.run(main())