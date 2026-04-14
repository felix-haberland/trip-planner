"""Tool handler implementations for Claude function calling.

Each handler receives the tool input dict, the trips DB session, and the
VacationMap DB session, then returns a result string for Claude.
"""

import json

from sqlalchemy.orm import Session

from . import crud, vacationmap

# ---------------------------------------------------------------------------
# Tool definitions (passed to Claude API)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "search_destinations",
        "description": (
            "Search VacationMap destinations for a given month with optional filters. "
            "Returns top scored results with weather, cost, busyness, attractiveness, "
            "golf, safety scores, and travel tips."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "enum": [
                        "jan",
                        "feb",
                        "mar",
                        "apr",
                        "may",
                        "jun",
                        "jul",
                        "aug",
                        "sep",
                        "oct",
                        "nov",
                        "dec",
                        "christmas",
                        "easter",
                    ],
                },
                "activity_focus": {
                    "type": "string",
                    "enum": ["golf", "hiking", "nature", "city", "beach", "general"],
                    "description": (
                        "Activity focus adjusts scoring weights (e.g. golf boosts golf_score weight)"
                    ),
                },
                "max_flight_hours": {
                    "type": "number",
                    "description": "Maximum flight time from Munich in hours",
                },
                "min_safety_score": {
                    "type": "number",
                    "description": "Minimum safety score (0-10). Default 6.0",
                },
                "exclude_visited_never": {
                    "type": "boolean",
                    "description": (
                        "Exclude destinations marked 'visit_again: never'. Default true"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return. Default 10",
                },
            },
            "required": ["month"],
        },
    },
    {
        "name": "get_destination_details",
        "description": (
            "Get full details for a specific destination including all scores "
            "for a given month, travel tips, flight info, and visit history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region_lookup_key": {
                    "type": "string",
                    "description": (
                        "Format: CC:RegionName (e.g., PT:Algarve, TH:Bangkok)"
                    ),
                },
                "month": {"type": "string"},
            },
            "required": ["region_lookup_key", "month"],
        },
    },
    {
        "name": "get_visit_history",
        "description": (
            "Get all previously visited regions with ratings and revisit preferences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "suggest_for_review",
        "description": (
            "Add a destination to the 'To Review' list for the user to evaluate. "
            "Call this once for EACH destination you want to suggest. The user will "
            "then shortlist or exclude it from the UI. Include your reasoning and scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_name": {
                    "type": "string",
                    "description": "Display name (e.g. 'Algarve, Portugal')",
                },
                "region_lookup_key": {
                    "type": "string",
                    "description": (
                        "VacationMap stable key (e.g. PT:Algarve). Omit if not in database."
                    ),
                },
                "ai_reasoning": {
                    "type": "string",
                    "description": (
                        "Your pros/cons reasoning for why this destination fits (or doesn't perfectly fit) the trip"
                    ),
                },
                "scores_snapshot": {
                    "type": "object",
                    "description": (
                        "Key scores: total_score, weather_score, cost_relative, busyness_relative, attractiveness, golf_score, flight_hours"
                    ),
                },
                "pre_filled_exclude_reason": {
                    "type": "string",
                    "description": (
                        "Optional pre-filled reason for excluding. Use for recently visited destinations, e.g. 'Visited in 2024, rated 8/10 — revisit not planned soon'"
                    ),
                },
            },
            "required": ["destination_name", "ai_reasoning"],
        },
    },
    {
        "name": "shortlist_destination",
        "description": (
            "Directly add a destination to the shortlist (use when the user explicitly asks to shortlist something)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_name": {"type": "string"},
                "region_lookup_key": {"type": "string"},
                "ai_reasoning": {"type": "string"},
                "scores_snapshot": {"type": "object"},
                "user_note": {"type": "string"},
            },
            "required": ["destination_name", "ai_reasoning"],
        },
    },
    {
        "name": "exclude_destination",
        "description": (
            "Directly exclude a destination (use when the user explicitly asks to exclude something)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_name": {"type": "string"},
                "region_lookup_key": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["destination_name", "reason"],
        },
    },
    {
        "name": "get_trip_state",
        "description": (
            "Get the current shortlisted and excluded destinations for this trip."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def handle_search_destinations(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    month = params["month"]
    results = vacationmap.search_destinations(
        db=vm_db,
        month=month,
        activity_focus=params.get("activity_focus", "general"),
        max_flight_hours=params.get("max_flight_hours"),
        min_safety_score=params.get("min_safety_score", 6.0),
        exclude_visited_never=params.get("exclude_visited_never", True),
        limit=params.get("limit", 10),
    )

    m = month.lower()
    formatted = []
    for r in results:
        entry = {
            "destination": f"{r['region_name']}, {r['country_name']}",
            "lookup_key": r["lookup_key"],
            "total_score": r["total_score"],
            "weather_score": round(r["weather_score"], 1),
            "temp_day": r.get(f"temp_{m}"),
            "rain_days": r.get(f"rain_{m}"),
            "cost_relative": r.get(f"cost_relative_{m}"),
            "busyness_relative": r.get(f"busyness_relative_{m}"),
            "attractiveness": r.get(f"attractiveness_relative_{m}"),
            "golf_score": r.get("golf_score"),
            "safety": r.get("crime_safety"),
            "nature_score": r.get("nature_score"),
            "hiking_score": r.get("hiking_score"),
            "flight_hours": r.get("flight_time_hours"),
            "flight_transfers": r.get("flight_transfers"),
            "tips": r.get(f"tips_{m}"),
        }
        formatted.append(entry)

    return json.dumps(formatted, indent=2)


def handle_get_destination_details(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    details = vacationmap.get_destination_details(
        vm_db, params["region_lookup_key"], params["month"]
    )
    if details is None:
        return json.dumps(
            {
                "error": (
                    f"Destination '{params['region_lookup_key']}' not found in VacationMap database"
                )
            }
        )

    m = params["month"].lower()
    result = {
        "destination": f"{details['region_name']}, {details['country_name']}",
        "lookup_key": details["lookup_key"],
        "total_score": details["total_score"],
        "weather_score": round(details["weather_score"], 1),
        "temp_day": details.get(f"temp_{m}"),
        "temp_night": details.get(f"temp_night_{m}"),
        "rain_days": details.get(f"rain_{m}"),
        "cost_relative": details.get(f"cost_relative_{m}"),
        "cost_absolute": details.get(f"cost_absolute_{m}"),
        "busyness_relative": details.get(f"busyness_relative_{m}"),
        "busyness_absolute": details.get(f"busyness_absolute_{m}"),
        "attractiveness": details.get(f"attractiveness_relative_{m}"),
        "golf_score": details.get("golf_score"),
        "nature_score": details.get("nature_score"),
        "hiking_score": details.get("hiking_score"),
        "safety": details.get("crime_safety"),
        "city_access": details.get("city_access"),
        "hotel_quality": details.get("hotel_quality"),
        "tourism_level": details.get("tourism_level"),
        "flight_hours": details.get("flight_time_hours"),
        "flight_transfers": details.get("flight_transfers"),
        "tips": details.get(f"tips_{m}"),
        "visit": details.get("visit"),
    }
    return json.dumps(result, indent=2)


def handle_get_visit_history(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    visits = vacationmap.get_visit_history(vm_db)
    formatted = []
    for v in visits:
        formatted.append(
            {
                "destination": f"{v['region_name']}, {v['country_name']}",
                "lookup_key": f"{v['country_code']}:{v['region_name']}",
                "rating": v.get("rating"),
                "rating_summary": v.get("rating_summary"),
                "visit_again": v.get("visit_again"),
                "visited_month": v.get("visited_month"),
                "visited_year": v.get("visited_year"),
                "summary": v.get("summary"),
            }
        )
    return json.dumps(formatted, indent=2)


def handle_suggest_for_review(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    dest = crud.add_suggested(
        db=trips_db,
        trip_id=trip_id,
        destination_name=params["destination_name"],
        ai_reasoning=params["ai_reasoning"],
        region_lookup_key=params.get("region_lookup_key"),
        scores_snapshot=params.get("scores_snapshot"),
        pre_filled_exclude_reason=params.get("pre_filled_exclude_reason"),
    )
    return json.dumps(
        {
            "status": "suggested_for_review",
            "destination": dest.destination_name,
            "id": dest.id,
        }
    )


def handle_shortlist_destination(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    dest = crud.add_shortlisted(
        db=trips_db,
        trip_id=trip_id,
        destination_name=params["destination_name"],
        ai_reasoning=params["ai_reasoning"],
        region_lookup_key=params.get("region_lookup_key"),
        scores_snapshot=params.get("scores_snapshot"),
        user_note=params.get("user_note"),
    )
    return json.dumps(
        {
            "status": "added",
            "destination": dest.destination_name,
            "id": dest.id,
        }
    )


def handle_exclude_destination(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    dest = crud.add_excluded(
        db=trips_db,
        trip_id=trip_id,
        destination_name=params["destination_name"],
        reason=params["reason"],
        region_lookup_key=params.get("region_lookup_key"),
    )
    return json.dumps(
        {
            "status": "excluded",
            "destination": dest.destination_name,
            "reason": dest.reason,
        }
    )


def handle_get_trip_state(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    trip = crud.get_trip(trips_db, trip_id)
    if trip is None:
        return json.dumps({"error": "Trip not found"})

    shortlisted = []
    for s in trip.shortlisted:
        scores = json.loads(s.scores_snapshot) if s.scores_snapshot else None
        shortlisted.append(
            {
                "destination": s.destination_name,
                "lookup_key": s.region_lookup_key,
                "scores": scores,
                "user_note": s.user_note,
            }
        )

    excluded = [
        {"destination": e.destination_name, "reason": e.reason} for e in trip.excluded
    ]

    suggested = []
    for s in trip.suggested:
        scores = json.loads(s.scores_snapshot) if s.scores_snapshot else None
        suggested.append(
            {
                "destination": s.destination_name,
                "lookup_key": s.region_lookup_key,
                "scores": scores,
            }
        )

    return json.dumps(
        {
            "pending_review": suggested,
            "shortlisted": shortlisted,
            "excluded": excluded,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    "search_destinations": handle_search_destinations,
    "get_destination_details": handle_get_destination_details,
    "get_visit_history": handle_get_visit_history,
    "suggest_for_review": handle_suggest_for_review,
    "shortlist_destination": handle_shortlist_destination,
    "exclude_destination": handle_exclude_destination,
    "get_trip_state": handle_get_trip_state,
}


def execute_tool(
    tool_name: str,
    tool_input: dict,
    trips_db: Session,
    vm_db: Session,
    trip_id: int,
) -> str:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return handler(tool_input, trips_db, vm_db, trip_id)
