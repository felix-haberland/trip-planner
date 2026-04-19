from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# --- Trip ---


class TripCreate(BaseModel):
    name: str
    description: str


class TripUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # "active" or "archived"
    # Spec 006 FR-017a
    activity_weights: Optional[dict] = None


class TripSummary(BaseModel):
    id: int
    name: str
    description: str
    target_month: Optional[str] = None
    status: str
    suggested_count: int
    shortlisted_count: int
    excluded_count: int
    created_at: datetime
    updated_at: datetime
    activity_weights: Optional[dict] = None

    class Config:
        from_attributes = True


class SuggestedDestinationResponse(BaseModel):
    id: int
    destination_name: str
    region_lookup_key: Optional[str] = None
    ai_reasoning: str
    scores_snapshot: Optional[dict] = None
    user_note: Optional[str] = None
    pre_filled_exclude_reason: Optional[str] = None
    suggested_at: datetime
    # Spec 006 FR-019
    resort_id: Optional[int] = None
    course_id: Optional[int] = None

    class Config:
        from_attributes = True


class ShortlistedDestinationResponse(BaseModel):
    id: int
    destination_name: str
    region_lookup_key: Optional[str] = None
    ai_reasoning: str
    scores_snapshot: Optional[dict] = None
    user_note: Optional[str] = None
    added_at: datetime
    resort_id: Optional[int] = None
    course_id: Optional[int] = None

    class Config:
        from_attributes = True


class ExcludedDestinationResponse(BaseModel):
    id: int
    destination_name: str
    region_lookup_key: Optional[str] = None
    reason: str
    user_note: Optional[str] = None
    excluded_at: datetime
    resort_id: Optional[int] = None
    course_id: Optional[int] = None

    class Config:
        from_attributes = True


# --- Conversations ---


class ConversationCreate(BaseModel):
    name: str = "New conversation"


class ConversationSummary(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime
    message_count: int

    class Config:
        from_attributes = True


# --- Trip aggregates ---


class TripDetail(BaseModel):
    id: int
    name: str
    description: str
    target_month: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    conversations: list[ConversationSummary]
    suggested: list[SuggestedDestinationResponse]
    shortlisted: list[ShortlistedDestinationResponse]
    excluded: list[ExcludedDestinationResponse]

    class Config:
        from_attributes = True


# --- Messages ---


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    trip_state_changed: bool
