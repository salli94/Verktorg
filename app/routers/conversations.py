import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Bid,
    BidStatus,
    ConversationMessage,
    ConversationQuote,
    ConversationStatus,
    ConversationThread,
    CraftsmanProfile,
    Job,
    JobStatus,
    QuoteStatus,
    User,
)
from ..notification_service import create_and_send_notification
from ..schemas import (
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationQuoteCreate,
    ConversationQuoteResponse,
    ConversationThreadCreate,
    ConversationThreadResponse,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

THREAD_LIMIT_PER_DAY = 5
MESSAGE_LIMIT_PER_10_MIN = 20

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_RE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?354[\s-]?)?(?:\d[\s-]?){7,}")
OFF_PLATFORM_KEYWORDS = (
    "telegram",
    "whatsapp",
    "signal",
    "instagram",
    "facebook",
    "messenger",
    "crypto",
    "bitcoin",
    "wallet",
    "bank transfer",
)


def _utcnow():
    return datetime.now(timezone.utc)


def _detect_risk_flags(body: str):
    lowered = body.lower()
    flags = []
    contains_contact = bool(EMAIL_RE.search(body) or PHONE_RE.search(body))
    contains_link = bool(URL_RE.search(body))

    if contains_contact:
        flags.append("contact_info")
    if contains_link:
        flags.append("external_link")
    if any(keyword in lowered for keyword in OFF_PLATFORM_KEYWORDS):
        flags.append("off_platform_keyword")

    return flags, contains_contact, contains_link


async def _get_thread_or_404(thread_id: int, db: AsyncSession):
    result = await db.execute(select(ConversationThread).where(ConversationThread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return thread


def _ensure_participant(thread: ConversationThread, user: User):
    if user.id not in {thread.requester_id, thread.craftsman_user_id}:
        raise HTTPException(status_code=403, detail="You do not have access to this conversation")


async def _decorate_thread(thread: ConversationThread, db: AsyncSession, include_details: bool = False):
    requester_result = await db.execute(select(User).where(User.id == thread.requester_id))
    craftsman_result = await db.execute(select(User).where(User.id == thread.craftsman_user_id))
    set_committed_value(thread, "requester", requester_result.scalar_one_or_none())
    set_committed_value(thread, "craftsman_user", craftsman_result.scalar_one_or_none())

    latest_message_result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.thread_id == thread.id)
        .order_by(desc(ConversationMessage.created_at))
        .limit(1)
    )
    latest_message = latest_message_result.scalar_one_or_none()
    thread.latest_message_preview = latest_message.body[:140] if latest_message else None

    if include_details:
        message_result = await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.thread_id == thread.id)
            .order_by(ConversationMessage.created_at.asc())
        )
        messages = message_result.scalars().all()
        set_committed_value(thread, "messages", messages)
        for message in messages:
            sender_result = await db.execute(select(User).where(User.id == message.sender_id))
            set_committed_value(message, "sender", sender_result.scalar_one_or_none())

        quote_result = await db.execute(
            select(ConversationQuote)
            .where(ConversationQuote.thread_id == thread.id)
            .order_by(desc(ConversationQuote.created_at))
        )
        quotes = quote_result.scalars().all()
        set_committed_value(thread, "quotes", quotes)
        for quote in quotes:
            quote_user_result = await db.execute(select(User).where(User.id == quote.craftsman_user_id))
            set_committed_value(quote, "craftsman_user", quote_user_result.scalar_one_or_none())
    else:
        set_committed_value(thread, "messages", [])
        set_committed_value(thread, "quotes", [])

    return thread


