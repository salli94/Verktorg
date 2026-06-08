from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import User, Job, Review, JobStatus, Bid
from ..schemas import ReviewCreate, ReviewResponse
from ..auth import get_current_user

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.post("/", response_model=ReviewResponse, status_code=201)
async def create_review(
    job_id: int,
    data: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Can only review completed jobs")

    # Find the accepted bid to determine reviewee
    bid_result = await db.execute(
        select(Bid).where(Bid.job_id == job_id)
    )
    accepted_bid = None
    for b in bid_result.scalars().all():
        if b.status == "accepted":
            accepted_bid = b
            break

    if not accepted_bid:
        raise HTTPException(status_code=400, detail="No accepted bid found for this job")

    if current_user.id == job.customer_id:
        reviewee_id = accepted_bid.craftsman_id
    elif current_user.id == accepted_bid.craftsman_id:
        reviewee_id = job.customer_id
    else:
        raise HTTPException(status_code=403, detail="Not part of this job")

    existing = await db.execute(
        select(Review).where(
            Review.job_id == job_id,
            Review.reviewer_id == current_user.id,
            Review.reviewee_id == reviewee_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already reviewed")

    review = Review(
        job_id=job_id,
        reviewer_id=current_user.id,
        reviewee_id=reviewee_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return ReviewResponse.model_validate(review)
