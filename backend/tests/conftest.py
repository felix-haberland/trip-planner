"""Shared pytest fixtures.

Each fixture spins up a throwaway SQLite DB under `$TMPDIR`; no real
`trips.db` / `golf.db` is touched. The two engines are independent so
tests that need both request both fixtures.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest


def _purge_app_modules() -> None:
    """Drop cached `app.*` modules so the next import picks up new
    TRIPS_DB_PATH / GOLF_DB_PATH from the environment."""
    for mod_name in list(sys.modules):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]


@pytest.fixture()
def trips_session(monkeypatch):
    """Yield a SQLAlchemy session bound to a throwaway trips DB.

    The bundled seed loader is disabled in tests so each test starts with a
    truly empty DB — otherwise cascade/delete tests would see 10 trips and
    3 year-plans from the seed snapshot.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    monkeypatch.setenv("TRIPS_DB_PATH", tmp.name)
    monkeypatch.setenv("DISABLE_TRIPS_SEED", "1")
    # Point the golf engine at a throwaway location too; not all tests use
    # it, but any module-level `from app.database import ...` picks up the
    # path at import time.
    golf_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    golf_tmp.close()
    monkeypatch.setenv("GOLF_DB_PATH", golf_tmp.name)

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
        for p in (tmp.name, golf_tmp.name):
            try:
                os.unlink(p)
            except OSError:
                pass
        _purge_app_modules()


@pytest.fixture()
def golf_session(monkeypatch):
    """Yield a SQLAlchemy session bound to a throwaway golf DB.

    Separate from `trips_session` because golf lives in its own SQLite
    engine. Tests that need both can request both fixtures.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    monkeypatch.setenv("GOLF_DB_PATH", tmp.name)

    _purge_app_modules()

    from app import database as db_module  # noqa: E402
    from app.golf import models as _golf_models  # noqa: F401,E402

    db_module.init_golf_db()
    session = db_module.GolfSessionLocal()
    try:
        yield session
    finally:
        session.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        _purge_app_modules()
