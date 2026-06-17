from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import date
from ..database import get_db
from ..models import User, CraftsmanProfile, AvailabilitySlot, UserRole
from ..schemas import AvailabilitySlotCreate, AvailabilitySlotResponse
from ..auth import get_current_user

router = APIRouter(prefix="/api/availability", tags=["availability"])


async def _get_craftsman_profile(user: User, db: AsyncSession):
    result = await db.execute(select(CraftsmanProfile).where(CraftsmanProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Create a craftsman profile first")
    return profile


async def _ensure_slot_available(profile_id: int, data: AvailabilitySlotCreate, db: AsyncSession):
    overlap_result = await db.execute(
        select(AvailabilitySlot).where(
            AvailabilitySlot.craftsman_id == profile_id,
            AvailabilitySlot.date == data.date,
            AvailabilitySlot.start_time < data.end_time,
            AvailabilitySlot.end_time > data.start_time,
        )
    )
    if overlap_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Availability slot overlaps an existing slot")


@router.post("/", response_model=AvailabilitySlotResponse, status_code=201)
async def add_slot(
    data: AvailabilitySlotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await _get_craftsman_profile(current_user, db)
    await _ensure_slot_available(profile.id, data, db)
    slot = AvailabilitySlot(
        craftsman_id=profile.id,
        date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return AvailabilitySlotResponse.model_validate(slot)


@router.post("/bulk")
async def add_bulk_slots(
    slots: list[AvailabilitySlotCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await _get_craftsman_profile(current_user, db)
    created = []
    for s in slots:
        await _ensure_slot_available(profile.id, s, db)
        slot = AvailabilitySlot(
            craftsman_id=profile.id,
            date=s.date,
            start_time=s.start_time,
            end_time=s.end_time,
        )
        db.add(slot)
        created.append(slot)
    await db.commit()
    for s in created:
        await db.refresh(s)
    return [AvailabilitySlotResponse.model_validate(s) for s in created]


@router.get("/")
async def get_availability(
    craftsman_user_id: int = Query(...),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == craftsman_user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return []

    query = select(AvailabilitySlot).where(
        AvailabilitySlot.craftsman_id == profile.id,
        AvailabilitySlot.is_booked == False,
    )
    if from_date:
        query = query.where(AvailabilitySlot.date >= from_date)
    if to_date:
        query = query.where(AvailabilitySlot.date <= to_date)
    query = query.order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)

    result = await db.execute(query)
    slots = result.scalars().all()
    return [AvailabilitySlotResponse.model_validate(s) for s in slots]


@router.delete("/{slot_id}")
async def delete_slot(
    slot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await _get_craftsman_profile(current_user, db)
    result = await db.execute(
        select(AvailabilitySlot).where(
            AvailabilitySlot.id == slot_id,
            AvailabilitySlot.craftsman_id == profile.id,
        )
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.is_booked:
        raise HTTPException(status_code=400, detail="Cannot delete a booked slot")
    await db.delete(slot)
    await db.commit()
    return {"ok": True}
