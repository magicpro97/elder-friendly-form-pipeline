"""Pytest configuration and fixtures."""

import os
import sys
import types

# Set environment variable to skip Redis connection in tests
os.environ["TESTING"] = "true"

# Provide a lightweight stub for WeasyPrint on platforms where native deps are missing (e.g., Windows CI/dev)
try:
    import weasyprint  # noqa: F401
except Exception:
    stub = types.ModuleType("weasyprint")

    class _StubHTML:  # minimal API used in tests; usually patched by tests
        def __init__(self, *args, **kwargs):
            pass

        def write_pdf(self, *args, **kwargs):  # pragma: no cover - not used in patched tests
            return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"  # minimal header

    stub.HTML = _StubHTML
    sys.modules["weasyprint"] = stub

from unittest.mock import Mock, patch  # noqa: E402

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def session_manager(mock_redis):
    """SessionManager with fake Redis."""
    from app import SessionManager

    return SessionManager(mock_redis, ttl=3600)


@pytest.fixture
def mock_settings():
    """Mock Settings with test configuration."""
    with patch("app.Settings") as mock:
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
    with patch("app.redis.Redis", return_value=mock_redis):
        with patch("app.settings", mock_settings):
            from app import app

            return TestClient(app)


@pytest.fixture
def sample_form():
    """Sample form data for testing."""
    return {
        "form_id": "don_xin_viec",
        "title": "Đơn xin việc",
        "aliases": ["xin việc", "apply job", "đơn tuyển dụng"],
        "fields": [
            {
                "id": "full_name",
                "label": "Họ và tên",
                "type": "text",
                "required": True,
                "normalizers": ["strip_spaces", "title_case"],
                "validators": [{"type": "length", "min": 2, "max": 100}],
            },
            {
                "id": "birth_date",
                "label": "Ngày sinh",
                "type": "date",
                "required": True,
                "normalizers": ["strip_spaces"],
                "validators": [{"type": "date_range", "min": "1930-01-01", "max": "2010-12-31"}],
                "pattern": r"^\d{2}/\d{2}/\d{4}$",
            },
        ],
    }


@pytest.fixture
def sample_session():
    """Sample session data for testing."""
    return {
        "form_id": "don_xin_viec",
        "answers": {},
        "field_idx": 0,
        "questions": [
            {
                "name": "full_name",
                "ask": "Họ và tên của bác là gì ạ?",
                "reprompt": "Cháu chưa nghe rõ, bác nhắc lại họ và tên giúp cháu nhé.",
                "example": None,
            },
            {
                "name": "birth_date",
                "ask": "Ngày sinh của bác là ngày nào ạ?",
                "reprompt": "Cháu chưa nghe rõ, bác nhắc lại ngày sinh giúp cháu nhé.",
                "example": None,
            },
        ],
        "stage": "ask",
        "pending": None,
    }
