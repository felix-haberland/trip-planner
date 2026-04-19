"""Tests for the polymorphic Conversation owner shape.

Covers cross-owner isolation and the message dispatcher that routes
`POST /api/conversations/{id}/messages` based on owner_type.

(The one-time legacy-table-rebuild migration test was removed when we moved
to Alembic — the pre-polymorphic shape no longer exists in the wild and
the baseline migration creates the polymorphic shape directly.)
"""

from __future__ import annotations

import os
import tempfile


def test_conversations_isolated_by_owner_type(trips_session):
    """A year-plan conversation should not show up in a trip's conversation list
    (and vice versa)."""
    from app.trips import crud as trips_crud, schemas as trips_schemas
    from app.yearly import crud as yearly_crud, schemas as yearly_schemas

    trip = trips_crud.create_trip(
        trips_session, trips_schemas.TripCreate(name="T", description="d")
    )
    trips_crud.create_conversation(trips_session, trip.id, "Main")

    plan = yearly_crud.create_year_plan(
        trips_session, yearly_schemas.YearPlanCreate(year=2026, name="Main")
    )
    yearly_crud.create_conversation(trips_session, plan.id, "Follow-up")

    trip_convs = trips_crud.list_conversations(trips_session, trip.id)
    year_convs = yearly_crud.list_conversations(trips_session, plan.id)

    assert len(trip_convs) == 1 and trip_convs[0].name == "Main"
    # Year plan auto-seeds Main conversation at create + we added Follow-up.
    assert {c.name for c in year_convs} == {"Main", "Follow-up"}


def test_delete_trip_cascades_conversations(trips_session):
    """Without the ORM back_populates, cascade must be hand-rolled — verify it
    works for trip-owned conversations."""
    from app.trips import crud as trips_crud, schemas as trips_schemas
    from app.trips.models import Conversation

    trip = trips_crud.create_trip(
        trips_session, trips_schemas.TripCreate(name="T", description="d")
    )
    trips_crud.create_conversation(trips_session, trip.id, "Main")
    trips_crud.create_conversation(trips_session, trip.id, "Follow-up")
    assert trips_crud.delete_trip(trips_session, trip.id) is True

    remaining = (
        trips_session.query(Conversation)
        .filter(Conversation.owner_type == "trip", Conversation.owner_id == trip.id)
        .count()
    )
    assert remaining == 0


def test_message_dispatch_for_year_plan(monkeypatch):
    """POST /api/conversations/{id}/messages should dispatch to the yearly
    handler for year-plan-owned conversations."""
    from fastapi.testclient import TestClient

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    try:
        monkeypatch.setenv("TRIPS_DB_PATH", tmp.name)
        # Clear the anthropic key so the handler returns its no-key error path
        # (deterministic, no network).
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")

        import sys

        for m in list(sys.modules):
            if m == "app" or m.startswith("app."):
                del sys.modules[m]

        from app.main import app

        with TestClient(app) as client:
            r = client.post(
                "/api/year-plans",
                json={"year": 2026, "name": "Main"},
            )
            assert r.status_code == 201
            plan_id = r.json()["id"]
            convs = client.get(f"/api/year-plans/{plan_id}/conversations").json()
            assert convs, "Main conversation should be seeded"
            conv_id = convs[0]["id"]

            r = client.post(
                f"/api/conversations/{conv_id}/messages",
                json={"content": "hi"},
            )
            assert r.status_code == 200
            body = r.json()
            # The dispatcher routed to the year-plan handler — response
            # shape is the yearly one (contains year_plan_state_changed).
            assert "year_plan_state_changed" in body
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
