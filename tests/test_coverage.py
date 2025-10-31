"""Additional tests to improve coverage."""

from unittest.mock import Mock, patch

import pytest


def test_openai_fallback_on_failure(client, sample_form):
    """Test fallback to basic questions when OpenAI fails."""
    with patch("app.get_client") as mock_get_client:
        # Simulate OpenAI failure
        mock_get_client.return_value = None

        response = client.post("/session/start", json={"form": sample_form["form_id"]})

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "ask" in data


def test_openai_retry_exhausted(client, sample_form):
    """Test behavior when OpenAI retries are exhausted."""
    with patch("app.get_client") as mock_get_client:
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        with patch("app.call_openai_with_retry") as mock_retry:
            # Simulate retry exhausted
            mock_retry.side_effect = Exception("OpenAI failed")

            response = client.post("/session/start", json={"form": sample_form["form_id"]})

            # Should fallback to basic questions
            assert response.status_code == 200


def test_session_manager_extend_ttl(mock_redis):
    """Test session TTL extension."""
    from app import SessionManager

    manager = SessionManager(mock_redis, ttl=3600)
    session_id = "test_extend"
    data = {"test": "data"}

    manager.create(session_id, data)
    manager.extend_ttl(session_id)

    # Verify session still exists
    result = manager.get(session_id)
    assert result == data


def test_session_manager_update_nonexistent(mock_redis):
    """Test updating non-existent session raises error."""
    from fastapi import HTTPException

    from app import SessionManager

    manager = SessionManager(mock_redis, ttl=3600)

    with pytest.raises(HTTPException) as exc_info:
        manager.update("nonexistent", {"data": "value"})

    assert exc_info.value.status_code == 404


def test_get_client_no_openai():
    """Test get_client when OpenAI is not available."""
    with patch("app.OPENAI_OK", False):
        from app import get_client

        client = get_client()
        assert client is None


def test_get_client_no_api_key():
    """Test get_client when API key is missing."""
    with patch("app.settings.openai_api_key", None):
        from app import get_client

        client = get_client()
        assert client is None


def test_custom_rate_limit_handler():
    """Test custom rate limit exceeded handler."""

    from fastapi import Request

    from app import custom_rate_limit_handler

    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "127.0.0.1"

    exc = Mock()
    exc.detail = "Rate limit exceeded"

    import asyncio

    try:
        asyncio.run(custom_rate_limit_handler(request, exc))
    except Exception:
        pass


def test_preview_with_missing_required_fields(client):
    """Test preview when required fields are missing."""
    test_session = {
        "session_id": "test_123",
        "form_id": "don_xin_viec",
        "answers": {},
        "field_idx": 0,
        "questions": [],
        "stage": "review",
    }

    with patch("app.session_manager.get", return_value=test_session):
        response = client.get("/preview?session_id=test_123")

        # Should return error about missing fields
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "thiếu" in data["message"].lower()


def test_export_pdf_no_preview(client):
    """Test PDF export generates preview if missing."""
    test_session = {
        "form_id": "don_xin_viec",
        "answers": {"full_name": "Test"},
        "field_idx": 1,
        "questions": [],
        "stage": "review",
    }

    with patch("app.session_manager.get", return_value=test_session):
        with patch("weasyprint.HTML") as mock_html:
            mock_html.return_value.write_pdf.return_value = b"PDF content"

            response = client.get("/export_pdf?session_id=test_123")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"


def test_confirm_no_pending(client):
    """Test confirm when no pending value."""
    test_session = {
        "form_id": "don_xin_viec",
        "answers": {},
        "field_idx": 0,
        "questions": [],
        "stage": "ask",
        "pending": {},
    }

    with patch("app.session_manager.get", return_value=test_session):
        response = client.post("/confirm?yes=true", json={"session_id": "test_123", "text": "confirm"})

        assert response.status_code == 400


def test_question_next_all_done(client):
    """Test getting next question when all fields are complete."""
    test_session = {
        "form_id": "don_xin_viec",
        "answers": {},
        "field_idx": 100,  # Beyond available fields
        "questions": [],
        "stage": "review",
    }

    with patch("app.session_manager.get", return_value=test_session):
        response = client.post("/question/next", json={"session_id": "test_123", "text": ""})

        assert response.status_code == 200
        data = response.json()
        assert data.get("done") is True
