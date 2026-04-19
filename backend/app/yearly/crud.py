"""CRUD for the yearly planner (F009).

Hierarchy: YearPlan → YearOption → Slot. Windows live on YearPlan as JSON.
Each slot may optionally bridge to a concrete trip_plan via `trip_plan_id`.
"""

import json
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import models, schemas
from ..trips import crud as trips_crud, models as trips_models


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_weights(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


def _parse_windows(raw: Optional[str]) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return list(data) if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def _windows_as_models(raw: Optional[str]) -> list[schemas.WindowSpec]:
    out = []
    for w in _parse_windows(raw):
        try:
            out.append(schemas.WindowSpec(**w))
        except Exception:
            # Ignore malformed window entries rather than crash the whole view.
            continue
    return out


def _dump_windows(windows: Optional[list[schemas.WindowSpec]]) -> str:
    if not windows:
        return "[]"
    return json.dumps([w.model_dump(mode="json", exclude_none=True) for w in windows])


# =============================================================================
# Year Plans
# =============================================================================


def create_year_plan(db: Session, body: schemas.YearPlanCreate) -> models.YearPlan:
    plan = models.YearPlan(
        year=body.year,
        name=body.name,
        intent=body.intent,
        activity_weights=json.dumps(body.activity_weights or {}),
        windows=_dump_windows(body.windows),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    create_conversation(db, plan.id, "Main")
    return plan


def get_year_plan(db: Session, year_plan_id: int) -> Optional[models.YearPlan]:
    return db.query(models.YearPlan).filter(models.YearPlan.id == year_plan_id).first()


def list_year_plans(
    db: Session, year: Optional[int] = None, status: Optional[str] = None
) -> list[models.YearPlan]:
    q = db.query(models.YearPlan)
    if year is not None:
        q = q.filter(models.YearPlan.year == year)
    if status is not None:
        q = q.filter(models.YearPlan.status == status)
    return q.order_by(
        models.YearPlan.year.desc(), models.YearPlan.updated_at.desc()
    ).all()


def update_year_plan(
    db: Session, year_plan_id: int, body: schemas.YearPlanUpdate
) -> Optional[models.YearPlan]:
    plan = get_year_plan(db, year_plan_id)
    if plan is None:
        return None
    if body.name is not None:
        plan.name = body.name
    if body.intent is not None:
        plan.intent = body.intent
    if body.activity_weights is not None:
        plan.activity_weights = json.dumps(body.activity_weights)
    if body.windows is not None:
        plan.windows = _dump_windows(body.windows)
    if body.status is not None:
        if body.status not in ("draft", "archived"):
            raise ValueError(f"invalid status: {body.status}")
        plan.status = body.status
    plan.updated_at = _utcnow()
    db.commit()
    db.refresh(plan)
    return plan


def delete_year_plan(db: Session, year_plan_id: int) -> bool:
    plan = get_year_plan(db, year_plan_id)
    if plan is None:
        return False
    convs = (
        db.query(trips_models.Conversation)
        .filter(
            trips_models.Conversation.owner_type == "year_plan",
            trips_models.Conversation.owner_id == year_plan_id,
        )
        .all()
    )
    for c in convs:
        db.delete(c)
    db.delete(plan)
    db.commit()
    return True


# =============================================================================
# Year Options
# =============================================================================


_ALLOWED_OPTION_STATUS = ("draft", "chosen", "excluded", "archived")


def create_year_option(
    db: Session, year_plan_id: int, body: schemas.YearOptionCreate
) -> models.YearOption:
    plan = get_year_plan(db, year_plan_id)
    if plan is None:
        raise LookupError("year plan not found")
    status = body.status or "draft"
    if status not in _ALLOWED_OPTION_STATUS:
        raise ValueError(f"invalid option status: {status}")
    if body.created_by not in ("ai", "user"):
        raise ValueError(f"invalid created_by: {body.created_by}")
    position = len(plan.options)
    option = models.YearOption(
        year_plan_id=year_plan_id,
        name=body.name,
        summary=body.summary or "",
        created_by=body.created_by,
        status=status,
        position=position,
    )
    db.add(option)
    plan.updated_at = _utcnow()
    db.commit()
    db.refresh(option)
    return option


def get_year_option(db: Session, option_id: int) -> Optional[models.YearOption]:
    return db.query(models.YearOption).filter(models.YearOption.id == option_id).first()


def list_options_for_plan(db: Session, year_plan_id: int) -> list[models.YearOption]:
    return (
        db.query(models.YearOption)
        .filter(models.YearOption.year_plan_id == year_plan_id)
        .order_by(models.YearOption.position, models.YearOption.created_at)
        .all()
    )


def update_year_option(
    db: Session, option_id: int, body: schemas.YearOptionUpdate
) -> Optional[models.YearOption]:
    option = get_year_option(db, option_id)
    if option is None:
        return None
    if body.name is not None:
        option.name = body.name
    if body.summary is not None:
        option.summary = body.summary
    if body.status is not None:
        if body.status not in _ALLOWED_OPTION_STATUS:
            raise ValueError(f"invalid option status: {body.status}")
        option.status = body.status
        # Clear the reason when leaving excluded.
        if body.status != "excluded":
            option.excluded_reason = None
    if body.excluded_reason is not None:
        option.excluded_reason = body.excluded_reason
    if body.position is not None:
        option.position = body.position
    option.updated_at = _utcnow()
    plan = get_year_plan(db, option.year_plan_id)
    if plan:
        plan.updated_at = _utcnow()
    db.commit()
    db.refresh(option)
    return option


def delete_year_option(db: Session, option_id: int) -> bool:
    option = get_year_option(db, option_id)
    if option is None:
        return False
    plan_id = option.year_plan_id
    db.delete(option)
    plan = get_year_plan(db, plan_id)
    if plan:
        plan.updated_at = _utcnow()
    db.commit()
    return True


def mark_option_chosen(db: Session, option_id: int) -> Optional[models.YearOption]:
    option = get_year_option(db, option_id)
    if option is None:
        return None
    option.status = "chosen"
    option.updated_at = _utcnow()
    plan = get_year_plan(db, option.year_plan_id)
    if plan:
        plan.updated_at = _utcnow()
    db.commit()
    db.refresh(option)
    return option


def unpick_option(db: Session, option_id: int) -> Optional[models.YearOption]:
    """Revert a 'chosen' option back to 'draft'."""
    option = get_year_option(db, option_id)
    if option is None:
        return None
    if option.status == "chosen":
        option.status = "draft"
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
        db.commit()
        db.refresh(option)
    return option


def exclude_option(
    db: Session, option_id: int, reason: str
) -> Optional[models.YearOption]:
    option = get_year_option(db, option_id)
    if option is None:
        return None
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason is required when excluding an option")
    option.status = "excluded"
    option.excluded_reason = reason
    option.updated_at = _utcnow()
    plan = get_year_plan(db, option.year_plan_id)
    if plan:
        plan.updated_at = _utcnow()
    db.commit()
    db.refresh(option)
    return option


def unexclude_option(db: Session, option_id: int) -> Optional[models.YearOption]:
    option = get_year_option(db, option_id)
    if option is None:
        return None
    if option.status == "excluded":
        option.status = "draft"
        option.excluded_reason = None
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
        db.commit()
        db.refresh(option)
    return option


def fork_option(
    db: Session, option_id: int, new_name: str
) -> Optional[models.YearOption]:
    """Clone an option (and its slots) as a new draft option under the same plan.

    Linked trip_plans are **not** duplicated — the fork's slots start unlinked
    so the user can start fresh destination discovery if they want, or link
    them back manually.
    """
    src = get_year_option(db, option_id)
    if src is None:
        return None
    plan = get_year_plan(db, src.year_plan_id)
    if plan is None:
        return None
    new_option = models.YearOption(
        year_plan_id=src.year_plan_id,
        name=new_name,
        summary=src.summary,
        created_by="user",
        status="draft",
        position=len(plan.options),
    )
    db.add(new_option)
    db.flush()
    for s in src.slots:
        db.add(
            models.Slot(
                year_option_id=new_option.id,
                window_index=s.window_index,
                label=s.label,
                theme=s.theme,
                start_year=s.start_year,
                start_month=s.start_month,
                end_year=s.end_year,
                end_month=s.end_month,
                exact_start_date=s.exact_start_date,
                exact_end_date=s.exact_end_date,
                duration_days=s.duration_days,
                climate_hint=s.climate_hint,
                constraints_note=s.constraints_note,
                activity_weights=s.activity_weights,
                status=s.status,
                position=s.position,
            )
        )
    plan.updated_at = _utcnow()
    db.commit()
    db.refresh(new_option)
    return new_option


# =============================================================================
# Slots
# =============================================================================


def _month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _slot_span(slot_or_body) -> tuple[int, int, Optional[date], Optional[date]]:
    return (
        _month_index(slot_or_body.start_year, slot_or_body.start_month),
        _month_index(slot_or_body.end_year, slot_or_body.end_month),
        slot_or_body.exact_start_date,
        slot_or_body.exact_end_date,
    )


def _ranges_overlap(
    a_start: int,
    a_end: int,
    a_start_date: Optional[date],
    a_end_date: Optional[date],
    b_start: int,
    b_end: int,
    b_start_date: Optional[date],
    b_end_date: Optional[date],
) -> bool:
    if all([a_start_date, a_end_date, b_start_date, b_end_date]):
        return not (a_end_date < b_start_date or b_end_date < a_start_date)
    return not (a_end < b_start or b_end < a_start)


def _check_no_overlap(
    db: Session,
    year_option_id: int,
    candidate,
    excluding_slot_id: Optional[int] = None,
) -> None:
    c_start, c_end, c_sd, c_ed = _slot_span(candidate)
    if c_end < c_start:
        raise ValueError("slot end is before slot start")
    if c_sd and c_ed and c_ed < c_sd:
        raise ValueError("slot exact_end_date is before exact_start_date")
    existing = (
        db.query(models.Slot).filter(models.Slot.year_option_id == year_option_id).all()
    )
    for s in existing:
        if excluding_slot_id is not None and s.id == excluding_slot_id:
            continue
        s_start, s_end, s_sd, s_ed = _slot_span(s)
        if _ranges_overlap(c_start, c_end, c_sd, c_ed, s_start, s_end, s_sd, s_ed):
            raise ValueError(
                f"slot overlaps existing slot id={s.id} in this option "
                f"({s.start_year}-{s.start_month:02d} → {s.end_year}-{s.end_month:02d})"
            )


_ALLOWED_SLOT_STATUS = ("open", "proposed", "excluded", "archived")


def _resolve_window(plan: models.YearPlan, window_index: int) -> dict:
    windows = _parse_windows(plan.windows)
    if window_index < 0 or window_index >= len(windows):
        raise ValueError(
            f"window_index {window_index} out of range (plan has {len(windows)} windows)"
        )
    return windows[window_index]


def _inherit_dates_from_window(body: schemas.SlotCreate, window: dict) -> dict:
    """Return a dict of the four {start,end}_{year,month} values for a slot,
    filling in anything the caller left blank from the window's dates."""
    from datetime import date as _date

    def _parse(v):
        if isinstance(v, _date):
            return v
        if isinstance(v, str) and v:
            return _date.fromisoformat(v)
        return None

    w_start = _parse(window.get("start_date"))
    w_end = _parse(window.get("end_date"))
    if w_start is None or w_end is None:
        raise ValueError(
            f"window #{body.window_index} is missing start_date/end_date; "
            "cannot inherit slot dates"
        )
    return {
        "start_year": body.start_year if body.start_year is not None else w_start.year,
        "start_month": (
            body.start_month if body.start_month is not None else w_start.month
        ),
        "end_year": body.end_year if body.end_year is not None else w_end.year,
        "end_month": body.end_month if body.end_month is not None else w_end.month,
    }


def create_slot(
    db: Session, year_option_id: int, body: schemas.SlotCreate
) -> models.Slot:
    option = get_year_option(db, year_option_id)
    if option is None:
        raise LookupError("year option not found")
    plan = get_year_plan(db, option.year_plan_id)
    if plan is None:
        raise LookupError("year plan not found")

    window = _resolve_window(plan, body.window_index)
    dates = _inherit_dates_from_window(body, window)

    status = body.status or "open"
    if status not in _ALLOWED_SLOT_STATUS:
        raise ValueError(f"invalid slot status: {status}")

    # Multiple ideas per (option, window) are legitimate (alternatives inside
    # one option); no overlap check between siblings in the same cell.

    slot = models.Slot(
        year_option_id=year_option_id,
        window_index=body.window_index,
        label=body.label,
        theme=body.theme or "",
        start_year=dates["start_year"],
        start_month=dates["start_month"],
        end_year=dates["end_year"],
        end_month=dates["end_month"],
        exact_start_date=body.exact_start_date,
        exact_end_date=body.exact_end_date,
        duration_days=body.duration_days,
        climate_hint=body.climate_hint,
        constraints_note=body.constraints_note,
        activity_weights=json.dumps(body.activity_weights or {}),
        status=status,
    )
    db.add(slot)
    option.updated_at = _utcnow()
    plan.updated_at = _utcnow()
    db.commit()
    db.refresh(slot)
    return slot


def get_slot(db: Session, slot_id: int) -> Optional[models.Slot]:
    return db.query(models.Slot).filter(models.Slot.id == slot_id).first()


def update_slot(
    db: Session, slot_id: int, body: schemas.SlotUpdate
) -> Optional[models.Slot]:
    slot = get_slot(db, slot_id)
    if slot is None:
        return None

    time_fields_touched = any(
        v is not None
        for v in (
            body.start_year,
            body.start_month,
            body.end_year,
            body.end_month,
            body.exact_start_date,
            body.exact_end_date,
        )
    )
    if body.label is not None:
        slot.label = body.label
    if body.theme is not None:
        slot.theme = body.theme
    if body.window_index is not None:
        slot.window_index = body.window_index
    if body.start_year is not None:
        slot.start_year = body.start_year
    if body.start_month is not None:
        slot.start_month = body.start_month
    if body.end_year is not None:
        slot.end_year = body.end_year
    if body.end_month is not None:
        slot.end_month = body.end_month
    if body.exact_start_date is not None:
        slot.exact_start_date = body.exact_start_date
    if body.exact_end_date is not None:
        slot.exact_end_date = body.exact_end_date
    if body.duration_days is not None:
        slot.duration_days = body.duration_days
    if body.climate_hint is not None:
        slot.climate_hint = body.climate_hint
    if body.constraints_note is not None:
        slot.constraints_note = body.constraints_note
    if body.activity_weights is not None:
        slot.activity_weights = json.dumps(body.activity_weights)
    if body.status is not None:
        if body.status not in _ALLOWED_SLOT_STATUS:
            raise ValueError(f"invalid slot status: {body.status}")
        slot.status = body.status
        if body.status != "excluded":
            slot.excluded_reason = None
    if body.position is not None:
        slot.position = body.position
    # Date overlap between alternatives in the same option is allowed.
    _ = time_fields_touched

    slot.updated_at = _utcnow()
    option = get_year_option(db, slot.year_option_id)
    if option:
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
    db.commit()
    db.refresh(slot)
    return slot


def delete_slot(db: Session, slot_id: int) -> bool:
    slot = get_slot(db, slot_id)
    if slot is None:
        return False
    option_id = slot.year_option_id
    db.delete(slot)
    option = get_year_option(db, option_id)
    if option:
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
    db.commit()
    return True


def accept_slot(db: Session, slot_id: int) -> Optional[models.Slot]:
    slot = get_slot(db, slot_id)
    if slot is None:
        return None
    if slot.status == "proposed":
        slot.status = "open"
        slot.updated_at = _utcnow()
        option = get_year_option(db, slot.year_option_id)
        if option:
            option.updated_at = _utcnow()
            plan = get_year_plan(db, option.year_plan_id)
            if plan:
                plan.updated_at = _utcnow()
        db.commit()
        db.refresh(slot)
    return slot


def unreview_slot(db: Session, slot_id: int) -> Optional[models.Slot]:
    """Revert an accepted trip idea ('open') back to 'proposed'."""
    slot = get_slot(db, slot_id)
    if slot is None:
        return None
    if slot.status == "open":
        slot.status = "proposed"
        slot.updated_at = _utcnow()
        option = get_year_option(db, slot.year_option_id)
        if option:
            option.updated_at = _utcnow()
            plan = get_year_plan(db, option.year_plan_id)
            if plan:
                plan.updated_at = _utcnow()
        db.commit()
        db.refresh(slot)
    return slot


def exclude_slot(db: Session, slot_id: int, reason: str) -> Optional[models.Slot]:
    slot = get_slot(db, slot_id)
    if slot is None:
        return None
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason is required when excluding a trip idea")
    slot.status = "excluded"
    slot.excluded_reason = reason
    slot.updated_at = _utcnow()
    option = get_year_option(db, slot.year_option_id)
    if option:
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
    db.commit()
    db.refresh(slot)
    return slot


def unexclude_slot(db: Session, slot_id: int) -> Optional[models.Slot]:
    slot = get_slot(db, slot_id)
    if slot is None:
        return None
    if slot.status == "excluded":
        slot.status = "open"
        slot.excluded_reason = None
        slot.updated_at = _utcnow()
        option = get_year_option(db, slot.year_option_id)
        if option:
            option.updated_at = _utcnow()
            plan = get_year_plan(db, option.year_plan_id)
            if plan:
                plan.updated_at = _utcnow()
        db.commit()
        db.refresh(slot)
    return slot


# =============================================================================
# Slot → Trip bridge
# =============================================================================


_MONTH_LOOKUP = {
    1: "jan",
    2: "feb",
    3: "mar",
    4: "apr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "aug",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dec",
}


def _derive_target_month(slot: models.Slot) -> Optional[str]:
    return _MONTH_LOOKUP.get(slot.start_month)


def start_trip_for_slot(db: Session, slot_id: int) -> Optional[trips_models.TripPlan]:
    slot = get_slot(db, slot_id)
    if slot is None:
        return None
    if slot.trip_plan_id is not None:
        existing = (
            db.query(trips_models.TripPlan)
            .filter(trips_models.TripPlan.id == slot.trip_plan_id)
            .first()
        )
        if existing is not None:
            return existing

    name = slot.label or f"Slot {slot.start_year}-{slot.start_month:02d}"
    description_bits = []
    if slot.theme:
        description_bits.append(slot.theme)
    if slot.constraints_note:
        description_bits.append(f"Constraints: {slot.constraints_note}")
    description = "\n\n".join(description_bits)
    weights: dict = {}
    if slot.activity_weights:
        try:
            weights = json.loads(slot.activity_weights) or {}
        except (ValueError, TypeError):
            weights = {}

    trip = trips_models.TripPlan(
        name=name,
        description=description,
        target_month=_derive_target_month(slot),
        activity_weights=json.dumps(weights),
    )
    db.add(trip)
    db.flush()

    slot.trip_plan_id = trip.id
    slot.updated_at = _utcnow()
    option = get_year_option(db, slot.year_option_id)
    if option:
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
    trips_crud.create_conversation(db, trip.id, "Main")
    db.commit()
    db.refresh(trip)
    db.refresh(slot)
    return trip


def link_existing_trip_to_slot(
    db: Session, slot_id: int, trip_id: int
) -> Optional[models.Slot]:
    slot = get_slot(db, slot_id)
    if slot is None:
        return None
    trip = (
        db.query(trips_models.TripPlan)
        .filter(trips_models.TripPlan.id == trip_id)
        .first()
    )
    if trip is None:
        raise LookupError("trip not found")
    slot.trip_plan_id = trip.id
    slot.updated_at = _utcnow()
    option = get_year_option(db, slot.year_option_id)
    if option:
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
    db.commit()
    db.refresh(slot)
    return slot


def unlink_trip_from_slot(db: Session, slot_id: int) -> Optional[models.Slot]:
    slot = get_slot(db, slot_id)
    if slot is None:
        return None
    slot.trip_plan_id = None
    slot.updated_at = _utcnow()
    option = get_year_option(db, slot.year_option_id)
    if option:
        option.updated_at = _utcnow()
        plan = get_year_plan(db, option.year_plan_id)
        if plan:
            plan.updated_at = _utcnow()
    db.commit()
    db.refresh(slot)
    return slot


# =============================================================================
# Conversations (polymorphic; owner_type='year_plan')
# =============================================================================


def create_conversation(
    db: Session, year_plan_id: int, name: str = "Main"
) -> trips_models.Conversation:
    conv = trips_models.Conversation(
        owner_type="year_plan", owner_id=year_plan_id, name=name
    )
    db.add(conv)
    plan = get_year_plan(db, year_plan_id)
    if plan:
        plan.updated_at = _utcnow()
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations(
    db: Session, year_plan_id: int
) -> list[trips_models.Conversation]:
    return (
        db.query(trips_models.Conversation)
        .filter(
            trips_models.Conversation.owner_type == "year_plan",
            trips_models.Conversation.owner_id == year_plan_id,
        )
        .order_by(trips_models.Conversation.created_at.asc())
        .all()
    )


# =============================================================================
# Surface trips linked to this year plan (via any option's slots)
# =============================================================================


def trips_in_year(db: Session, year: int) -> list[trips_models.TripPlan]:
    year_token = str(year)
    return (
        db.query(trips_models.TripPlan)
        .filter(
            or_(
                trips_models.TripPlan.target_month.contains(year_token),
                trips_models.TripPlan.name.contains(year_token),
                trips_models.TripPlan.description.contains(year_token),
            )
        )
        .all()
    )


def trips_linked_in_plan(db: Session, year_plan_id: int) -> list[trips_models.TripPlan]:
    option_ids = [
        o.id
        for o in (
            db.query(models.YearOption)
            .filter(models.YearOption.year_plan_id == year_plan_id)
            .all()
        )
    ]
    if not option_ids:
        return []
    linked_ids = [
        s.trip_plan_id
        for s in (
            db.query(models.Slot)
            .filter(models.Slot.year_option_id.in_(option_ids))
            .all()
        )
        if s.trip_plan_id is not None
    ]
    linked_ids = list({i for i in linked_ids if i is not None})
    if not linked_ids:
        return []
    return (
        db.query(trips_models.TripPlan)
        .filter(trips_models.TripPlan.id.in_(linked_ids))
        .all()
    )


def trips_linked_in_option(db: Session, option_id: int) -> list[trips_models.TripPlan]:
    linked_ids = [
        s.trip_plan_id
        for s in (
            db.query(models.Slot).filter(models.Slot.year_option_id == option_id).all()
        )
        if s.trip_plan_id is not None
    ]
    if not linked_ids:
        return []
    return (
        db.query(trips_models.TripPlan)
        .filter(trips_models.TripPlan.id.in_(linked_ids))
        .all()
    )


def slot_for_trip(db: Session, trip_id: int) -> Optional[models.Slot]:
    """Reverse lookup used by trips/chat to inject slot context."""
    return db.query(models.Slot).filter(models.Slot.trip_plan_id == trip_id).first()


# =============================================================================
# Serializers
# =============================================================================


def _trip_summary(
    db: Session, trip_id: Optional[int]
) -> Optional[schemas.LinkedTripSummary]:
    if trip_id is None:
        return None
    trip = (
        db.query(trips_models.TripPlan)
        .filter(trips_models.TripPlan.id == trip_id)
        .first()
    )
    if trip is None:
        return None
    shortlisted = (
        db.query(trips_models.ShortlistedDestination)
        .filter(trips_models.ShortlistedDestination.trip_id == trip.id)
        .count()
    )
    return schemas.LinkedTripSummary(
        id=trip.id,
        name=trip.name,
        status=trip.status,
        target_month=trip.target_month,
        shortlisted_count=shortlisted,
    )


def slot_to_detail(slot: models.Slot, db: Session) -> schemas.SlotDetail:
    return schemas.SlotDetail(
        id=slot.id,
        year_option_id=slot.year_option_id,
        window_index=slot.window_index,
        label=slot.label,
        theme=slot.theme or "",
        start_year=slot.start_year,
        start_month=slot.start_month,
        end_year=slot.end_year,
        end_month=slot.end_month,
        exact_start_date=slot.exact_start_date,
        exact_end_date=slot.exact_end_date,
        duration_days=slot.duration_days,
        climate_hint=slot.climate_hint,
        constraints_note=slot.constraints_note,
        activity_weights=_parse_weights(slot.activity_weights),
        status=slot.status,
        excluded_reason=slot.excluded_reason,
        position=slot.position,
        trip_plan_id=slot.trip_plan_id,
        trip=_trip_summary(db, slot.trip_plan_id),
        created_at=slot.created_at,
        updated_at=slot.updated_at,
    )


def option_to_detail(
    option: models.YearOption, db: Session
) -> schemas.YearOptionDetail:
    return schemas.YearOptionDetail(
        id=option.id,
        year_plan_id=option.year_plan_id,
        name=option.name,
        summary=option.summary or "",
        created_by=option.created_by,
        status=option.status,
        excluded_reason=option.excluded_reason,
        position=option.position,
        slots=[slot_to_detail(s, db) for s in option.slots],
        created_at=option.created_at,
        updated_at=option.updated_at,
    )


def option_to_summary(
    option: models.YearOption, db: Session
) -> schemas.YearOptionSummary:
    linked = trips_linked_in_option(db, option.id)
    return schemas.YearOptionSummary(
        id=option.id,
        year_plan_id=option.year_plan_id,
        name=option.name,
        summary=option.summary or "",
        created_by=option.created_by,
        status=option.status,
        position=option.position,
        slot_count=len(option.slots),
        linked_trip_count=len(linked),
        created_at=option.created_at,
        updated_at=option.updated_at,
    )


def year_plan_to_summary(
    plan: models.YearPlan, linked_trip_count: int = 0
) -> schemas.YearPlanSummary:
    return schemas.YearPlanSummary(
        id=plan.id,
        year=plan.year,
        name=plan.name,
        intent=plan.intent or "",
        activity_weights=_parse_weights(plan.activity_weights),
        windows=_windows_as_models(plan.windows),
        status=plan.status,
        option_count=len(plan.options),
        linked_trip_count=linked_trip_count,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def year_plan_to_detail(plan: models.YearPlan, db: Session) -> schemas.YearPlanDetail:
    conversations = [
        {
            "id": c.id,
            "name": c.name,
            "status": c.status or "active",
            "created_at": c.created_at,
            "message_count": len(c.messages),
        }
        for c in list_conversations(db, plan.id)
    ]
    attachable = trips_in_year(db, plan.year)
    linked = trips_linked_in_plan(db, plan.id)
    linked_ids = {t.id for t in linked}
    attachable_ids = [t.id for t in attachable if t.id not in linked_ids]
    return schemas.YearPlanDetail(
        id=plan.id,
        year=plan.year,
        name=plan.name,
        intent=plan.intent or "",
        activity_weights=_parse_weights(plan.activity_weights),
        windows=_windows_as_models(plan.windows),
        status=plan.status,
        options=[option_to_detail(o, db) for o in plan.options],
        conversations=conversations,
        attachable_trip_ids=attachable_ids,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )
