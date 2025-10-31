"""Tests for form matching and loading."""

from app import ALIASES, FORM_INDEX, pick_form


def test_pick_form_by_exact_id():
    """Test form selection by exact form_id."""
    form_id = pick_form("don_xin_viec")
    assert form_id is not None
    assert form_id == "don_xin_viec"


def test_pick_form_by_alias():
    """Test form selection by alias keyword."""
    form_id = pick_form("xin việc")
    assert form_id is not None
    assert form_id == "don_xin_viec"


def test_pick_form_by_title():
    """Test form selection by partial title match."""
    form_id = pick_form("đơn xin việc")
    assert form_id is not None


def test_pick_form_not_found():
    """Test form selection with invalid query."""
    form_id = pick_form("nonexistent_form_12345")
    assert form_id is None


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
    for _form_id, form in FORM_INDEX.items():
        assert "form_id" in form
        assert "title" in form
        assert "fields" in form
        assert isinstance(form["fields"], list)
        assert len(form["fields"]) > 0
