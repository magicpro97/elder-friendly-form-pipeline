"""Tests for validation logic."""
import pytest
from datetime import datetime
from app import _validate_field


def test_validate_text_field_valid():
    """Test text field validation with valid input."""
    field = {
        "id": "name",
        "type": "text",
        "normalizers": ["strip_spaces", "title_case"],
        "validators": [{"type": "length", "min": 2, "max": 50}]
    }
    
    is_valid, error, normalized = _validate_field(field, "  john doe  ")
    assert is_valid is True
    assert error == ""
    assert normalized == "John Doe"


def test_validate_text_field_too_short():
    """Test text field validation with too short input."""
    field = {
        "id": "name",
        "type": "text",
        "validators": [{"type": "length", "min": 5, "max": 100}]
    }
    
    is_valid, error, normalized = _validate_field(field, "Joe")
    assert is_valid is False
    assert "Độ dài cần" in error


def test_validate_text_field_too_long():
    """Test text field validation with too long input."""
    field = {
        "id": "name",
        "type": "text",
        "validators": [{"type": "length", "min": 1, "max": 10}]
    }
    
    is_valid, error, normalized = _validate_field(field, "A" * 20)
    assert is_valid is False
    assert "Độ dài cần" in error


def test_validate_numeric_field_valid():
    """Test numeric field validation with valid input."""
    field = {
        "id": "age",
        "type": "number",
        "validators": [{"type": "numeric_range", "min": 18, "max": 100}]
    }
    
    is_valid, error, normalized = _validate_field(field, "25")
    assert is_valid is True
    assert error == ""
    assert normalized == "25"


def test_validate_numeric_field_invalid():
    """Test numeric field validation with non-numeric input."""
    field = {
        "id": "age",
        "type": "number",
        "validators": [{"type": "numeric_range", "min": 0, "max": 200}]
    }
    
    is_valid, error, normalized = _validate_field(field, "not a number")
    assert is_valid is False
    assert "Cần số" in error


def test_validate_numeric_field_out_of_range():
    """Test numeric field validation with out of range value."""
    field = {
        "id": "age",
        "type": "number",
        "validators": [{"type": "numeric_range", "min": 18, "max": 65}]
    }
    
    is_valid, error, normalized = _validate_field(field, "100")
    assert is_valid is False
    assert "18" in error and "65" in error


def test_validate_date_field_valid():
    """Test date field validation with valid format."""
    field = {
        "id": "birth_date",
        "type": "date",
        "validators": [{"type": "date_range", "min": "1930-01-01", "max": "2010-12-31"}],
        "pattern": r"^\d{2}/\d{2}/\d{4}$"
    }
    
    is_valid, error, normalized = _validate_field(field, "15/05/1990")
    assert is_valid is True
    assert error == ""
    assert normalized == "15/05/1990"


def test_validate_date_field_invalid_format():
    """Test date field validation with invalid format."""
    field = {
        "id": "birth_date",
        "type": "date",
        "pattern": r"^\d{2}/\d{2}/\d{4}$"
    }
    
    is_valid, error, normalized = _validate_field(field, "1990-05-15")
    assert is_valid is False
    assert "chưa đúng" in error


def test_validate_date_field_out_of_range():
    """Test date field validation with out of range date."""
    field = {
        "id": "birth_date",
        "type": "date",
        "validators": [{"type": "date_range", "min": "1950-01-01", "max": "2000-12-31"}]
    }
    
    is_valid, error, normalized = _validate_field(field, "01/01/1920")
    assert is_valid is False
    assert "Ngày ngoài khoảng cho phép" in error


def test_validate_email_field_valid():
    """Test email field validation with valid email."""
    field = {
        "id": "email",
        "type": "email",
        "validators": [{"type": "regex", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}]
    }
    
    is_valid, error, normalized = _validate_field(field, "test@example.com")
    assert is_valid is True
    assert error == ""


def test_validate_email_field_invalid():
    """Test email field validation with invalid email."""
    field = {
        "id": "email",
        "type": "email",
        "validators": [{"type": "regex", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}]
    }
    
    is_valid, error, normalized = _validate_field(field, "not-an-email")
    assert is_valid is False
    assert error != ""


def test_normalizers_applied():
    """Test that normalizers are applied correctly."""
    field = {
        "id": "text",
        "type": "text",
        "normalizers": ["strip_spaces", "upper"]
    }
    
    is_valid, error, normalized = _validate_field(field, "  hello world  ")
    assert normalized == "HELLO WORLD"


def test_multiple_normalizers():
    """Test multiple normalizers applied in sequence."""
    field = {
        "id": "text",
        "type": "text",
        "normalizers": ["strip_spaces", "collapse_whitespace", "title_case"]
    }
    
    is_valid, error, normalized = _validate_field(field, "  hello    world  ")
    assert normalized == "Hello World"
