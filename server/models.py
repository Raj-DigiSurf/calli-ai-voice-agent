"""
models.py — Pydantic request/response models for all API endpoints.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


# ── Booking ───────────────────────────────────────────────────────────────────

class BookingRequest(BaseModel):
    service: str
    stylist: Optional[str] = "(anyone)"
    date: str                        # YYYY-MM-DD
    time: str                        # HH:MM or natural (e.g. "10am")
    customer_phone: Optional[str] = ""
    customer_name: Optional[str] = ""
    business_id: Optional[str] = "default"


class RescheduleRequest(BaseModel):
    booking_id: str
    new_date: str                    # YYYY-MM-DD
    new_time: str                    # HH:MM
    business_id: Optional[str] = "default"


class CancelRequest(BaseModel):
    booking_id: str
    reason: Optional[str] = ""
    business_id: Optional[str] = "default"


# ── Waitlist ──────────────────────────────────────────────────────────────────

class WaitlistRequest(BaseModel):
    customer_phone: str
    customer_name: str
    service: str
    preferred_date: str              # YYYY-MM-DD
    time_preference: Optional[str] = "any"
    business_id: Optional[str] = "default"


# ── Callback ──────────────────────────────────────────────────────────────────

class CallbackRequest(BaseModel):
    customer_phone: str
    customer_name: Optional[str] = ""
    reason: Optional[str] = ""
    business_id: Optional[str] = "default"


# ── Dashboard ─────────────────────────────────────────────────────────────────

class BookingOut(BaseModel):
    id: str
    service: str
    staff_name: str
    date: str
    time: str
    duration_mins: int
    customer_name: str
    customer_phone: str
    status: str
    source: str
    deposit_paid: bool
