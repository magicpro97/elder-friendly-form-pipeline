"""Pytest configuration and fixtures."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import fakeredis


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_settings():
    """Mock Settings with test configuration."""
    with patch('app.Settings') as mock:
        mock.return_value.openai_api_key = "test-key"
        mock.return_value.openai_model = "gpt-4"
        mock.return_value.redis_host = "localhost"
        mock.return_value.redis_port = 6379
        mock.return_value.session_ttl_seconds = 3600
        mock.return_value.pdf_template = "generic_form.html"
        mock.return_value.rate_limit_enabled = True
        mock.return_value.rate_limit_per_minute = 60
        mock.return_value.rate_limit_per_hour = 1000
        yield mock.return_value


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Mocked response"))]
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


@pytest.fixture
def client(mock_redis, mock_settings):
    """FastAPI test client with mocked dependencies."""
    with patch('app.redis.Redis', return_value=mock_redis):
        with patch('app.settings', mock_settings):
            from app import app
            return TestClient(app)


@pytest.fixture
def sample_form():
    """Sample form data for testing."""
    return {
        "form_id": "test_form",
        "title": "Test Form",
        "aliases": ["test", "mẫu thử"],
        "fields": [
            {
                "id": "full_name",
                "label": "Họ và tên",
                "type": "text",
                "required": True,
                "normalizers": ["strip_spaces", "title_case"],
                "validators": [
                    {"type": "length", "min": 2, "max": 100}
                ]
            },
            {
                "id": "birth_date",
                "label": "Ngày sinh",
                "type": "date",
                "required": True,
                "normalizers": ["strip_spaces"],
                "validators": [
                    {"type": "date_range", "min": "1930-01-01", "max": "2010-12-31"}
                ],
                "pattern": r"^\d{2}/\d{2}/\d{4}$"
            }
        ]
    }


@pytest.fixture
def sample_session():
    """Sample session data for testing."""
    return {
        "form_id": "test_form",
        "answers": {},
        "field_idx": 0,
        "questions": ["Họ và tên của bác là gì ạ?"],
        "stage": "ask",
        "pending": None
    }
