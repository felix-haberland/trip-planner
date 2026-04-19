"""CRUD operations for the golf library (spec 006).

Covers resorts, courses, images, and `_auto_resolve_region` — which runs
extracted region names through the same fuzzy matcher trip planning uses
(`app.trips.tools._resolve_lookup_key`).
"""

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..text_utils import normalize_name
from . import models, schemas


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Spec 006 — Golf library (resorts, courses, images)
# ---------------------------------------------------------------------------


class DuplicateEntity(Exception):
    """Raised by create_resort / create_course when an entry with the same
    normalized name + country + entity_type already exists and `force=False`.

    The caller (a FastAPI route) converts this to HTTP 409 with the
    existing entity attached per FR-003a dedup rules.
    """

    def __init__(self, existing, entity_type: str):
        super().__init__(f"duplicate {entity_type}: id={existing.id}")
        self.existing = existing
        self.entity_type = entity_type


class DeleteBlocked(Exception):
    """Raised by delete_resort / delete_course per FR-020a when references
    exist. The caller converts this to HTTP 409 with the blocker list."""

    def __init__(self, reason: str, blockers: dict):
        super().__init__(reason)
        self.reason = reason
        self.blockers = blockers


def _dump_list(value) -> str:
    return json.dumps(value if value is not None else [])


def _load_list(s: Optional[str]) -> list:
    if not s:
        return []
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return []


# --- Resorts ---


def _find_resort_by_name(
    db: Session, name_norm: str, country_code: str
) -> Optional[models.GolfResort]:
    return (
        db.query(models.GolfResort)
        .filter(
            models.GolfResort.name_norm == name_norm,
            models.GolfResort.country_code == country_code,
        )
        .first()
    )


def _find_course_by_name(
    db: Session, name_norm: str, country_code: Optional[str]
) -> Optional[models.GolfCourse]:
    q = db.query(models.GolfCourse).filter(models.GolfCourse.name_norm == name_norm)
    if country_code is not None:
        q = q.filter(models.GolfCourse.country_code == country_code)
    return q.first()


def find_resort_by_name_norm(
    db: Session, name: str, country_code: Optional[str] = None
) -> Optional[models.GolfResort]:
    """Public helper used by extraction.py to detect 'possible parent resort'."""
    norm = normalize_name(name)
    q = db.query(models.GolfResort).filter(models.GolfResort.name_norm == norm)
    if country_code is not None:
        q = q.filter(models.GolfResort.country_code == country_code)
    return q.first()


def _auto_resolve_region(
    vm_db, country_code: Optional[str], region_name_raw: Optional[str]
) -> Optional[str]:
    """Use `tools._resolve_lookup_key`'s 6-step fallback to turn a country +
    region-name pair into a VacationMap region key like 'PT:Algarve'.

    Returns None if vm_db is unavailable, the inputs are empty, or no match.
    """
    if vm_db is None or not region_name_raw or not region_name_raw.strip():
        return None
    from sqlalchemy import text

    country_name = ""
    if country_code:
        row = vm_db.execute(
            text("SELECT name FROM countries WHERE code = :cc"),
            {"cc": country_code},
        ).fetchone()
        if row:
            country_name = row[0]
    dest_name = (
        f"{region_name_raw}, {country_name}" if country_name else region_name_raw
    )
    from ..trips import tools as trip_tools

    try:
        return trip_tools._resolve_lookup_key({"destination_name": dest_name}, vm_db)
    except Exception:
        return None


