"""F011 — drag-and-drop reorder for trips, year options, and windows."""

from __future__ import annotations

from datetime import date

import pytest

# --- helpers ---------------------------------------------------------------


def _make_trip(db, name="Trip"):
    from app.trips import crud, schemas

    return crud.create_trip(db, schemas.TripCreate(name=name, description="d"))


def _windows():
    from app.yearly import schemas

    return [
        schemas.WindowSpec(
            label="June", start_date=date(2026, 6, 5), end_date=date(2026, 6, 19)
        ),
        schemas.WindowSpec(
            label="Sept", start_date=date(2026, 9, 8), end_date=date(2026, 9, 18)
        ),
        schemas.WindowSpec(
            label="Dec",
            start_date=date(2026, 12, 21),
            end_date=date(2026, 12, 28),
        ),
    ]


def _plan_with_three_windows(db):
    from app.yearly import crud, schemas

    return crud.create_year_plan(
        db, schemas.YearPlanCreate(year=2026, name="P", windows=_windows())
    )


def _option(db, plan_id, name="Opt"):
    from app.yearly import crud, schemas

    return crud.create_year_option(db, plan_id, schemas.YearOptionCreate(name=name))


def _slot(db, option_id, window_index, label):
    from app.yearly import crud, schemas

    return crud.create_slot(
        db,
        option_id,
        schemas.SlotCreate(window_index=window_index, label=label),
    )


# --- Trips reorder ---------------------------------------------------------


def test_reorder_trips_assigns_positions_in_supplied_order(trips_session):
    from app.trips import crud

    a = _make_trip(trips_session, "A")
    b = _make_trip(trips_session, "B")
    c = _make_trip(trips_session, "C")

    # Move C to front, then A, then B.
    result = crud.reorder_trips(trips_session, [c.id, a.id, b.id])

    assert [t.id for t in result] == [c.id, a.id, b.id]
    assert [t.position for t in result] == [0, 1, 2]
    # list_trips reflects the new order.
    assert [t.id for t in crud.list_trips(trips_session)] == [c.id, a.id, b.id]


def test_reorder_trips_rejects_missing_id(trips_session):
    from app.trips import crud

    a = _make_trip(trips_session, "A")
    b = _make_trip(trips_session, "B")

    with pytest.raises(ValueError, match="missing"):
        crud.reorder_trips(trips_session, [a.id])  # b is missing
    # Order is unchanged.
    assert [t.id for t in crud.list_trips(trips_session)] == [a.id, b.id]


def test_reorder_trips_rejects_unknown_id(trips_session):
    from app.trips import crud

    a = _make_trip(trips_session, "A")
    b = _make_trip(trips_session, "B")

    with pytest.raises(ValueError, match="unknown"):
        crud.reorder_trips(trips_session, [a.id, b.id, 9999])


def test_reorder_trips_rejects_duplicates(trips_session):
    from app.trips import crud

    a = _make_trip(trips_session, "A")
    b = _make_trip(trips_session, "B")

    with pytest.raises(ValueError, match="duplicate"):
        crud.reorder_trips(trips_session, [a.id, a.id, b.id])


def test_new_trip_appends_at_end(trips_session):
    from app.trips import crud

    a = _make_trip(trips_session, "A")
    b = _make_trip(trips_session, "B")
    c = _make_trip(trips_session, "C")

    assert [t.position for t in crud.list_trips(trips_session)] == [0, 1, 2]
    # Created in insertion order.
    assert [t.id for t in crud.list_trips(trips_session)] == [a.id, b.id, c.id]


# --- Year option reorder ---------------------------------------------------


def test_reorder_year_options_happy_path(trips_session):
    from app.yearly import crud

    plan = _plan_with_three_windows(trips_session)
    a = _option(trips_session, plan.id, "A")
    b = _option(trips_session, plan.id, "B")
    c = _option(trips_session, plan.id, "C")

    crud.reorder_year_options(trips_session, plan.id, [c.id, a.id, b.id])

    listed = crud.list_options_for_plan(trips_session, plan.id)
    assert [o.id for o in listed] == [c.id, a.id, b.id]
    assert [o.position for o in listed] == [0, 1, 2]


def test_reorder_year_options_rejects_non_permutation(trips_session):
    from app.yearly import crud

    plan = _plan_with_three_windows(trips_session)
    a = _option(trips_session, plan.id, "A")
    b = _option(trips_session, plan.id, "B")

    with pytest.raises(ValueError):
        crud.reorder_year_options(trips_session, plan.id, [a.id])  # missing b
    with pytest.raises(ValueError):
        crud.reorder_year_options(trips_session, plan.id, [a.id, b.id, 9999])


def test_reorder_year_options_unknown_plan_returns_none(trips_session):
    from app.yearly import crud

    assert crud.reorder_year_options(trips_session, 9999, []) is None


# --- Window reorder (the tricky one — remap slot.window_index) ------------


def test_reorder_windows_reshuffles_array_and_remaps_slot_indices(trips_session):
    from app.yearly import crud

    plan = _plan_with_three_windows(trips_session)
    opt_a = _option(trips_session, plan.id, "A")
    opt_b = _option(trips_session, plan.id, "B")

    s_a0 = _slot(trips_session, opt_a.id, 0, "A-June")
    s_a2 = _slot(trips_session, opt_a.id, 2, "A-Dec")
    s_b1 = _slot(trips_session, opt_b.id, 1, "B-Sept")

    # New order: window 2 first, then 0, then 1. So:
    #   old 0 → new 1
    #   old 1 → new 2
    #   old 2 → new 0
    plan = crud.reorder_windows(trips_session, plan.id, [2, 0, 1])
    assert plan is not None

    # Window array order follows the request.
    import json

    new_windows = json.loads(plan.windows)
    assert new_windows[0]["label"] == "Dec"
    assert new_windows[1]["label"] == "June"
    assert new_windows[2]["label"] == "Sept"

    # All affected slots are remapped.
    trips_session.refresh(s_a0)
    trips_session.refresh(s_a2)
    trips_session.refresh(s_b1)
    assert s_a0.window_index == 1
    assert s_a2.window_index == 0
    assert s_b1.window_index == 2


def test_reorder_windows_rejects_non_permutation(trips_session):
    from app.yearly import crud

    plan = _plan_with_three_windows(trips_session)

    with pytest.raises(ValueError, match="permutation"):
        crud.reorder_windows(trips_session, plan.id, [0, 0, 1])
    with pytest.raises(ValueError, match="permutation"):
        crud.reorder_windows(trips_session, plan.id, [0, 1, 5])


def test_reorder_windows_rejects_wrong_length(trips_session):
    from app.yearly import crud

    plan = _plan_with_three_windows(trips_session)

    with pytest.raises(ValueError, match="entries"):
        crud.reorder_windows(trips_session, plan.id, [0, 1])


def test_reorder_windows_unknown_plan_returns_none(trips_session):
    from app.yearly import crud

    assert crud.reorder_windows(trips_session, 9999, []) is None


def test_reorder_windows_noop_identity_preserves_slot_indices(trips_session):
    from app.yearly import crud

    plan = _plan_with_three_windows(trips_session)
    opt = _option(trips_session, plan.id, "A")
    s = _slot(trips_session, opt.id, 1, "Sept")

    crud.reorder_windows(trips_session, plan.id, [0, 1, 2])
    trips_session.refresh(s)
    assert s.window_index == 1