@router.post("/", response_model=ConversationThreadResponse, status_code=201)
async def create_conversation_thread(
    data: ConversationThreadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.craftsman_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot create a private request to yourself")

    craftsman_profile_result = await db.execute(
        select(CraftsmanProfile).where(CraftsmanProfile.user_id == data.craftsman_user_id)
    )
    if craftsman_profile_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Craftsman not found")

    cutoff = _utcnow() - timedelta(days=1)
    recent_thread_count = await db.execute(
        select(func.count()).select_from(
            select(ConversationThread)
            .where(
                ConversationThread.requester_id == current_user.id,
                ConversationThread.created_at >= cutoff,
            )
            .subquery()
        )
    )
    if (recent_thread_count.scalar() or 0) >= THREAD_LIMIT_PER_DAY:
        raise HTTPException(status_code=429, detail="Too many new private requests today")

    duplicate_result = await db.execute(
        select(ConversationThread).where(
            ConversationThread.requester_id == current_user.id,
            ConversationThread.craftsman_user_id == data.craftsman_user_id,
            ConversationThread.title == data.title,
            ConversationThread.project_summary == data.project_summary,
            ConversationThread.created_at >= cutoff,
        )
    )
    if duplicate_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A similar request was already sent recently")

    flags, contains_contact, contains_link = _detect_risk_flags(data.project_summary)
    if contains_contact or contains_link or "off_platform_keyword" in flags:
        raise HTTPException(status_code=400, detail="Keep first contact inside VerkTorg without phone numbers, email addresses, or external links")

    if not data.title.strip() or not data.project_summary.strip():
        raise HTTPException(status_code=400, detail="Title and request description cannot be empty")

    thread = ConversationThread(
        requester_id=current_user.id,
        craftsman_user_id=data.craftsman_user_id,
        title=data.title.strip(),
        project_summary=data.project_summary.strip(),
        category=data.category,
        location=data.location,
        budget_min=data.budget_min,
        budget_max=data.budget_max,
        preferred_date=data.preferred_date,
        last_message_at=_utcnow(),
    )
    db.add(thread)
    await db.flush()

    initial_message = ConversationMessage(
        thread_id=thread.id,
        sender_id=current_user.id,
        body=data.project_summary.strip(),
        contains_contact_info=False,
        contains_external_link=False,
        is_flagged=False,
        risk_flags=[],
    )
    db.add(initial_message)
    await db.commit()
    await db.refresh(thread)

    await create_and_send_notification(
        db,
        user_id=thread.craftsman_user_id,
        type="new_private_request",
        message=f"Ný einkabeiðni frá viðskiptavini: {thread.title}",
        data={"thread_id": thread.id},
    )

    thread = await _decorate_thread(thread, db, include_details=True)
    return ConversationThreadResponse.model_validate(thread)


@router.get("/", response_model=list[ConversationThreadResponse])
async def list_conversation_threads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ConversationThread)
        .where(
            (ConversationThread.requester_id == current_user.id)
            | (ConversationThread.craftsman_user_id == current_user.id)
        )
        .order_by(desc(ConversationThread.last_message_at), desc(ConversationThread.created_at))
    )
    threads = result.scalars().all()
    items = []
    for thread in threads:
        items.append(ConversationThreadResponse.model_validate(await _decorate_thread(thread, db)))
    return items


@router.get("/{thread_id}", response_model=ConversationThreadResponse)
async def get_conversation_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread = await _get_thread_or_404(thread_id, db)
    _ensure_participant(thread, current_user)
    thread = await _decorate_thread(thread, db, include_details=True)
    return ConversationThreadResponse.model_validate(thread)


