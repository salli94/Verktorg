from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from ..database import get_db
from ..models import User, Job, Bid, CraftsmanProfile, UserRole, BidStatus, JobStatus
from ..schemas import BidCreate, BidResponse
from ..auth import get_current_user
from ..notification_service import create_and_send_notification

router = APIRouter(prefix="/api/bids", tags=["bids"])


@router.post("/", response_model=BidResponse, status_code=201)
async def create_bid(
    job_id: int,
    data: BidCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile_result = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == current_user.id)
    )
    if profile_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Create a craftsman profile before bidding")

    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.OPEN:
        raise HTTPException(status_code=400, detail="Job is not open for bids")
    if job.customer_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot bid on your own job")

    existing = await db.execute(
        select(Bid).where(Bid.job_id == job_id, Bid.craftsman_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already bid on this job")

    bid = Bid(
        job_id=job_id,
        craftsman_id=current_user.id,
        amount=data.amount,
        message=data.message,
        estimated_hours=data.estimated_hours,
    )
    db.add(bid)
    await db.commit()
    await db.refresh(bid)

    await create_and_send_notification(
        db,
        user_id=job.customer_id,
        type="new_bid",
        message=f"Nýtt tilboð berst í verkefnið \"{job.title}\"",
        data={"job_id": job.id, "bid_id": bid.id, "amount": bid.amount},
    )

    return BidResponse.model_validate(bid)


@router.get("/my")
async def get_my_bids(
    scope: str = Query("auto", pattern=r"^(auto|made|received)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    has_profile_result = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == current_user.id)
    )
    has_craftsman_profile = has_profile_result.scalar_one_or_none() is not None

    if scope == "made" or (scope == "auto" and has_craftsman_profile):
        result = await db.execute(
            select(Bid).where(Bid.craftsman_id == current_user.id)
            .order_by(Bid.created_at.desc())
        )
    else:
        result = await db.execute(
            select(Bid).join(Job).where(Job.customer_id == current_user.id)
            .order_by(Bid.created_at.desc())
        )
    bids = result.scalars().all()
    items = []
    for b in bids:
        c = await db.execute(select(User).where(User.id == b.craftsman_id))
        b.craftsman = c.scalar_one_or_none()
        items.append(BidResponse.model_validate(b))
    return items


@router.put("/{bid_id}/accept")
async def accept_bid(
    bid_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Bid).where(Bid.id == bid_id))
    bid = result.scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")

    job_result = await db.execute(select(Job).where(Job.id == bid.job_id))
    job = job_result.scalar_one_or_none()
    if job.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your job")
    if job.status != JobStatus.OPEN:
        raise HTTPException(status_code=400, detail="Job is not open for bid acceptance")
    if bid.status != BidStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending bids can be accepted")

    transition_result = await db.execute(
        update(Job)
        .where(
            Job.id == bid.job_id,
            Job.customer_id == current_user.id,
            Job.status == JobStatus.OPEN,
        )
        .values(status=JobStatus.IN_PROGRESS)
    )
    if transition_result.rowcount != 1:
        raise HTTPException(status_code=400, detail="A bid has already been accepted for this job")

    bid.status = BidStatus.ACCEPTED
    job.status = JobStatus.IN_PROGRESS

    # Reject all other bids
    other = await db.execute(
        select(Bid).where(Bid.job_id == bid.job_id, Bid.id != bid_id, Bid.status == BidStatus.PENDING)
    )
    for b in other.scalars().all():
        b.status = BidStatus.REJECTED

    await db.commit()

    await create_and_send_notification(
        db,
        user_id=bid.craftsman_id,
        type="bid_accepted",
        message=f"Tilboðið þitt í \"{job.title}\" var samþykkt!",
        data={"job_id": job.id, "bid_id": bid.id},
    )

    return {"ok": True, "message": "Bid accepted, job in progress"}
