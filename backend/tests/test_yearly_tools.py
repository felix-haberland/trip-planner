"""Tests for the yearly Claude tools (F009 — year-options advisor).

Tools: list_options, list_slots_in_option, list_linked_trips,
get_visit_history, generate_year_option, propose_slot_in_option.
"""

from __future__ import annotations

import json


def _windows():
    from datetime import date

    from app.yearly import schemas

    return [
        schemas.WindowSpec(
            label="June", start_date=date(2026, 6, 5), end_date=date(2026, 6, 19)
        ),
        schemas.WindowSpec(
            label="Sept", start_date=date(2026, 9, 8), end_date=date(2026, 9, 18)
        ),
        schemas.WindowSpec(
            label="Dec", start_date=date(2026, 12, 21), end_date=date(2026, 12, 28)
        ),
    ]


def _plan(db):
    from app.yearly import crud, schemas

    return crud.create_year_plan(
        db, schemas.YearPlanCreate(year=2026, name="Main", windows=_windows())
    )


def _option(db, plan_id):
    from app.yearly import crud, schemas

    return crud.create_year_option(db, plan_id, schemas.YearOptionCreate(name="A"))


def _slot(db, option_id, window_index=0, **overrides):
    from app.yearly import crud, schemas

    defaults = dict(window_index=window_index)
    defaults.update(overrides)
    return crud.create_slot(db, option_id, schemas.SlotCreate(**defaults))


def test_list_options_empty(trips_session):
    from app.yearly import tools

    plan = _plan(trips_session)
    out = json.loads(
        tools.execute_tool("list_options", {}, trips_session, None, plan.id)
    )
    assert out["year"] == 2026
    assert out["options"] == []


def test_list_options_includes_slots(trips_session):
    from app.yearly import tools

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    _slot(trips_session, opt.id, label="Safari")
    out = json.loads(
        tools.execute_tool("list_options", {}, trips_session, None, plan.id)
    )
    assert len(out["options"]) == 1
    assert out["options"][0]["slot_count"] == 1
    assert out["options"][0]["slots"][0]["label"] == "Safari"


def test_list_slots_in_option(trips_session):
    from app.yearly import tools

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    _slot(trips_session, opt.id, label="S1")
    out = json.loads(
        tools.execute_tool(
            "list_slots_in_option",
            {"option_id": opt.id},
            trips_session,
            None,
            plan.id,
        )
    )
    assert out["name"] == "A"
    assert len(out["slots"]) == 1


def test_list_slots_in_option_rejects_foreign(trips_session):
    from app.yearly import tools

    plan_a = _plan(trips_session)
    plan_b = _plan(trips_session)
    opt_b = _option(trips_session, plan_b.id)
    out = json.loads(
        tools.execute_tool(
            "list_slots_in_option",
            {"option_id": opt_b.id},
            trips_session,
            None,
            plan_a.id,
        )
    )
    assert "error" in out


def test_generate_year_option_creates_option_and_slots(trips_session):
    """AI-generated options fill windows by index; dates inherit from the windows."""
    from app.yearly import crud, tools

    plan = _plan(trips_session)
    out = json.loads(
        tools.execute_tool(
            "generate_year_option",
            {
                "name": "Adventurous mix",
                "summary": "Safari + warm Christmas",
                "slots": [
                    {
                        "label": "Safari",
                        "theme": "bush + walking",
                        "window_index": 1,
                        "activity_weights": {"wildlife": 100},
                    },
                    {
                        "label": "Winter escape",
                        "theme": "warm beach",
                        "window_index": 2,
                    },
                ],
            },
            trips_session,
            None,
            plan.id,
        )
    )
    assert out["ok"] is True
    assert len(out["slot_ids"]) == 2
    assert out["slot_errors"] == []
    option = crud.get_year_option(trips_session, out["option_id"])
    assert option.name == "Adventurous mix"
    assert option.created_by == "ai"
    assert len(option.slots) == 2
    assert all(s.status == "proposed" for s in option.slots)
    # Dates inherited: Sept window slot should have start_month=9.
    sept = next(s for s in option.slots if s.window_index == 1)
    assert sept.start_month == 9


def test_generate_year_option_allows_multiple_ideas_same_window(trips_session):
    """Multiple trip ideas in the same (option, window) cell are alternatives."""
    from app.yearly import crud, tools

    plan = _plan(trips_session)
    out = json.loads(
        tools.execute_tool(
            "generate_year_option",
            {
                "name": "Flexible June",
                "slots": [
                    {"label": "Golf", "theme": "warm iberia", "window_index": 0},
                    {"label": "Beach", "theme": "relaxed coast", "window_index": 0},
                ],
            },
            trips_session,
            None,
            plan.id,
        )
    )
    assert out["ok"] is True
    assert len(out["slot_ids"]) == 2
    assert out["slot_errors"] == []
    option = crud.get_year_option(trips_session, out["option_id"])
    assert len(option.slots) == 2


def test_generate_year_option_rejects_slot_missing_window_index(trips_session):
    from app.yearly import tools

    plan = _plan(trips_session)
    out = json.loads(
        tools.execute_tool(
            "generate_year_option",
            {
                "name": "No window",
                "slots": [{"label": "A", "theme": "x"}],
            },
            trips_session,
            None,
            plan.id,
        )
    )
    assert out["ok"] is True
    assert len(out["slot_ids"]) == 0
    assert len(out["slot_errors"]) == 1


def test_generate_year_option_requires_name_and_slots(trips_session):
    from app.yearly import tools

    plan = _plan(trips_session)
    out = json.loads(
        tools.execute_tool(
            "generate_year_option",
            {"name": "", "slots": []},
            trips_session,
            None,
            plan.id,
        )
    )
    assert "error" in out


def test_propose_slot_in_option_appends_slot(trips_session):
    from app.yearly import crud, tools

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    out = json.loads(
        tools.execute_tool(
            "propose_slot_in_option",
            {
                "option_id": opt.id,
                "label": "Safari",
                "theme": "walking",
                "window_index": 1,
            },
            trips_session,
            None,
            plan.id,
        )
    )
    assert out["ok"] is True
    slot = crud.get_slot(trips_session, out["slot_id"])
    assert slot is not None and slot.status == "proposed"
    assert slot.year_option_id == opt.id
    # Dates inherited from the Sept window (see _windows).
    assert slot.start_month == 9


def test_propose_slot_rejects_foreign_option(trips_session):
    from app.yearly import tools

    plan_a = _plan(trips_session)
    plan_b = _plan(trips_session)
    opt_b = _option(trips_session, plan_b.id)
    out = json.loads(
        tools.execute_tool(
            "propose_slot_in_option",
            {
                "option_id": opt_b.id,
                "label": "x",
                "theme": "y",
                "window_index": 0,
            },
            trips_session,
            None,
            plan_a.id,
        )
    )
    assert "error" in out


def test_list_linked_trips_reports_across_options(trips_session):
    from app.yearly import crud, tools

    plan = _plan(trips_session)
    opt = _option(trips_session, plan.id)
    slot = _slot(trips_session, opt.id)
    trip = crud.start_trip_for_slot(trips_session, slot.id)
    out = json.loads(
        tools.execute_tool("list_linked_trips", {}, trips_session, None, plan.id)
    )
    assert trip.id in {t["trip_id"] for t in out["linked_to_option_slots"]}


def test_unknown_tool_returns_error(trips_session):
    from app.yearly import tools

    plan = _plan(trips_session)
    out = json.loads(
        tools.execute_tool("no_such_tool", {}, trips_session, None, plan.id)
    )
    assert "error" in out
