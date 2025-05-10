# chuk session manager

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, async-first session management system for AI applications, with robust support for conversations, tool calls, and hierarchical relationships.

## Quick Install

```bash
# Install with uv (recommended)
uv pip install chuk-session-manager

# With Redis support
uv pip install chuk-session-manager[redis]

# Full install with all dependencies
uv pip install chuk-session-manager[full]
```

## Key Features

- 🔄 **Fully Async**: Built from the ground up for non-blocking I/O
- 🗃️ **Multiple Storage Backends**: Choose from in-memory, file-based, or Redis
- 🔄 **Hierarchical Sessions**: Create parent-child relationships
- 📝 **Event Tracking**: Record all conversation interactions
- 📊 **Token Tracking**: Monitor usage and estimate costs
- 🔧 **Tool Integration**: Track tool calls and results
- 💬 **Infinite Conversations**: Handle conversations exceeding token limits

## Basic Usage

### Create a simple session with events

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

async def main():
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a session
    session = await Session.create()
    
    # Add events
    await session.add_event_and_save(SessionEvent(
        message="How do I calculate the area of a circle?",
        source=EventSource.USER
    ))
    
    await session.add_event_and_save(SessionEvent(
        message="The area of a circle is calculated using the formula: A = πr²",
        source=EventSource.LLM
    ))
    
    # Print session info
    print(f"Session ID: {session.id}")
    print(f"Event count: {len(session.events)}")

# Run the example
if __name__ == "__main__":
    asyncio.run(main())
```

Run with: `uv run examples/simple_session.py`

### Storage Options

#### In-Memory (Default)

```python
from chuk_session_manager.storage import InMemorySessionStore, SessionStoreProvider

# Great for testing or single-process applications
store = InMemorySessionStore()
SessionStoreProvider.set_store(store)
```

#### File Storage

```python
from chuk_session_manager.storage.providers.file import create_file_session_store

# Persistent JSON file storage
store = await create_file_session_store(directory="./sessions")
SessionStoreProvider.set_store(store)
```

#### Redis Storage

```python
from chuk_session_manager.storage.providers.redis import create_redis_session_store

# Distributed storage for production
store = await create_redis_session_store(
    host="localhost",
    port=6379,
    expiration_seconds=86400  # 24-hour TTL
)
SessionStoreProvider.set_store(store)
```

### Hierarchical Sessions

```python
# Create a parent session
parent = await Session.create()

# Create child sessions
child1 = await Session.create(parent_id=parent.id)
child2 = await Session.create(parent_id=parent.id)

# Navigate the hierarchy
ancestors = await child1.ancestors()
descendants = await parent.descendants()
```

### Token Usage Tracking

```python
# Create an event with token tracking
user_message = "Explain quantum computing"
assistant_response = "Quantum computing uses qubits that can be both 0 and 1..."

# Auto-tracks tokens and estimates cost
event = await SessionEvent.create_with_tokens(
    message=assistant_response,
    prompt=user_message,
    completion=assistant_response,
    model="gpt-4",
    source=EventSource.LLM
)
await session.add_event_and_save(event)

# Check usage statistics
print(f"Total tokens: {session.total_tokens}")
print(f"Estimated cost: ${session.total_cost:.6f}")
```

### Building LLM Prompts

```python
from chuk_session_manager.session_prompt_builder import build_prompt_from_session, PromptStrategy

# Generate a prompt from session data
prompt = await build_prompt_from_session(
    session,
    strategy=PromptStrategy.CONVERSATION,  # MINIMAL, TOOL_FOCUSED, HIERARCHICAL also available
    max_tokens=4000
)

# Use the prompt with your LLM client
response = await llm_client.complete(prompt)
```

### Tool Processing

```python
from chuk_session_manager.session_aware_tool_processor import SessionAwareToolProcessor

# Process and record tool calls
processor = await SessionAwareToolProcessor.create(session_id=session.id)

# Process LLM response with tool calls
llm_response = {
    "role": "assistant",
    "content": "Let me check that for you.",
    "tool_calls": [
        {
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "New York"}'
            }
        }
    ]
}

