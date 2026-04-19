"""FastAPI application entry point.

Just the app object + router mounting + static file serving. All business
logic and routes live in the per-domain packages:
    - app/trips/routes.py → /api/trips/*, /api/vacationmap/*, conversations, messages
    - app/golf/routes.py  → /api/golf-library/*
"""

import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import init_golf_db, init_trips_db
from .trips.routes import router as trips_router
from .golf.routes import router as golf_router
from .yearly.routes import router as yearly_router

# Unhandled-exception log: append-only, human-readable. Ask "check latest error"
# to have Claude tail this file.
_ERROR_LOG_PATH = Path(__file__).resolve().parent.parent / "errors.log"
_error_logger = logging.getLogger("vacationplanner.errors")
if not _error_logger.handlers:
    _handler = logging.FileHandler(_ERROR_LOG_PATH)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _error_logger.addHandler(_handler)
    _error_logger.setLevel(logging.ERROR)
    _error_logger.propagate = False

app = FastAPI(title="Trip Planner Chatbot")


@app.exception_handler(Exception)
async def _log_unhandled_exception(request: Request, exc: Exception):
    _error_logger.error(
        "%s %s\n%s",
        request.method,
        request.url.path,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_type": type(exc).__name__},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_trips_db()
    init_golf_db()


app.include_router(trips_router)
app.include_router(golf_router)
app.include_router(yearly_router)


# ---------------------------------------------------------------------------
# Static frontend serving
# ---------------------------------------------------------------------------

_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(_frontend_dir / "index.html"))
