"""Tests for yearly CRUD (F009 redesign).

Hierarchy: YearPlan (with `windows`) → YearOption → Slot.
"""

from __future__ import annotations

from datetime import date

import pytest


def _default_windows():
    from app.yearly import schemas

    return [
        schemas.WindowSpec(
            label="June", start_date=date(2026, 6, 5), end_date=date(2026, 6, 19)
        ),
        schemas.WindowSpec(
            label="Sept", start_date=date(2026, 9, 8), end_date=date(2026, 9, 18)
        ),
        schemas.WindowSpec(
            label="Christmas",
            start_date=date(2026, 12, 21),
            end_date=date(2026, 12, 28),
        ),
    ]


def _plan(db, **overrides):
    from app.yearly import crud, schemas

    defaults = dict(year=2026, name="Main", windows=_default_windows())
    defaults.update(overrides)
    body = schemas.YearPlanCreate(**defaults)
    return crud.create_year_plan(db, body)


def _option(db, plan_id, name="Opt A"):
    from app.yearly import crud, schemas

    return crud.create_year_option(db, plan_id, schemas.YearOptionCreate(name=name))


def _slot(db, option_id, window_index=0, **overrides):
    from app.yearly import crud, schemas

    defaults = dict(window_index=window_index)
    defaults.update(overrides)
    body = schemas.SlotCreate(**defaults)
    return crud.create_slot(db, option_id, body)


# --- Year plan lifecycle ---------------------------------------------------


def test_create_year_plan_seeds_main_conversation(trips_session):
    from app.trips.models import Conversation

    plan = _plan(trips_session)
    convs = (
        trips_session.query(Conversation)
        .filter(
            Conversation.owner_type == "year_plan",
            Conversation.owner_id == plan.id,
        )
        .all()
    )
    assert len(convs) == 1 and convs[0].name == "Main"


def test_year_plan_windows_roundtrip(trips_session):
    from app.yearly import crud, schemas

    plan = _plan(
        trips_session,
        windows=[
            schemas.WindowSpec(
                label="June break",
                start_date=date(2026, 6, 5),
                end_date=date(2026, 6, 19),
                duration_hint=14,
            ),
            schemas.WindowSpec(
                start_date=date(2026, 12, 21),
                end_date=date(2026, 12, 28),
            ),
        ],
    )
    parsed = crud._parse_windows(plan.windows)
    assert len(parsed) == 2
    assert parsed[0]["label"] == "June break"
    assert parsed[0]["duration_hint"] == 14
    assert parsed[1]["start_date"] == "2026-12-21"


def test_multiple_plans_same_year_allowed(trips_session):
    from app.yearly import crud

    a = _plan(trips_session, name="Conservative 2026")
    b = _plan(trips_session, name="Wild 2026")
    listed = crud.list_year_plans(trips_session, year=2026)
    assert {p.id for p in listed} == {a.id, b.id}


def test_delete_year_plan_cascades_options_and_slots(trips_session):
    from app.yearly import crud, models

    plan = _plan(trips_session)
    option = _option(trips_session, plan.id)
    _slot(trips_session, option.id)
    assert crud.delete_year_plan(trips_session, plan.id) is True
    assert trips_session.query(models.YearOption).count() == 0
    assert trips_session.query(models.Slot).count() == 0


def test_delete_year_plan_does_not_delete_linked_trip(trips_session):
    from app.yearly import crud
    from app.trips import models as trips_models

    plan = _plan(trips_session)
    option = _option(trips_session, plan.id)
    slot = _slot(trips_session, option.id)
    trip = crud.start_trip_for_slot(trips_session, slot.id)
    assert crud.delete_year_plan(trips_session, plan.id) is True
    assert (
        trips_session.query(trips_models.TripPlan)
        .filter(trips_models.TripPlan.id == trip.id)
        .first()
        is not None
    )


# --- Options ---------------------------------------------------------------