# Execute tools and record in session
results = await processor.process_llm_message(llm_response, llm_callback)
```

### Infinite Conversations

```python
from chuk_session_manager.infinite_conversation import InfiniteConversationManager, SummarizationStrategy

# Manage conversations that exceed token limits
manager = InfiniteConversationManager(
    token_threshold=3000,
    summarization_strategy=SummarizationStrategy.KEY_POINTS
)

# Add a message and potentially create a new segment
new_session_id = await manager.process_message(
    session_id, 
    message,
    source,
    llm_callback
)

# Get full history across all segments
history = await manager.get_full_conversation_history(new_session_id)
```

## Practical Examples

### Example 1: LLM Chat with Tool Use

This example demonstrates how to:
- Create a session for a conversation
- Record user and LLM messages
- Process tool calls from an LLM response
- Store tool execution results 
- Maintain conversation context

```python
import asyncio
import json
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.models.event_type import EventType
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from chuk_session_manager.session_aware_tool_processor import SessionAwareToolProcessor

async def main():
    # Set up store
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a session
    session = await Session.create()
    
    # 1. User asks about weather
    await session.add_event_and_save(SessionEvent(
        message="What's the weather like in New York today?",
        source=EventSource.USER
    ))
    
    # 2. LLM responds with a tool call
    assistant_message = {
        "role": "assistant",
        "content": "I'll check the weather for you.",
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"location": "New York"})
                }
            }
        ]
    }
    
    # 3. Create tool processor for this session
    processor = await SessionAwareToolProcessor.create(session_id=session.id)
    
    # 4. Process tool calls (simplified for example)
    async def llm_callback(prompt, model=None):
        return {"content": "Here's the weather information."}
    
    # Mock tool execution
    processor._exec_calls = lambda calls: asyncio.sleep(0)
    processor._log_event = lambda *args, **kwargs: None
    
    # Execute and record tool result
    await processor.process_llm_message(assistant_message, llm_callback)
    
    # 5. Add a manual tool result for illustration
    await session.add_event_and_save(SessionEvent(
        message={
            "tool": "get_weather",
            "arguments": {"location": "New York"},
            "result": {
                "temperature": 72,
                "condition": "Sunny",
                "humidity": 45,
                "wind": "5 mph"
            }
        },
        source=EventSource.SYSTEM,
        type=EventType.TOOL_CALL
    ))
    
    # 6. LLM responds based on tool result
    await session.add_event_and_save(SessionEvent(
        message="The weather in New York today is sunny with a temperature of 72°F. Humidity is at 45% with a light breeze of 5 mph.",
        source=EventSource.LLM
    ))
    
    # 7. User asks a follow-up
    await session.add_event_and_save(SessionEvent(
        message="Thanks! Should I bring an umbrella?",
        source=EventSource.USER
    ))
    
    # 8. LLM responds to follow-up
    await session.add_event_and_save(SessionEvent(
        message="No, you don't need an umbrella today. It's sunny with no chance of rain in the forecast.",
        source=EventSource.LLM
    ))
    
    # Print session summary
    print(f"Session ID: {session.id}")
    print(f"Events: {len(session.events)}")
    for i, evt in enumerate(session.events):
        source = f"[{evt.source.value.upper()}]"
        type_str = f"({evt.type.value})" if evt.type != EventType.MESSAGE else ""
        content = str(evt.message)
        if len(content) > 60:
            content = content[:57] + "..."
        print(f"{i+1}. {source} {type_str} {content}")

if __name__ == "__main__":
    asyncio.run(main())
