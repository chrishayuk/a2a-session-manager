"""
A2A Session Manager package.

This package provides session management capabilities for A2A applications.
"""
# Import core components for easier access
try:
    from a2a_session_manager.models.event_source import EventSource
    from a2a_session_manager.models.event_type import EventType
    from a2a_session_manager.models.session import Session
    from a2a_session_manager.models.session_event import SessionEvent
    from a2a_session_manager.models.session_metadata import SessionMetadata
    from a2a_session_manager.models.session_run import SessionRun, RunStatus
except ImportError:
    # During package setup or circular imports, these might not be available
    pass

# Import storage components
try:
    from a2a_session_manager.storage.base import SessionStoreInterface, SessionStoreProvider
except ImportError:
    # During package setup or circular imports, these might not be available
    pass

# Import exceptions
try:
    from a2a_session_manager.exceptions import (
        SessionManagerError,
        SessionNotFound,
        SessionAlreadyExists,
        InvalidSessionOperation,
    )
except ImportError:
    # During package setup or circular imports, these might not be available
    pass

__version__ = "0.1.0"

# Define __all__ only if imports succeeded
__all__ = []

# Check which imports succeeded and add them to __all__
for name in [
    # Models
    'EventSource', 'EventType', 'Session', 'SessionEvent', 
    'SessionMetadata', 'SessionRun', 'RunStatus',
    
    # Storage
    'SessionStoreInterface', 'SessionStoreProvider',
    
    # Exceptions
    'SessionManagerError', 'SessionNotFound', 
    'SessionAlreadyExists', 'InvalidSessionOperation',
]:
    if name in globals():
        __all__.append(name)