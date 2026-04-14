"""CRUD operations for the trips database."""

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from . import models, schemas


def _utcnow():
    return datetime.now(timezone.utc)


# --- Trip Plans ---


def create_trip(db: Session, trip: schemas.TripCreate) -> models.TripPlan:
    db_trip = models.TripPlan(name=trip.name, description=trip.description)
    db.add(db_trip)
    db.commit()
    db.refresh(db_trip)
    return db_trip


def list_trips(db: Session) -> list[models.TripPlan]:
    return db.query(models.TripPlan).order_by(models.TripPlan.updated_at.desc()).all()


def get_trip(db: Session, trip_id: int) -> Optional[models.TripPlan]:
    return db.query(models.TripPlan).filter(models.TripPlan.id == trip_id).first()


def update_trip(
    db: Session, trip_id: int, update: schemas.TripUpdate
) -> Optional[models.TripPlan]:
    trip = get_trip(db, trip_id)
    if trip is None:
        return None
    if update.name is not None:
        trip.name = update.name
    if update.description is not None:
        trip.description = update.description
    if update.status is not None:
        trip.status = update.status
    trip.updated_at = _utcnow()
    db.commit()
    db.refresh(trip)
    return trip


def delete_trip(db: Session, trip_id: int) -> bool:
    trip = get_trip(db, trip_id)
    if trip is None:
        return False
    db.delete(trip)
    db.commit()
    return True


def set_target_month(
    db: Session, trip_id: int, month: str
) -> Optional[models.TripPlan]:
    trip = get_trip(db, trip_id)
    if trip is None:
        return None
    trip.target_month = month
    trip.updated_at = _utcnow()
    db.commit()
    db.refresh(trip)
    return trip


# --- Suggested Destinations ---