```

In this example, we create a session to track a weather-related conversation. The session records:
1. The user's initial question about weather
2. The LLM's response indicating it will use a tool
3. The result from a weather tool call
4. The LLM's formatted response based on the tool result
5. A follow-up question from the user
6. The LLM's final answer

The `SessionAwareToolProcessor` handles tool execution and automatically records the results in the session, maintaining the parent-child relationship between the LLM response and tool call events.

### Example 2: Multi-Session Conversation with Hierarchical Context

This example shows how to:
- Create hierarchical session relationships (parent-child)
- Add session summaries for context preservation
- Build prompts that include context from parent sessions
- Organize complex conversations into related segments

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.models.event_type import EventType
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from chuk_session_manager.session_prompt_builder import build_prompt_from_session, PromptStrategy

async def main():
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a parent session: Initial travel planning
    parent = await Session.create()
    await parent.add_event_and_save(SessionEvent(
        message="I'm planning a trip to Japan next month. Can you help me?",
        source=EventSource.USER
    ))
    
    await parent.add_event_and_save(SessionEvent(
        message="I'd be happy to help plan your trip to Japan! Japan offers beautiful temples, gardens, modern cities, and delicious cuisine. When exactly are you traveling and how long will you stay?",
        source=EventSource.LLM
    ))
    
    await parent.add_event_and_save(SessionEvent(
        message="I'll be there for 10 days in October, starting in Tokyo.",
        source=EventSource.USER
    ))
    
    await parent.add_event_and_save(SessionEvent(
        message="Great! With 10 days starting in Tokyo in October, you can experience beautiful fall colors. Here's a suggested itinerary:\n\n- Days 1-3: Tokyo\n- Days 4-5: Hakone/Mt. Fuji\n- Days 6-8: Kyoto\n- Day 9: Nara (day trip from Kyoto)\n- Day 10: Osaka\n\nWould you like more specific recommendations for any of these locations?",
        source=EventSource.LLM
    ))
    
    # Add a summary for parent session
    await parent.add_event_and_save(SessionEvent(
        message="User is planning a 10-day Japan trip in October, starting in Tokyo. Recommended itinerary covers Tokyo, Hakone/Mt. Fuji, Kyoto, Nara, and Osaka.",
        source=EventSource.SYSTEM,
        type=EventType.SUMMARY
    ))
    
    # Create child session 1: Tokyo specifics
    tokyo_session = await Session.create(parent_id=parent.id)
    await tokyo_session.add_event_and_save(SessionEvent(
        message="What should I see in Tokyo?",
        source=EventSource.USER
    ))
    
    await tokyo_session.add_event_and_save(SessionEvent(
        message="For your Tokyo visit, here are the top attractions:\n\n1. Senso-ji Temple in Asakusa\n2. Meiji Shrine and Harajuku\n3. Tokyo Skytree\n4. Shibuya Crossing\n5. Shinjuku Gyoen National Garden (beautiful in fall)\n6. Tsukiji Outer Market for food\n7. Akihabara for electronics and anime\n8. Tokyo Imperial Palace\n\nOctober weather in Tokyo is pleasant with temperatures around 15-20°C (59-68°F).",
        source=EventSource.LLM
    ))
    
    # Create child session 2: Kyoto specifics
    kyoto_session = await Session.create(parent_id=parent.id)
    await kyoto_session.add_event_and_save(SessionEvent(
        message="What are the must-visit temples in Kyoto?",
        source=EventSource.USER
    ))
    
    await kyoto_session.add_event_and_save(SessionEvent(
        message="Kyoto has many incredible temples. The must-visit ones are:\n\n1. Kinkaku-ji (Golden Pavilion)\n2. Fushimi Inari Shrine (with thousands of torii gates)\n3. Kiyomizu-dera (with a wooden stage offering city views)\n4. Arashiyama Bamboo Grove\n5. Ginkaku-ji (Silver Pavilion)\n6. Ryoan-ji (famous rock garden)\n\nIn October, the fall colors start to appear, making these temples even more scenic. I recommend visiting Fushimi Inari early morning to avoid crowds.",
        source=EventSource.LLM
    ))
    
    # Build a hierarchical prompt from the Kyoto session
    prompt = await build_prompt_from_session(
        kyoto_session, 
        strategy=PromptStrategy.HIERARCHICAL,
        include_parent_context=True
    )
    
    # Print session hierarchy and prompt
    print(f"Parent session: {parent.id} ({len(parent.events)} events)")
    print(f"├── Tokyo session: {tokyo_session.id} ({len(tokyo_session.events)} events)")
    print(f"└── Kyoto session: {kyoto_session.id} ({len(kyoto_session.events)} events)")
    
    print("\nHierarchical prompt for Kyoto session:")
    for i, msg in enumerate(prompt):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if content:
            if len(content) > 70:
                content = content[:67] + "..."
            print(f"{i+1}. [{role.upper()}] {content}")
        else:
            print(f"{i+1}. [{role.upper()}] <content placeholder>")

if __name__ == "__main__":
    asyncio.run(main())
```

