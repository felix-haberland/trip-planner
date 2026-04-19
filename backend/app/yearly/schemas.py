"""Pydantic schemas for the yearly planner (F009).

Hierarchy: YearPlan (with `windows`) → YearOption → Slot.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

# --- Windows (JSON list on YearPlan) --------------------------------------


class WindowSpec(BaseModel):
    """One open calendar window on a YearPlan.

    Dates are soft anchors: Options may propose shifted exact dates per slot.
    """

    label: Optional[str] = None
    start_date: date
    end_date: date
    duration_hint: Optional[int] = Field(default=None, ge=1, le=365)
    constraints: Optional[str] = None


# --- Year Plan -------------------------------------------------------------


class YearPlanCreate(BaseModel):
    year: int = Field(..., ge=1900, le=2200)
    name: str
    intent: str = ""
    activity_weights: Optional[dict] = None
    windows: Optional[list[WindowSpec]] = None


class YearPlanUpdate(BaseModel):
    name: Optional[str] = None
    intent: Optional[str] = None
    activity_weights: Optional[dict] = None
    windows: Optional[list[WindowSpec]] = None
    status: Optional[str] = None  # 'draft' | 'archived'


class YearPlanSummary(BaseModel):
    id: int
    year: int
    name: str
    intent: str
    activity_weights: dict = {}
    windows: list[WindowSpec] = []
    status: str
    option_count: int
    linked_trip_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Year Option -----------------------------------------------------------


class YearOptionCreate(BaseModel):
    name: str
    summary: str = ""
    created_by: str = "user"  # 'ai' | 'user'
    status: Optional[str] = None  # default 'draft'


class YearOptionUpdate(BaseModel):
    name: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None  # 'draft' | 'chosen' | 'excluded' | 'archived'
    excluded_reason: Optional[str] = None
    position: Optional[int] = None


class ExcludeReasonBody(BaseModel):
    reason: str = Field(..., min_length=1)


# --- Slot (now child of YearOption) ---------------------------------------


class SlotCreate(BaseModel):
    """Create a trip idea inside one option, anchored to one window.

    Dates (start_year/month, end_year/month) are inherited from the parent
    YearPlan's `windows[window_index]` when omitted — so the usual payload is
    just `{window_index, label, theme, activity_weights?}`.
    """

    label: Optional[str] = None
    theme: str = ""
    window_index: int = Field(..., ge=0)
    start_year: Optional[int] = None
    start_month: Optional[int] = Field(default=None, ge=1, le=12)
    end_year: Optional[int] = None
    end_month: Optional[int] = Field(default=None, ge=1, le=12)
    exact_start_date: Optional[date] = None
    exact_end_date: Optional[date] = None
    duration_days: Optional[int] = Field(default=None, ge=1, le=365)
    climate_hint: Optional[str] = None
    constraints_note: Optional[str] = None
    activity_weights: Optional[dict] = None
    status: Optional[str] = None


class SlotUpdate(BaseModel):
    label: Optional[str] = None
    theme: Optional[str] = None
    window_index: Optional[int] = None
    start_year: Optional[int] = None
    start_month: Optional[int] = Field(default=None, ge=1, le=12)
    end_year: Optional[int] = None
    end_month: Optional[int] = Field(default=None, ge=1, le=12)
    exact_start_date: Optional[date] = None
    exact_end_date: Optional[date] = None
    duration_days: Optional[int] = Field(default=None, ge=1, le=365)
    climate_hint: Optional[str] = None
    constraints_note: Optional[str] = None
    activity_weights: Optional[dict] = None
    status: Optional[str] = None
    position: Optional[int] = None


class LinkedTripSummary(BaseModel):
    id: int
    name: str
    status: str
    target_month: Optional[str] = None
    shortlisted_count: int = 0


class SlotDetail(BaseModel):
    id: int
    year_option_id: int
    window_index: Optional[int] = None
    label: Optional[str] = None
    theme: str = ""
    start_year: int
    start_month: int
    end_year: int
    end_month: int
    exact_start_date: Optional[date] = None
    exact_end_date: Optional[date] = None
    duration_days: Optional[int] = None
    climate_hint: Optional[str] = None
    constraints_note: Optional[str] = None
    activity_weights: dict = {}
    status: str
    excluded_reason: Optional[str] = None
    position: int
    trip_plan_id: Optional[int] = None
    trip: Optional[LinkedTripSummary] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SlotLinkTripBody(BaseModel):
    trip_id: int


# --- Year Option aggregate ------------------------------------------------


class YearOptionDetail(BaseModel):
    id: int
    year_plan_id: int
    name: str
    summary: str = ""
    created_by: str
    status: str
    excluded_reason: Optional[str] = None
    position: int
    slots: list[SlotDetail] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class YearOptionSummary(BaseModel):
    id: int
    year_plan_id: int
    name: str
    summary: str
    created_by: str
    status: str
    excluded_reason: Optional[str] = None
    position: int
    slot_count: int
    linked_trip_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Year plan aggregate --------------------------------------------------


class YearPlanDetail(BaseModel):
    id: int
    year: int
    name: str
    intent: str
    activity_weights: dict = {}
    windows: list[WindowSpec] = []
    status: str
    options: list[YearOptionDetail] = []
    conversations: list = []
    attachable_trip_ids: list[int] = []
    created_at: datetime
    updated_at: datetime


# --- Chat -----------------------------------------------------------------


class YearPlanChatResponse(BaseModel):
    user_message: dict
    assistant_message: dict
    year_plan_state_changed: bool
