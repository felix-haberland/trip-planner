"""Golf library subsystem (spec 006).

Self-contained module for the curated golf resorts + courses library:
    - models.py    — SQLAlchemy tables (in trips.db, bound to TripsBase)
    - schemas.py   — Pydantic request/response types
    - crud.py      — DB operations (create/read/update/delete/link) + dedup + region auto-match
    - extraction.py — Claude-powered extraction from URL or name
    - fetcher.py   — SSRF-guarded HTTP fetcher (used by extraction + image validation)
    - tools.py     — Claude tool definitions + handlers (search_golf_resorts, search_golf_courses, library annotations)
    - routes.py    — FastAPI APIRouter with all /api/golf-library/* endpoints

The trip-planning code under `app/` (main, crud, models, schemas, chat, tools)
does not depend on any golf internals except via the integration points:
    - `app.golf.routes.router` is mounted by `app.main`
    - `app.golf.tools` registers its tools into the shared `TOOL_DEFINITIONS` +
      `TOOL_HANDLERS` dicts used by `app.chat`
    - `app.tools.handle_search_destinations` calls
      `app.golf.tools.annotate_with_curated_library` to annotate regions

Everything else stays inside this package.
"""