This example demonstrates hierarchical session management for a Japan travel planning conversation:

1. We create a parent session for the initial travel planning where the user discusses their overall trip
2. A summary event is added to the parent session to capture key information
3. Two child sessions are created for specific aspects of the trip (Tokyo and Kyoto)
4. The `build_prompt_from_session` function with `PromptStrategy.HIERARCHICAL` creates a prompt that incorporates context from both the child session and its parent
5. This hierarchical structure helps maintain context while allowing focused sub-conversations

This approach is ideal for complex interactions where users might want to branch off into specific topics while maintaining the overall conversation context.

### Example 3: Token Usage Tracking

This example demonstrates how to:
- Track token usage for LLM interactions
- Monitor token counts for different models
- Calculate estimated API costs
- Analyze token usage patterns

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

async def main():
    # Set up storage
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a session
    session = await Session.create()
    
    # Add a user question without token tracking
    await session.add_event_and_save(SessionEvent(
        message="Can you explain how nuclear fusion works and how it differs from nuclear fission?",
        source=EventSource.USER
    ))
    
    # Assistant response with token tracking
    prompt = "Can you explain how nuclear fusion works and how it differs from nuclear fission?"
    completion = """
    Nuclear fusion is the process where two light atomic nuclei combine to form a heavier nucleus, releasing energy. This is the process that powers the Sun and stars.
    
    Nuclear fission, on the other hand, is the splitting of a heavy atomic nucleus into lighter nuclei, also releasing energy. This is the process used in current nuclear power plants.
    
    Key differences:
    1. Fusion combines light atoms (like hydrogen), while fission splits heavy atoms (like uranium)
    2. Fusion releases more energy per reaction than fission
    3. Fusion produces minimal radioactive waste, while fission produces significant waste
    4. Fusion requires extremely high temperatures (millions of degrees), while fission can occur at lower temperatures
    5. Fusion is difficult to sustain and control, which is why commercial fusion power remains experimental
    
    Both processes convert mass to energy according to Einstein's E=mc² equation, but fusion is generally considered the "cleaner" technology, though technically much more challenging to implement.
    """
    
    # Create event with automatic token counting
    assistant_event = await SessionEvent.create_with_tokens(
        message=completion,
        prompt=prompt,
        completion=completion,
        model="gpt-4",
        source=EventSource.LLM
    )
    await session.add_event_and_save(assistant_event)
    
    # Follow-up question
    await session.add_event_and_save(SessionEvent(
        message="Is ITER the largest fusion project currently underway?",
        source=EventSource.USER
    ))
    
    # Follow-up response with a different model
    prompt2 = "Is ITER the largest fusion project currently underway?"
    completion2 = """
    Yes, ITER (International Thermonuclear Experimental Reactor) is currently the largest fusion project in the world. It's an international collaboration between 35 countries, being built in southern France.
    
    ITER aims to prove the feasibility of fusion as a large-scale carbon-free energy source by creating a plasma that produces more energy than it consumes. When completed, it will be the world's largest tokamak fusion device.
    
    Other significant fusion projects include:
    
    - JET (Joint European Torus) in the UK
    - National Ignition Facility in the US
    - EAST (Experimental Advanced Superconducting Tokamak) in China
    - Various private ventures like Commonwealth Fusion Systems and TAE Technologies
    
    But in terms of scale, international collaboration, and potential impact, ITER remains the largest and most ambitious fusion project to date.
    """
    
    # Create event with a different model
    assistant_event2 = await SessionEvent.create_with_tokens(
        message=completion2,
        prompt=prompt2,
        completion=completion2,
        model="gpt-3.5-turbo",
        source=EventSource.LLM
    )
    await session.add_event_and_save(assistant_event2)
    
    # Print token usage statistics
    print(f"Session token usage: {session.total_tokens} tokens")
    print(f"Estimated cost: ${session.total_cost:.6f}")
    
    print("\nUsage by model:")
    for model, usage in session.token_summary.usage_by_model.items():
        print(f"- {model}: {usage.total_tokens} tokens (${usage.estimated_cost_usd:.6f})")
    
    print("\nEvent token breakdown:")
    for i, evt in enumerate(session.events):
        if evt.token_usage:
            print(f"Event {i+1}: {evt.token_usage.prompt_tokens} prompt + "
                  f"{evt.token_usage.completion_tokens} completion = "
                  f"{evt.token_usage.total_tokens} tokens")
        else:
            print(f"Event {i+1}: No token tracking")

