"""Tests for the golf-library Claude tools (spec 006 FR-015/015a/015b/016)."""

from __future__ import annotations

import json

from app.golf import crud, schemas, tools


def _setup_library(db):
    crud.create_resort(
        db,
        schemas.GolfResortCreate(
            name="Monte Rei",
            country_code="PT",
            hotel_type="luxury",
            price_category="€€€€",
            rank_rating=92,
            best_months=[4, 5, 10],
            vacationmap_region_key="PT:Algarve",
        ),
    )
    crud.create_resort(
        db,
        schemas.GolfResortCreate(
            name="Son Gual",
            country_code="ES",
            hotel_type="boutique",
            price_category="€€€",
            rank_rating=85,
        ),
    )
    crud.create_course(
        db,
        schemas.GolfCourseCreate(
            name="Old Course",
            country_code="GB",
            holes=18,
            par=72,
            type="links",
            rank_rating=99,
        ),
    )
    crud.create_course(
        db,
        schemas.GolfCourseCreate(
            name="Royal County Down",
            country_code="GB",
            holes=18,
            par=71,
            type="links",
            difficulty=5,
            rank_rating=96,
        ),
    )


def _trip(db) -> int:
    trip = crud.create_trip(db, schemas.TripCreate(name="T", description="d"))
    return trip.id


# --- search_golf_resorts -----------------------------------------


def test_search_golf_resorts_returns_library_size(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool("search_golf_resorts", {}, trips_session, None, trip_id)
    )
    assert out["library_size"] == 2
    assert out["total_matches"] == 2


def test_search_golf_resorts_fuzzy_name_query(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool(
            "search_golf_resorts",
            {"name_query": "monte"},
            trips_session,
            None,
            trip_id,
        )
    )
    assert out["total_matches"] == 1
    assert out["results"][0]["name"] == "Monte Rei"


def test_search_golf_resorts_country_price_filter(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool(
            "search_golf_resorts",
            {"country": "PT", "price_category": ["€€€€"]},
            trips_session,
            None,
            trip_id,
        )
    )
    assert out["total_matches"] == 1
    assert out["results"][0]["name"] == "Monte Rei"


def test_search_golf_resorts_min_rank_post_filter(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool(
            "search_golf_resorts",
            {"min_rank": 90},
            trips_session,
            None,
            trip_id,
        )
    )
    assert all(r["rank_rating"] >= 90 for r in out["results"])


# --- search_golf_courses ----------------------------------------


def test_search_golf_courses_type_filter(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool(
            "search_golf_courses",
            {"course_type": ["links"]},
            trips_session,
            None,
            trip_id,
        )
    )
    assert out["total_matches"] == 2
    assert {r["name"] for r in out["results"]} == {"Old Course", "Royal County Down"}


def test_search_golf_courses_fuzzy_name(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool(
            "search_golf_courses",
            {"name_query": "royal"},
            trips_session,
            None,
            trip_id,
        )
    )
    assert out["total_matches"] == 1
    assert out["results"][0]["name"] == "Royal County Down"


def test_search_golf_courses_standalone_only(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool(
            "search_golf_courses",
            {"parent_resort": "standalone"},
            trips_session,
            None,
            trip_id,
        )
    )
    assert out["total_matches"] == 2  # Both test courses are standalone


# --- suggest_for_review mutex (FR-018) --------------------------


def test_suggest_for_review_mutex_rejected(trips_session):
    _setup_library(trips_session)
    trip_id = _trip(trips_session)
    out = json.loads(
        tools.execute_tool(
            "suggest_for_review",
            {
                "destination_name": "X",
                "ai_reasoning": "y",
                "resort_id": 1,
                "course_id": 1,
            },
            trips_session,
            None,
            trip_id,
        )
    )
    assert out["status"] == "rejected"
    assert "mutually exclusive" in out["reason"]


# --- curated annotations on search_destinations (FR-016) -----


def test_annotate_with_curated_library(trips_session):
    _setup_library(trips_session)
    # Simulate a search_destinations response entry for PT:Algarve
    entries = [
        {"lookup_key": "PT:Algarve", "destination": "Algarve, PT"},
        {"lookup_key": "ZZ:Nowhere", "destination": "Nowhere"},
    ]
    tools.annotate_with_curated_library(entries, trips_session)
    assert entries[0]["curated_resort_count"] == 1
    assert entries[0]["resort_names"] == ["Monte Rei"]
    assert "curated_resort_count" not in entries[1]
