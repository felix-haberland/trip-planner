"""Tests for golf library CRUD (FR-003a dedup, FR-001/002 creation)."""

from __future__ import annotations

import pytest

from app.golf import crud, schemas


def _resort(**overrides) -> schemas.GolfResortCreate:
    base = dict(name="Monte Rei Golf & Country Club", country_code="PT")
    base.update(overrides)
    return schemas.GolfResortCreate(**base)


def _course(**overrides) -> schemas.GolfCourseCreate:
    base = dict(name="Old Course", country_code="GB")
    base.update(overrides)
    return schemas.GolfCourseCreate(**base)


# --- Resort creation ----------------------------------------------------


def test_create_resort_basic(trips_session):
    r = crud.create_resort(trips_session, _resort())
    assert r.id is not None
    assert r.name_norm == "monte rei golf and country club"
    assert r.country_code == "PT"


def test_create_resort_persists_json_fields(trips_session):
    r = crud.create_resort(
        trips_session,
        _resort(best_months=[4, 5, 10], tags=["luxury", "portugal"], amenities=["spa"]),
    )
    import json

    assert json.loads(r.best_months) == [4, 5, 10]
    assert json.loads(r.tags) == ["luxury", "portugal"]
    assert json.loads(r.amenities) == ["spa"]


def test_create_resort_with_attached_courses(trips_session):
    r = crud.create_resort(
        trips_session,
        _resort(
            courses=[
                _course(name="North Course", country_code=None),
                _course(name="South Course", country_code=None),
            ]
        ),
    )
    from app import models

    courses = (
        trips_session.query(models.GolfCourse)
        .filter(models.GolfCourse.resort_id == r.id)
        .all()
    )
    assert len(courses) == 2
    assert {c.name for c in courses} == {"North Course", "South Course"}
    # Attached courses don't require their own country_code (inherit from parent)
    for c in courses:
        assert c.country_code is None


