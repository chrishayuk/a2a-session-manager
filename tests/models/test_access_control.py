# tests/test_access_control.py
import pytest
from a2a_session_manager.models.access_control import AccessControlled
from a2a_session_manager.models.access_levels import AccessLevel


def make_control(account_id="owner", access_level=AccessLevel.PRIVATE, shared_with=None):
    shared = set(shared_with) if shared_with is not None else set()
    return AccessControlled(account_id=account_id, access_level=access_level, shared_with=shared)


def test_default_private_access():
    ctrl = make_control()
    # Owner should have access
    assert ctrl.has_access("owner") is True
    # Others should not
    assert ctrl.has_access("someone_else") is False
    # Properties
    assert ctrl.is_public is False
    assert ctrl.is_shared is False


def test_public_access_allows_anyone():
    ctrl = make_control(access_level=AccessLevel.PUBLIC)
    assert ctrl.is_public is True
    # Any account, even random, has access
    for acc in ["alice", "bob", "owner"]:
        assert ctrl.has_access(acc) is True
    assert ctrl.is_shared is False  # public implies not "shared"


def test_shared_access_with_explicit_accounts():
    ctrl = make_control(access_level=AccessLevel.SHARED, shared_with={"alice", "bob"})
    assert ctrl.is_shared is True
    # Owner always has access
    assert ctrl.has_access("owner") is True
    # Shared users have access
    assert ctrl.has_access("alice") is True
    assert ctrl.has_access("bob") is True
    # Others do not
    assert ctrl.has_access("charlie") is False
    # Not public
    assert ctrl.is_public is False


def test_shared_without_shared_with_empty():
    # SHARED level but no shared_with should not grant access to others
    ctrl = make_control(access_level=AccessLevel.SHARED, shared_with=set())
    assert ctrl.is_shared is False
    # Owner still has access
    assert ctrl.has_access("owner") is True
    # Others should not get access
    assert ctrl.has_access("alice") is False

@pytest.mark.parametrize("level, shared, expected_shared", [
    (AccessLevel.PRIVATE, {"x"}, False),
    (AccessLevel.PUBLIC, {"x"}, False),
    (AccessLevel.SHARED, {"x"}, True),
    (AccessLevel.SHARED, set(), False),
])
def test_is_shared_property(level, shared, expected_shared):
    ctrl = make_control(access_level=level, shared_with=shared)
    assert ctrl.is_shared is expected_shared

@pytest.mark.parametrize("level, expected_public", [
    (AccessLevel.PRIVATE, False),
    (AccessLevel.PUBLIC, True),
    (AccessLevel.SHARED, False),
])
def test_is_public_property(level, expected_public):
    ctrl = make_control(access_level=level)
    assert ctrl.is_public is expected_public
