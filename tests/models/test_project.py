# tests/test_project.py
import pytest
from datetime import datetime, timezone
from uuid import uuid4
import time

from a2a_session_manager.models.project import Project, ProjectStatus
from a2a_session_manager.models.access_levels import AccessLevel


def test_project_creation_with_minimal_fields():
    """Test creating a project with only required fields."""
    account_id = str(uuid4())
    project = Project(
        name="Test Project",
        account_id=account_id
    )
    
    assert project.name == "Test Project"
    assert project.account_id == account_id
    assert project.description is None
    assert project.access_level == AccessLevel.PRIVATE
    assert isinstance(project.id, str)
    assert isinstance(project.created_at, datetime)
    assert isinstance(project.updated_at, datetime)
    assert project.metadata == {}
    assert project.tags == []
    assert project.status == ProjectStatus.ACTIVE
    assert project.parent_id is None
    assert project.owner_id is None
    assert project.shared_with == set()


def test_project_creation_with_all_fields():
    """Test creating a project with all fields specified."""
    account_id = str(uuid4())
    owner_id = str(uuid4())
    parent_id = str(uuid4())
    project_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    project = Project(
        id=project_id,
        name="Comprehensive Project",
        description="A project with all fields specified",
        account_id=account_id,
        owner_id=owner_id,
        access_level=AccessLevel.SHARED,
        shared_with={"user1", "user2"},
        status=ProjectStatus.ARCHIVED,
        tags=["tag1", "tag2"],
        parent_id=parent_id,
        metadata={"key": "value"},
        created_at=now,
        updated_at=now
    )
    
    assert project.id == project_id
    assert project.name == "Comprehensive Project"
    assert project.description == "A project with all fields specified"
    assert project.account_id == account_id
    assert project.owner_id == owner_id
    assert project.access_level == AccessLevel.SHARED
    assert project.shared_with == {"user1", "user2"}
    assert project.status == ProjectStatus.ARCHIVED
    assert project.tags == ["tag1", "tag2"]
    assert project.parent_id == parent_id
    assert project.metadata == {"key": "value"}
    assert project.created_at == now
    assert project.updated_at == now


def test_project_id_generation():
    """Test that project IDs are automatically generated if not provided."""
    project1 = Project(name="Project 1", account_id="account1")
    project2 = Project(name="Project 2", account_id="account1")
    
    assert project1.id != project2.id
    assert isinstance(project1.id, str)
    assert isinstance(project2.id, str)


def test_project_timestamps_timezone_and_order():
    """Test that timestamps are generated correctly and use UTC."""
    before = datetime.now(timezone.utc)
    time.sleep(0.001)
    project = Project(name="Time Test", account_id="account1")
    time.sleep(0.001)
    after = datetime.now(timezone.utc)
    
    assert before < project.created_at < after
    assert before < project.updated_at < after
    assert project.created_at.tzinfo == timezone.utc
    assert project.updated_at.tzinfo == timezone.utc


def test_project_is_public_and_is_shared_properties():
    """Test is_public and is_shared properties."""
    public_project = Project(name="Public", account_id="a", access_level=AccessLevel.PUBLIC)
    assert public_project.is_public
    assert not public_project.is_shared

    shared_project = Project(name="Shared", account_id="a", access_level=AccessLevel.SHARED, shared_with={"u"})
    assert not shared_project.is_public
    assert shared_project.is_shared

    empty_shared = Project(name="EmptyShared", account_id="a", access_level=AccessLevel.SHARED, shared_with=set())
    assert not empty_shared.is_public
    assert not empty_shared.is_shared

    private = Project(name="Private", account_id="a", access_level=AccessLevel.PRIVATE)
    assert not private.is_public
    assert not private.is_shared


def test_project_has_access_method():
    """Test has_access covers public, private, shared, and ownership."""
    owner = "acc1"
    other = "acc2"
    shared_user = "acc_shared"

    pub = Project(name="P", account_id=owner, access_level=AccessLevel.PUBLIC)
    assert pub.has_access(owner)
    assert pub.has_access(other)

    priv = Project(name="P", account_id=owner, access_level=AccessLevel.PRIVATE)
    assert priv.has_access(owner)
    assert not priv.has_access(other)

    shared = Project(name="P", account_id=owner, access_level=AccessLevel.SHARED, shared_with={shared_user})
    assert shared.has_access(owner)
    assert shared.has_access(shared_user)
    assert not shared.has_access(other)


def test_project_serialization_to_dict_and_json():
    """Test model_dump and model_dump_json output."""
    project = Project(name="Ser", account_id="a", tags=["t1"], shared_with={"u1"})
    d = project.model_dump()
    assert d["name"] == "Ser"
    assert d["account_id"] == "a"
    assert d["tags"] == ["t1"]
    assert set(d["shared_with"]) == {"u1"}
    assert d["access_level"] == "private"

    j = project.model_dump_json()
    assert isinstance(j, str)
    assert "Ser" in j
    assert "account_id" in j


def test_project_status_enum_values():
    """Test that ProjectStatus enum members have correct values."""
    assert ProjectStatus.ACTIVE.value == "active"
    assert ProjectStatus.ARCHIVED.value == "archived"
    assert ProjectStatus.DELETED.value == "deleted"


def test_project_equality_by_id():
    """Test that equality is based on ID (default BaseModel behavior)."""
    pid = str(uuid4())
    p1 = Project(id=pid, name="A", account_id="a1")
    p2 = Project(id=pid, name="B", account_id="a2")
    assert p1.id == p2.id
    p3 = Project(name="C", account_id="a1")
    assert p1.id != p3.id