def test_create_resort_with_images(trips_session):
    r = crud.create_resort(
        trips_session,
        _resort(image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"]),
    )
    images = crud.get_images_for(trips_session, "resort", r.id)
    assert [i.url for i in images] == [
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",
    ]
    assert [i.display_order for i in images] == [0, 1]


# --- Dedup (FR-003a) ---------------------------------------------------


def test_resort_dedup_triggers_on_exact_match(trips_session):
    crud.create_resort(trips_session, _resort())
    with pytest.raises(crud.DuplicateEntity) as exc:
        crud.create_resort(trips_session, _resort())
    assert exc.value.existing is not None


def test_resort_dedup_case_and_punctuation_variants(trips_session):
    crud.create_resort(trips_session, _resort(name="Monte Rei Golf & Country Club"))
    variants = [
        "MONTE REI GOLF & COUNTRY CLUB",
        "monte rei golf & country club",
        "Monte-Rei  Golf & Country Club!",
        "Monte Rei Golf and Country Club",  # & -> and
    ]
    for v in variants:
        with pytest.raises(crud.DuplicateEntity):
            crud.create_resort(trips_session, _resort(name=v))


def test_resort_dedup_respects_country_boundary(trips_session):
    crud.create_resort(trips_session, _resort(name="Golf Club", country_code="PT"))
    # Same normalized name, different country → NOT a duplicate
    r2 = crud.create_resort(trips_session, _resort(name="Golf Club", country_code="ES"))
    assert r2.id is not None


def test_resort_dedup_bypassed_with_force(trips_session):
    crud.create_resort(trips_session, _resort())
    # force=True allows a duplicate to be saved
    r2 = crud.create_resort(trips_session, _resort(), force=True)
    assert r2.id is not None


def test_resort_dedup_diacritics_normalized(trips_session):
    crud.create_resort(
        trips_session, _resort(name="Nürburgring Golf", country_code="DE")
    )
    with pytest.raises(crud.DuplicateEntity):
        crud.create_resort(
            trips_session, _resort(name="Nurburgring Golf", country_code="DE")
        )


# --- Course creation + standalone rules --------------------------------


def test_standalone_course_requires_country(trips_session):
    with pytest.raises(ValueError) as exc:
        crud.create_course(
            trips_session,
            schemas.GolfCourseCreate(name="Mystery Links"),
        )
    assert "country_code" in str(exc.value)


def test_standalone_course_ok_with_country(trips_session):
    c = crud.create_course(trips_session, _course())
    assert c.id is not None
    assert c.resort_id is None
    assert c.country_code == "GB"
    assert c.name_norm == "old course"


def test_attached_course_inherits_country_for_dedup(trips_session):
    resort = crud.create_resort(
        trips_session, _resort(name="Quinta do Lago", country_code="PT")
    )
    c = crud.create_course(
        trips_session,
        schemas.GolfCourseCreate(
            name="North Course", resort_id=resort.id
        ),  # no country_code
    )
    assert c.resort_id == resort.id
    # Duplicate check uses inherited country
    with pytest.raises(crud.DuplicateEntity):
        crud.create_course(
            trips_session,
            schemas.GolfCourseCreate(name="North Course", resort_id=resort.id),
        )


# --- find_resort_by_name_norm -----------------------------------------


def test_find_resort_by_name_norm(trips_session):
    crud.create_resort(
        trips_session, _resort(name="Son Gual Mallorca", country_code="ES")
    )
    assert (
        crud.find_resort_by_name_norm(trips_session, "SON GUAL MALLORCA").country_code
        == "ES"
    )
    assert (
        crud.find_resort_by_name_norm(trips_session, "son-gual mallorca").name
        == "Son Gual Mallorca"
    )
    assert crud.find_resort_by_name_norm(trips_session, "Nonexistent") is None


# --- Images ---------------------------------------------------------


def test_add_image_auto_increments_display_order(trips_session):
    r = crud.create_resort(trips_session, _resort())
    i1 = crud.add_image(
        trips_session, entity_type="resort", entity_id=r.id, url="https://a.com/1"
    )
    i2 = crud.add_image(
        trips_session, entity_type="resort", entity_id=r.id, url="https://a.com/2"
    )
    i3 = crud.add_image(
        trips_session, entity_type="resort", entity_id=r.id, url="https://a.com/3"
    )
    assert i1.display_order == 0
    assert i2.display_order == 1
    assert i3.display_order == 2


def test_add_image_rejects_unknown_parent(trips_session):
    with pytest.raises(ValueError):
        crud.add_image(
            trips_session, entity_type="resort", entity_id=99999, url="https://a.com/x"
        )


# --- Update + prevent-delete (US4) ---------------------------------


def test_update_resort_recomputes_name_norm(trips_session):
    r = crud.create_resort(trips_session, _resort())
    updated = crud.update_resort(
        trips_session, r.id, schemas.GolfResortPatch(name="Monte Rei — Grande")
    )
    assert updated.name == "Monte Rei — Grande"
    assert updated.name_norm == "monte rei grande"


def test_update_resort_preserves_unset_fields(trips_session):
    r = crud.create_resort(
        trips_session, _resort(hotel_type="luxury", price_category="€€€€")
    )
    crud.update_resort(trips_session, r.id, schemas.GolfResortPatch(rank_rating=95))
    refreshed = crud.get_resort(trips_session, r.id)
    assert refreshed.hotel_type == "luxury"
    assert refreshed.price_category == "€€€€"
    assert refreshed.rank_rating == 95


def test_delete_resort_when_no_blockers(trips_session):
    r = crud.create_resort(trips_session, _resort())
    ok = crud.delete_resort(trips_session, r.id)
    assert ok is True
    assert crud.get_resort(trips_session, r.id) is None


def test_delete_resort_blocked_by_attached_course(trips_session):
    r = crud.create_resort(trips_session, _resort())
    crud.create_course(
        trips_session,
        schemas.GolfCourseCreate(name="North", resort_id=r.id),
    )
    with pytest.raises(crud.DeleteBlocked) as exc:
        crud.delete_resort(trips_session, r.id)
    assert exc.value.reason == "has_attached_courses"
    assert len(exc.value.blockers["attached_courses"]) == 1
    assert exc.value.blockers["attached_courses"][0]["name"] == "North"


def test_delete_resort_blocked_by_shortlist(trips_session):
    r = crud.create_resort(trips_session, _resort())
    trip = crud.create_trip(
        trips_session, schemas.TripCreate(name="T", description="d")
    )
    crud.add_suggested(
        trips_session,
        trip_id=trip.id,
        destination_name="Monte Rei",
        ai_reasoning="x",
        resort_id=r.id,
    )
    with pytest.raises(crud.DeleteBlocked) as exc:
        crud.delete_resort(trips_session, r.id)
    assert exc.value.reason == "referenced_by_shortlist"
    refs = exc.value.blockers["shortlist_references"]
    assert len(refs) == 1
    assert refs[0]["trip_name"] == "T"
    assert refs[0]["section"] == "suggested"


def test_delete_resort_blocked_both(trips_session):
    r = crud.create_resort(trips_session, _resort())
    crud.create_course(
        trips_session, schemas.GolfCourseCreate(name="North", resort_id=r.id)
    )
    trip = crud.create_trip(
        trips_session, schemas.TripCreate(name="T", description="d")
    )
    crud.add_suggested(
        trips_session,
        trip_id=trip.id,
        destination_name="Monte Rei",
        ai_reasoning="x",
        resort_id=r.id,
    )
    with pytest.raises(crud.DeleteBlocked) as exc:
        crud.delete_resort(trips_session, r.id)
    assert exc.value.reason == "both"


def test_delete_course_blocked_by_shortlist(trips_session):
    c = crud.create_course(trips_session, _course())
    trip = crud.create_trip(
        trips_session, schemas.TripCreate(name="T", description="d")
    )
    crud.add_suggested(
        trips_session,
        trip_id=trip.id,
        destination_name="Old Course",
        ai_reasoning="x",
        course_id=c.id,
    )
    with pytest.raises(crud.DeleteBlocked) as exc:
        crud.delete_course(trips_session, c.id)
    assert exc.value.reason == "referenced_by_shortlist"


def test_delete_after_removing_blockers(trips_session):
    r = crud.create_resort(trips_session, _resort())
    child = crud.create_course(
        trips_session, schemas.GolfCourseCreate(name="North", resort_id=r.id)
    )
    with pytest.raises(crud.DeleteBlocked):
        crud.delete_resort(trips_session, r.id)
    # Unlink the course (convert to standalone with its own country)
    crud.update_course(
        trips_session, child.id, schemas.GolfCoursePatch(country_code="PT")
    )
    crud.link_course_resort(trips_session, child.id, None)
    # Now delete succeeds
    assert crud.delete_resort(trips_session, r.id) is True


def test_delete_cascades_images(trips_session):
    r = crud.create_resort(
        trips_session, _resort(image_urls=["https://x.com/1", "https://x.com/2"])
    )
    imgs = crud.get_images_for(trips_session, "resort", r.id)
    assert len(imgs) == 2
    crud.delete_resort(trips_session, r.id)
    assert crud.get_images_for(trips_session, "resort", r.id) == []


# --- Linking (US5) -------------------------------------------------


def test_link_resort_region_sets_vm_key(trips_session):
    r = crud.create_resort(trips_session, _resort())
    crud.link_resort_region(trips_session, r.id, "PT:Algarve")
    refreshed = crud.get_resort(trips_session, r.id)
    assert refreshed.vacationmap_region_key == "PT:Algarve"


def test_link_course_to_resort_and_unlink(trips_session):
    r = crud.create_resort(trips_session, _resort(country_code="PT"))
    c = crud.create_course(trips_session, _course(country_code="PT"))
    crud.link_course_resort(trips_session, c.id, r.id)
    assert crud.get_course(trips_session, c.id).resort_id == r.id
    # Unlink — course still has country_code, so it's allowed
    crud.link_course_resort(trips_session, c.id, None)
    assert crud.get_course(trips_session, c.id).resort_id is None


def test_unlink_course_without_country_rejected(trips_session):
    """If a course has no country_code (inherited from parent), unlinking
    is refused — the course would be orphaned with no country."""
    r = crud.create_resort(trips_session, _resort(country_code="PT"))
    c = crud.create_course(
        trips_session, schemas.GolfCourseCreate(name="Hidden", resort_id=r.id)
    )
    with pytest.raises(ValueError, match="country_code"):
        crud.link_course_resort(trips_session, c.id, None)