if __name__ == "__main__":
    asyncio.run(main())
```

This example showcases the token tracking capabilities of the session manager:

1. We create events with the `create_with_tokens` method, which automatically counts tokens and calculates costs
2. Usage for different models (GPT-4 and GPT-3.5-Turbo) is tracked separately
3. The session keeps a running total of token usage and cost
4. Token information is broken down by prompt and completion components

Key benefits:
- Monitor API costs in real-time
- Track usage patterns across different models
- Optimize prompt strategies based on token usage
- Generate reports for usage analytics

This feature is particularly useful for applications that need to monitor and control LLM API costs, or for implementing rate limiting and budgeting features.

## Advanced Features

### Infinite Conversations

For handling very long conversations that would exceed model context limits:

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore
from chuk_session_manager.infinite_conversation import (
    InfiniteConversationManager,
    SummarizationStrategy
)

async def main():
    # Setup store
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a session
    session = await Session.create()
    
    # Initialize the conversation manager
    manager = InfiniteConversationManager(
        token_threshold=1000,  # Low for demo purposes
        max_turns_per_segment=10,
        summarization_strategy=SummarizationStrategy.KEY_POINTS
    )
    
    # Simulated LLM function
    async def fake_llm_call(messages, model="gpt-4"):
        return "This is a summarized version of the conversation."
    
    # Add a series of messages
    current_session_id = session.id
    
    # In a real application, this might be many messages over time
    for i in range(12):
        # Add user message
        current_session_id = await manager.process_message(
            current_session_id,
            f"User message {i+1}: This is a test message that would be longer in a real conversation.",
            EventSource.USER,
            fake_llm_call
        )
        
        # Add assistant message
        current_session_id = await manager.process_message(
            current_session_id,
            f"Assistant message {i+1}: This is a response that would be longer in a real conversation.",
            EventSource.LLM,
            fake_llm_call
        )
        
        # Check if we've moved to a new session segment
        if current_session_id != session.id:
            print(f"Created new session segment: {current_session_id}")
            session_id = current_session_id
    
    # Get the final session
    final_session = await store.get(current_session_id)
    
    # Get session chain from oldest to newest
    session_chain = await manager.get_session_chain(current_session_id)
    
    # Get complete conversation history
    history = await manager.get_full_conversation_history(current_session_id)
    
    # Print information
    print(f"Created {len(session_chain)} session segments")
    print(f"Total conversation history: {len(history)} messages")
    
    # Print session chain
    print("\nSession chain:")
    for i, sess in enumerate(session_chain):
        summary = next((e.message for e in sess.events if e.type == "summary"), None)
        print(f"Segment {i+1}: {sess.id} - {len(sess.events)} events")
        if summary:
            print(f"  Summary: {summary}")
    
    # Build context for the next LLM call
    context = await manager.build_context_for_llm(current_session_id)
    print(f"\nContext for next LLM call: {len(context)} messages")

if __name__ == "__main__":
    asyncio.run(main())
```

