from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from .database import TripsBase


def _utcnow():
    return datetime.now(timezone.utc)


class TripPlan(TripsBase):
    __tablename__ = "trip_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    target_month = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
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
    conversations = relationship(
        "Conversation",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="Conversation.created_at",
    )


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

    trip = relationship("TripPlan", back_populates="excluded")


class Conversation(TripsBase):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(
        Integer, ForeignKey("trip_plans.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False, default="Main")
    status = Column(String, nullable=False, default="active")  # "active" or "archived"
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    trip = relationship("TripPlan", back_populates="conversations")
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
