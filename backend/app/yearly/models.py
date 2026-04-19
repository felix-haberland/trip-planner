"""SQLAlchemy models for the yearly planner (F009 redesign).

Hierarchy — YearPlan → YearOption → Slot:

  * **YearPlan**: one per calendar year *context* (e.g. "My 2027",
    "Wild 2027 experiment"). Multiple YearPlans can coexist for the same
    `year` — they represent genuinely different starting contexts. Owns
    user-level intent, activity targets, and the list of open **windows**
    (calendar availability) shared across its sibling Options.
  * **YearOption**: a candidate arrangement of that year under one YearPlan
    ("Adventurous mix", "Golf-heavy"). Many per YearPlan. The AI generates
    them; the user compares, forks, and picks.
  * **Slot**: a single trip intent inside one YearOption (theme + timing +
    activity mix). A slot can optionally point at a window of the parent
    YearPlan (`window_index`) and, once the user is ready to pick a
    destination, at a concrete `trip_plans` row (`trip_plan_id`).

Conversations live on the YearPlan (advisor chat); owner_type='year_plan'.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from ..database import TripsBase


def _utcnow():
    return datetime.now(timezone.utc)


class YearPlan(TripsBase):
    __tablename__ = "year_plans"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    intent = Column(Text, nullable=False, default="")
    activity_weights = Column(Text, nullable=False, default="{}")
    # Open windows (JSON list of `{label?, start_date, end_date,
    # duration_hint?, constraints?}`). Soft anchors — Options may propose
    # shifted exact dates per slot.
    windows = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="draft")  # 'draft' | 'archived'
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    options = relationship(
        "YearOption",
        back_populates="year_plan",
        cascade="all, delete-orphan",
        order_by="YearOption.position, YearOption.created_at",
    )


class YearOption(TripsBase):
    """A candidate arrangement of a year under one YearPlan.

    Multiple options coexist so the user can compare and fork. Status:
    'draft' (user or AI, still being iterated), 'chosen' (the user's pick —
    informational; sibling options are kept as reference), 'archived'
    (parked).
    """

    __tablename__ = "year_options"

    id = Column(Integer, primary_key=True, index=True)
    year_plan_id = Column(
        Integer,
        ForeignKey("year_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String, nullable=False)
    summary = Column(Text, nullable=False, default="")
    # 'ai' when created by generate_year_option; 'user' for manual creates
    # or forks.
    created_by = Column(String, nullable=False, default="user")
    status = Column(
        String, nullable=False, default="draft"
    )  # 'draft' | 'chosen' | 'archived'
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_year_options_plan", "year_plan_id"),)

    year_plan = relationship("YearPlan", back_populates="options")
    slots = relationship(
        "Slot",
        back_populates="year_option",
        cascade="all, delete-orphan",
        order_by="Slot.start_year, Slot.start_month, Slot.position",
    )


class Slot(TripsBase):
    """A single trip intent inside one YearOption.

    `window_index` (optional) points into the parent YearPlan's `windows`
    list — a display/reasoning hint ("this is the June trip"). It is not a
    DB-level FK; windows are JSON-encoded on the YearPlan.

    `trip_plan_id` bridges to destination discovery — populated once the
    user clicks "Find destination" (see `yearly.crud.start_trip_for_slot`).
    """

    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, index=True)
    year_option_id = Column(
        Integer,
        ForeignKey("year_options.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Each trip idea sits in exactly one window of the parent YearPlan.
    # Multiple ideas per (option, window) are allowed — alternatives the user
    # is sketching inside a single option. Options can also leave windows empty.
    window_index = Column(Integer, nullable=False)
    label = Column(String, nullable=True)
    theme = Column(Text, nullable=False, default="")
    start_year = Column(Integer, nullable=False)
    start_month = Column(Integer, nullable=False)
    end_year = Column(Integer, nullable=False)
    end_month = Column(Integer, nullable=False)
    exact_start_date = Column(Date, nullable=True)
    exact_end_date = Column(Date, nullable=True)
    duration_days = Column(Integer, nullable=True)
    climate_hint = Column(String, nullable=True)
    constraints_note = Column(Text, nullable=True)
    activity_weights = Column(Text, nullable=False, default="{}")
    status = Column(
        String, nullable=False, default="open"
    )  # 'open' | 'proposed' | 'archived'
    position = Column(Integer, nullable=False, default=0)
    trip_plan_id = Column(
        Integer,
        ForeignKey("trip_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("start_month BETWEEN 1 AND 12", name="ck_slot_start_month"),
        CheckConstraint("end_month BETWEEN 1 AND 12", name="ck_slot_end_month"),
        Index(
            "ix_slots_year_option_window",
            "year_option_id",
            "window_index",
        ),
    )

    year_option = relationship("YearOption", back_populates="slots")
