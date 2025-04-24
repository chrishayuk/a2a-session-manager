# a2a_session_manager/exceptions.py
"""
Exceptions for the session manager.
"""
class SessionManagerError(Exception):
    """Base exception for session manager errors."""
    pass


class SessionNotFound(SessionManagerError):
    """Raised when the requested session ID is unknown."""
    pass


class SessionAlreadyExists(SessionManagerError):
    """Raised when trying to create a session that already exists."""
    pass


class InvalidSessionOperation(SessionManagerError):
    """Raised when an operation on a session is invalid."""
    pass