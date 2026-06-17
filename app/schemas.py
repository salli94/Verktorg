from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import Optional, Annotated
from datetime import datetime, date, time
from .models import UserRole, JobStatus, JobCategory, BidStatus, ConversationStatus, QuoteStatus


class UserRegister(BaseModel):
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    role: UserRole = UserRole.CUSTOMER


class UserLogin(BaseModel):
    email: str
    password: str


class PublicUserResponse(BaseModel):
    id: int
    full_name: str
    role: UserRole
    created_at: datetime

    class Config:
        from_attributes = True


class UserResponse(PublicUserResponse):
    email: str
    phone: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CraftsmanProfileCreate(BaseModel):
    trade_category: JobCategory
    license_number: Optional[str] = None
    description: Optional[str] = None
    hourly_rate: Optional[float] = Field(None, ge=0)
    years_experience: Optional[int] = Field(None, ge=0)
    location: Optional[str] = None
    portfolio_photos: Optional[list[str]] = None


class CraftsmanProfileResponse(BaseModel):
    id: int
    user_id: int
    trade_category: JobCategory
    license_number: Optional[str] = None
    is_verified: bool
    description: Optional[str] = None
    hourly_rate: Optional[float] = None
    years_experience: Optional[int] = None
    location: Optional[str] = None
    portfolio_photos: list[str]
    is_available: bool
    created_at: datetime
    user: Optional[PublicUserResponse] = None

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=120)
    description: str = Field(..., min_length=10)
    category: JobCategory
    location: Optional[str] = None
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    is_fixed_price: bool = False
    preferred_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_budget_range(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min must be less than or equal to budget_max")
        return self


class JobUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=120)
    description: Optional[str] = Field(None, min_length=10)
    category: Optional[JobCategory] = None
    location: Optional[str] = None
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    is_fixed_price: Optional[bool] = None
    preferred_date: Optional[date] = None
    status: Optional[JobStatus] = None

    @model_validator(mode="after")
    def validate_budget_range(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min must be less than or equal to budget_max")
        return self


class JobResponse(BaseModel):
    id: int
    customer_id: int
    title: str
    description: str
    category: JobCategory
    location: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    is_fixed_price: bool
    preferred_date: Optional[date] = None
    status: JobStatus
    created_at: datetime
    customer: Optional[PublicUserResponse] = None
    bid_count: Optional[int] = None

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


class AvailabilitySlotCreate(BaseModel):
    date: date
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class AvailabilitySlotResponse(BaseModel):
    id: int
    craftsman_id: int
    date: date
    start_time: time
    end_time: time
    is_booked: bool
    job_id: Optional[int] = None

    class Config:
        from_attributes = True


class BidCreate(BaseModel):
    amount: float = Field(..., ge=0)
    message: Optional[str] = None
    estimated_hours: Optional[float] = Field(None, ge=0)


class BidResponse(BaseModel):
    id: int
    job_id: int
    craftsman_id: int
    amount: float
    message: Optional[str] = None
    estimated_hours: Optional[float] = None
    status: BidStatus
    created_at: datetime
    craftsman: Optional[PublicUserResponse] = None

    class Config:
        from_attributes = True


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    job_id: int
    reviewer_id: int
    reviewee_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime
    reviewer: Optional[PublicUserResponse] = None

    class Config:
        from_attributes = True


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: str
    message: str
    data: dict
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class JobSearchParams(BaseModel):
    q: Optional[str] = None
    category: Optional[JobCategory] = None
    location: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    status: Optional[JobStatus] = None
    sort_by: str = "newest"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=50)


class ConversationThreadCreate(BaseModel):
    craftsman_user_id: int
    title: str = Field(..., min_length=5, max_length=140)
    project_summary: str = Field(..., min_length=10, max_length=2000)
    category: JobCategory
    location: Optional[str] = None
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    preferred_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_budget_range(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min must be less than or equal to budget_max")
        return self


class ConversationMessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class ConversationQuoteCreate(BaseModel):
    amount: float = Field(..., ge=0)
    note: Optional[str] = Field(None, max_length=1200)
    estimated_hours: Optional[float] = Field(None, ge=0)


class ConversationMessageResponse(BaseModel):
    id: int
    thread_id: int
    sender_id: int
    body: str
    contains_contact_info: bool
    contains_external_link: bool
    is_flagged: bool
    risk_flags: list[str]
    created_at: datetime
    sender: Optional[PublicUserResponse] = None

    class Config:
        from_attributes = True


class ConversationQuoteResponse(BaseModel):
    id: int
    thread_id: int
    craftsman_user_id: int
    amount: float
    note: Optional[str] = None
    estimated_hours: Optional[float] = None
    status: QuoteStatus
    created_at: datetime
    accepted_at: Optional[datetime] = None
    craftsman_user: Optional[PublicUserResponse] = None

    class Config:
        from_attributes = True


class ConversationThreadResponse(BaseModel):
    id: int
    requester_id: int
    craftsman_user_id: int
    title: str
    project_summary: str
    category: JobCategory
    location: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    preferred_date: Optional[date] = None
    related_job_id: Optional[int] = None
    status: ConversationStatus
    is_flagged: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    requester: Optional[PublicUserResponse] = None
    craftsman_user: Optional[PublicUserResponse] = None
    latest_message_preview: Optional[str] = None
    messages: list[ConversationMessageResponse] = []
    quotes: list[ConversationQuoteResponse] = []

    class Config:
        from_attributes = True
