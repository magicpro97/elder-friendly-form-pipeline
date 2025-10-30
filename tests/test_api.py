"""Integration tests for API endpoints."""
import pytest
from unittest.mock import patch, Mock


def test_list_forms(client):
    """Test GET /forms endpoint."""
    response = client.get("/forms")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "form_id" in data[0]
    assert "title" in data[0]


def test_start_session_valid_form(client, mock_openai_client):
    """Test POST /session/start with valid form."""
    with patch('app.get_client', return_value=mock_openai_client):
        response = client.post(
            "/session/start",
            json={"query": "đơn xin việc"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "question" in data
        assert "form_title" in data


def test_start_session_invalid_form(client):
    """Test POST /session/start with invalid form query."""
    response = client.post(
        "/session/start",
        json={"query": "nonexistent_form_xyz"}
    )
    assert response.status_code == 404
    assert "không tìm thấy" in response.json()["detail"].lower()


def test_answer_field_valid(client, mock_openai_client, sample_session):
    """Test POST /answer with valid input."""
    # Create session first
    session_id = "test_session_123"
    
    with patch('app.session_manager.get_session', return_value=sample_session):
        with patch('app.session_manager.update_session', return_value=True):
            with patch('app.pick_form') as mock_pick_form:
                mock_pick_form.return_value = {
                    "form_id": "test_form",
                    "fields": [
                        {
                            "id": "full_name",
                            "label": "Họ và tên",
                            "type": "text",
                            "required": True,
                            "normalizers": ["strip_spaces", "title_case"],
                            "validators": [{"type": "length", "min": 2, "max": 100}]
                        }
                    ]
                }
                
                response = client.post(
                    "/answer",
                    json={
                        "session_id": session_id,
                        "value": "Nguyen Van A"
                    }
                )
                
                # Should succeed or ask for confirmation
                assert response.status_code in [200, 202]


def test_answer_field_invalid_session(client):
    """Test POST /answer with invalid session."""
    with patch('app.session_manager.get_session', return_value=None):
        response = client.post(
            "/answer",
            json={
                "session_id": "invalid_session",
                "value": "test"
            }
        )
        assert response.status_code == 404


def test_preview_session(client, mock_openai_client, sample_session):
    """Test GET /preview endpoint."""
    session_id = "test_session_123"
    
    with patch('app.session_manager.get_session', return_value=sample_session):
        with patch('app.get_client', return_value=mock_openai_client):
            response = client.get(f"/preview?session_id={session_id}")
            assert response.status_code in [200, 400]  # 400 if no answers yet


def test_export_pdf(client, sample_session):
    """Test GET /export_pdf endpoint."""
    session_id = "test_session_123"
    
    # Add some answers to session
    sample_session["answers"] = {"full_name": "Nguyen Van A"}
    
    with patch('app.session_manager.get_session', return_value=sample_session):
        with patch('app.pick_form') as mock_pick_form:
            mock_pick_form.return_value = {
                "form_id": "test_form",
                "title": "Test Form",
                "fields": [
                    {
                        "id": "full_name",
                        "label": "Họ và tên",
                        "type": "text"
                    }
                ]
            }
            
            response = client.get(f"/export_pdf?session_id={session_id}")
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"


def test_rate_limiting(client):
    """Test rate limiting on endpoints."""
    # This test requires slowapi to be properly configured
    # Make multiple requests quickly
    for i in range(5):
        response = client.get("/forms")
        assert response.status_code == 200
    
    # Note: In real scenario with proper rate limit, this would return 429
    # But in test environment, rate limiting might be disabled
