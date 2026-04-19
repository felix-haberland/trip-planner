"""Shared pytest fixtures.

Each test that requests `trips_session` gets a throwaway SQLite DB under
`$TMPDIR`; migrations run via `init_trips_db()`. No real `trips.db` is
touched.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest


def _purge_app_modules() -> None:
    """Drop cached `app.*` modules so the next import picks up a new
    `TRIPS_DB_PATH` from the environment."""
    for mod_name in list(sys.modules):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]


@pytest.fixture()
def trips_session(monkeypatch):
    """Yield a SQLAlchemy session bound to a throwaway trips DB.

    The bundled seed loader is disabled in tests so each test starts with a
    truly empty DB — otherwise cascade/delete tests would see 48 curated
    resorts + 10 trips from the seed snapshot.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    monkeypatch.setenv("TRIPS_DB_PATH", tmp.name)
    monkeypatch.setenv("DISABLE_TRIPS_SEED", "1")

    _purge_app_modules()

    from app import database as db_module  # noqa: E402
    from app.trips import models  # noqa: F401,E402 — registers with TripsBase
    from app.golf import models as _golf_models  # noqa: F401,E402
    from app.yearly import models as _yearly_models  # noqa: F401,E402

    db_module.init_trips_db()
    session = db_module.TripsSessionLocal()
    try:
        yield session
    finally:
        session.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        _purge_app_modules()
