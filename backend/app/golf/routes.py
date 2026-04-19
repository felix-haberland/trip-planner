"""FastAPI APIRouter for the golf library (spec 006)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import crud, schemas
from ..database import get_golf_db, get_vacationmap_db

router = APIRouter()


def _parse_list_param(value) -> list[str] | None:
    """FastAPI normalizes repeated query params to a list; passthrough."""
    if value is None:
        return None
    if isinstance(value, str):
        return [value] if value else None
    return list(value)


@router.get("/api/golf-library/resorts")
def list_resorts_endpoint(
    country: str | None = None,
    price_category: list[str] | None = Query(default=None),
    hotel_type: list[str] | None = Query(default=None),
    month: int | None = None,
    tags: list[str] | None = Query(default=None),
    region_match: str = "any",
    q: str | None = None,
    sort: str = "rank_rating",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_golf_db),
):
    total, items = crud.list_resorts(
        db,
        country=country,
        price_category=_parse_list_param(price_category),
        hotel_type=_parse_list_param(hotel_type),
        month=month,
        tags=_parse_list_param(tags),
        region_match=region_match,
        q=q,
        sort=sort,
        sort_dir=sort_dir,
        limit=min(limit, 200),
        offset=offset,
    )
    return {"total": total, "results": [i.model_dump() for i in items]}


@router.get("/api/golf-library/resorts/{resort_id}")
def get_resort_detail_endpoint(
    resort_id: int,
    db: Session = Depends(get_golf_db),
    vm_db: Session = Depends(get_vacationmap_db),
):
    detail = crud.get_resort_detail(db, resort_id, vm_db=vm_db)
    if detail is None:
        raise HTTPException(status_code=404, detail="Resort not found")
    return detail


@router.get("/api/golf-library/courses")
def list_courses_endpoint(
    country: str | None = None,
    course_type: list[str] | None = Query(default=None),
    min_difficulty: int | None = None,
    max_difficulty: int | None = None,
    min_holes: int | None = None,
    parent_resort: str = "any",
    max_green_fee_eur: int | None = None,
    tags: list[str] | None = Query(default=None),
    region_match: str = "any",
    q: str | None = None,
    sort: str = "rank_rating",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_golf_db),
):
    total, items = crud.list_courses(
        db,
        country=country,
        course_type=_parse_list_param(course_type),
        min_difficulty=min_difficulty,
        max_difficulty=max_difficulty,
        min_holes=min_holes,
        parent_resort=parent_resort,
        max_green_fee_eur=max_green_fee_eur,
        tags=_parse_list_param(tags),
        region_match=region_match,
        q=q,
        sort=sort,
        sort_dir=sort_dir,
        limit=min(limit, 200),
        offset=offset,
    )
    return {"total": total, "results": [i.model_dump() for i in items]}


@router.get("/api/golf-library/courses/{course_id}")
def get_course_detail_endpoint(
    course_id: int,
    db: Session = Depends(get_golf_db),
    vm_db: Session = Depends(get_vacationmap_db),
):
    detail = crud.get_course_detail(db, course_id, vm_db=vm_db)
    if detail is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return detail


@router.post("/api/golf-library/extract")
def extract_entity(payload: schemas.ExtractRequest):
    """Run AI extraction against a URL or a name. The user reviews the result
    before persisting via the /resorts or /courses POST endpoints."""
    from . import extraction, crud as crud_mod

    try:
        if payload.entity_type == "resort":
            result = extraction.extract_resort(url=payload.url, name=payload.name)
            return result.model_dump()
        else:
            # Build a DB-backed lookup for the "possible parent resort" hint.
            def _lookup(name: str):
                from .database import TripsSessionLocal

                with TripsSessionLocal() as _db:
                    return crud_mod.find_resort_by_name_norm(_db, name)

            result = extraction.extract_course(
                url=payload.url,
                name=payload.name,
                existing_parent_resort_lookup=_lookup,
            )
            return result.model_dump()
    except extraction.ExtractError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "status": e.status,
                "message": e.message,
                "partial_data": e.partial_data,
                "candidates": e.candidates,
            },
        )


@router.post("/api/golf-library/resorts", status_code=201)
def create_resort(
    payload: schemas.GolfResortCreate,
    force: bool = False,
    db: Session = Depends(get_golf_db),
    vm_db: Session = Depends(get_vacationmap_db),
):
    try:
        resort = crud.create_resort(db, payload, force=force, vm_db=vm_db)
    except crud.DuplicateEntity as dup:
        # 409 + existing entity as list item for the UI's dup-warning modal.
        existing_item = crud.resort_to_list_item(db, dup.existing)
        raise HTTPException(
            status_code=409,
            detail={
                "existing_entity": existing_item.model_dump(),
                "match_reason": "exact_name_norm_country",
                "actions": ["create_anyway", "edit_existing", "cancel"],
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud.resort_to_list_item(db, resort).model_dump()


@router.post("/api/golf-library/courses", status_code=201)
def create_course(
    payload: schemas.GolfCourseCreate,
    force: bool = False,
    db: Session = Depends(get_golf_db),
    vm_db: Session = Depends(get_vacationmap_db),
):
    try:
        course = crud.create_course(db, payload, force=force, vm_db=vm_db)
    except crud.DuplicateEntity as dup:
        existing_item = crud.course_to_list_item(db, dup.existing)
        raise HTTPException(
            status_code=409,
            detail={
                "existing_entity": existing_item.model_dump(),
                "match_reason": "exact_name_norm_country",
                "actions": ["create_anyway", "edit_existing", "cancel"],
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud.course_to_list_item(db, course).model_dump()


@router.patch("/api/golf-library/resorts/{resort_id}")
def update_resort(
    resort_id: int,
    patch: schemas.GolfResortPatch,
    db: Session = Depends(get_golf_db),
):
    resort = crud.update_resort(db, resort_id, patch)
    if resort is None:
        raise HTTPException(status_code=404, detail="Resort not found")
    return crud.resort_to_list_item(db, resort).model_dump()


@router.patch("/api/golf-library/courses/{course_id}")
def update_course(
    course_id: int,
    patch: schemas.GolfCoursePatch,
    db: Session = Depends(get_golf_db),
):
    course = crud.update_course(db, course_id, patch)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return crud.course_to_list_item(db, course).model_dump()


@router.delete("/api/golf-library/resorts/{resort_id}", status_code=204)
def delete_resort_endpoint(resort_id: int, db: Session = Depends(get_golf_db)):
    try:
        ok = crud.delete_resort(db, resort_id)
    except crud.DeleteBlocked as blocked:
        raise HTTPException(
            status_code=409,
            detail={"reason": blocked.reason, "blockers": blocked.blockers},
        )
    if not ok:
        raise HTTPException(status_code=404, detail="Resort not found")


@router.delete("/api/golf-library/courses/{course_id}", status_code=204)
def delete_course_endpoint(course_id: int, db: Session = Depends(get_golf_db)):
    try:
        ok = crud.delete_course(db, course_id)
    except crud.DeleteBlocked as blocked:
        raise HTTPException(
            status_code=409,
            detail={"reason": blocked.reason, "blockers": blocked.blockers},
        )
    if not ok:
        raise HTTPException(status_code=404, detail="Course not found")


@router.patch("/api/golf-library/images/{image_id}")
def update_image_endpoint(
    image_id: int, payload: dict, db: Session = Depends(get_golf_db)
):
    img = crud.update_image(
        db,
        image_id,
        caption=payload.get("caption"),
        display_order=payload.get("display_order"),
    )
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return {
        "id": img.id,
        "caption": img.caption,
        "display_order": img.display_order,
    }


@router.delete("/api/golf-library/images/{image_id}", status_code=204)
def delete_image_endpoint(image_id: int, db: Session = Depends(get_golf_db)):
    if not crud.delete_image(db, image_id):
        raise HTTPException(status_code=404, detail="Image not found")


# Linking (US5)


@router.post("/api/golf-library/resorts/{resort_id}/link-region")
def link_resort_region_endpoint(
    resort_id: int, payload: dict, db: Session = Depends(get_golf_db)
):
    vm_key = payload.get("vacationmap_region_key")
    resort = crud.link_resort_region(db, resort_id, vm_key)
    if resort is None:
        raise HTTPException(status_code=404, detail="Resort not found")
    return crud.resort_to_list_item(db, resort).model_dump()


@router.post("/api/golf-library/courses/{course_id}/link-region")
def link_course_region_endpoint(
    course_id: int, payload: dict, db: Session = Depends(get_golf_db)
):
    vm_key = payload.get("vacationmap_region_key")
    course = crud.link_course_region(db, course_id, vm_key)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return crud.course_to_list_item(db, course).model_dump()


@router.post("/api/golf-library/courses/{course_id}/link-resort")
def link_course_resort_endpoint(
    course_id: int, payload: dict, db: Session = Depends(get_golf_db)
):
    try:
        course = crud.link_course_resort(db, course_id, payload.get("resort_id"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return crud.course_to_list_item(db, course).model_dump()


@router.post("/api/golf-library/images", status_code=201)
def add_image(
    payload: dict,  # {entity_type, entity_id, url, caption?}
    db: Session = Depends(get_golf_db),
):
    entity_type = payload.get("entity_type")
    entity_id = payload.get("entity_id")
    url = payload.get("url")
    caption = payload.get("caption")
    if not all([entity_type, entity_id, url]):
        raise HTTPException(
            status_code=400,
            detail="entity_type, entity_id, and url are required",
        )
    # Validate the URL through the SSRF gate before persisting.
    from . import fetcher as _fetcher

    try:
        _fetcher.safe_head(url)
    except _fetcher.FetchError as e:
        raise HTTPException(status_code=400, detail=f"image URL rejected: {e.reason}")

    try:
        image = crud.add_image(
            db, entity_type=entity_type, entity_id=entity_id, url=url, caption=caption
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": image.id,
        "entity_type": image.entity_type,
        "entity_id": image.entity_id,
        "url": image.url,
        "caption": image.caption,
        "display_order": image.display_order,
    }
