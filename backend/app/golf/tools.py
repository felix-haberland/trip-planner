"""Claude tools for the golf library (spec 006).

These register into the shared TOOL_DEFINITIONS / TOOL_HANDLERS via
`GOLF_TOOL_DEFINITIONS` + `GOLF_TOOL_HANDLERS`, which `app.trips.chat`
merges with the trip-planning tools.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from . import crud, models

GOLF_TOOL_DEFINITIONS = [
    {
        "name": "search_golf_resorts",
        "description": (
            "Search the user's curated golf-resorts library. Returns resort records with "
            "hero image, hotel type, price, best months, rank, and course count. Use this "
            "when the user's trip is golf-heavy (activity_weights.golf >= 30) or when they "
            "ask about a specific named resort via `name_query`. Library entries are "
            "authoritative — cite them as 'from your library'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name_query": {
                    "type": "string",
                    "description": (
                        "Fuzzy substring match against a normalized resort name. Use this "
                        "when the user asks about a specific named resort "
                        "(e.g. 'what about Monte Rei?'). Omit for broad searches."
                    ),
                },
                "country": {
                    "type": "string",
                    "description": (
                        "ISO 3166-1 alpha-2 country code, e.g. 'PT', 'ES', 'GB'"
                    ),
                },
                "price_category": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "\u20ac",
                            "\u20ac\u20ac",
                            "\u20ac\u20ac\u20ac",
                            "\u20ac\u20ac\u20ac\u20ac",
                        ],
                    },
                },
                "hotel_type": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["luxury", "boutique", "golf_hotel", "none"],
                    },
                },
                "month": {"type": "integer", "minimum": 1, "maximum": 12},
                "tags": {"type": "array", "items": {"type": "string"}},
                "min_rank": {"type": "integer", "minimum": 0, "maximum": 100},
                "limit": {"type": "integer", "description": "Default 10"},
            },
        },
    },
    {
        "name": "search_golf_courses",
        "description": (
            "Search the user's curated golf-courses library. Returns course records "
            "(resort-attached or standalone) with par, length, architect, difficulty, "
            "green fee, and rank. Use this when the user's prompt is course-centric "
            "('best courses at X', 'top links courses', etc.) or when they ask about a "
            "specific named course via `name_query`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name_query": {
                    "type": "string",
                    "description": (
                        "Fuzzy substring match against a normalized course name."
                    ),
                },
                "country": {"type": "string"},
                "course_type": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "links",
                            "parkland",
                            "heathland",
                            "desert",
                            "coastal",
                            "mountain",
                            "other",
                        ],
                    },
                },
                "min_difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
                "max_difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
                "min_holes": {"type": "integer", "enum": [9, 18, 27, 36]},
                "parent_resort": {
                    "type": "string",
                    "enum": ["any", "has_resort", "standalone"],
                    "description": "Default 'any'",
                },
                "max_green_fee_eur": {"type": "integer"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "min_rank": {"type": "integer", "minimum": 0, "maximum": 100},
                "limit": {"type": "integer", "description": "Default 10"},
            },
        },
    },
]


def annotate_with_curated_library(entries: list[dict], trips_db: Session) -> None:
    """Mutate each entry in `entries` to add curated_resort_count / resort_names
    and curated_course_count / course_names when the region has library content."""

    if not entries:
        return
    for entry in entries:
        key = entry.get("lookup_key")
        if not key:
            continue
        resorts = (
            trips_db.query(models.GolfResort.id, models.GolfResort.name)
            .filter(models.GolfResort.vacationmap_region_key == key)
            .all()
        )
        if resorts:
            entry["curated_resort_count"] = len(resorts)
            entry["resort_names"] = [r.name for r in resorts[:3]]
        # Courses linked directly to this region OR via their parent resort.
        resort_ids = [r.id for r in resorts]
        course_query = trips_db.query(
            models.GolfCourse.id, models.GolfCourse.name
        ).filter(
            (models.GolfCourse.vacationmap_region_key == key)
            | (models.GolfCourse.resort_id.in_(resort_ids) if resort_ids else False)
        )
        courses = course_query.all()
        if courses:
            entry["curated_course_count"] = len(courses)
            entry["course_names"] = [c.name for c in courses[:3]]


def handle_search_golf_resorts(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    """FR-015 + FR-015b — curated resorts with fuzzy name lookup."""

    total, items = crud.list_resorts(
        trips_db,
        country=params.get("country"),
        price_category=params.get("price_category"),
        hotel_type=params.get("hotel_type"),
        month=params.get("month"),
        tags=params.get("tags"),
        q=params.get("name_query"),
        sort="rank_rating",
        sort_dir="desc",
        limit=params.get("limit", 10),
        offset=0,
    )
    # Apply min_rank filter post-query (crud.list_resorts doesn't take it)
    min_rank = params.get("min_rank")
    if min_rank is not None:
        items = [i for i in items if (i.rank_rating or 0) >= min_rank]

    # library_size signals "empty library" vs "populated but no match" (research R8)
    library_size = trips_db.query(models.GolfResort).count()

    out = {
        "library_size": library_size,
        "total_matches": len(items),
        "results": [i.model_dump() for i in items],
    }
    return json.dumps(out, indent=2, default=str)


def handle_search_golf_courses(
    params: dict, trips_db: Session, vm_db: Session, trip_id: int
) -> str:
    """FR-015a + FR-015b — curated courses with fuzzy name lookup."""

    total, items = crud.list_courses(
        trips_db,
        country=params.get("country"),
        course_type=params.get("course_type"),
        min_difficulty=params.get("min_difficulty"),
        max_difficulty=params.get("max_difficulty"),
        min_holes=params.get("min_holes"),
        parent_resort=params.get("parent_resort", "any"),
        max_green_fee_eur=params.get("max_green_fee_eur"),
        tags=params.get("tags"),
        q=params.get("name_query"),
        sort="rank_rating",
        sort_dir="desc",
        limit=params.get("limit", 10),
        offset=0,
    )
    min_rank = params.get("min_rank")
    if min_rank is not None:
        items = [i for i in items if (i.rank_rating or 0) >= min_rank]

    library_size = trips_db.query(models.GolfCourse).count()

    out = {
        "library_size": library_size,
        "total_matches": len(items),
        "results": [i.model_dump() for i in items],
    }
    return json.dumps(out, indent=2, default=str)


GOLF_TOOL_HANDLERS = {
    "search_golf_resorts": handle_search_golf_resorts,
    "search_golf_courses": handle_search_golf_courses,
}


def execute_tool(
    tool_name: str, tool_input: dict, trips_db, vm_db, trip_id: int
) -> str:
    """Dispatch a golf tool call by name. Intended for tests and for callers
    who want to exercise a single golf tool outside the shared registry."""
    handler = GOLF_TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown golf tool: {tool_name}"})
    return handler(tool_input, trips_db, vm_db, trip_id)
