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
    
    normalized, error = _validate_field("  john doe  ", field)
    assert error is None
    assert normalized == "John Doe"


def test_validate_text_field_too_short():
    """Test text field validation with too short input."""
    field = {
        "id": "name",
        "type": "text",
        "validators": [{"type": "length", "min": 5}]
    }
    
    normalized, error = _validate_field("Joe", field)
    assert error is not None
    assert "ít nhất 5 ký tự" in error


def test_validate_text_field_too_long():
    """Test text field validation with too long input."""
    field = {
        "id": "name",
        "type": "text",
        "validators": [{"type": "length", "max": 10}]
    }
    
    normalized, error = _validate_field("A" * 20, field)
    assert error is not None
    assert "không quá 10 ký tự" in error


def test_validate_numeric_field_valid():
    """Test numeric field validation with valid input."""
    field = {
        "id": "age",
        "type": "number",
        "validators": [{"type": "numeric_range", "min": 18, "max": 100}]
    }
    
    normalized, error = _validate_field("25", field)
    assert error is None
    assert normalized == "25"


def test_validate_numeric_field_invalid():
    """Test numeric field validation with non-numeric input."""
    field = {
        "id": "age",
        "type": "number",
        "validators": [{"type": "numeric_range", "min": 0}]
    }
    
    normalized, error = _validate_field("not a number", field)
    assert error is not None
    assert "số" in error.lower()


def test_validate_numeric_field_out_of_range():
    """Test numeric field validation with out of range value."""
    field = {
        "id": "age",
        "type": "number",
        "validators": [{"type": "numeric_range", "min": 18, "max": 65}]
    }
    
    normalized, error = _validate_field("100", field)
    assert error is not None
    assert "18" in error and "65" in error


def test_validate_date_field_valid():
    """Test date field validation with valid format."""
    field = {
        "id": "birth_date",
        "type": "date",
        "validators": [{"type": "date_range", "min": "1930-01-01", "max": "2010-12-31"}],
        "pattern": r"^\d{2}/\d{2}/\d{4}$"
    }
    
    normalized, error = _validate_field("15/05/1990", field)
    assert error is None
    assert normalized == "15/05/1990"


def test_validate_date_field_invalid_format():
    """Test date field validation with invalid format."""
    field = {
        "id": "birth_date",
        "type": "date",
        "pattern": r"^\d{2}/\d{2}/\d{4}$"
    }
    
    normalized, error = _validate_field("1990-05-15", field)
    assert error is not None
    assert "dd/mm/yyyy" in error.lower()


def test_validate_date_field_out_of_range():
    """Test date field validation with out of range date."""
    field = {
        "id": "birth_date",
        "type": "date",
        "validators": [{"type": "date_range", "min": "1950-01-01", "max": "2000-12-31"}]
    }
    
    normalized, error = _validate_field("01/01/1920", field)
    assert error is not None


def test_validate_email_field_valid():
    """Test email field validation with valid email."""
    field = {
        "id": "email",
        "type": "email",
        "validators": [{"type": "regex", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}]
    }
    
    normalized, error = _validate_field("test@example.com", field)
    assert error is None


def test_validate_email_field_invalid():
    """Test email field validation with invalid email."""
    field = {
        "id": "email",
        "type": "email",
        "validators": [{"type": "regex", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}]
    }
    
    normalized, error = _validate_field("not-an-email", field)
    assert error is not None


def test_normalizers_applied():
    """Test that normalizers are applied correctly."""
    field = {
        "id": "text",
        "type": "text",
        "normalizers": ["strip_spaces", "upper_case"]
    }
    
    normalized, error = _validate_field("  hello world  ", field)
    assert normalized == "HELLO WORLD"


def test_multiple_normalizers():
    """Test multiple normalizers applied in sequence."""
    field = {
        "id": "text",
        "type": "text",
        "normalizers": ["strip_spaces", "collapse_whitespace", "title_case"]
    }
    
    normalized, error = _validate_field("  hello    world  ", field)
    assert normalized == "Hello World"
