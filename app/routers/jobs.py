from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from ..database import get_db
from ..models import User, Job, JobStatus, JobCategory, Bid, BidStatus
from ..schemas import JobCreate, JobUpdate, JobResponse, PaginatedResponse
from ..auth import get_current_user
from ..notification_service import create_and_send_notification

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(
    data: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_job = Job(
        customer_id=current_user.id,
        **data.model_dump(),
    )
    db.add(db_job)
    await db.commit()
    await db.refresh(db_job)
    return JobResponse.model_validate(db_job)


@router.get("/")
async def list_jobs(
    q: str | None = Query(None),
    category: str | None = Query(None),
    location: str | None = Query(None),
    budget_min: float | None = Query(None, ge=0),
    budget_max: float | None = Query(None, ge=0),
    status: str | None = Query(None),
    sort_by: str = Query("newest", pattern=r"^(newest|oldest|budget_asc|budget_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(Job)

    if q:
        query = query.where(
            Job.title.ilike(f"%{q}%") | Job.description.ilike(f"%{q}%")
        )
    if category:
        query = query.where(Job.category == category)
    if location:
        query = query.where(Job.location.ilike(f"%{location}%"))
    if budget_min is not None:
        query = query.where(Job.budget_max >= budget_min)
    if budget_max is not None:
        query = query.where(Job.budget_min <= budget_max)
    if status:
        query = query.where(Job.status == status)
    else:
        query = query.where(Job.status == JobStatus.OPEN)

    sort_map = {
        "newest": desc(Job.created_at),
        "oldest": Job.created_at,
        "budget_asc": Job.budget_min,
        "budget_desc": desc(Job.budget_max),
    }
    query = query.order_by(sort_map.get(sort_by, desc(Job.created_at)))

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    items = []
    for job in jobs:
        c = await db.execute(select(User).where(User.id == job.customer_id))
        job.customer = c.scalar_one_or_none()
        bid_count = await db.execute(
            select(func.count()).select_from(select(Bid).where(Bid.job_id == job.id).subquery())
        )
        job.bid_count = bid_count.scalar() or 0
        items.append(JobResponse.model_validate(job))

    return PaginatedResponse(
        items=[i.model_dump() for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/my")
async def get_my_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Job).where(Job.customer_id == current_user.id)
        .order_by(desc(Job.created_at))
    )
    jobs = result.scalars().all()
    items = []
    for job in jobs:
        bid_count = await db.execute(
            select(func.count()).select_from(select(Bid).where(Bid.job_id == job.id).subquery())
        )
        job.bid_count = bid_count.scalar() or 0
        items.append(JobResponse.model_validate(job))
    return items


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    c = await db.execute(select(User).where(User.id == job.customer_id))
    job.customer = c.scalar_one_or_none()
    bid_count = await db.execute(
        select(func.count()).select_from(select(Bid).where(Bid.job_id == job.id).subquery())
    )
    job.bid_count = bid_count.scalar() or 0
    return JobResponse.model_validate(job)


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    data: JobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    if data.status is not None and data.status != job.status:
        allowed_transition = (
            (data.status == JobStatus.COMPLETED and job.status == JobStatus.IN_PROGRESS)
            or (data.status == JobStatus.CANCELLED and job.status == JobStatus.OPEN)
        )
        if not allowed_transition:
            raise HTTPException(status_code=400, detail="Invalid job status transition")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    await db.commit()
    await db.refresh(job)

    if data.status == JobStatus.COMPLETED:
        bid_result = await db.execute(
            select(Bid).where(Bid.job_id == job.id, Bid.status == BidStatus.ACCEPTED)
        )
        accepted_bid = bid_result.scalar_one_or_none()
        if accepted_bid:
            await create_and_send_notification(
                db,
                user_id=accepted_bid.craftsman_id,
                type="job_completed",
                message=f"Verkefnið \"{job.title}\" hefur verið merkt sem lokið",
                data={"job_id": job.id},
            )

    return JobResponse.model_validate(job)


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your job")
    if job.status != JobStatus.OPEN:
        raise HTTPException(status_code=400, detail="Only open jobs can be deleted")
    await db.delete(job)
    await db.commit()
    return {"ok": True}
