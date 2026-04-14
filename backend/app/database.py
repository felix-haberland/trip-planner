import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# === Trips database (read-write, own data) ===
TRIPS_DB_PATH = os.environ.get("TRIPS_DB_PATH", "./trips.db")
trips_engine = create_engine(
    f"sqlite:///{TRIPS_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TripsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=trips_engine)
TripsBase = declarative_base()

# === VacationMap database (read-only) ===
VACATIONMAP_DB_PATH = os.environ.get(
    "VACATIONMAP_DB_PATH",
    os.path.expanduser("~/Documents/VacationMap/backend/vacation.db"),
)
vacationmap_engine = create_engine(
    f"sqlite:///{VACATIONMAP_DB_PATH}",
    connect_args={"check_same_thread": False},
)


VacationMapSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=vacationmap_engine
)


def init_trips_db():
    """Create trips.db tables if they don't exist."""
    from . import models  # noqa: F401 — registers models with TripsBase

    TripsBase.metadata.create_all(bind=trips_engine)


def get_trips_db():
    """Dependency: yields a trips database session."""
    db = TripsSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_vacationmap_db():
    """Dependency: yields a read-only VacationMap database session."""
    db = VacationMapSessionLocal()
    try:
        yield db
    finally:
        db.close()
