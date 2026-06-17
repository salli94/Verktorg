import enum
from datetime import datetime, date, time
from sqlalchemy import (
    Column, Integer, String, Float, Text, Enum, DateTime, Date, Time,
    Boolean, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    CRAFTSMAN = "craftsman"


class JobStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BidStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ConversationStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class QuoteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class JobCategory(str, enum.Enum):
    RAFVIRKJUN = "rafvirkjun"
    PIPULAGNIR = "pipulagnir"
    BYGGINGARVINNA = "byggingarvinna"
    MALUN = "malun"
    GARDYRKJA = "gardyrkja"
    HREINSUN = "hreinsun"
    HUSGAGNASMIDI = "husgagnasmidi"
    SMIDI = "smidi"
    LAGNINGAR = "lagningar"
    LAGNIR = "lagnir"
    RAFEINDAVERK = "rafeindaverk"
    HJOLUN = "hjolun"
    ANNAD = "annad"

    @classmethod
    def icelandic_label(cls, value):
        labels = {
            "rafvirkjun": "Rafvirkjun",
            "pipulagnir": "Pípulagnir",
            "byggingarvinna": "Byggingarvinna",
            "malun": "Málun",
            "gardyrkja": "Garðyrkja",
            "hreinsun": "Hreinsun",
            "husgagnasmidi": "Húsgagnasmíði",
            "smidi": "Smíði",
            "lagningar": "Lagningar",
            "lagnir": "Lagnir",
            "rafeindaverk": "Rafeindaverk",
            "hjolun": "Hjólun",
            "annad": "Annað",
        }
        return labels.get(value, value)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String)
    role = Column(Enum(UserRole), default=UserRole.CUSTOMER)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    craftsman_profile = relationship("CraftsmanProfile", back_populates="user", uselist=False)
    jobs_posted = relationship("Job", back_populates="customer")
    bids_made = relationship("Bid", back_populates="craftsman")
    reviews_given = relationship("Review", back_populates="reviewer", foreign_keys="Review.reviewer_id")
    reviews_received = relationship("Review", back_populates="reviewee", foreign_keys="Review.reviewee_id")
    conversation_threads_requested = relationship("ConversationThread", back_populates="requester", foreign_keys="ConversationThread.requester_id")
    conversation_threads_received = relationship("ConversationThread", back_populates="craftsman_user", foreign_keys="ConversationThread.craftsman_user_id")
    conversation_messages = relationship("ConversationMessage", back_populates="sender")
    conversation_quotes = relationship("ConversationQuote", back_populates="craftsman_user")


class CraftsmanProfile(Base):
    __tablename__ = "craftsman_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    trade_category = Column(Enum(JobCategory), nullable=False)
    license_number = Column(String)
    is_verified = Column(Boolean, default=False)
    description = Column(Text)
    hourly_rate = Column(Float)
    years_experience = Column(Integer, default=0)
    location = Column(String)
    portfolio_photos = Column(JSON, default=list)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="craftsman_profile")
    availability_slots = relationship("AvailabilitySlot", back_populates="craftsman", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(Enum(JobCategory), nullable=False)
    location = Column(String)
    budget_min = Column(Float)
    budget_max = Column(Float)
    is_fixed_price = Column(Boolean, default=False)
    preferred_date = Column(Date)
    status = Column(Enum(JobStatus), default=JobStatus.OPEN)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    customer = relationship("User", back_populates="jobs_posted")
    bids = relationship("Bid", back_populates="job", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="job", cascade="all, delete-orphan")


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id = Column(Integer, primary_key=True, index=True)
    craftsman_id = Column(Integer, ForeignKey("craftsman_profiles.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_booked = Column(Boolean, default=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)

    craftsman = relationship("CraftsmanProfile", back_populates="availability_slots")


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    craftsman_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    message = Column(Text)
    estimated_hours = Column(Float)
    status = Column(Enum(BidStatus), default=BidStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="bids")
    craftsman = relationship("User", back_populates="bids_made")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews_given", foreign_keys=[reviewer_id])
    reviewee = relationship("User", back_populates="reviews_received", foreign_keys=[reviewee_id])


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, default=dict)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")


class ConversationThread(Base):
    __tablename__ = "conversation_threads"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    craftsman_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    project_summary = Column(Text, nullable=False)
    category = Column(Enum(JobCategory), nullable=False)
    location = Column(String)
    budget_min = Column(Float)
    budget_max = Column(Float)
    preferred_date = Column(Date)
    related_job_id = Column(Integer, ForeignKey("jobs.id"))
    status = Column(Enum(ConversationStatus), default=ConversationStatus.OPEN, nullable=False)
    is_flagged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_message_at = Column(DateTime(timezone=True), server_default=func.now())

    requester = relationship("User", back_populates="conversation_threads_requested", foreign_keys=[requester_id])
    craftsman_user = relationship("User", back_populates="conversation_threads_received", foreign_keys=[craftsman_user_id])
    related_job = relationship("Job")
    messages = relationship("ConversationMessage", back_populates="thread", cascade="all, delete-orphan")
    quotes = relationship("ConversationQuote", back_populates="thread", cascade="all, delete-orphan")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("conversation_threads.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    contains_contact_info = Column(Boolean, default=False)
    contains_external_link = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    risk_flags = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    thread = relationship("ConversationThread", back_populates="messages")
    sender = relationship("User", back_populates="conversation_messages")


class ConversationQuote(Base):
    __tablename__ = "conversation_quotes"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("conversation_threads.id"), nullable=False)
    craftsman_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    note = Column(Text)
    estimated_hours = Column(Float)
    status = Column(Enum(QuoteStatus), default=QuoteStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at = Column(DateTime(timezone=True))

    thread = relationship("ConversationThread", back_populates="quotes")
    craftsman_user = relationship("User", back_populates="conversation_quotes")