def add_suggested(
    db: Session,
    trip_id: int,
    destination_name: str,
    ai_reasoning: str,
    region_lookup_key: Optional[str] = None,
    scores_snapshot: Optional[dict] = None,
    pre_filled_exclude_reason: Optional[str] = None,
) -> models.SuggestedDestination:
    dest = models.SuggestedDestination(
        trip_id=trip_id,
        destination_name=destination_name,
        region_lookup_key=region_lookup_key,
        ai_reasoning=ai_reasoning,
        scores_snapshot=json.dumps(scores_snapshot) if scores_snapshot else None,
        pre_filled_exclude_reason=pre_filled_exclude_reason,
    )
    db.add(dest)
    trip = get_trip(db, trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


def get_suggested(
    db: Session, suggested_id: int
) -> Optional[models.SuggestedDestination]:
    return (
        db.query(models.SuggestedDestination)
        .filter(models.SuggestedDestination.id == suggested_id)
        .first()
    )


def move_suggested_to_shortlist(
    db: Session, suggested_id: int, user_note: Optional[str] = None
) -> Optional[models.ShortlistedDestination]:
    """Move a suggested destination to the shortlist."""
    sug = get_suggested(db, suggested_id)
    if sug is None:
        return None
    dest = models.ShortlistedDestination(
        trip_id=sug.trip_id,
        destination_name=sug.destination_name,
        region_lookup_key=sug.region_lookup_key,
        ai_reasoning=sug.ai_reasoning,
        scores_snapshot=sug.scores_snapshot,
        user_note=user_note,
    )
    db.add(dest)
    db.delete(sug)
    trip = get_trip(db, sug.trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


def move_suggested_to_excluded(
    db: Session, suggested_id: int, reason: str
) -> Optional[models.ExcludedDestination]:
    """Move a suggested destination to the excluded list."""
    sug = get_suggested(db, suggested_id)
    if sug is None:
        return None
    dest = models.ExcludedDestination(
        trip_id=sug.trip_id,
        destination_name=sug.destination_name,
        region_lookup_key=sug.region_lookup_key,
        reason=reason,
        ai_reasoning=sug.ai_reasoning,
    )
    db.add(dest)
    db.delete(sug)
    trip = get_trip(db, sug.trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


# --- Shortlisted Destinations ---


def add_shortlisted(
    db: Session,
    trip_id: int,
    destination_name: str,
    ai_reasoning: str,
    region_lookup_key: Optional[str] = None,
    scores_snapshot: Optional[dict] = None,
    user_note: Optional[str] = None,
) -> models.ShortlistedDestination:
    dest = models.ShortlistedDestination(
        trip_id=trip_id,
        destination_name=destination_name,
        region_lookup_key=region_lookup_key,
        ai_reasoning=ai_reasoning,
        scores_snapshot=json.dumps(scores_snapshot) if scores_snapshot else None,
        user_note=user_note,
    )
    db.add(dest)
    # Touch trip updated_at
    trip = get_trip(db, trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


# --- Excluded Destinations ---


def add_excluded(
    db: Session,
    trip_id: int,
    destination_name: str,
    reason: str,
    region_lookup_key: Optional[str] = None,
    ai_reasoning: Optional[str] = None,
) -> models.ExcludedDestination:
    dest = models.ExcludedDestination(
        trip_id=trip_id,
        destination_name=destination_name,
        region_lookup_key=region_lookup_key,
        reason=reason,
        ai_reasoning=ai_reasoning,
    )
    db.add(dest)
    trip = get_trip(db, trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


def get_shortlisted(
    db: Session, shortlisted_id: int
) -> Optional[models.ShortlistedDestination]:
    return (
        db.query(models.ShortlistedDestination)
        .filter(models.ShortlistedDestination.id == shortlisted_id)
        .first()
    )


def move_shortlisted_to_excluded(
    db: Session, shortlisted_id: int, reason: str
) -> Optional[models.ExcludedDestination]:
    sl = get_shortlisted(db, shortlisted_id)
    if sl is None:
        return None
    dest = models.ExcludedDestination(
        trip_id=sl.trip_id,
        destination_name=sl.destination_name,
        region_lookup_key=sl.region_lookup_key,
        reason=reason,
        ai_reasoning=sl.ai_reasoning,
    )
    db.add(dest)
    db.delete(sl)
    trip = get_trip(db, sl.trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


def move_shortlisted_to_suggested(
    db: Session, shortlisted_id: int
) -> Optional[models.SuggestedDestination]:
    sl = get_shortlisted(db, shortlisted_id)
    if sl is None:
        return None
    dest = models.SuggestedDestination(
        trip_id=sl.trip_id,
        destination_name=sl.destination_name,
        region_lookup_key=sl.region_lookup_key,
        ai_reasoning=sl.ai_reasoning,
        scores_snapshot=sl.scores_snapshot,
        user_note=sl.user_note,
    )
    db.add(dest)
    db.delete(sl)
    trip = get_trip(db, sl.trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


def get_excluded(db: Session, excluded_id: int) -> Optional[models.ExcludedDestination]:
    return (
        db.query(models.ExcludedDestination)
        .filter(models.ExcludedDestination.id == excluded_id)
        .first()
    )


def move_excluded_to_shortlist(
    db: Session, excluded_id: int, user_note: Optional[str] = None
) -> Optional[models.ShortlistedDestination]:
    """Reconsider an excluded destination — move it to the shortlist."""
    exc = get_excluded(db, excluded_id)
    if exc is None:
        return None
    dest = models.ShortlistedDestination(
        trip_id=exc.trip_id,
        destination_name=exc.destination_name,
        region_lookup_key=exc.region_lookup_key,
        ai_reasoning=exc.ai_reasoning or "",
        scores_snapshot=None,
        user_note=user_note,
    )
    db.add(dest)
    db.delete(exc)
    trip = get_trip(db, exc.trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(dest)
    return dest


def delete_message(db: Session, message_id: int) -> bool:
    msg = (
        db.query(models.ConversationMessage)
        .filter(models.ConversationMessage.id == message_id)
        .first()
    )
    if msg is None:
        return False
    db.delete(msg)
    db.commit()
    return True


def update_message(
    db: Session, message_id: int, content: str
) -> Optional[models.ConversationMessage]:
    msg = (
        db.query(models.ConversationMessage)
        .filter(models.ConversationMessage.id == message_id)
        .first()
    )
    if msg is None:
        return None
    msg.content = content
    db.commit()
    db.refresh(msg)
    return msg


# --- Conversations ---


def create_conversation(
    db: Session, trip_id: int, name: str = "Main"
) -> models.Conversation:
    conv = models.Conversation(trip_id=trip_id, name=name)
    db.add(conv)
    trip = get_trip(db, trip_id)
    if trip:
        trip.updated_at = _utcnow()
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(
    db: Session, conversation_id: int
) -> Optional[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.id == conversation_id)
        .first()
    )


def list_conversations(db: Session, trip_id: int) -> list[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.trip_id == trip_id)
        .order_by(models.Conversation.created_at.asc())
        .all()
    )


def archive_conversation(
    db: Session, conversation_id: int
) -> Optional[models.Conversation]:
    conv = get_conversation(db, conversation_id)
    if conv is None:
        return None
    conv.status = "archived"
    db.commit()
    db.refresh(conv)
    return conv


def unarchive_conversation(
    db: Session, conversation_id: int
) -> Optional[models.Conversation]:
    conv = get_conversation(db, conversation_id)
    if conv is None:
        return None
    conv.status = "active"
    db.commit()
    db.refresh(conv)
    return conv


def delete_conversation(db: Session, conversation_id: int) -> bool:
    conv = get_conversation(db, conversation_id)
    if conv is None:
        return False
    db.delete(conv)
    db.commit()
    return True


def rename_conversation(
    db: Session, conversation_id: int, name: str
) -> Optional[models.Conversation]:
    conv = get_conversation(db, conversation_id)
    if conv is None:
        return None
    conv.name = name
    db.commit()
    db.refresh(conv)
    return conv


# --- Conversation Messages ---


def add_message(
    db: Session, conversation_id: int, role: str, content: str
) -> models.ConversationMessage:
    conv = get_conversation(db, conversation_id)
    msg = models.ConversationMessage(
        conversation_id=conversation_id,
        trip_id=conv.trip_id if conv else None,
        role=role,
        content=content,
    )
    db.add(msg)
    if conv:
        trip = get_trip(db, conv.trip_id)
        if trip:
            trip.updated_at = _utcnow()
    db.commit()
    db.refresh(msg)
    return msg


def list_messages(
    db: Session, conversation_id: int
) -> list[models.ConversationMessage]:
    return (
        db.query(models.ConversationMessage)
        .filter(models.ConversationMessage.conversation_id == conversation_id)
        .order_by(models.ConversationMessage.created_at.asc())
        .all()
    )


# --- Helpers for schemas ---


def trip_to_summary(trip: models.TripPlan) -> schemas.TripSummary:
    return schemas.TripSummary(
        id=trip.id,
        name=trip.name,
        description=trip.description,
        target_month=trip.target_month,
        status=trip.status,
        suggested_count=len(trip.suggested),
        shortlisted_count=len(trip.shortlisted),
        excluded_count=len(trip.excluded),
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


def trip_to_detail(trip: models.TripPlan) -> schemas.TripDetail:
    shortlisted = []
    for s in trip.shortlisted:
        scores = json.loads(s.scores_snapshot) if s.scores_snapshot else None
        shortlisted.append(
            schemas.ShortlistedDestinationResponse(
                id=s.id,
                destination_name=s.destination_name,
                region_lookup_key=s.region_lookup_key,
                ai_reasoning=s.ai_reasoning,
                scores_snapshot=scores,
                user_note=s.user_note,
                added_at=s.added_at,
            )
        )

    excluded = [
        schemas.ExcludedDestinationResponse(
            id=e.id,
            destination_name=e.destination_name,
            region_lookup_key=e.region_lookup_key,
            reason=e.reason,
            user_note=e.user_note,
            excluded_at=e.excluded_at,
        )
        for e in trip.excluded
    ]

    suggested = []
    for s in trip.suggested:
        scores = json.loads(s.scores_snapshot) if s.scores_snapshot else None
        suggested.append(
            schemas.SuggestedDestinationResponse(
                id=s.id,
                destination_name=s.destination_name,
                region_lookup_key=s.region_lookup_key,
                ai_reasoning=s.ai_reasoning,
                scores_snapshot=scores,
                user_note=s.user_note,
                pre_filled_exclude_reason=s.pre_filled_exclude_reason,
                suggested_at=s.suggested_at,
            )
        )

    convos = [
        schemas.ConversationSummary(
            id=c.id,
            name=c.name,
            status=c.status or "active",
            created_at=c.created_at,
            message_count=len(c.messages),
        )
        for c in trip.conversations
    ]

    return schemas.TripDetail(
        id=trip.id,
        name=trip.name,
        description=trip.description,
        target_month=trip.target_month,
        status=trip.status,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
        conversations=convos,
        suggested=suggested,
        shortlisted=shortlisted,
        excluded=excluded,
    )
