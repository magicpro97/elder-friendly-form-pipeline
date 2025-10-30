"""Tests for session management with Redis."""
import pytest
import fakeredis
from app import SessionManager


@pytest.fixture
def redis_client():
    """Create fake Redis client for testing."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def session_manager(redis_client):
    """Create SessionManager with fake Redis."""
    return SessionManager(redis_client, ttl_seconds=3600)


def test_create_session(session_manager):
    """Test creating a new session."""
    session_id = "test_session_123"
    data = {
        "form_id": "test_form",
        "answers": {},
        "field_idx": 0,
        "stage": "ask"
    }
    
    result = session_manager.create_session(session_id, data)
    assert result is True


def test_get_session_exists(session_manager):
    """Test getting an existing session."""
    session_id = "test_session_123"
    data = {
        "form_id": "test_form",
        "answers": {},
        "field_idx": 0,
        "stage": "ask"
    }
    
    session_manager.create_session(session_id, data)
    retrieved = session_manager.get_session(session_id)
    
    assert retrieved is not None
    assert retrieved["form_id"] == "test_form"
    assert retrieved["stage"] == "ask"


def test_get_session_not_exists(session_manager):
    """Test getting a non-existent session."""
    result = session_manager.get_session("nonexistent_session")
    assert result is None


def test_update_session(session_manager):
    """Test updating an existing session."""
    session_id = "test_session_123"
    data = {
        "form_id": "test_form",
        "answers": {},
        "field_idx": 0,
        "stage": "ask"
    }
    
    session_manager.create_session(session_id, data)
    
    # Update session
    data["answers"]["name"] = "John Doe"
    data["field_idx"] = 1
    result = session_manager.update_session(session_id, data)
    
    assert result is True
    
    # Verify update
    retrieved = session_manager.get_session(session_id)
    assert retrieved["answers"]["name"] == "John Doe"
    assert retrieved["field_idx"] == 1


def test_delete_session(session_manager):
    """Test deleting a session."""
    session_id = "test_session_123"
    data = {"form_id": "test_form"}
    
    session_manager.create_session(session_id, data)
    result = session_manager.delete_session(session_id)
    
    assert result is True
    assert session_manager.get_session(session_id) is None


def test_session_ttl(session_manager, redis_client):
    """Test that session has TTL set."""
    session_id = "test_session_123"
    data = {"form_id": "test_form"}
    
    session_manager.create_session(session_id, data)
    
    # Check TTL is set
    ttl = redis_client.ttl(f"session:{session_id}")
    assert ttl > 0
    assert ttl <= 3600


def test_refresh_ttl(session_manager, redis_client):
    """Test TTL refresh on session access."""
    session_id = "test_session_123"
    data = {"form_id": "test_form"}
    
    session_manager.create_session(session_id, data)
    
    # Reduce TTL
    redis_client.expire(f"session:{session_id}", 10)
    ttl_before = redis_client.ttl(f"session:{session_id}")
    
    # Access session should refresh TTL
    session_manager.get_session(session_id)
    ttl_after = redis_client.ttl(f"session:{session_id}")
    
    assert ttl_after > ttl_before
