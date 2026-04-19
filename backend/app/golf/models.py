"""SQLAlchemy models for the golf library (spec 006).

Tables live in their **own SQLite** at `backend/data/golf.db` (bound to
`GolfBase`), separate from the trips/yearly Postgres. Inter-engine
references from trip-planning tables (suggested/shortlisted/excluded
destinations' `resort_id` / `course_id`) are plain INTEGER columns —
enforced in application code, not by the database.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from ..database import GolfBase


def _utcnow():
    return datetime.now(timezone.utc)


class GolfResort(GolfBase):
    __tablename__ = "golf_resorts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # Derived; kept in sync by crud on insert/update (FR-003a).
    name_norm = Column(String, nullable=False)
    url = Column(String, nullable=True)
    source_urls = Column(Text, nullable=False, default="[]")
    country_code = Column(String, nullable=False)
    region_name_raw = Column(String, nullable=True)
    # Stable cross-DB key: "country_code:region_name". Null = unmatched.
    vacationmap_region_key = Column(String, nullable=True)
    town = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    hotel_name = Column(String, nullable=True)
    # 'luxury' | 'boutique' | 'golf_hotel' | 'none' | NULL
    hotel_type = Column(String, nullable=True)
    star_rating = Column(Integer, nullable=True)
    # '€' | '€€' | '€€€' | '€€€€' | NULL
    price_category = Column(String, nullable=True)
    best_months = Column(Text, nullable=False, default="[]")
    description = Column(Text, nullable=True)
    amenities = Column(Text, nullable=False, default="[]")
    rank_rating = Column(Integer, nullable=True)  # 0..100
    tags = Column(Text, nullable=False, default="[]")
    personal_notes = Column(Text, nullable=True)
    source_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    courses = relationship(
        "GolfCourse",
        back_populates="resort",
        order_by="GolfCourse.display_order",
    )


Index(
    "ix_golf_resorts_name_norm_country",
    GolfResort.name_norm,
    GolfResort.country_code,
)
Index("ix_golf_resorts_vm_region_key", GolfResort.vacationmap_region_key)
Index("ix_golf_resorts_country", GolfResort.country_code)


class GolfCourse(GolfBase):
    __tablename__ = "golf_courses"

    id = Column(Integer, primary_key=True, index=True)
    resort_id = Column(
        Integer,
        ForeignKey("golf_resorts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name = Column(String, nullable=False)
    name_norm = Column(String, nullable=False)
    url = Column(String, nullable=True)
    source_urls = Column(Text, nullable=False, default="[]")
    country_code = Column(String, nullable=True)
    region_name_raw = Column(String, nullable=True)
    vacationmap_region_key = Column(String, nullable=True)
    town = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    holes = Column(Integer, nullable=True)
    par = Column(Integer, nullable=True)
    length_yards = Column(Integer, nullable=True)
    type = Column(String, nullable=True)
    architect = Column(String, nullable=True)
    year_opened = Column(Integer, nullable=True)
    difficulty = Column(Integer, nullable=True)
    signature_holes = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    green_fee_low_eur = Column(Integer, nullable=True)
    green_fee_high_eur = Column(Integer, nullable=True)
    green_fee_notes = Column(String, nullable=True)
    best_months = Column(Text, nullable=False, default="[]")
    rank_rating = Column(Integer, nullable=True)
    tags = Column(Text, nullable=False, default="[]")
    personal_notes = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    source_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    resort = relationship("GolfResort", back_populates="courses")


Index(
    "ix_golf_courses_name_norm_country",
    GolfCourse.name_norm,
    GolfCourse.country_code,
)
Index("ix_golf_courses_resort_id", GolfCourse.resort_id)
Index("ix_golf_courses_vm_region_key", GolfCourse.vacationmap_region_key)
Index("ix_golf_courses_type", GolfCourse.type)


class EntityImage(GolfBase):
    """Polymorphic image table. Currently dormant — image extraction is
    disabled because Claude's URL output was too unreliable (hallucinated
    paths, wrong photos). The table is preserved so images can be
    re-enabled later without a destructive migration."""

    __tablename__ = "entity_images"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False)  # 'resort' | 'course'
    entity_id = Column(Integer, nullable=False)
    url = Column(String, nullable=False)
    caption = Column(String, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


Index(
    "ix_entity_images_lookup",
    EntityImage.entity_type,
    EntityImage.entity_id,
    EntityImage.display_order,
)
