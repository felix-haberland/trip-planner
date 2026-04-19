"""Tests for the seed_golf_library script (spec 006 FR-S-002 idempotence)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sys

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))


def _fake_extract_resort(*, url=None, name=None, existing_parent_resort_lookup=None):
    """Return a minimal valid ExtractedResort without hitting Claude."""
    from app.golf import schemas

    return schemas.ExtractedResort(
        data=schemas.GolfResortCreate(name=name, country_code="PT"),
        source_urls=["https://example.com"],
    )


def _fake_extract_course(*, url=None, name=None, existing_parent_resort_lookup=None):
    from app.golf import schemas

    return schemas.ExtractedCourse(
        data=schemas.GolfCourseCreate(name=name, country_code="GB"),
        source_urls=["https://example.com"],
    )


@pytest.fixture
def seeded_db(trips_session, monkeypatch):
    """Patch extraction + the seed_script's TripsSessionLocal to use our test
    session, then return the script module."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    # Import the script
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "seed_golf_library",
        _BACKEND_ROOT / "scripts" / "seed_golf_library.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Patch extraction + sleep to make the test fast.
    monkeypatch.setattr(mod.extraction, "extract_resort", _fake_extract_resort)
    monkeypatch.setattr(mod.extraction, "extract_course", _fake_extract_course)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    return mod, trips_session


def test_seed_creates_entries(seeded_db):
    mod, db = seeded_db
    entries = {
        "resorts": [
            {"name": "Alpha Resort", "country_code": "PT"},
            {"name": "Beta Resort", "country_code": "ES"},
        ],
        "courses": [
            {"name": "Gamma Course", "country_code": "GB"},
        ],
    }
    for e in entries["resorts"]:
        result = mod._seed_one_resort(db, e, dry_run=False)
        assert result.startswith("CREATED"), result
    for e in entries["courses"]:
        result = mod._seed_one_course(db, e, dry_run=False)
        assert result.startswith("CREATED"), result


def test_seed_is_idempotent(seeded_db):
    mod, db = seeded_db
    entry = {"name": "Alpha Resort", "country_code": "PT"}
    first = mod._seed_one_resort(db, entry, dry_run=False)
    assert first.startswith("CREATED")
    # Re-run — should skip.
    second = mod._seed_one_resort(db, entry, dry_run=False)
    assert second.startswith("SKIPPED (duplicate)")


def test_seed_dry_run_creates_nothing(seeded_db):
    from app.golf import models

    mod, db = seeded_db
    line = mod._seed_one_resort(
        db, {"name": "Zeta Resort", "country_code": "PT"}, dry_run=True
    )
    assert line.startswith("WOULD CREATE")
    assert (
        db.query(models.GolfResort)
        .filter(models.GolfResort.name_norm == "zeta resort")
        .count()
        == 0
    )
