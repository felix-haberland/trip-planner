"""FastAPI router for the yearly planner (F009).

Hierarchy: YearPlan (with `windows`) → YearOption → Slot. Conversation
endpoints remain on `/api/conversations/*` in the trips router, dispatching
on `owner_type='year_plan'`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import crud, schemas
from ..database import get_trips_db
from ..trips import crud as trips_crud
from ..trips import schemas as trip_schemas

router = APIRouter()


# ---------------------------------------------------------------------------
# Year plans
# ---------------------------------------------------------------------------


@router.get("/api/year-plans", response_model=list[schemas.YearPlanSummary])
def list_year_plans(
    year: int | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_trips_db),
):
    plans = crud.list_year_plans(db, year=year, status=status)
    out = []
    for p in plans:
        linked = len(crud.trips_linked_in_plan(db, p.id))
        out.append(crud.year_plan_to_summary(p, linked_trip_count=linked))
    return out


@router.post(
    "/api/year-plans",
    response_model=schemas.YearPlanSummary,
    status_code=201,
)
def create_year_plan(body: schemas.YearPlanCreate, db: Session = Depends(get_trips_db)):
    plan = crud.create_year_plan(db, body)
    return crud.year_plan_to_summary(plan)


@router.get("/api/year-plans/{year_plan_id}", response_model=schemas.YearPlanDetail)
def get_year_plan(year_plan_id: int, db: Session = Depends(get_trips_db)):
    plan = crud.get_year_plan(db, year_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Year plan not found")
    return crud.year_plan_to_detail(plan, db)


@router.patch("/api/year-plans/{year_plan_id}", response_model=schemas.YearPlanSummary)
def update_year_plan(
    year_plan_id: int,
    body: schemas.YearPlanUpdate,
    db: Session = Depends(get_trips_db),
):
    try:
        plan = crud.update_year_plan(db, year_plan_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if plan is None:
        raise HTTPException(status_code=404, detail="Year plan not found")
    return crud.year_plan_to_summary(plan)


@router.delete("/api/year-plans/{year_plan_id}", status_code=204)
def delete_year_plan(
    year_plan_id: int,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_trips_db),
):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Destructive action: pass ?confirm=true to delete a year plan "
                "(cascades to options, slots, and conversations; linked trips are kept)."
            ),
        )
    if not crud.delete_year_plan(db, year_plan_id):
        raise HTTPException(status_code=404, detail="Year plan not found")


# ---------------------------------------------------------------------------
# Year options
# ---------------------------------------------------------------------------


@router.post(
    "/api/year-plans/{year_plan_id}/options",
    response_model=schemas.YearOptionDetail,
    status_code=201,
)
def create_year_option(
    year_plan_id: int,
    body: schemas.YearOptionCreate,
    db: Session = Depends(get_trips_db),
):
    try:
        option = crud.create_year_option(db, year_plan_id, body)
    except LookupError:
        raise HTTPException(status_code=404, detail="Year plan not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud.option_to_detail(option, db)


@router.get(
    "/api/year-options/{option_id}",
    response_model=schemas.YearOptionDetail,
)
def get_year_option(option_id: int, db: Session = Depends(get_trips_db)):
    option = crud.get_year_option(db, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Year option not found")
    return crud.option_to_detail(option, db)


@router.patch(
    "/api/year-options/{option_id}",
    response_model=schemas.YearOptionDetail,
)
def update_year_option(
    option_id: int,
    body: schemas.YearOptionUpdate,
    db: Session = Depends(get_trips_db),
):
    try:
        option = crud.update_year_option(db, option_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if option is None:
        raise HTTPException(status_code=404, detail="Year option not found")
    return crud.option_to_detail(option, db)


@router.delete("/api/year-options/{option_id}", status_code=204)
def delete_year_option(
    option_id: int,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_trips_db),
):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Destructive action: pass ?confirm=true to delete an option "
                "(cascades to its slots; linked trips are kept)."
            ),
        )
    if not crud.delete_year_option(db, option_id):
        raise HTTPException(status_code=404, detail="Year option not found")


@router.post(
    "/api/year-options/{option_id}/fork",
    response_model=schemas.YearOptionDetail,
    status_code=201,
)
def fork_option(
    option_id: int,
    body: schemas.YearOptionCreate,
    db: Session = Depends(get_trips_db),
):
    """Clone an option (with its slots) as a new draft option. `name` in the
    body is required; other fields are ignored."""
    forked = crud.fork_option(db, option_id, body.name)
    if forked is None:
        raise HTTPException(status_code=404, detail="Year option not found")
    return crud.option_to_detail(forked, db)


@router.post(
    "/api/year-options/{option_id}/mark-chosen",
    response_model=schemas.YearOptionDetail,
)
def mark_chosen(option_id: int, db: Session = Depends(get_trips_db)):
    option = crud.mark_option_chosen(db, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Year option not found")
    return crud.option_to_detail(option, db)


@router.post(
    "/api/year-options/{option_id}/unpick",
    response_model=schemas.YearOptionDetail,
)
def unpick(option_id: int, db: Session = Depends(get_trips_db)):
    """Revert a 'chosen' option back to 'draft'."""
    option = crud.unpick_option(db, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Year option not found")
    return crud.option_to_detail(option, db)


# ---------------------------------------------------------------------------
# Slots (under a YearOption)
# ---------------------------------------------------------------------------


@router.post(
    "/api/year-options/{option_id}/slots",
    response_model=schemas.SlotDetail,
    status_code=201,
)
def create_slot(
    option_id: int,
    body: schemas.SlotCreate,
    db: Session = Depends(get_trips_db),
):
    try:
        slot = crud.create_slot(db, option_id, body)
    except LookupError:
        raise HTTPException(status_code=404, detail="Year option not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud.slot_to_detail(slot, db)


@router.patch(
    "/api/slots/{slot_id}",
    response_model=schemas.SlotDetail,
)
def update_slot(
    slot_id: int,
    body: schemas.SlotUpdate,
    db: Session = Depends(get_trips_db),
):
    try:
        slot = crud.update_slot(db, slot_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    return crud.slot_to_detail(slot, db)


@router.delete("/api/slots/{slot_id}", status_code=204)
def delete_slot(
    slot_id: int,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_trips_db),
):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Destructive action: pass ?confirm=true to delete a slot "
                "(linked trip, if any, is kept)."
            ),
        )
    if not crud.delete_slot(db, slot_id):
        raise HTTPException(status_code=404, detail="Slot not found")


@router.post(
    "/api/slots/{slot_id}/accept",
    response_model=schemas.SlotDetail,
)
def accept_slot(slot_id: int, db: Session = Depends(get_trips_db)):
    slot = crud.accept_slot(db, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    return crud.slot_to_detail(slot, db)


@router.post(
    "/api/slots/{slot_id}/unreview",
    response_model=schemas.SlotDetail,
)
def unreview_slot(slot_id: int, db: Session = Depends(get_trips_db)):
    """Revert an accepted trip idea ('open') back to 'proposed'."""
    slot = crud.unreview_slot(db, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    return crud.slot_to_detail(slot, db)


@router.post(
    "/api/slots/{slot_id}/start-trip",
    status_code=201,
)
def start_trip_for_slot(slot_id: int, db: Session = Depends(get_trips_db)):
    existing = crud.get_slot(db, slot_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    trip = crud.start_trip_for_slot(db, slot_id)
    if trip is None:
        raise HTTPException(status_code=400, detail="Could not start trip")
    return {
        "trip_id": trip.id,
        "slot_id": slot_id,
        "trip": trips_crud.trip_to_summary(trip).model_dump(),
    }


@router.post(
    "/api/slots/{slot_id}/link-trip",
    response_model=schemas.SlotDetail,
)
def link_existing_trip(
    slot_id: int,
    body: schemas.SlotLinkTripBody,
    db: Session = Depends(get_trips_db),
):
    if crud.get_slot(db, slot_id) is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    try:
        slot = crud.link_existing_trip_to_slot(db, slot_id, body.trip_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return crud.slot_to_detail(slot, db)


@router.post(
    "/api/slots/{slot_id}/unlink-trip",
    response_model=schemas.SlotDetail,
)
def unlink_trip(slot_id: int, db: Session = Depends(get_trips_db)):
    if crud.get_slot(db, slot_id) is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    slot = crud.unlink_trip_from_slot(db, slot_id)
    return crud.slot_to_detail(slot, db)


# ---------------------------------------------------------------------------
# Conversations (plan-scoped)
# ---------------------------------------------------------------------------


@router.get("/api/year-plans/{year_plan_id}/conversations")
def list_conversations(year_plan_id: int, db: Session = Depends(get_trips_db)):
    if crud.get_year_plan(db, year_plan_id) is None:
        raise HTTPException(status_code=404, detail="Year plan not found")
    convs = crud.list_conversations(db, year_plan_id)
    return [
        {
            "id": c.id,
            "name": c.name,
            "status": c.status or "active",
            "created_at": c.created_at,
            "message_count": len(c.messages),
        }
        for c in convs
    ]


@router.post("/api/year-plans/{year_plan_id}/conversations", status_code=201)
def create_conversation(
    year_plan_id: int,
    body: trip_schemas.ConversationCreate,
    db: Session = Depends(get_trips_db),
):
    if crud.get_year_plan(db, year_plan_id) is None:
        raise HTTPException(status_code=404, detail="Year plan not found")
    conv = crud.create_conversation(db, year_plan_id, body.name)
    return {"id": conv.id, "name": conv.name}
