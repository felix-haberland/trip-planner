"""Claude tools for the yearly chat (F009 — year-options advisor).

The year-level chatbot helps the user compose and compare **year options**
(candidate whole-year arrangements). It reads existing options/slots/visit
history and can generate new full options or add/refine single slots in an
existing option. It does **not** pick destinations — that's the trip chat's
job via the slot → trip_plan bridge.

Tools:
  * Read: list_options, list_slots_in_option, get_visit_history, list_linked_trips.
  * Write (suggest, don't decide):
    - generate_year_option(name, summary?, slots=[…]) creates a full new
      YearOption with its slots as status='proposed'.
    - propose_slot_in_option(option_id, …) adds a single slot to an existing
      option with status='proposed'.
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from . import crud, models, schemas
from ..trips import tools as trip_tools, vacationmap

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


_SLOT_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "Short label ('Safari', 'Golf trip').",
        },
        "theme": {
            "type": "string",
            "description": (
                "Prose description of the trip intent — activities, mood, "
                "rough region direction. Do NOT lock in a specific destination."
            ),
        },
        "window_index": {
            "type": "integer",
            "minimum": 0,
            "description": (
                "Which window this trip idea fills (0-based index into the "
                "parent YearPlan's `windows` list). Required. An option may "
                "leave some windows empty — just don't include a slot for them."
            ),
        },
        "start_year": {
            "type": "integer",
            "description": (
                "Optional — inherits from the window's start_date if omitted."
            ),
        },
        "start_month": {"type": "integer", "minimum": 1, "maximum": 12},
        "end_year": {"type": "integer"},
        "end_month": {"type": "integer", "minimum": 1, "maximum": 12},
        "exact_start_date": {
            "type": "string",
            "description": (
                "ISO date (YYYY-MM-DD). Only needed to shift inside the window."
            ),
        },
        "exact_end_date": {"type": "string"},
        "duration_days": {"type": "integer", "minimum": 1, "maximum": 365},
        "climate_hint": {"type": "string"},
        "constraints_note": {"type": "string"},
        "activity_weights": {"type": "object"},
    },
    "required": ["label", "theme", "window_index"],
}


YEARLY_TOOL_DEFINITIONS = [
    {
        "name": "list_options",
        "description": (
            "List every YearOption under the current YearPlan with its slots "
            "summarized. Use this to see what candidate years already exist "
            "before generating another one."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_slots_in_option",
        "description": "List the slots of a specific YearOption in detail.",
        "input_schema": {
            "type": "object",
            "properties": {"option_id": {"type": "integer"}},
            "required": ["option_id"],
        },
    },
    {
        "name": "get_visit_history",
        "description": (
            "Return the couple's travel history with visit_again annotations. "
            "Use to avoid repeating recent destinations across options."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_linked_trips",
        "description": (
            "List trips that are already linked to slots across any option "
            "in this year plan, plus existing trips whose dates loosely "
            "match this year."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "generate_year_option",
        "description": (
            "Create a new YearOption under the current YearPlan with a full "
            "slate of slots. Use when the user asks for a whole-year "
            "alternative ('give me a golf-heavy option'). Slots are created "
            "with status='proposed'; the user accepts or rejects them in "
            "the UI. Slots inside one option must not overlap each other — "
            "one trip per window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "summary": {
                    "type": "string",
                    "description": "One-line description of the option's theme.",
                },
                "slots": {
                    "type": "array",
                    "items": _SLOT_SPEC_SCHEMA,
                    "description": "List of trip intents — typically one per window.",
                },
            },
            "required": ["name", "slots"],
        },
    },
    {
        "name": "propose_slot_in_option",
        "description": (
            "Add a single slot to an existing YearOption with status='proposed'. "
            "Use for iterative refinement ('add a September trip to option 2')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "option_id": {"type": "integer"},
                **_SLOT_SPEC_SCHEMA["properties"],
            },
            "required": ["option_id"] + _SLOT_SPEC_SCHEMA["required"],
        },
    },
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _format_slot(slot: models.Slot) -> dict:
    return {
        "slot_id": slot.id,
        "window_index": slot.window_index,
        "label": slot.label,
        "theme": slot.theme or "",
        "start": f"{slot.start_year}-{slot.start_month:02d}",
        "end": f"{slot.end_year}-{slot.end_month:02d}",
        "exact_start_date": (
            slot.exact_start_date.isoformat() if slot.exact_start_date else None
        ),
        "exact_end_date": (
            slot.exact_end_date.isoformat() if slot.exact_end_date else None
        ),
        "duration_days": slot.duration_days,
        "climate_hint": slot.climate_hint,
        "constraints": slot.constraints_note,
        "activity_weights": crud._parse_weights(slot.activity_weights),
        "status": slot.status,
        "trip_plan_id": slot.trip_plan_id,
    }


def _format_option(option: models.YearOption) -> dict:
    return {
        "option_id": option.id,
        "name": option.name,
        "summary": option.summary or "",
        "status": option.status,
        "created_by": option.created_by,
        "slot_count": len(option.slots),
        "slots": [_format_slot(s) for s in option.slots],
    }


def handle_list_options(
    params: dict, trips_db: Session, vm_db: Session, year_plan_id: int
) -> str:
    plan = crud.get_year_plan(trips_db, year_plan_id)
    if plan is None:
        return json.dumps({"error": "year plan not found"})
    return json.dumps(
        {
            "year": plan.year,
            "windows": crud._parse_windows(plan.windows),
            "options": [_format_option(o) for o in plan.options],
        },
        indent=2,
        default=str,
    )


def handle_list_slots_in_option(
    params: dict, trips_db: Session, vm_db: Session, year_plan_id: int
) -> str:
    option_id = params.get("option_id")
    if not option_id:
        return json.dumps({"error": "option_id is required"})
    option = crud.get_year_option(trips_db, int(option_id))
    if option is None or option.year_plan_id != year_plan_id:
        return json.dumps({"error": "option not found in this year plan"})
    return json.dumps(_format_option(option), indent=2, default=str)


def handle_get_visit_history(
    params: dict, trips_db: Session, vm_db: Session, year_plan_id: int
) -> str:
    return trip_tools.handle_get_visit_history(params, trips_db, vm_db, year_plan_id)


def handle_list_linked_trips(
    params: dict, trips_db: Session, vm_db: Session, year_plan_id: int
) -> str:
    plan = crud.get_year_plan(trips_db, year_plan_id)
    if plan is None:
        return json.dumps({"error": "year plan not found"})
    linked = crud.trips_linked_in_plan(trips_db, year_plan_id)
    attachable = crud.trips_in_year(trips_db, plan.year)
    linked_ids = {t.id for t in linked}
    result = {
        "linked_to_option_slots": [
            {
                "trip_id": t.id,
                "name": t.name,
                "target_month": t.target_month,
                "status": t.status,
            }
            for t in linked
        ],
        "loose_date_match_unlinked": [
            {
                "trip_id": t.id,
                "name": t.name,
                "target_month": t.target_month,
                "status": t.status,
            }
            for t in attachable
            if t.id not in linked_ids
        ],
    }
    return json.dumps(result, indent=2)


def _opt_date(v) -> Optional[str]:
    if v is None or v == "":
        return None
    return str(v)


def _slot_body_from_spec(spec: dict) -> schemas.SlotCreate:
    wi = spec.get("window_index")
    if wi is None:
        raise ValueError("window_index is required")

    def _opt_int(v):
        if v is None or v == "":
            return None
        return int(v)

    return schemas.SlotCreate(
        label=spec.get("label"),
        theme=spec.get("theme") or "",
        window_index=int(wi),
        start_year=_opt_int(spec.get("start_year")),
        start_month=_opt_int(spec.get("start_month")),
        end_year=_opt_int(spec.get("end_year")),
        end_month=_opt_int(spec.get("end_month")),
        exact_start_date=_opt_date(spec.get("exact_start_date")),
        exact_end_date=_opt_date(spec.get("exact_end_date")),
        duration_days=_opt_int(spec.get("duration_days")),
        climate_hint=spec.get("climate_hint") or None,
        constraints_note=spec.get("constraints_note") or None,
        activity_weights=spec.get("activity_weights") or None,
        status="proposed",
    )


def handle_generate_year_option(
    params: dict, trips_db: Session, vm_db: Session, year_plan_id: int
) -> str:
    plan = crud.get_year_plan(trips_db, year_plan_id)
    if plan is None:
        return json.dumps({"error": "year plan not found"})

    name = (params.get("name") or "").strip()
    slots_spec = params.get("slots") or []
    if not name or not isinstance(slots_spec, list) or not slots_spec:
        return json.dumps({"error": "name and a non-empty slots list are required"})

    option = crud.create_year_option(
        trips_db,
        year_plan_id,
        schemas.YearOptionCreate(
            name=name,
            summary=params.get("summary") or "",
            created_by="ai",
            status="draft",
        ),
    )

    created_slot_ids: list[int] = []
    errors: list[dict] = []
    for idx, spec in enumerate(slots_spec):
        try:
            body = _slot_body_from_spec(spec)
        except (ValueError, TypeError) as e:
            errors.append({"slot_index": idx, "error": str(e)})
            continue
        try:
            slot = crud.create_slot(trips_db, option.id, body)
            created_slot_ids.append(slot.id)
        except (ValueError, LookupError) as e:
            errors.append({"slot_index": idx, "error": str(e)})

    return json.dumps(
        {
            "ok": True,
            "option_id": option.id,
            "option_name": option.name,
            "slot_ids": created_slot_ids,
            "slot_errors": errors,
        }
    )


def handle_propose_slot_in_option(
    params: dict, trips_db: Session, vm_db: Session, year_plan_id: int
) -> str:
    option_id = params.get("option_id")
    if not option_id:
        return json.dumps({"error": "option_id is required"})
    option = crud.get_year_option(trips_db, int(option_id))
    if option is None or option.year_plan_id != year_plan_id:
        return json.dumps({"error": "option not found in this year plan"})
    try:
        body = _slot_body_from_spec(params)
        slot = crud.create_slot(trips_db, int(option_id), body)
    except (ValueError, LookupError, TypeError) as e:
        return json.dumps({"error": str(e)})
    return json.dumps(
        {
            "ok": True,
            "slot_id": slot.id,
            "option_id": option.id,
            "status": slot.status,
            "label": slot.label,
            "start": f"{slot.start_year}-{slot.start_month:02d}",
            "end": f"{slot.end_year}-{slot.end_month:02d}",
        }
    )


TOOL_HANDLERS = {
    "list_options": handle_list_options,
    "list_slots_in_option": handle_list_slots_in_option,
    "get_visit_history": handle_get_visit_history,
    "list_linked_trips": handle_list_linked_trips,
    "generate_year_option": handle_generate_year_option,
    "propose_slot_in_option": handle_propose_slot_in_option,
}


def execute_tool(
    tool_name: str,
    tool_input: dict,
    trips_db: Session,
    vm_db: Session,
    year_plan_id: int,
) -> str:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown yearly tool: {tool_name}"})
    return handler(tool_input, trips_db, vm_db, year_plan_id)


_ = vacationmap