def create_resort(
    db: Session,
    data: "schemas.GolfResortCreate",
    *,
    force: bool = False,
    vm_db=None,
) -> models.GolfResort:
    """Create a resort with dedup (FR-003a) and optional attached-course/image rows.

    If `vm_db` is provided and `data.vacationmap_region_key` is not set, try
    to auto-resolve the region via the same 6-step fuzzy matcher trip
    planning uses (`tools._resolve_lookup_key`).

    Raises DuplicateEntity if `(name_norm, country_code)` already exists and
    `force=False`.
    """
    name_norm = normalize_name(data.name)
    existing = _find_resort_by_name(db, name_norm, data.country_code)
    if existing is not None and not force:
        raise DuplicateEntity(existing, entity_type="resort")

    vm_key = data.vacationmap_region_key
    if not vm_key:
        vm_key = _auto_resolve_region(vm_db, data.country_code, data.region_name_raw)

    resort = models.GolfResort(
        name=data.name,
        name_norm=name_norm,
        url=data.url,
        source_urls=_dump_list(data.source_urls),
        country_code=data.country_code,
        region_name_raw=data.region_name_raw,
        vacationmap_region_key=vm_key,
        town=data.town,
        latitude=data.latitude,
        longitude=data.longitude,
        hotel_name=data.hotel_name,
        hotel_type=data.hotel_type,
        star_rating=data.star_rating,
        price_category=data.price_category,
        best_months=_dump_list(data.best_months),
        description=data.description,
        amenities=_dump_list(data.amenities),
        rank_rating=data.rank_rating,
        tags=_dump_list(data.tags),
        personal_notes=data.personal_notes,
        source_checked_at=_utcnow(),
    )
    db.add(resort)
    db.flush()  # need resort.id for images and course-inline inserts

    # Attach inline courses (no extraction, just persistence)
    for idx, course_in in enumerate(data.courses):
        _create_course_row(
            db, course_in, resort_id=resort.id, display_order=idx, vm_db=vm_db
        )

    # Attach images
    for idx, url in enumerate(data.image_urls):
        db.add(
            models.EntityImage(
                entity_type="resort",
                entity_id=resort.id,
                url=url,
                display_order=idx,
            )
        )

    db.commit()
    db.refresh(resort)
    return resort


def _create_course_row(
    db: Session,
    data: "schemas.GolfCourseCreate",
    *,
    resort_id: Optional[int],
    display_order: int = 0,
    vm_db=None,
) -> models.GolfCourse:
    """Internal helper; callers handle commit."""
    if resort_id is None and not data.country_code:
        raise ValueError(
            "country_code is required when the course has no parent resort"
        )
    name_norm = normalize_name(data.name)
    vm_key = data.vacationmap_region_key
    if not vm_key:
        vm_key = _auto_resolve_region(vm_db, data.country_code, data.region_name_raw)
    course = models.GolfCourse(
        resort_id=resort_id,
        name=data.name,
        name_norm=name_norm,
        url=data.url,
        source_urls=_dump_list(data.source_urls),
        country_code=data.country_code,
        region_name_raw=data.region_name_raw,
        vacationmap_region_key=vm_key,
        town=data.town,
        latitude=data.latitude,
        longitude=data.longitude,
        holes=data.holes,
        par=data.par,
        length_yards=data.length_yards,
        type=data.type,
        architect=data.architect,
        year_opened=data.year_opened,
        difficulty=data.difficulty,
        signature_holes=data.signature_holes,
        description=data.description,
        green_fee_low_eur=data.green_fee_low_eur,
        green_fee_high_eur=data.green_fee_high_eur,
        green_fee_notes=data.green_fee_notes,
        best_months=_dump_list(data.best_months),
        rank_rating=data.rank_rating,
        tags=_dump_list(data.tags),
        personal_notes=data.personal_notes,
        display_order=data.display_order or display_order,
        source_checked_at=_utcnow(),
    )
    db.add(course)
    db.flush()
    # Attach images for this course
    for idx, url in enumerate(data.image_urls):
        db.add(
            models.EntityImage(
                entity_type="course",
                entity_id=course.id,
                url=url,
                display_order=idx,
            )
        )
    return course


