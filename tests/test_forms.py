"""Tests for form matching and loading."""
import pytest
from app import pick_form, FORM_INDEX, ALIASES


def test_pick_form_by_exact_id():
    """Test form selection by exact form_id."""
    form = pick_form("don_xin_viec")
    assert form is not None
    assert form["form_id"] == "don_xin_viec"


def test_pick_form_by_alias():
    """Test form selection by alias keyword."""
    form = pick_form("xin việc")
    assert form is not None
    assert form["form_id"] == "don_xin_viec"


def test_pick_form_by_title():
    """Test form selection by partial title match."""
    form = pick_form("việc làm")
    assert form is not None


def test_pick_form_not_found():
    """Test form selection with invalid query."""
    form = pick_form("nonexistent_form_12345")
    assert form is None


def test_form_index_loaded():
    """Test that form index is populated."""
    assert len(FORM_INDEX) > 0
    assert "don_xin_viec" in FORM_INDEX


def test_aliases_loaded():
    """Test that aliases are populated."""
    assert len(ALIASES) > 0
    assert any("xin việc" in alias for alias in ALIASES.keys())


def test_all_forms_have_required_fields():
    """Test that all forms have required structure."""
    for form_id, form in FORM_INDEX.items():
        assert "form_id" in form
        assert "title" in form
        assert "fields" in form
        assert isinstance(form["fields"], list)
        assert len(form["fields"]) > 0