The `InfiniteConversationManager` handles long conversations by:
1. Tracking token usage across messages
2. Automatically creating new session segments when thresholds are reached
3. Generating summaries of previous segments
4. Building context for LLM calls that includes summaries from previous segments
5. Providing methods to retrieve the full conversation history

This feature is essential for applications that need to maintain context in long-running conversations without hitting model token limits.

### Session Runs for Task Management

For organizing workflow steps and tracking multi-step processes:

```python
import asyncio
from chuk_session_manager.models.session import Session
from chuk_session_manager.models.session_event import SessionEvent
from chuk_session_manager.models.session_run import SessionRun, RunStatus
from chuk_session_manager.models.event_source import EventSource
from chuk_session_manager.storage import SessionStoreProvider, InMemorySessionStore

async def main():
    # Setup
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    
    # Create a session for data analysis task
    session = await Session.create()
    
    # Create a run for data processing
    processing_run = await SessionRun.create(metadata={"task": "data_processing"})
    await processing_run.mark_running()
    
    # Add run to session
    session.runs.append(processing_run)
    await store.save(session)
    
    # Log events associated with this run
    await session.add_event_and_save(SessionEvent(
        message="Starting data processing...",
        source=EventSource.SYSTEM,
        task_id=processing_run.id
    ))
    
    await session.add_event_and_save(SessionEvent(
        message="Loading dataset from source...",
        source=EventSource.SYSTEM,
        task_id=processing_run.id
    ))
    
    await session.add_event_and_save(SessionEvent(
        message="Dataset loaded: 1000 records processed",
        source=EventSource.SYSTEM,
        task_id=processing_run.id
    ))
    
    # Mark run as completed
    await processing_run.mark_completed()
    await store.save(session)
    
    # Start another run for analysis
    analysis_run = await SessionRun.create(metadata={"task": "data_analysis"})
    await analysis_run.mark_running()
    
    # Add to session
    session.runs.append(analysis_run)
    await store.save(session)
    
    # Log events for analysis run
    await session.add_event_and_save(SessionEvent(
        message="Performing statistical analysis...",
        source=EventSource.SYSTEM,
        task_id=analysis_run.id
    ))
    
    # Simulate a failure
    await analysis_run.mark_failed(reason="Memory limit exceeded")
    await store.save(session)
    
    # Report run statuses
    print(f"Session ID: {session.id}")
    print(f"Number of runs: {len(session.runs)}")
    
    for i, run in enumerate(session.runs):
        print(f"\nRun {i+1}: {run.id}")
        print(f"Status: {run.status.value}")
        print(f"Started: {run.started_at}")
        print(f"Ended: {run.ended_at or 'Not ended'}")
        
        duration = await run.get_duration()
        if duration:
            print(f"Duration: {duration:.2f} seconds")
        
        run_events = [e for e in session.events if e.task_id == run.id]
        print(f"Events: {len(run_events)}")
        for j, evt in enumerate(run_events):
            print(f"  {j+1}. {evt.message}")
            
        if run.status == RunStatus.FAILED:
            reason = await run.get_metadata("failure_reason")
            print(f"Failure reason: {reason}")

if __name__ == "__main__":
    asyncio.run(main())
```

Session Runs provide a way to:
1. Organize events into logical execution groups
2. Track the status of different processing steps
3. Associate events with specific tasks or runs
4. Record timing information and performance metrics
5. Handle failures and error conditions

This feature is particularly useful for agent-based systems, multi-step workflows, or any application that needs to track progress and status of complex operations.

## More Examples

Run the provided examples with `uv`:

```bash
# Basic session example
uv run examples/session_example.py

# Prompt building
uv run examples/session_prompt_builder.py

# Token tracking
uv run examples/session_token_usage_example.py

# Tool processing
uv run examples/session_aware_tool_processor.py

# Infinite conversations
uv run examples/example_infinite_conversation.py

# Web API integration
uv run examples/fastapi_session_example.py
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.