def create_course(
    db: Session,
    data: "schemas.GolfCourseCreate",
    *,
    force: bool = False,
    vm_db=None,
) -> models.GolfCourse:
    """Create a standalone course or a course attached to an existing resort.

    Dedup check uses `(name_norm, country_code)` — inherited country from the
    parent resort when the input leaves it blank.
    """
    # Resolve effective country_code for dedup: course's own, else parent resort's.
    effective_country = data.country_code
    if effective_country is None and data.resort_id is not None:
        parent = (
            db.query(models.GolfResort)
            .filter(models.GolfResort.id == data.resort_id)
            .first()
        )
        if parent is None:
            raise ValueError(f"parent resort {data.resort_id} not found")
        effective_country = parent.country_code

    if effective_country is None:
        raise ValueError(
            "country_code is required when the course has no parent resort"
        )

    name_norm = normalize_name(data.name)
    existing = _find_course_by_name(db, name_norm, effective_country)
    if existing is not None and not force:
        raise DuplicateEntity(existing, entity_type="course")

    course = _create_course_row(
        db,
        data,
        resort_id=data.resort_id,
        display_order=data.display_order,
        vm_db=vm_db,
    )
    db.commit()
    db.refresh(course)
    return course


def add_image(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    url: str,
    caption: Optional[str] = None,
) -> models.EntityImage:
    """Append an image to a resort or course. Next `display_order`."""
    if entity_type not in ("resort", "course"):
        raise ValueError("entity_type must be 'resort' or 'course'")

    # Validate parent exists
    if entity_type == "resort":
        parent = (
            db.query(models.GolfResort)
            .filter(models.GolfResort.id == entity_id)
            .first()
        )
    else:
        parent = (
            db.query(models.GolfCourse)
            .filter(models.GolfCourse.id == entity_id)
            .first()
        )
    if parent is None:
        raise ValueError(f"{entity_type} id={entity_id} not found")

    # Next display_order
    max_order = (
        db.query(models.EntityImage.display_order)
        .filter(
            models.EntityImage.entity_type == entity_type,
            models.EntityImage.entity_id == entity_id,
        )
        .order_by(models.EntityImage.display_order.desc())
        .limit(1)
        .scalar()
    )
    next_order = (max_order + 1) if max_order is not None else 0

    image = models.EntityImage(
        entity_type=entity_type,
        entity_id=entity_id,
        url=url,
        caption=caption,
        display_order=next_order,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def get_resort(db: Session, resort_id: int) -> Optional[models.GolfResort]:
    return db.query(models.GolfResort).filter(models.GolfResort.id == resort_id).first()


def get_course(db: Session, course_id: int) -> Optional[models.GolfCourse]:
    return db.query(models.GolfCourse).filter(models.GolfCourse.id == course_id).first()


def get_images_for(
    db: Session, entity_type: str, entity_id: int
) -> list[models.EntityImage]:
    return (
        db.query(models.EntityImage)
        .filter(
            models.EntityImage.entity_type == entity_type,
            models.EntityImage.entity_id == entity_id,
        )
        .order_by(models.EntityImage.display_order)
        .all()
    )


def resort_to_list_item(
    db: Session, resort: models.GolfResort
) -> "schemas.GolfResortListItem":
    """Serialize a resort for the list/tool-response view."""
    course_count = (
        db.query(models.GolfCourse)
        .filter(models.GolfCourse.resort_id == resort.id)
        .count()
    )
    hero = (
        db.query(models.EntityImage.url)
        .filter(
            models.EntityImage.entity_type == "resort",
            models.EntityImage.entity_id == resort.id,
        )
        .order_by(models.EntityImage.display_order)
        .limit(1)
        .scalar()
    )
    return schemas.GolfResortListItem(
        id=resort.id,
        name=resort.name,
        country_code=resort.country_code,
        region_name_raw=resort.region_name_raw,
        vacationmap_region_key=resort.vacationmap_region_key,
        hotel_type=resort.hotel_type,
        price_category=resort.price_category,
        course_count=course_count,
        rank_rating=resort.rank_rating,
        best_months=_load_list(resort.best_months),
        hero_image_url=hero,
        region_matched=resort.vacationmap_region_key is not None,
    )


def course_to_list_item(
    db: Session, course: models.GolfCourse
) -> "schemas.GolfCourseListItem":
    resort_name = None
    country_code = course.country_code
    region_name_raw = course.region_name_raw
    vm_key = course.vacationmap_region_key
    if course.resort_id is not None:
        parent = (
            db.query(models.GolfResort)
            .filter(models.GolfResort.id == course.resort_id)
            .first()
        )
        if parent is not None:
            resort_name = parent.name
            # Inherit when own is null
            if country_code is None:
                country_code = parent.country_code
            if region_name_raw is None:
                region_name_raw = parent.region_name_raw
            if vm_key is None:
                vm_key = parent.vacationmap_region_key
    hero = (
        db.query(models.EntityImage.url)
        .filter(
            models.EntityImage.entity_type == "course",
            models.EntityImage.entity_id == course.id,
        )
        .order_by(models.EntityImage.display_order)
        .limit(1)
        .scalar()
    )
    return schemas.GolfCourseListItem(
        id=course.id,
        resort_id=course.resort_id,
        resort_name=(
            resort_name
            if resort_name
            else ("Standalone" if course.resort_id is None else None)
        ),
        name=course.name,
        country_code=country_code,
        region_name_raw=region_name_raw,
        vacationmap_region_key=vm_key,
        type=course.type,
        par=course.par,
        length_yards=course.length_yards,
        architect=course.architect,
        difficulty=course.difficulty,
        rank_rating=course.rank_rating,
        hero_image_url=hero,
        green_fee_low_eur=course.green_fee_low_eur,
        green_fee_high_eur=course.green_fee_high_eur,
        region_matched=vm_key is not None,
    )


# ---------------------------------------------------------------------------
# Spec 006 — Golf library: list + detail (US2)
# ---------------------------------------------------------------------------


from sqlalchemy import or_  # noqa: E402

_RESORT_SORT_COLUMNS = {
    "rank_rating": models.GolfResort.rank_rating,
    "price_category": models.GolfResort.price_category,
    "updated_at": models.GolfResort.updated_at,
    # course_count is an aggregate — handled specially below
}

_COURSE_SORT_COLUMNS = {
    "rank_rating": models.GolfCourse.rank_rating,
    "length_yards": models.GolfCourse.length_yards,
    "difficulty": models.GolfCourse.difficulty,
    "green_fee_low_eur": models.GolfCourse.green_fee_low_eur,
    "updated_at": models.GolfCourse.updated_at,
}


def list_resorts(
    db: Session,
    *,
    country: Optional[str] = None,
    price_category: Optional[list[str]] = None,
    hotel_type: Optional[list[str]] = None,
    month: Optional[int] = None,
    tags: Optional[list[str]] = None,
    region_match: str = "any",
    q: Optional[str] = None,
    sort: str = "rank_rating",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list["schemas.GolfResortListItem"]]:
    """List resorts with filters + sort + pagination. Returns (total, items)."""
    base = db.query(models.GolfResort)

    if country:
        base = base.filter(models.GolfResort.country_code == country)
    if price_category:
        base = base.filter(models.GolfResort.price_category.in_(price_category))
    if hotel_type:
        base = base.filter(models.GolfResort.hotel_type.in_(hotel_type))
    if region_match == "matched":
        base = base.filter(models.GolfResort.vacationmap_region_key.isnot(None))
    elif region_match == "unmatched":
        base = base.filter(models.GolfResort.vacationmap_region_key.is_(None))

    if q:
        q_norm = normalize_name(q)
        pattern = f"%{q_norm}%"
        base = base.filter(
            or_(
                models.GolfResort.name_norm.like(pattern),
                models.GolfResort.description.like(f"%{q}%"),
            )
        )

    # JSON-array filters (month, tags): fall back to Python-side post-filter —
    # SQLite JSON1 extension may not be available. Acceptable at library size.
    pre = base.all()

    def _matches_month(r):
        if month is None:
            return True
        return month in _load_list(r.best_months)

    def _matches_tags(r):
        if not tags:
            return True
        row_tags = set(_load_list(r.tags))
        return all(t in row_tags for t in tags)

    filtered = [r for r in pre if _matches_month(r) and _matches_tags(r)]
    total = len(filtered)

    # Sorting
    if sort == "course_count":
        counts = {
            r.id: (
                db.query(models.GolfCourse)
                .filter(models.GolfCourse.resort_id == r.id)
                .count()
            )
            for r in filtered
        }
        filtered.sort(
            key=lambda r: (counts[r.id] if counts[r.id] is not None else -1),
            reverse=(sort_dir == "desc"),
        )
    else:
        col = _RESORT_SORT_COLUMNS.get(sort, models.GolfResort.rank_rating)

        def _key(r):
            v = getattr(r, col.key, None)
            return (v is None, v)

        filtered.sort(key=_key, reverse=(sort_dir == "desc"))

    page = filtered[offset : offset + limit]
    return total, [resort_to_list_item(db, r) for r in page]


def list_courses(
    db: Session,
    *,
    country: Optional[str] = None,
    course_type: Optional[list[str]] = None,
    min_difficulty: Optional[int] = None,
    max_difficulty: Optional[int] = None,
    min_holes: Optional[int] = None,
    parent_resort: str = "any",  # any | has_resort | standalone
    max_green_fee_eur: Optional[int] = None,
    tags: Optional[list[str]] = None,
    region_match: str = "any",
    q: Optional[str] = None,
    sort: str = "rank_rating",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list["schemas.GolfCourseListItem"]]:
    """List courses with filters + sort + pagination."""
    # We need resort-level join for country inheritance filtering.
    base = db.query(models.GolfCourse).outerjoin(
        models.GolfResort, models.GolfCourse.resort_id == models.GolfResort.id
    )

    if country:
        # Match course's own country OR parent resort's country (inheritance).
        base = base.filter(
            or_(
                models.GolfCourse.country_code == country,
                models.GolfResort.country_code == country,
            )
        )
    if course_type:
        base = base.filter(models.GolfCourse.type.in_(course_type))
    if min_difficulty is not None:
        base = base.filter(models.GolfCourse.difficulty >= min_difficulty)
    if max_difficulty is not None:
        base = base.filter(models.GolfCourse.difficulty <= max_difficulty)
    if min_holes is not None:
        base = base.filter(models.GolfCourse.holes >= min_holes)
    if parent_resort == "has_resort":
        base = base.filter(models.GolfCourse.resort_id.isnot(None))
    elif parent_resort == "standalone":
        base = base.filter(models.GolfCourse.resort_id.is_(None))
    if max_green_fee_eur is not None:
        base = base.filter(
            or_(
                models.GolfCourse.green_fee_low_eur.is_(None),
                models.GolfCourse.green_fee_low_eur <= max_green_fee_eur,
            )
        )
    if region_match == "matched":
        base = base.filter(
            or_(
                models.GolfCourse.vacationmap_region_key.isnot(None),
                models.GolfResort.vacationmap_region_key.isnot(None),
            )
        )
    elif region_match == "unmatched":
        base = base.filter(
            models.GolfCourse.vacationmap_region_key.is_(None),
            or_(
                models.GolfCourse.resort_id.is_(None),
                models.GolfResort.vacationmap_region_key.is_(None),
            ),
        )
    if q:
        q_norm = normalize_name(q)
        pattern = f"%{q_norm}%"
        base = base.filter(
            or_(
                models.GolfCourse.name_norm.like(pattern),
                models.GolfCourse.description.like(f"%{q}%"),
            )
        )

    pre = base.all()

    def _matches_tags(c):
        if not tags:
            return True
        row_tags = set(_load_list(c.tags))
        return all(t in row_tags for t in tags)

    filtered = [c for c in pre if _matches_tags(c)]
    total = len(filtered)

    col = _COURSE_SORT_COLUMNS.get(sort, models.GolfCourse.rank_rating)

    def _key(c):
        v = getattr(c, col.key, None)
        return (v is None, v)

    filtered.sort(key=_key, reverse=(sort_dir == "desc"))
    page = filtered[offset : offset + limit]
    return total, [course_to_list_item(db, c) for c in page]


def get_resort_detail(
    db: Session, resort_id: int, vm_db: Optional[Session] = None
) -> Optional[dict]:
    """Return resort + attached courses + images + VacationMap scores dict."""
    resort = get_resort(db, resort_id)
    if resort is None:
        return None

    courses = (
        db.query(models.GolfCourse)
        .filter(models.GolfCourse.resort_id == resort.id)
        .order_by(models.GolfCourse.display_order)
        .all()
    )
    images = get_images_for(db, "resort", resort.id)
    vm_scores = (
        _fetch_vm_scores(vm_db, resort.vacationmap_region_key) if vm_db else None
    )

    return {
        "id": resort.id,
        "name": resort.name,
        "url": resort.url,
        "source_urls": _load_list(resort.source_urls),
        "country_code": resort.country_code,
        "region_name_raw": resort.region_name_raw,
        "vacationmap_region_key": resort.vacationmap_region_key,
        "town": resort.town,
        "latitude": resort.latitude,
        "longitude": resort.longitude,
        "hotel_name": resort.hotel_name,
        "hotel_type": resort.hotel_type,
        "star_rating": resort.star_rating,
        "price_category": resort.price_category,
        "best_months": _load_list(resort.best_months),
        "description": resort.description,
        "amenities": _load_list(resort.amenities),
        "rank_rating": resort.rank_rating,
        "tags": _load_list(resort.tags),
        "personal_notes": resort.personal_notes,
        "source_checked_at": resort.source_checked_at,
        "created_at": resort.created_at,
        "updated_at": resort.updated_at,
        "courses": [_course_detail_dict(db, c) for c in courses],
        "images": [_image_to_dict(i) for i in images],
        "vacationmap_scores": vm_scores,
    }


def get_course_detail(
    db: Session, course_id: int, vm_db: Optional[Session] = None
) -> Optional[dict]:
    course = get_course(db, course_id)
    if course is None:
        return None
    parent_item = None
    vm_key = course.vacationmap_region_key
    if course.resort_id is not None:
        parent = get_resort(db, course.resort_id)
        if parent is not None:
            parent_item = resort_to_list_item(db, parent).model_dump()
            if vm_key is None:
                vm_key = parent.vacationmap_region_key
    vm_scores = _fetch_vm_scores(vm_db, vm_key) if vm_db else None
    detail = _course_detail_dict(db, course)
    detail["parent_resort"] = parent_item
    detail["vacationmap_scores"] = vm_scores
    return detail


def _course_detail_dict(db: Session, course: models.GolfCourse) -> dict:
    images = get_images_for(db, "course", course.id)
    return {
        "id": course.id,
        "resort_id": course.resort_id,
        "name": course.name,
        "url": course.url,
        "source_urls": _load_list(course.source_urls),
        "country_code": course.country_code,
        "region_name_raw": course.region_name_raw,
        "vacationmap_region_key": course.vacationmap_region_key,
        "town": course.town,
        "latitude": course.latitude,
        "longitude": course.longitude,
        "holes": course.holes,
        "par": course.par,
        "length_yards": course.length_yards,
        "type": course.type,
        "architect": course.architect,
        "year_opened": course.year_opened,
        "difficulty": course.difficulty,
        "signature_holes": course.signature_holes,
        "description": course.description,
        "green_fee_low_eur": course.green_fee_low_eur,
        "green_fee_high_eur": course.green_fee_high_eur,
        "green_fee_notes": course.green_fee_notes,
        "best_months": _load_list(course.best_months),
        "rank_rating": course.rank_rating,
        "tags": _load_list(course.tags),
        "personal_notes": course.personal_notes,
        "display_order": course.display_order,
        "source_checked_at": course.source_checked_at,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "images": [_image_to_dict(i) for i in images],
    }


def _image_to_dict(img: models.EntityImage) -> dict:
    return {
        "id": img.id,
        "entity_type": img.entity_type,
        "entity_id": img.entity_id,
        "url": img.url,
        "caption": img.caption,
        "display_order": img.display_order,
    }


def _fetch_vm_scores(vm_db: Optional[Session], vm_key: Optional[str]) -> Optional[dict]:
    if not vm_db or not vm_key:
        return None
    try:
        from . import vacationmap as vm

        details = vm.get_destination_details(vm_db, vm_key, "jun")
        if details is None:
            return None
        # Compact scores dict for display; avoids duplicating the full 60-field payload.
        return {
            "total_score": details.get("total_score"),
            "golf_score": details.get("golf_score"),
            "attractiveness": details.get("attractiveness_relative_jun"),
            "cost_relative": details.get("cost_relative_jun"),
            "busyness_relative": details.get("busyness_relative_jun"),
            "weather_score": details.get("weather_score"),
            "safety": details.get("crime_safety"),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Spec 006 — Update / delete / link (US4 + US5)
# ---------------------------------------------------------------------------


def _apply_patch(target, patch_model) -> None:
    """Apply non-None fields from a Pydantic patch onto a SQLAlchemy row.

    Special-cased fields: `name` triggers `name_norm` recompute; list fields
    are JSON-dumped into Text columns.
    """
    data = patch_model.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is None and key not in {
            # These are nullable and we allow explicit null-setting
            "url",
            "region_name_raw",
            "vacationmap_region_key",
            "town",
            "latitude",
            "longitude",
            "hotel_name",
            "hotel_type",
            "star_rating",
            "price_category",
            "description",
            "rank_rating",
            "personal_notes",
            "signature_holes",
            "architect",
            "year_opened",
            "holes",
            "par",
            "length_yards",
            "type",
            "difficulty",
            "green_fee_low_eur",
            "green_fee_high_eur",
            "green_fee_notes",
        }:
            continue
        if key in {"source_urls", "best_months", "amenities", "tags"}:
            setattr(target, key, json.dumps(value if value is not None else []))
        else:
            setattr(target, key, value)
    if "name" in data and data["name"] is not None:
        target.name_norm = normalize_name(data["name"])


def update_resort(
    db: Session, resort_id: int, patch: "schemas.GolfResortPatch"
) -> Optional[models.GolfResort]:
    resort = get_resort(db, resort_id)
    if resort is None:
        return None
    _apply_patch(resort, patch)
    resort.updated_at = _utcnow()
    db.commit()
    db.refresh(resort)
    return resort


def update_course(
    db: Session, course_id: int, patch: "schemas.GolfCoursePatch"
) -> Optional[models.GolfCourse]:
    course = get_course(db, course_id)
    if course is None:
        return None
    _apply_patch(course, patch)
    course.updated_at = _utcnow()
    db.commit()
    db.refresh(course)
    return course


def _find_shortlist_references(
    db: Session, *, resort_id: Optional[int] = None, course_id: Optional[int] = None
) -> list[dict]:
    """Return blocker descriptors for any suggested/shortlisted/excluded rows
    referencing the given resort or course."""
    blockers: list[dict] = []
    for section, Model in (
        ("suggested", models.SuggestedDestination),
        ("shortlisted", models.ShortlistedDestination),
        ("excluded", models.ExcludedDestination),
    ):
        q = db.query(Model, models.TripPlan).join(
            models.TripPlan, Model.trip_id == models.TripPlan.id
        )
        if resort_id is not None:
            q = q.filter(Model.resort_id == resort_id)
        else:
            q = q.filter(Model.course_id == course_id)
        for row, trip in q.all():
            blockers.append(
                {
                    "trip_id": trip.id,
                    "trip_name": trip.name,
                    "section": section,
                    "destination_id": row.id,
                    "destination_name": row.destination_name,
                }
            )
    return blockers


def delete_resort(db: Session, resort_id: int) -> bool:
    """Delete a resort iff no attached courses and no shortlist references.

    Raises DeleteBlocked with a structured blocker list per FR-020a.
    Returns False if the resort doesn't exist.
    """
    resort = get_resort(db, resort_id)
    if resort is None:
        return False

    attached = (
        db.query(models.GolfCourse)
        .filter(models.GolfCourse.resort_id == resort_id)
        .all()
    )
    shortlist_refs = _find_shortlist_references(db, resort_id=resort_id)
    if attached or shortlist_refs:
        reason = (
            "both"
            if (attached and shortlist_refs)
            else ("has_attached_courses" if attached else "referenced_by_shortlist")
        )
        raise DeleteBlocked(
            reason,
            {
                "attached_courses": [{"id": c.id, "name": c.name} for c in attached],
                "shortlist_references": shortlist_refs,
            },
        )

    # Cascade-delete owned images in the same transaction.
    db.query(models.EntityImage).filter(
        models.EntityImage.entity_type == "resort",
        models.EntityImage.entity_id == resort_id,
    ).delete(synchronize_session=False)
    db.delete(resort)
    db.commit()
    return True


def delete_course(db: Session, course_id: int) -> bool:
    course = get_course(db, course_id)
    if course is None:
        return False

    shortlist_refs = _find_shortlist_references(db, course_id=course_id)
    if shortlist_refs:
        raise DeleteBlocked(
            "referenced_by_shortlist",
            {
                "attached_courses": [],
                "shortlist_references": shortlist_refs,
            },
        )

    db.query(models.EntityImage).filter(
        models.EntityImage.entity_type == "course",
        models.EntityImage.entity_id == course_id,
    ).delete(synchronize_session=False)
    db.delete(course)
    db.commit()
    return True


def update_image(
    db: Session,
    image_id: int,
    *,
    caption: Optional[str] = None,
    display_order: Optional[int] = None,
) -> Optional[models.EntityImage]:
    img = db.query(models.EntityImage).filter(models.EntityImage.id == image_id).first()
    if img is None:
        return None
    if caption is not None:
        img.caption = caption
    if display_order is not None:
        img.display_order = display_order
    db.commit()
    db.refresh(img)
    return img


def delete_image(db: Session, image_id: int) -> bool:
    img = db.query(models.EntityImage).filter(models.EntityImage.id == image_id).first()
    if img is None:
        return False
    db.delete(img)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Spec 006 — Linking (US5)
# ---------------------------------------------------------------------------


def link_resort_region(
    db: Session, resort_id: int, vm_key: Optional[str]
) -> Optional[models.GolfResort]:
    resort = get_resort(db, resort_id)
    if resort is None:
        return None
    resort.vacationmap_region_key = vm_key
    resort.updated_at = _utcnow()
    db.commit()
    db.refresh(resort)
    return resort


def link_course_region(
    db: Session, course_id: int, vm_key: Optional[str]
) -> Optional[models.GolfCourse]:
    course = get_course(db, course_id)
    if course is None:
        return None
    course.vacationmap_region_key = vm_key
    course.updated_at = _utcnow()
    db.commit()
    db.refresh(course)
    return course


def link_course_resort(
    db: Session, course_id: int, resort_id: Optional[int]
) -> Optional[models.GolfCourse]:
    """Link or unlink a course from a parent resort. When unlinking
    (resort_id=None), the course must have its own country_code set."""
    course = get_course(db, course_id)
    if course is None:
        return None
    if resort_id is None and not course.country_code:
        raise ValueError("cannot unlink: course has no country_code of its own")
    if resort_id is not None:
        parent = get_resort(db, resort_id)
        if parent is None:
            raise ValueError(f"parent resort {resort_id} not found")
    course.resort_id = resort_id
    course.updated_at = _utcnow()
    db.commit()
    db.refresh(course)
    return course
