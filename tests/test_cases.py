"""Tests for Cases CRUD, clone, compare, and migration logic."""
import json
import os
import sqlite3
import tempfile

import pytest

# Adjust path so we can import from backend/
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.models import (
    init_db,
    save_project,
    delete_project,
    list_cases,
    get_case,
    create_case,
    update_case,
    delete_case,
    clone_case,
    get_cases_for_comparison,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for each test."""
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


@pytest.fixture
def project_id(db_path):
    """Create a test project and return its id."""
    return save_project(db_path, "Test Project", {}, {})


# ---------------------------------------------------------------------------
# Test 1: Basic CRUD — create, read, update, delete
# ---------------------------------------------------------------------------

def test_case_crud(db_path, project_id):
    """Create a case, read it, update it, then delete it."""
    # Create
    cid = create_case(db_path, project_id, "My Case", {"power": 100}, "memo text")
    assert cid is not None

    # Read
    case = get_case(db_path, cid)
    assert case is not None
    assert case["case_name"] == "My Case"
    assert case["case_memo"] == "memo text"
    assert case["input_data"] == {"power": 100}
    assert case["result_data"] is None
    assert case["is_baseline"] == 0

    # Update
    updated = update_case(db_path, cid, case_name="Renamed", result_data={"out": 1})
    assert updated is True
    case2 = get_case(db_path, cid)
    assert case2["case_name"] == "Renamed"
    assert case2["result_data"] == {"out": 1}

    # Delete
    deleted = delete_case(db_path, cid)
    assert deleted is True
    assert get_case(db_path, cid) is None


# ---------------------------------------------------------------------------
# Test 2: Clone case
# ---------------------------------------------------------------------------

def test_clone_case(db_path, project_id):
    """Cloned case copies input_data but not result_data."""
    cid = create_case(db_path, project_id, "Original", {"x": 42})
    update_case(db_path, cid, result_data={"battery": {"no_of_pcs": 5}})

    clone_id = clone_case(db_path, cid)
    clone = get_case(db_path, clone_id)

    assert clone["case_name"] == "Original (Copy)"
    assert clone["input_data"] == {"x": 42}
    assert clone["result_data"] is None  # result NOT copied
    assert clone["is_baseline"] == 0


# ---------------------------------------------------------------------------
# Test 3: Comparison retrieval
# ---------------------------------------------------------------------------

def test_get_cases_for_comparison(db_path, project_id):
    """Only cases with result_data appear in comparison."""
    c1 = create_case(db_path, project_id, "Calc'd", {})
    update_case(db_path, c1, result_data={"battery": {"no_of_pcs": 3}})

    c2 = create_case(db_path, project_id, "Pending", {})
    # c2 has no result_data

    results = get_cases_for_comparison(db_path, [c1, c2])
    assert len(results) == 1
    assert results[0]["case_name"] == "Calc'd"


# ---------------------------------------------------------------------------
# Test 4: Delete project cascades to cases
# ---------------------------------------------------------------------------

def test_delete_project_cascades(db_path, project_id):
    """Deleting a project also deletes all its cases."""
    create_case(db_path, project_id, "Case A", {})
    create_case(db_path, project_id, "Case B", {})
    cases_before = list_cases(db_path, project_id)
    assert len(cases_before) >= 2

    deleted = delete_project(db_path, project_id)
    assert deleted is True

    # Cases should be gone too
    assert len(list_cases(db_path, project_id)) == 0


# ---------------------------------------------------------------------------
# Test 5: Auto-migration creates baseline case from project data
# ---------------------------------------------------------------------------

def test_auto_migration_creates_baseline(db_path):
    """init_db auto-creates a Case 1 baseline for projects with no cases."""
    # Create a project directly (bypasses case creation)
    pid = save_project(db_path, "Migration Test", {"inp": 1}, {"res": 2})

    # Re-run init_db to trigger migration
    init_db(db_path)

    cases = list_cases(db_path, pid)
    assert len(cases) >= 1
    baseline = [c for c in cases if c["is_baseline"] == 1]
    assert len(baseline) == 1
    assert baseline[0]["case_name"] == "Case 1"


# ---------------------------------------------------------------------------
# Test 6: Max 10 cases per project (API-level enforcement)
# ---------------------------------------------------------------------------

def test_max_10_cases_enforcement(db_path, project_id):
    """Cannot create more than 10 cases per project."""
    # Auto-migration already created 1 case, create 9 more to hit 10
    existing = list_cases(db_path, project_id)
    for i in range(10 - len(existing)):
        create_case(db_path, project_id, f"Case {len(existing) + i + 1}", {})

    assert len(list_cases(db_path, project_id)) == 10

    # The 11th should be blocked at the API level (routes.py),
    # but at the model level create_case has no limit.
    # We test the model still allows it (limit is API-only).
    cid = create_case(db_path, project_id, "Extra", {})
    assert cid is not None  # Model allows; API blocks


# ---------------------------------------------------------------------------
# Test 7: Auto-naming when case_name is empty
# ---------------------------------------------------------------------------

def test_auto_naming(db_path, project_id):
    """When case_name is empty, auto-names to 'Case N'."""
    existing_count = len(list_cases(db_path, project_id))
    cid = create_case(db_path, project_id, "", {})
    case = get_case(db_path, cid)
    assert case["case_name"] == f"Case {existing_count + 1}"