def test_option_create_and_list(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    a = _option(trips_session, plan.id, name="A")
    b = _option(trips_session, plan.id, name="B")
    listed = crud.list_options_for_plan(trips_session, plan.id)
    assert [o.id for o in listed] == [a.id, b.id]


def test_option_mark_chosen(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    chosen = crud.mark_option_chosen(trips_session, opt.id)
    assert chosen.status == "chosen"


def test_option_unpick_reverts_to_draft(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    crud.mark_option_chosen(trips_session, opt.id)
    reverted = crud.unpick_option(trips_session, opt.id)
    assert reverted.status == "draft"


def test_option_unpick_no_op_when_not_chosen(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)  # status='draft'
    reverted = crud.unpick_option(trips_session, opt.id)
    assert reverted.status == "draft"


def test_fork_option_clones_slots_not_trip_links(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    src = _option(trips_session, plan.id, name="A")
    slot = _slot(
        trips_session,
        src.id,
        label="Safari",
        theme="bush + walking",
        activity_weights={"wildlife": 100},
    )
    # Link a real trip to the slot — fork must NOT copy the link.
    crud.start_trip_for_slot(trips_session, slot.id)
    trips_session.refresh(slot)
    assert slot.trip_plan_id is not None

    forked = crud.fork_option(trips_session, src.id, "A (copy)")
    assert forked.name == "A (copy)"
    assert forked.status == "draft"
    assert forked.created_by == "user"
    assert len(forked.slots) == 1
    forked_slot = forked.slots[0]
    assert forked_slot.id != slot.id
    assert forked_slot.label == "Safari"
    assert forked_slot.theme == "bush + walking"
    assert forked_slot.trip_plan_id is None


def test_delete_option_cascades_slots(trips_session):
    from app.yearly import crud, models

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    _slot(trips_session, opt.id)
    assert crud.delete_year_option(trips_session, opt.id) is True
    assert trips_session.query(models.Slot).count() == 0


# --- Slots: window-anchored, unique per (option, window) -----------------


def test_multiple_ideas_per_option_window_allowed(trips_session):
    """Users can sketch alternative ideas inside a single cell."""
    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    a = _slot(trips_session, opt.id, window_index=0, label="Golf")
    b = _slot(trips_session, opt.id, window_index=0, label="Beach")
    assert a.id != b.id
    assert a.window_index == b.window_index == 0
    trips_session.refresh(opt)
    assert len([s for s in opt.slots if s.window_index == 0]) == 2


def test_same_window_across_different_options_allowed(trips_session):
    """Sibling options can both fill window #0 — they're alternatives."""
    plan = _plan(trips_session)
    a = _option(trips_session, plan.id, name="A")
    b = _option(trips_session, plan.id, name="B")
    _slot(trips_session, a.id, window_index=0)
    slot_b = _slot(trips_session, b.id, window_index=0)
    assert slot_b.year_option_id == b.id


def test_slot_inherits_dates_from_window(trips_session):
    """Creating a slot without explicit dates pulls them from the window."""
    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    # window #0 = 2026-06-05 → 2026-06-19 (see _default_windows)
    slot = _slot(trips_session, opt.id, window_index=0, theme="safari")
    assert slot.start_year == 2026 and slot.start_month == 6
    assert slot.end_year == 2026 and slot.end_month == 6


def test_slot_window_index_out_of_range_rejected(trips_session):
    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    with pytest.raises(ValueError):
        _slot(trips_session, opt.id, window_index=99)


def test_option_can_leave_windows_empty(trips_session):
    """Options fill *some* windows, not all. An option with only window #0
    filled is perfectly valid."""
    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = _slot(trips_session, opt.id, window_index=0)
    # Option now has 1 slot even though plan has 3 windows.
    trips_session.refresh(opt)
    assert len(opt.slots) == 1
    assert slot.window_index == 0


def test_proposed_slot_accept(trips_session):
    from app.yearly import crud, schemas

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = crud.create_slot(
        trips_session,
        opt.id,
        schemas.SlotCreate(
            label="Safari",
            theme="bush",
            window_index=1,
            status="proposed",
        ),
    )
    assert slot.status == "proposed"
    accepted = crud.accept_slot(trips_session, slot.id)
    assert accepted.status == "open"


def test_slot_unreview_reverts_to_proposed(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = _slot(trips_session, opt.id, window_index=0)  # status='open' by default
    reverted = crud.unreview_slot(trips_session, slot.id)
    assert reverted.status == "proposed"


def test_slot_unreview_no_op_on_archived(trips_session):
    from app.yearly import crud, schemas

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = _slot(trips_session, opt.id, window_index=0)
    crud.update_slot(trips_session, slot.id, schemas.SlotUpdate(status="archived"))
    result = crud.unreview_slot(trips_session, slot.id)
    assert result.status == "archived"  # unchanged


# --- start_trip_for_slot & reverse lookup ---------------------------------


def test_start_trip_for_slot_creates_linked_trip(trips_session):
    from app.yearly import crud, schemas

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    # window #0 = June (see _default_windows) — dates inherited.
    slot = crud.create_slot(
        trips_session,
        opt.id,
        schemas.SlotCreate(
            label="Golf",
            theme="warm Iberia",
            window_index=0,
            activity_weights={"golf": 100},
        ),
    )
    trip = crud.start_trip_for_slot(trips_session, slot.id)
    trips_session.refresh(slot)
    assert trip is not None
    assert trip.target_month == "jun"
    assert "warm Iberia" in (trip.description or "")
    assert slot.trip_plan_id == trip.id


def test_start_trip_is_idempotent(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = _slot(trips_session, opt.id)
    t1 = crud.start_trip_for_slot(trips_session, slot.id)
    t2 = crud.start_trip_for_slot(trips_session, slot.id)
    assert t1.id == t2.id


def test_slot_for_trip_reverse_lookup(trips_session):
    from app.yearly import crud

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = _slot(trips_session, opt.id)
    trip = crud.start_trip_for_slot(trips_session, slot.id)
    back = crud.slot_for_trip(trips_session, trip.id)
    assert back is not None and back.id == slot.id


def test_link_and_unlink_existing_trip(trips_session):
    from app.yearly import crud
    from app.trips import models as trips_models

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = _slot(trips_session, opt.id)
    trip = trips_models.TripPlan(
        name="Existing", description="", target_month="jun", activity_weights="{}"
    )
    trips_session.add(trip)
    trips_session.commit()

    linked = crud.link_existing_trip_to_slot(trips_session, slot.id, trip.id)
    assert linked.trip_plan_id == trip.id

    unlinked = crud.unlink_trip_from_slot(trips_session, slot.id)
    assert unlinked.trip_plan_id is None
