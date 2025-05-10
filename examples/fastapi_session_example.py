#!/usr/bin/env python3
# examples/fastapi_session_example.py
"""
fastapi_session_example.py
~~~~~~~~~~~~~~~~~~~~~~~~~

Demonstrates using A2A Session Manager with FastAPI.

This example shows:
- Integration with a modern async web framework
- Creating and managing sessions via RESTful API
- Adding events and retrieving session history
- Building prompts for LLM calls

Run:
```bash
uvicorn examples.fastapi_session_example:app --reload
```

Then open http://localhost:8000/docs in your browser to see the API documentation.
"""

import json
import logging
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, BackgroundTasks

from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.session import Session, SessionEvent
from a2a_session_manager.storage import SessionStoreProvider
from a2a_session_manager.storage.providers.memory import InMemorySessionStore
from a2a_session_manager.session_prompt_builder import build_prompt_from_session, PromptStrategy

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="A2A Session Manager API",
    description="Demo API for A2A Session Manager with async support",
    version="0.1.0"
)

# Initialize in-memory store
store = InMemorySessionStore()
SessionStoreProvider.set_store(store)

# Define API models

class EventCreate(BaseModel):
    """Model for creating a new event."""
    message: Any
    source: str
    event_type: str = "message"
    metadata: Optional[Dict[str, Any]] = None

class SessionResponse(BaseModel):
    """Response model for a session."""
    id: str
    event_count: int
    parent_id: Optional[str] = None
    child_ids: List[str]

class EventResponse(BaseModel):
    """Response model for an event."""
    id: str
    timestamp: str
    source: str
    type: str
    message: Any
    metadata: Dict[str, Any]

class PromptRequest(BaseModel):
    """Request model for building a prompt."""
    strategy: str = "minimal"
    max_tokens: Optional[int] = None
    include_parent_context: bool = False

class PromptResponse(BaseModel):
    """Response model for a prompt."""
    prompt: List[Dict[str, Any]]
    token_estimate: Optional[int] = None

# API routes

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "A2A Session Manager API",
        "endpoints": [
            "/sessions - List all sessions",
            "/sessions/{session_id} - Get session details",
            "/sessions/{session_id}/events - Get session events",
            "/sessions/{session_id}/prompt - Build a prompt from session"
        ]
    }

@app.post("/sessions", response_model=SessionResponse)
async def create_session(background_tasks: BackgroundTasks, parent_id: Optional[str] = None):
    """Create a new session."""
    session = await Session.create(parent_id=parent_id)
    
    # Return the session details
    return {
        "id": session.id,
        "event_count": len(session.events),
        "parent_id": session.parent_id,
        "child_ids": session.child_ids
    }

@app.get("/sessions", response_model=List[SessionResponse])
async def list_sessions():
    """List all sessions."""
    session_ids = await store.list_sessions()
    sessions = []
    
    for sid in session_ids:
        session = await store.get(sid)
        if session:
            sessions.append({
                "id": session.id,
                "event_count": len(session.events),
                "parent_id": session.parent_id,
                "child_ids": session.child_ids
            })
    
    return sessions

@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session details by ID."""
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "id": session.id,
        "event_count": len(session.events),
        "parent_id": session.parent_id,
        "child_ids": session.child_ids
    }

@app.post("/sessions/{session_id}/events", response_model=EventResponse)
async def add_event(session_id: str, event: EventCreate):
    """Add an event to a session."""
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Map source string to EventSource enum
    try:
        source = EventSource(event.source.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid source: {event.source}")
    
    # Map event_type string to EventType enum
    try:
        event_type = EventType(event.event_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event type: {event.event_type}")
    
    # Create event
    new_event = SessionEvent(
        message=event.message,
        source=source,
        type=event_type,
        metadata=event.metadata or {}
    )
    
    # Add and save
    await session.add_event_and_save(new_event)
    
    # Return the event details
    return {
        "id": new_event.id,
        "timestamp": new_event.timestamp.isoformat(),
        "source": new_event.source.value,
        "type": new_event.type.value,
        "message": new_event.message,
        "metadata": new_event.metadata
    }

@app.get("/sessions/{session_id}/events", response_model=List[EventResponse])
async def get_events(session_id: str):
    """Get all events for a session."""
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    events = []
    for event in session.events:
        events.append({
            "id": event.id,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source.value,
            "type": event.type.value,
            "message": event.message,
            "metadata": event.metadata
        })
    
    return events

@app.post("/sessions/{session_id}/prompt", response_model=PromptResponse)
async def build_prompt(session_id: str, req: PromptRequest):
    """Build a prompt from a session."""
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build the prompt
    try:
        prompt = await build_prompt_from_session(
            session,
            strategy=req.strategy,
            max_tokens=req.max_tokens,
            include_parent_context=req.include_parent_context
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Estimate token count
    token_estimate = None
    if prompt:
        prompt_text = json.dumps(prompt)
        from a2a_session_manager.models.token_usage import TokenUsage
        token_estimate = TokenUsage.count_tokens(prompt_text)
    
    return {
        "prompt": prompt,
        "token_estimate": token_estimate
    }

@app.post("/sessions/{session_id}/children", response_model=SessionResponse)
async def create_child_session(session_id: str):
    """Create a child session."""
    parent = await store.get(session_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent session not found")
    
    # Create child session
    child = await Session.create(parent_id=parent.id)
    
    return {
        "id": child.id,
        "event_count": len(child.events),
        "parent_id": child.parent_id,
        "child_ids": child.child_ids
    }

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await store.delete(session_id)
    return {"message": f"Session {session_id} deleted"}


# Create some sample data when the app starts
@app.on_event("startup")
async def startup_event():
    logger.info("Creating sample session data")
    
    # Create a parent session
    parent = await Session.create()
    parent.add_event(SessionEvent(
        message="What's the weather like today?",
        source=EventSource.USER
    ))
    parent.add_event(SessionEvent(
        message="I'll check the weather for you.",
        source=EventSource.LLM
    ))
    await store.save(parent)
    
    # Create a child session
    child = await Session.create(parent_id=parent.id)
    child.add_event(SessionEvent(
        message="What about tomorrow's forecast?",
        source=EventSource.USER
    ))
    await store.save(child)
    
    logger.info(f"Created sample parent session: {parent.id}")
    logger.info(f"Created sample child session: {child.id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)