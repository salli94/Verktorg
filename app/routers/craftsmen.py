from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import User, CraftsmanProfile, UserRole, Review
from ..schemas import (
    CraftsmanProfileCreate, CraftsmanProfileResponse, UserResponse, ReviewResponse, PaginatedResponse
)
from ..auth import get_current_user

router = APIRouter(prefix="/api/craftsmen", tags=["craftsmen"])


@router.post("/profile", response_model=CraftsmanProfileResponse, status_code=201)
async def create_profile(
    data: CraftsmanProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.CRAFTSMAN:
        raise HTTPException(status_code=403, detail="Only craftsmen can create profiles")

    existing = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Profile already exists")

    profile = CraftsmanProfile(
        user_id=current_user.id,
        trade_category=data.trade_category,
        license_number=data.license_number,
        description=data.description,
        hourly_rate=data.hourly_rate,
        years_experience=data.years_experience,
        location=data.location,
        portfolio_photos=data.portfolio_photos or [],
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return CraftsmanProfileResponse.model_validate(profile)


@router.put("/profile", response_model=CraftsmanProfileResponse)
async def update_profile(
    data: CraftsmanProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Create one first.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return CraftsmanProfileResponse.model_validate(profile)


@router.get("/profile", response_model=CraftsmanProfileResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return CraftsmanProfileResponse.model_validate(profile)


@router.get("/{user_id}", response_model=CraftsmanProfileResponse)
async def get_craftsman_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Craftsman not found")
    user_result = await db.execute(select(User).where(User.id == user_id))
    profile.user = user_result.scalar_one_or_none()
    return CraftsmanProfileResponse.model_validate(profile)


@router.get("/")
async def list_craftsmen(
    category: str | None = Query(None),
    location: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(CraftsmanProfile).where(CraftsmanProfile.is_available == True)

    if category:
        query = query.where(CraftsmanProfile.trade_category == category)
    if location:
        query = query.where(CraftsmanProfile.location.ilike(f"%{location}%"))

    total_result = await db.execute(query)
    all_items = total_result.scalars().all()
    total = len(all_items)

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    profiles = result.scalars().all()

    items = []
    for p in profiles:
        u = await db.execute(select(User).where(User.id == p.user_id))
        p.user = u.scalar_one_or_none()
        items.append(CraftsmanProfileResponse.model_validate(p))

    return PaginatedResponse(
        items=[i.model_dump() for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{user_id}/reviews")
async def get_craftsman_reviews(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Review).where(Review.reviewee_id == user_id).order_by(Review.created_at.desc())
    )
    reviews = result.scalars().all()
    return [ReviewResponse.model_validate(r) for r in reviews]
