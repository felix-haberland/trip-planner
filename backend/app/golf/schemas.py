"""Pydantic schemas for the golf library (spec 006)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Spec 006 — Golf library schemas
# ---------------------------------------------------------------------------


HotelType = Literal["luxury", "boutique", "golf_hotel", "none"]
PriceCategory = Literal["€", "€€", "€€€", "€€€€"]
CourseType = Literal[
    "links", "parkland", "heathland", "desert", "coastal", "mountain", "other"
]
EntityType = Literal["resort", "course"]
ImageValidation = Literal["ok", "unreachable", "wrong_type", "unknown"]
ExtractStatus = Literal["api_error", "no_match", "fetch_error", "ambiguous"]


class EntityImageIn(BaseModel):
    url: str
    caption: Optional[str] = None
    display_order: int = 0


class EntityImageOut(BaseModel):
    id: int
    entity_type: EntityType
    entity_id: int
    url: str
    caption: Optional[str] = None
    display_order: int
    validation: Optional[ImageValidation] = None

    class Config:
        from_attributes = True


# --- Courses ---


class GolfCourseBase(BaseModel):
    name: str
    url: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)
    country_code: Optional[str] = None
    region_name_raw: Optional[str] = None
    vacationmap_region_key: Optional[str] = None
    town: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    holes: Optional[int] = None
    par: Optional[int] = None
    length_yards: Optional[int] = None
    type: Optional[CourseType] = None
    architect: Optional[str] = None
    year_opened: Optional[int] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    signature_holes: Optional[str] = None
    description: Optional[str] = None
    green_fee_low_eur: Optional[int] = None
    green_fee_high_eur: Optional[int] = None
    green_fee_notes: Optional[str] = None
    best_months: list[int] = Field(default_factory=list)
    rank_rating: Optional[int] = Field(default=None, ge=0, le=100)
    tags: list[str] = Field(default_factory=list)
    personal_notes: Optional[str] = None
    display_order: int = 0

    @field_validator("holes")
    @classmethod
    def _holes_allowed(cls, v):
        if v is not None and v not in (9, 18, 27, 36):
            raise ValueError("holes must be 9, 18, 27, or 36")
        return v

    @field_validator("best_months")
    @classmethod
    def _months_in_range(cls, v):
        for m in v:
            if not 1 <= m <= 12:
                raise ValueError("best_months entries must be 1..12")
        return v


class GolfCourseCreate(GolfCourseBase):
    resort_id: Optional[int] = None
    image_urls: list[str] = Field(default_factory=list)

    # country_code required when resort_id is None — enforced in crud,
    # where we also know whether the parent resort exists.


class GolfCoursePatch(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    source_urls: Optional[list[str]] = None
    country_code: Optional[str] = None
    region_name_raw: Optional[str] = None
    vacationmap_region_key: Optional[str] = None
    town: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    holes: Optional[int] = None
    par: Optional[int] = None
    length_yards: Optional[int] = None
    type: Optional[CourseType] = None
    architect: Optional[str] = None
    year_opened: Optional[int] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    signature_holes: Optional[str] = None
    description: Optional[str] = None
    green_fee_low_eur: Optional[int] = None
    green_fee_high_eur: Optional[int] = None
    green_fee_notes: Optional[str] = None
    best_months: Optional[list[int]] = None
    rank_rating: Optional[int] = Field(default=None, ge=0, le=100)
    tags: Optional[list[str]] = None
    personal_notes: Optional[str] = None
    display_order: Optional[int] = None


class GolfCourseListItem(BaseModel):
    id: int
    resort_id: Optional[int] = None
    resort_name: Optional[str] = None  # "Standalone" when None
    name: str
    country_code: Optional[str] = None  # inherited from resort when null
    region_name_raw: Optional[str] = None
    vacationmap_region_key: Optional[str] = None
    type: Optional[CourseType] = None
    par: Optional[int] = None
    length_yards: Optional[int] = None
    architect: Optional[str] = None
    difficulty: Optional[int] = None
    rank_rating: Optional[int] = None
    hero_image_url: Optional[str] = None
    green_fee_low_eur: Optional[int] = None
    green_fee_high_eur: Optional[int] = None
    region_matched: bool = False


class GolfCourseDetail(GolfCourseBase):
    id: int
    resort_id: Optional[int] = None
    parent_resort: Optional["GolfResortListItem"] = None
    images: list[EntityImageOut] = Field(default_factory=list)
    vacationmap_scores: Optional[dict] = None
    source_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Resorts ---


class GolfResortBase(BaseModel):
    name: str
    url: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)
    country_code: str
    region_name_raw: Optional[str] = None
    vacationmap_region_key: Optional[str] = None
    town: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    hotel_name: Optional[str] = None
    hotel_type: Optional[HotelType] = None
    star_rating: Optional[int] = Field(default=None, ge=0, le=5)
    price_category: Optional[PriceCategory] = None
    best_months: list[int] = Field(default_factory=list)
    description: Optional[str] = None
    amenities: list[str] = Field(default_factory=list)
    rank_rating: Optional[int] = Field(default=None, ge=0, le=100)
    tags: list[str] = Field(default_factory=list)
    personal_notes: Optional[str] = None

    @field_validator("best_months")
    @classmethod
    def _months_in_range(cls, v):
        for m in v:
            if not 1 <= m <= 12:
                raise ValueError("best_months entries must be 1..12")
        return v


class GolfResortCreate(GolfResortBase):
    courses: list[GolfCourseCreate] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)


class GolfResortPatch(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    source_urls: Optional[list[str]] = None
    country_code: Optional[str] = None
    region_name_raw: Optional[str] = None
    vacationmap_region_key: Optional[str] = None
    town: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    hotel_name: Optional[str] = None
    hotel_type: Optional[HotelType] = None
    star_rating: Optional[int] = Field(default=None, ge=0, le=5)
    price_category: Optional[PriceCategory] = None
    best_months: Optional[list[int]] = None
    description: Optional[str] = None
    amenities: Optional[list[str]] = None
    rank_rating: Optional[int] = Field(default=None, ge=0, le=100)
    tags: Optional[list[str]] = None
    personal_notes: Optional[str] = None


class GolfResortListItem(BaseModel):
    id: int
    name: str
    country_code: str
    region_name_raw: Optional[str] = None
    vacationmap_region_key: Optional[str] = None
    hotel_type: Optional[HotelType] = None
    price_category: Optional[PriceCategory] = None
    course_count: int = 0
    rank_rating: Optional[int] = None
    best_months: list[int] = Field(default_factory=list)
    hero_image_url: Optional[str] = None
    region_matched: bool = False


class GolfResortDetail(GolfResortBase):
    id: int
    courses: list[GolfCourseDetail] = Field(default_factory=list)
    images: list[EntityImageOut] = Field(default_factory=list)
    vacationmap_scores: Optional[dict] = None
    source_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Resolve forward references for GolfCourseDetail.parent_resort
GolfCourseDetail.model_rebuild()


# --- Extraction flow ---


class ExtractRequest(BaseModel):
    entity_type: EntityType
    url: Optional[str] = None
    name: Optional[str] = None


class ImageCandidate(BaseModel):
    url: str
    caption: Optional[str] = None
    validation: ImageValidation = "unknown"


class ExtractedResort(BaseModel):
    entity_type: Literal["resort"] = "resort"
    data: GolfResortCreate
    source_urls: list[str] = Field(default_factory=list)
    image_candidates: list[ImageCandidate] = Field(default_factory=list)
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)


class PossibleParentResort(BaseModel):
    detected_name: str
    existing_resort_id: Optional[int] = None


class ExtractedCourse(BaseModel):
    entity_type: Literal["course"] = "course"
    data: GolfCourseCreate
    source_urls: list[str] = Field(default_factory=list)
    image_candidates: list[ImageCandidate] = Field(default_factory=list)
    possible_parent_resort: Optional[PossibleParentResort] = None
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)


class ExtractErrorCandidate(BaseModel):
    name: str
    country_code: Optional[str] = None
    url: Optional[str] = None


class ExtractErrorResponse(BaseModel):
    status: ExtractStatus
    message: str
    partial_data: Optional[dict] = None
    candidates: Optional[list[ExtractErrorCandidate]] = None


# --- Duplicate warning + delete-blocked responses ---


class DuplicateWarning(BaseModel):
    existing_entity: dict  # ResortListItem | CourseListItem (rendered as dict)
    match_reason: Literal["exact_name_norm_country"] = "exact_name_norm_country"
    actions: list[str] = Field(
        default_factory=lambda: ["create_anyway", "edit_existing", "cancel"]
    )


class AttachedCourseBlocker(BaseModel):
    id: int
    name: str


class ShortlistReferenceBlocker(BaseModel):
    trip_id: int
    trip_name: str
    section: Literal["suggested", "shortlisted", "excluded"]
    destination_id: int


class DeleteBlocked(BaseModel):
    reason: Literal["has_attached_courses", "referenced_by_shortlist", "both"]
    blockers: dict  # {"attached_courses": [...], "shortlist_references": [...]}