@router.post("/{thread_id}/messages", response_model=ConversationMessageResponse, status_code=201)
async def send_conversation_message(
    thread_id: int,
    data: ConversationMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread = await _get_thread_or_404(thread_id, db)
    _ensure_participant(thread, current_user)
    if thread.status != ConversationStatus.OPEN:
        raise HTTPException(status_code=400, detail="Conversation is closed")

    recent_cutoff = _utcnow() - timedelta(minutes=10)
    recent_message_count = await db.execute(
        select(func.count()).select_from(
            select(ConversationMessage)
            .where(
                ConversationMessage.sender_id == current_user.id,
                ConversationMessage.created_at >= recent_cutoff,
            )
            .subquery()
        )
    )
    if (recent_message_count.scalar() or 0) >= MESSAGE_LIMIT_PER_10_MIN:
        raise HTTPException(status_code=429, detail="Too many messages sent recently")

    body = data.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    flags, contains_contact, contains_link = _detect_risk_flags(body)

    other_user_id = thread.craftsman_user_id if current_user.id == thread.requester_id else thread.requester_id
    recipient_reply_result = await db.execute(
        select(ConversationMessage).where(
            ConversationMessage.thread_id == thread.id,
            ConversationMessage.sender_id == other_user_id,
        )
    )
    recipient_has_replied = recipient_reply_result.scalar_one_or_none() is not None

    if current_user.id == thread.requester_id and not recipient_has_replied and (contains_contact or contains_link or "off_platform_keyword" in flags):
        raise HTTPException(status_code=400, detail="Keep first contact inside VerkTorg without phone numbers, email addresses, or external links")

    message = ConversationMessage(
        thread_id=thread.id,
        sender_id=current_user.id,
        body=body,
        contains_contact_info=contains_contact,
        contains_external_link=contains_link,
        is_flagged=bool(flags),
        risk_flags=flags,
    )
    thread.last_message_at = _utcnow()
    if flags:
        thread.is_flagged = True

    db.add(message)
    await db.commit()
    await db.refresh(message)

    sender_result = await db.execute(select(User).where(User.id == current_user.id))
    set_committed_value(message, "sender", sender_result.scalar_one_or_none())

    await create_and_send_notification(
        db,
        user_id=other_user_id,
        type="new_conversation_message",
        message=f"Ný skilaboð í þræði: {thread.title}",
        data={"thread_id": thread.id},
    )

    return ConversationMessageResponse.model_validate(message)


@router.post("/{thread_id}/quotes", response_model=ConversationQuoteResponse, status_code=201)
async def create_conversation_quote(
    thread_id: int,
    data: ConversationQuoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread = await _get_thread_or_404(thread_id, db)
    _ensure_participant(thread, current_user)
    if current_user.id != thread.craftsman_user_id:
        raise HTTPException(status_code=403, detail="Only the craftsman can send a quote")
    if thread.related_job_id is not None:
        raise HTTPException(status_code=400, detail="A quote has already been accepted for this private request")

    pending_quote_result = await db.execute(
        select(ConversationQuote).where(
            ConversationQuote.thread_id == thread.id,
            ConversationQuote.craftsman_user_id == current_user.id,
            ConversationQuote.status == QuoteStatus.PENDING,
        )
    )
    if pending_quote_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="You already have a pending quote in this conversation")

    accepted_quote_result = await db.execute(
        select(ConversationQuote).where(
            ConversationQuote.thread_id == thread.id,
            ConversationQuote.status == QuoteStatus.ACCEPTED,
        )
    )
    if accepted_quote_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="A quote has already been accepted for this private request")

    quote = ConversationQuote(
        thread_id=thread.id,
        craftsman_user_id=current_user.id,
        amount=data.amount,
        note=(data.note or "").strip() or None,
        estimated_hours=data.estimated_hours,
    )
    thread.last_message_at = _utcnow()
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    quote_user_result = await db.execute(select(User).where(User.id == current_user.id))
    set_committed_value(quote, "craftsman_user", quote_user_result.scalar_one_or_none())

    await create_and_send_notification(
        db,
        user_id=thread.requester_id,
        type="new_private_quote",
        message=f"Nýtt tilboð barst í einkabeiðni: {thread.title}",
        data={"thread_id": thread.id, "quote_id": quote.id},
    )

    return ConversationQuoteResponse.model_validate(quote)


@router.put("/quotes/{quote_id}/accept")
async def accept_conversation_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quote_result = await db.execute(select(ConversationQuote).where(ConversationQuote.id == quote_id))
    quote = quote_result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    thread = await _get_thread_or_404(quote.thread_id, db)
    if current_user.id != thread.requester_id:
        raise HTTPException(status_code=403, detail="Only the requester can accept this quote")
    if quote.status != QuoteStatus.PENDING:
        raise HTTPException(status_code=400, detail="Quote is no longer pending")
    if thread.related_job_id is not None:
        raise HTTPException(status_code=400, detail="This private request already has an accepted quote")

    quote.status = QuoteStatus.ACCEPTED
    quote.accepted_at = _utcnow()
    job = Job(
        customer_id=thread.requester_id,
        title=thread.title,
        description=thread.project_summary,
        category=thread.category,
        location=thread.location,
        budget_min=thread.budget_min,
        budget_max=thread.budget_max,
        is_fixed_price=False,
        preferred_date=thread.preferred_date,
        status=JobStatus.IN_PROGRESS,
    )
    db.add(job)
    await db.flush()

    accepted_bid = Bid(
        job_id=job.id,
        craftsman_id=thread.craftsman_user_id,
        amount=quote.amount,
        message=quote.note,
        estimated_hours=quote.estimated_hours,
        status=BidStatus.ACCEPTED,
    )
    db.add(accepted_bid)
    thread.related_job_id = job.id
    await db.execute(
        update(ConversationQuote)
        .where(
            ConversationQuote.thread_id == thread.id,
            ConversationQuote.id != quote.id,
            ConversationQuote.status == QuoteStatus.PENDING,
        )
        .values(status=QuoteStatus.DECLINED)
    )
    await db.commit()

    await create_and_send_notification(
        db,
        user_id=thread.craftsman_user_id,
        type="private_quote_accepted",
        message=f"Tilboð þitt í einkabeiðni var samþykkt: {thread.title}",
        data={"thread_id": thread.id, "quote_id": quote.id},
    )

    return {"ok": True, "message": "Quote accepted"}
