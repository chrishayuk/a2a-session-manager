"""
Graph-Aware Tool Processor (Updated for your Session implementation)

Executes tool calls based on a graph structure, working with both:
- Session state (SessionManager)
- Graph representation (Nodes and Edges)

Features:
- Plan-driven execution
- Parallel tool processing where possible
- Structured logging of execution in the graph
- Retry handling with proper linking

This processor extends the session-aware concept to incorporate
graph-based planning and execution, allowing more complex
patterns than a linear execution approach.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Callable, Optional, Set, Tuple
from uuid import uuid4

# --- Graph Model imports ---
from a2a_graph.models import (
    NodeKind, 
    GraphNode, 
    PlanNode, 
    PlanStep,
    AssistantMessage, 
    ToolCall, 
    TaskRun, 
    Summary
)
from a2a_graph.models.edges import (
    EdgeKind, 
    GraphEdge, 
    ParentChildEdge, 
    PlanEdge, 
    StepEdge
)

# --- Session Manager imports ---
from a2a_session_manager.storage import SessionStoreProvider
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.session_run import SessionRun, RunStatus

# --- Tool execution models ---
from chuk_tool_processor.models.tool_result import ToolResult

# --- Local imports ---
from .store.base import GraphStore

_log = logging.getLogger(__name__)


class GraphAwareToolProcessor:
    """
    Tool processor that uses the graph structure to drive execution.
    
    This processor can:
    1. Execute tools based on a plan in the graph
    2. Process tool calls from LLM responses
    3. Update both the session and graph with results
    """
    
    def __init__(
        self,
        session_id: str,
        graph_store: GraphStore,
        *,
        max_llm_retries: int = 2,
        llm_retry_prompt: str | None = None,
        enable_caching: bool = True,
        enable_retries: bool = True,
    ):
        """
        Initialize the graph-aware tool processor.
        
        Parameters
        ----------
        session_id : str
            ID of the session to log events into
        graph_store : GraphStore
            Object that provides access to the graph (nodes and edges)
        max_llm_retries : int
            Maximum number of retry attempts for the LLM if no valid tool call
        llm_retry_prompt : str | None
            Custom prompt used for LLM retries
        enable_caching : bool
            Whether to cache tool call results
        enable_retries : bool
            Whether to retry failed tool calls
        """
        self.session_id = session_id
        self.graph_store = graph_store
        self.max_llm_retries = max_llm_retries
        self.llm_retry_prompt = (
            llm_retry_prompt
            or "Previous response contained no valid `tool_call`.\n"
               "Return ONLY a JSON block invoking one of the declared tools."
        )
        self.enable_caching = enable_caching
        self.enable_retries = enable_retries
        self.tool_registry = {}  # Will be populated with actual tool functions
        
        # Cache for tool results
        self._cache = {}
        
        # Check available event types for error reporting
        self._error_event_type = EventType.MESSAGE  # Default fallback
        for event_type in EventType:
            if event_type.name in ('ERROR', 'EXCEPTION', 'FAILURE'):
                self._error_event_type = event_type
                break
    
    def register_tool(self, name: str, tool_fn: Callable):
        """Register a tool function with this processor."""
        self.tool_registry[name] = tool_fn
    
    async def process_plan(
        self, 
        plan_node_id: str,
        assistant_node_id: str,
        llm_call_fn: Callable[[str], Any]
    ) -> List[ToolResult]:
        """
        Execute a plan by processing its steps according to the graph structure.
        
        Parameters
        ----------
        plan_node_id : str
            ID of the PlanNode in the graph
        assistant_node_id : str
            ID of the AssistantMessage node that created the plan
        llm_call_fn : Callable
            Async function that can be called to get LLM responses
            
        Returns
        -------
        List[ToolResult]
            Results from all executed tools
        """
        # 1. Create a SessionRun to track this execution
        store = SessionStoreProvider.get_store()
        session = store.get(self.session_id)
        if not session:
            raise RuntimeError(f"Session {self.session_id!r} not found")
        
        # Create the run directly (matches your session example)
        run = SessionRun()
        run.mark_running()
        session.runs.append(run)
        store.save(session)
        
        # 2. Create a parent event in the session for this plan execution
        parent_evt = SessionEvent(
            message={"plan_id": plan_node_id},
            type=EventType.SUMMARY,
            source=EventSource.SYSTEM,
            metadata={"description": "Plan execution started"}
        )
        session.events.append(parent_evt)
        store.save(session)
        parent_id = parent_evt.id
        
        try:
            # 3. Find all steps in the plan
            step_nodes = self._get_plan_steps(plan_node_id)
            if not step_nodes:
                raise ValueError(f"No steps found for plan {plan_node_id}")
            
            # 4. Determine execution order based on dependencies
            execution_order = self._determine_execution_order(step_nodes)
            
            # 5. Execute steps in the correct order
            all_results = []
            
            for batch in execution_order:
                # Execute steps in this batch in parallel
                batch_tasks = [
                    self._execute_step(step_id, assistant_node_id, parent_id, llm_call_fn)
                    for step_id in batch
                ]
                batch_results = await asyncio.gather(*batch_tasks)
                
                # Flatten results from all steps in this batch
                for results in batch_results:
                    all_results.extend(results)
            
            # 6. Mark the run as completed
            run.mark_completed()
            store.save(session)
            
            # 7. Create a summary event
            summary_evt = SessionEvent(
                message={
                    "plan_id": plan_node_id,
                    "steps_executed": len(step_nodes),
                    "tools_executed": len(all_results)
                },
                type=EventType.SUMMARY,
                source=EventSource.SYSTEM,
                metadata={"parent_event_id": parent_id}
            )
            session.events.append(summary_evt)
            store.save(session)
            
            return all_results
            
        except Exception as e:
            # Mark the run as failed
            run.mark_failed(str(e))
            store.save(session)
            
            # Log the error
            error_evt = SessionEvent(
                message={"error": str(e)},
                type=self._error_event_type,  # Use detected error event type
                source=EventSource.SYSTEM,
                metadata={"parent_event_id": parent_id}
            )
            session.events.append(error_evt)
            store.save(session)
            
            # Re-raise the exception
            raise
    
    async def process_llm_message(
        self,
        assistant_msg: Dict[str, Any],
        llm_call_fn: Callable[[str], Any],
        assistant_node_id: Optional[str] = None
    ) -> List[ToolResult]:
        """
        Process tool calls from an LLM message, with retries if needed.
        
        Parameters
        ----------
        assistant_msg : Dict[str, Any]
            The assistant's message containing potential tool calls
        llm_call_fn : Callable
            Function to call the LLM if a retry is needed
        assistant_node_id : Optional[str]
            ID of the AssistantMessage node in the graph (if available)
            
        Returns
        -------
        List[ToolResult]
            Results from all executed tools
        """
        store = SessionStoreProvider.get_store()
        session = store.get(self.session_id)
        if not session:
            raise RuntimeError(f"Session {self.session_id!r} not found")
        
        # Create the run directly (matches your session example)
        run = SessionRun()
        run.mark_running()
        session.runs.append(run)
        store.save(session)
        
        # 2. Create a parent event for the assistant's message
        parent_evt = SessionEvent(
            message=assistant_msg,
            type=EventType.MESSAGE,
            source=EventSource.SYSTEM,
        )
        session.events.append(parent_evt)
        store.save(session)
        parent_id = parent_evt.id
        
        # 3. If we have a graph node ID, create/update the assistant node
        if assistant_node_id:
            # Update the assistant node with the actual message
            assistant_node = self.graph_store.get_node(assistant_node_id)
            if assistant_node and assistant_node.kind == NodeKind.ASSIST_MSG:
                updated_node = AssistantMessage(
                    id=assistant_node_id,
                    data={
                        **assistant_node.data,
                        "content": assistant_msg.get("content"),
                        "tool_calls": assistant_msg.get("tool_calls", []),
                    }
                )
                self.graph_store.update_node(updated_node)
        
        # 4. Extract and process tool calls
        attempt = 0
        while True:
            # Extract tool calls from the assistant message
            tool_calls = assistant_msg.get("tool_calls", [])
            
            if tool_calls:
                # Process all tool calls
                results = []
                for tool_call in tool_calls:
                    # Execute the tool
                    result = await self._process_single_tool_call(
                        tool_call, 
                        parent_id, 
                        assistant_node_id
                    )
                    results.append(result)
                
                # Mark the run as completed
                run.mark_completed()
                store.save(session)
                
                return results
            
            # No tool calls found - retry or fail
            if attempt >= self.max_llm_retries:
                run.mark_failed("Max LLM retries exceeded")
                store.save(session)
                
                # Log the error
                self._create_child_event(
                    self._error_event_type,  # Use detected error event type
                    {"error": "Max LLM retries exceeded"},
                    parent_id
                )
                
                raise RuntimeError("Max LLM retries exceeded")
            
            # Increment attempt counter
            attempt += 1
            _log.info("Retrying LLM for valid tool_call (attempt %d)", attempt)
            
            # Log the retry
            self._create_child_event(
                EventType.SUMMARY,
                {
                    "note": "Retry due to missing tool calls",
                    "attempt": attempt
                },
                parent_id
            )
            
            # Retry with the LLM
            assistant_msg = await llm_call_fn(self.llm_retry_prompt)
    
    async def _process_single_tool_call(
        self,
        tool_call: Dict[str, Any],
        parent_event_id: str,
        assistant_node_id: Optional[str] = None
    ) -> ToolResult:
        """
        Process a single tool call and update both session and graph.
        
        Parameters
        ----------
        tool_call : Dict[str, Any]
            The tool call from the LLM
        parent_event_id : str
            ID of the parent event in the session
        assistant_node_id : Optional[str]
            ID of the AssistantMessage node in the graph
            
        Returns
        -------
        ToolResult
            The result of the tool execution
        """
        try:
            # Extract tool details
            call_id = tool_call.get("id", str(uuid4()))
            function_data = tool_call.get("function", {})
            tool_name = function_data.get("name")
            
            # Parse arguments
            args_str = function_data.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {"raw_text": args_str}
            
            # Check cache if enabled
            cache_key = None
            if self.enable_caching:
                cache_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                if cache_key in self._cache:
                    _log.info(f"Cache hit for tool {tool_name}")
                    cached_result = self._cache[cache_key]
                    
                    # Log the cached result in the session
                    self._create_child_event(
                        EventType.TOOL_CALL,
                        {
                            "tool": tool_name,
                            "args": args,
                            "result": cached_result,
                            "cached": True
                        },
                        parent_event_id
                    )
                    
                    # Create tool call node in the graph (if we have an assistant node)
                    if assistant_node_id:
                        tool_node = self._create_tool_call_node(
                            tool_name, 
                            args, 
                            cached_result, 
                            assistant_node_id,
                            is_cached=True
                        )
                        
                        # Create a task run node
                        self._create_task_run_node(tool_node.id, True, "Cached result used")
                    
                    # Return the cached result
                    return ToolResult(
                        id=call_id,
                        tool=tool_name,
                        args=args,
                        result=cached_result
                    )
            
            # Look up the tool function
            tool_fn = self.tool_registry.get(tool_name)
            if not tool_fn:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            # Execute the tool
            try:
                result = await tool_fn(args)
                success = True
                error = None
            except Exception as e:
                # Handle tool execution failure
                result = None
                success = False
                error = str(e)
                
                # Retry if enabled
                if self.enable_retries:
                    # Logic for retrying the tool call would go here
                    pass
            
            # Cache the result if successful
            if success and cache_key and self.enable_caching:
                self._cache[cache_key] = result
            
            # Log the result in the session
            self._create_child_event(
                EventType.TOOL_CALL,
                {
                    "tool": tool_name,
                    "args": args,
                    "result": result,
                    "error": error
                },
                parent_event_id
            )
            
            # Create tool call node in the graph (if we have an assistant node)
            if assistant_node_id:
                tool_node = self._create_tool_call_node(
                    tool_name, 
                    args, 
                    result, 
                    assistant_node_id,
                    error=error
                )
                
                # Create a task run node
                self._create_task_run_node(tool_node.id, success, error)
            
            # Return the result
            return ToolResult(
                id=call_id,
                tool=tool_name,
                args=args,
                result=result,
                error=error
            )
            
        except Exception as e:
            # Log the error
            self._create_child_event(
                self._error_event_type,  # Use detected error event type
                {"error": str(e)},
                parent_id
            )
            
            # Re-raise the exception
            raise
    
    async def _execute_step(
        self,
        step_id: str,
        assistant_node_id: str,
        parent_event_id: str,
        llm_call_fn: Callable[[str], Any]
    ) -> List[ToolResult]:
        """
        Execute a single plan step.
        
        Parameters
        ----------
        step_id : str
            ID of the PlanStep node
        assistant_node_id : str
            ID of the AssistantMessage node
        parent_event_id : str
            ID of the parent event in the session
        llm_call_fn : Callable
            Function to call the LLM if needed
            
        Returns
        -------
        List[ToolResult]
            Results from all tools executed for this step
        """
        # Get the step details
        step_node = self.graph_store.get_node(step_id)
        if not step_node or step_node.kind != NodeKind.PLAN_STEP:
            raise ValueError(f"Invalid plan step: {step_id}")
        
        # Log step execution start
        step_evt = self._create_child_event(
            EventType.SUMMARY,
            {
                "step_id": step_id,
                "description": step_node.data.get("description", "Unknown step"),
                "status": "started"
            },
            parent_event_id
        )
        
        try:
            # Check if this step has pre-defined tool calls
            tool_edges = self.graph_store.get_edges(
                src=step_id,
                kind=EdgeKind.PLAN_LINK
            )
            
            results = []
            
            # If there are explicit tool links, execute those
            if tool_edges:
                for edge in tool_edges:
                    dest_node = self.graph_store.get_node(edge.dst)
                    
                    # If the destination is a tool call, execute it
                    if dest_node and dest_node.kind == NodeKind.TOOL_CALL:
                        tool_name = dest_node.data.get("name")
                        args = dest_node.data.get("args", {})
                        
                        # Create a synthetic tool call object
                        tool_call = {
                            "id": dest_node.id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(args)
                            }
                        }
                        
                        # Process the tool call
                        result = await self._process_single_tool_call(
                            tool_call,
                            step_evt.id,
                            assistant_node_id
                        )
                        results.append(result)
            else:
                # No explicit tool calls, might need to ask the LLM
                # This would implement more complex logic to determine
                # what tool(s) to call for this step
                pass
            
            # Mark step as completed
            self._create_child_event(
                EventType.SUMMARY,
                {
                    "step_id": step_id,
                    "status": "completed",
                    "tools_executed": len(results)
                },
                parent_event_id
            )
            
            return results
            
        except Exception as e:
            # Log step failure
            self._create_child_event(
                self._error_event_type,  # Use detected error event type
                {
                    "step_id": step_id,
                    "error": str(e),
                    "status": "failed"
                },
                parent_event_id
            )
            
            # Re-raise the exception
            raise
    
    def _get_plan_steps(self, plan_id: str) -> List[GraphNode]:
        """Get all steps for a plan in the correct order."""
        # Find all child steps
        step_edges = self.graph_store.get_edges(
            src=plan_id,
            kind=EdgeKind.PARENT_CHILD
        )
        
        steps = []
        for edge in step_edges:
            node = self.graph_store.get_node(edge.dst)
            if node and node.kind == NodeKind.PLAN_STEP:
                steps.append(node)
        
        # Sort steps by their index if available
        steps.sort(key=lambda s: s.data.get("index", 0))
        return steps
    
    def _determine_execution_order(self, steps: List[GraphNode]) -> List[List[str]]:
        """
        Determine the execution order of steps based on dependencies.
        
        Returns a list of batches, where each batch is a list of step IDs
        that can be executed in parallel.
        """
        # Build a dependency graph
        dependencies = {}
        dependents = {}
        
        for step in steps:
            step_id = step.id
            dependencies[step_id] = set()
            
            # Find outgoing step edges (this step depends on...)
            outgoing = self.graph_store.get_edges(
                src=step_id,
                kind=EdgeKind.STEP_ORDER
            )
            for edge in outgoing:
                dependencies[step_id].add(edge.dst)
                
                # Also track the reverse (which steps depend on this one)
                if edge.dst not in dependents:
                    dependents[edge.dst] = set()
                dependents[edge.dst].add(step_id)
        
        # Identify steps with no dependencies (can be executed first)
        execution_order = []
        no_dependencies = [
            step.id for step in steps 
            if step.id not in dependents or not dependents[step.id]
        ]
        
        if not no_dependencies:
            # If there are no steps without dependencies, there might be a cycle
            # For simplicity, we'll just pick the first step
            no_dependencies = [steps[0].id]
        
        # Build the execution order
        while no_dependencies:
            execution_order.append(no_dependencies)
            
            # Find the next batch of steps that can be executed
            next_batch = []
            for step_id in no_dependencies:
                # Check steps that depend on this one
                for dependent in dependencies.get(step_id, []):
                    # Remove this dependency
                    dependents[dependent].remove(step_id)
                    
                    # If the dependent has no more dependencies, it can be executed
                    if not dependents[dependent]:
                        next_batch.append(dependent)
            
            no_dependencies = next_batch
        
        return execution_order
    
    def _create_child_event(
        self,
        event_type: EventType,
        message: Dict[str, Any],
        parent_id: str
    ) -> SessionEvent:
        """Create a child event in the session."""
        store = SessionStoreProvider.get_store()
        session = store.get(self.session_id)
        if not session:
            _log.warning("Session %s disappeared while logging", self.session_id)
            return None
        
        event = SessionEvent(
            message=message,
            type=event_type,
            source=EventSource.SYSTEM,
            metadata={"parent_event_id": parent_id}
        )
        session.events.append(event)
        store.save(session)
        return event
    
    def _create_tool_call_node(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        assistant_node_id: str,
        error: str = None,
        is_cached: bool = False
    ) -> ToolCall:
        """Create a tool call node in the graph."""
        # Create the tool call node
        tool_node = ToolCall(
            data={
                "name": tool_name,
                "args": args,
                "result": result,
                "error": error,
                "cached": is_cached
            }
        )
        self.graph_store.add_node(tool_node)
        
        # Connect to the assistant node
        edge = ParentChildEdge(
            src=assistant_node_id,
            dst=tool_node.id
        )
        self.graph_store.add_edge(edge)
        
        return tool_node
    
    def _create_task_run_node(
        self,
        tool_node_id: str,
        success: bool,
        error: str = None
    ) -> TaskRun:
        """Create a task run node in the graph."""
        # Create the task run node
        task_node = TaskRun(
            data={
                "success": success,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        self.graph_store.add_node(task_node)
        
        # Connect to the tool call node
        edge = ParentChildEdge(
            src=tool_node_id,
            dst=task_node.id
        )
        self.graph_store.add_edge(edge)
        
        return task_node