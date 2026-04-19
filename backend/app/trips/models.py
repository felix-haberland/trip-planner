from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from ..database import TripsBase


def _utcnow():
    return datetime.now(timezone.utc)


class TripPlan(TripsBase):
    __tablename__ = "trip_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    target_month = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    # Spec 006 FR-017a: JSON dict mapping activity tag -> integer 0..100.
    # Empty dict ('{}') preserves free-text-inference behavior for pre-006 trips.
    activity_weights = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    suggested = relationship(
        "SuggestedDestination",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    shortlisted = relationship(
        "ShortlistedDestination",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    excluded = relationship(
        "ExcludedDestination",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    # Conversations live in a polymorphic (owner_type, owner_id) shape since spec 007.
    # No ORM back-populates here: query via crud helpers that filter by
    # owner_type='trip', owner_id=trip.id. Cascade-on-delete is hand-rolled in
    # crud.delete_trip so it fires regardless of load path.


class SuggestedDestination(TripsBase):
    __tablename__ = "suggested_destinations"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(
        Integer, ForeignKey("trip_plans.id", ondelete="CASCADE"), nullable=False
    )
    region_lookup_key = Column(String, nullable=True)
    destination_name = Column(String, nullable=False)
    ai_reasoning = Column(Text, nullable=False)
    scores_snapshot = Column(Text, nullable=True)  # JSON string
    user_note = Column(String, nullable=True)
    pre_filled_exclude_reason = Column(String, nullable=True)
    suggested_at = Column(DateTime, nullable=False, default=_utcnow)
    # Spec 006 FR-018/FR-019: optional link to a specific library entity.
    # Mutually exclusive by convention (enforced in crud, not SQL).
    resort_id = Column(Integer, nullable=True)
    course_id = Column(Integer, nullable=True)

    trip = relationship("TripPlan", back_populates="suggested")


class ShortlistedDestination(TripsBase):
    __tablename__ = "shortlisted_destinations"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(
        Integer, ForeignKey("trip_plans.id", ondelete="CASCADE"), nullable=False
    )
    region_lookup_key = Column(String, nullable=True)
    destination_name = Column(String, nullable=False)
    ai_reasoning = Column(Text, nullable=False)
    scores_snapshot = Column(Text, nullable=True)  # JSON string
    user_note = Column(String, nullable=True)
    added_at = Column(DateTime, nullable=False, default=_utcnow)
    # Spec 006 FR-018/FR-019
    resort_id = Column(Integer, nullable=True)
    course_id = Column(Integer, nullable=True)

    trip = relationship("TripPlan", back_populates="shortlisted")


class ExcludedDestination(TripsBase):
    __tablename__ = "excluded_destinations"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(
        Integer, ForeignKey("trip_plans.id", ondelete="CASCADE"), nullable=False
    )
    region_lookup_key = Column(String, nullable=True)
    destination_name = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    ai_reasoning = Column(Text, nullable=True)
    user_note = Column(String, nullable=True)
    excluded_at = Column(DateTime, nullable=False, default=_utcnow)
    # Spec 006 FR-018/FR-019
    resort_id = Column(Integer, nullable=True)
    course_id = Column(Integer, nullable=True)

    trip = relationship("TripPlan", back_populates="excluded")


class Conversation(TripsBase):
    """Polymorphic conversation.

    Spec 007 replaces the hard trip_id FK with (owner_type, owner_id) so the
    same table serves trips, year plans, and (future) trip options. No FK
    constraint at the DB level — owners live in different tables; integrity is
    enforced in crud. Cascade-on-delete is hand-rolled in each owner's
    `delete_*` function.
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    owner_type = Column(String, nullable=False, index=True)
    owner_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False, default="Main")
    status = Column(String, nullable=False, default="active")  # "active" or "archived"
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(TripsBase):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True
    )
    # Keep trip_id for backwards compat with old data
    trip_id = Column(
        Integer, ForeignKey("trip_plans.id", ondelete="CASCADE"), nullable=True
    )
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    conversation = relationship("Conversation", back_populates="messages")
