"""
routers/bookings.py — REST endpoints for booking management.
Used by the dashboard and direct API callers (mock page, tests).
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from datetime import datetime
from models import BookingRequest, RescheduleRequest, CancelRequest, WaitlistRequest, CallbackRequest
from core.database import (
    get_bookings, get_booked_slots, create_booking,
    update_booking_status, find_booking_by_customer,
    add_to_waitlist, log_callback, clear_all_bookings,
)
from core.config import BOOKING_CONFIRM_URL

router = APIRouter()

# ── Service duration lookup ───────────────────────────────────────────────────
SERVICE_DURATIONS: dict[str, int] = {
    "style cut": 45, "stylecut": 45, "cut": 45, "trim": 30,
    "blowdry": 45, "blow dry": 45,
    "regrowth & blowdry": 120, "regrowth": 120,
    "highlights": 150, "colour & shine": 150, "color & shine": 150,
    "classic colour": 135, "classic color": 135,
    "balayage": 240, "full head": 210, "full head colour": 210,
    "tint": 90, "toner": 60,
}

def _duration(service: str) -> int:
    return SERVICE_DURATIONS.get(service.lower().strip(), 60)

def _parse_time_24(t: str) -> str:
    t = t.strip().lower().replace(" ", "")
    if "am" in t or "pm" in t:
        for fmt in ("%I:%M%p", "%I%p"):
            try:
                return datetime.strptime(t, fmt).strftime("%H:%M")
            except ValueError:
                continue
    return t

def _normalise_phone(p: str) -> str:
    p = p.strip().replace(" ", "").replace("-", "")
    if p.startswith("04") and len(p) == 10:
        return "+61" + p[1:]
    if p.startswith("61") and not p.startswith("+"):
        return "+" + p
    return p


# ── GET /availability ─────────────────────────────────────────────────────────

@router.get("/availability")
async def availability(
    date: str,
    stylist: str = None,
    business_id: str = Query(default="default"),
):
    from datetime import datetime as dt

    AVAIL = {
        0: [], 6: [],
        1: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","13:00","13:15","13:30","14:00","14:15","14:30","15:00","15:15"],
        2: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","13:00","13:15","13:30","14:00","14:15","15:00","15:15","16:00","17:00","17:15","17:30","18:00","18:15"],
        3: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","13:00","13:15","13:30","14:00","14:15","15:00","15:15","16:00","17:00","17:30","18:00","18:15","18:30","19:00","19:15"],
        4: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","12:00","12:15","13:00","13:15","14:00","14:15","14:30","15:00"],
        5: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","13:00","13:15","14:00","14:15","14:30","15:00","15:15"],
    }

    date_obj = dt.strptime(date, "%Y-%m-%d")
    dow = date_obj.weekday() + 1
    if dow == 7:
        dow = 0

    base_slots = AVAIL.get(dow, [])
    if not base_slots:
        return {"date": date, "available": [], "message": "Salon is closed on this day"}

    booked = await get_booked_slots(date=date, business_id=business_id, stylist=stylist)
    available = [s for s in base_slots if s not in booked]

    return {
        "date": date,
        "day": date_obj.strftime("%A"),
        "available": available,
        "booked": booked,
    }


# ── POST /book ────────────────────────────────────────────────────────────────

@router.post("/book")
async def book(req: BookingRequest):
    time_24 = _parse_time_24(req.time)
    business_id = req.business_id or "default"

    booked = await get_booked_slots(date=req.date, business_id=business_id, stylist=req.stylist)
    if time_24 in booked:
        return JSONResponse(
            {"error": f"Sorry, {req.time} on {req.date} is no longer available. Please choose another time."},
            status_code=409,
        )

    phone = _normalise_phone(req.customer_phone) if req.customer_phone else ""
    duration = _duration(req.service)

    booking = await create_booking(
        business_id=business_id,
        service=req.service,
        staff_name=req.stylist or "(anyone)",
        date=req.date,
        time=time_24,
        duration_mins=duration,
        customer_phone=phone,
        customer_name=req.customer_name or "",
        source="web",
    )

    if phone:
        try:
            from core.sms import send_booking_sms
            send_booking_sms(phone=phone, booking_link=BOOKING_CONFIRM_URL)
        except Exception as e:
            print(f"[SMS] Failed: {e}")

    return {
        "success": True,
        "booking_id": booking["id"],
        "message": f"Booking confirmed! {req.service} on {req.date} at {req.time}.",
        "booking": booking,
    }


# ── POST /reschedule ──────────────────────────────────────────────────────────

@router.post("/reschedule")
async def reschedule(req: RescheduleRequest):
    business_id = req.business_id or "default"
    new_time_24 = _parse_time_24(req.new_time)

    booked = await get_booked_slots(date=req.new_date, business_id=business_id)
    if new_time_24 in booked:
        return JSONResponse(
            {"error": f"{req.new_time} on {req.new_date} is not available."},
            status_code=409,
        )

    cancelled = await update_booking_status(req.booking_id, "cancelled", "rescheduled")
    if not cancelled:
        return JSONResponse({"error": "Booking not found."}, status_code=404)

    new_booking = await create_booking(
        business_id=business_id,
        service=cancelled["service"],
        staff_name=cancelled["staff_name"],
        date=req.new_date,
        time=new_time_24,
        duration_mins=cancelled.get("duration_mins", 60),
        customer_phone=cancelled["customer_phone"],
        customer_name=cancelled["customer_name"],
        source="voice",
    )

    phone = cancelled.get("customer_phone", "")
    if phone:
        try:
            from core.sms import send_sms
            date_obj = datetime.strptime(req.new_date, "%Y-%m-%d")
            send_sms(
                phone,
                f"Your booking has been moved to {date_obj.strftime('%A %d %B')} "
                f"at {req.new_time}. See you then!",
            )
        except Exception as e:
            print(f"[SMS] Failed: {e}")

    return {
        "success": True,
        "old_booking_id": req.booking_id,
        "new_booking_id": new_booking["id"],
        "message": f"Rescheduled to {req.new_date} at {req.new_time}.",
    }


# ── POST /cancel ──────────────────────────────────────────────────────────────

@router.post("/cancel")
async def cancel(req: CancelRequest):
    cancelled = await update_booking_status(req.booking_id, "cancelled", req.reason or "")
    if not cancelled:
        return JSONResponse({"error": "Booking not found."}, status_code=404)

    phone = cancelled.get("customer_phone", "")
    if phone:
        try:
            from core.sms import send_sms
            send_sms(phone, "Your booking has been cancelled. We hope to see you again soon!")
        except Exception as e:
            print(f"[SMS] Failed: {e}")

    return {"success": True, "booking_id": req.booking_id, "message": "Booking cancelled."}


# ── GET /bookings ─────────────────────────────────────────────────────────────

@router.get("/bookings")
async def list_bookings(
    business_id: str = Query(default="default"),
    date: str = Query(default=None),
):
    bookings = await get_bookings(business_id=business_id, date=date)
    return {"bookings": bookings}


# ── DELETE /bookings/clear ────────────────────────────────────────────────────

@router.delete("/bookings/clear")
async def clear_bookings(business_id: str = Query(default="default")):
    await clear_all_bookings(business_id)
    return {"cleared": True}


# ── POST /waitlist ────────────────────────────────────────────────────────────

@router.post("/waitlist")
async def waitlist(req: WaitlistRequest):
    entry = await add_to_waitlist(
        business_id=req.business_id or "default",
        customer_phone=req.customer_phone,
        customer_name=req.customer_name,
        service=req.service,
        preferred_date=req.preferred_date,
        time_preference=req.time_preference or "any",
    )
    return {"success": True, "waitlist_id": entry["id"]}


# ── POST /callback ────────────────────────────────────────────────────────────

@router.post("/callback")
async def callback(req: CallbackRequest):
    entry = await log_callback(
        business_id=req.business_id or "default",
        customer_phone=req.customer_phone,
        customer_name=req.customer_name or "",
        reason=req.reason or "",
    )
    return {"success": True, "callback_id": entry["id"]}
