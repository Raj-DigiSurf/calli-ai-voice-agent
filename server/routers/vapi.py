"""
routers/vapi.py — Vapi webhook handler.

Receives tool-call and function-call events from Vapi, dispatches to the
correct business logic, and returns results Vapi reads aloud to the caller.
"""
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.config import BOOKING_CONFIRM_URL, TEST_PHONE
from core.database import (
    get_booked_slots, create_booking, update_booking_status,
    find_booking_by_customer, add_to_waitlist, log_callback,
    get_customer_by_phone, upsert_customer,
)
from core.sms import send_booking_sms, send_sms

router = APIRouter()

# ── Duration lookup ───────────────────────────────────────────────────────────
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


# ── Webhook entry point ───────────────────────────────────────────────────────

@router.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})
    call_type = message.get("type")

    print(f"[VAPI WEBHOOK] type={call_type} keys={list(message.keys())}")

    # Extract caller phone from Vapi payload — never ask the customer for it
    caller_phone = (
        message.get("call", {}).get("customer", {}).get("number")
        or body.get("call", {}).get("customer", {}).get("number")
        or ""
    )
    if caller_phone:
        print(f"[VAPI] caller phone: {caller_phone}")

    # Business ID — defaults to "default" until multi-tenant is wired
    business_id = (
        message.get("call", {}).get("phoneNumberId")
        or "default"
    )

    # ── New Vapi format: tool-calls ──────────────────────────────────────────
    if call_type == "tool-calls":
        tool_calls = message.get("toolCallList", [])
        results = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name")
            params = fn.get("arguments", {})
            tc_id = tc.get("id", "")
            print(f"[VAPI] tool-call: {name} params={params}")
            result = await _dispatch(name, params, caller_phone, business_id)
            results.append({"toolCallId": tc_id, "result": result})
        return JSONResponse({"results": results})

    # ── Old Vapi format: function-call ───────────────────────────────────────
    if call_type == "function-call":
        name = message.get("functionCall", {}).get("name")
        params = message.get("functionCall", {}).get("parameters", {})
        print(f"[VAPI] function-call: {name} params={params}")
        result = await _dispatch(name, params, caller_phone, business_id)
        return JSONResponse({"result": result})

    return JSONResponse({"result": "ok"})


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def _dispatch(name: str, params: dict,
                    caller_phone: str, business_id: str) -> str:

    # ── get_current_date ──────────────────────────────────────────────────────
    if name == "get_current_date":
        now = datetime.now()
        return (
            f"Today is {now.strftime('%A, %d %B %Y')}. "
            f"In YYYY-MM-DD format: {now.strftime('%Y-%m-%d')}."
        )

    # ── lookup_customer ───────────────────────────────────────────────────────
    if name == "lookup_customer":
        if not caller_phone:
            return "I don't have a phone number for this call."
        phone = _normalise_phone(caller_phone)
        customer = await get_customer_by_phone(phone, business_id)
        if not customer:
            return "new_customer"
        bookings = await find_booking_by_customer(phone, business_id, upcoming_only=True)
        upcoming = ""
        if bookings:
            b = bookings[0]
            upcoming = (
                f" You have a {b['service']} booked on "
                f"{b['date']} at {b['time']}."
            )
        return f"returning_customer|{customer['name']}|{upcoming.strip()}"

    # ── check_availability ────────────────────────────────────────────────────
    if name == "check_availability":
        return await _check_availability(
            service=params.get("service", ""),
            stylist=params.get("stylist", "(anyone)"),
            date=params.get("date", ""),
            business_id=business_id,
        )

    # ── book_appointment ──────────────────────────────────────────────────────
    if name == "book_appointment":
        phone = _normalise_phone(caller_phone or params.get("customer_phone", "")
                                 or TEST_PHONE)
        return await _book_appointment(
            service=params.get("service", ""),
            stylist=params.get("stylist", "(anyone)"),
            date=params.get("date", ""),
            time=params.get("time", ""),
            customer_phone=phone,
            customer_name=params.get("customer_name", ""),
            business_id=business_id,
        )

    # ── reschedule_appointment ────────────────────────────────────────────────
    if name == "reschedule_appointment":
        return await _reschedule(
            customer_phone=_normalise_phone(caller_phone or ""),
            new_date=params.get("new_date", ""),
            new_time=params.get("new_time", ""),
            business_id=business_id,
        )

    # ── cancel_appointment ────────────────────────────────────────────────────
    if name == "cancel_appointment":
        return await _cancel(
            customer_phone=_normalise_phone(caller_phone or ""),
            reason=params.get("reason", ""),
            business_id=business_id,
        )

    # ── add_to_waitlist ───────────────────────────────────────────────────────
    if name == "add_to_waitlist":
        phone = _normalise_phone(caller_phone or params.get("customer_phone", ""))
        await add_to_waitlist(
            business_id=business_id,
            customer_phone=phone,
            customer_name=params.get("customer_name", ""),
            service=params.get("service", ""),
            preferred_date=params.get("date", ""),
            time_preference=params.get("time_preference", "any"),
        )
        return (
            "You're on the waitlist! If a spot opens up I'll text you straight away."
        )

    # ── log_callback_request ──────────────────────────────────────────────────
    if name == "log_callback_request":
        phone = _normalise_phone(caller_phone or params.get("customer_phone", ""))
        name_val = params.get("customer_name", "")
        await log_callback(
            business_id=business_id,
            customer_phone=phone,
            customer_name=name_val,
            reason=params.get("reason", ""),
        )
        return (
            "No worries at all — I've passed your details on and someone will "
            "give you a call back as soon as they're free."
        )

    print(f"[VAPI] Unknown function: {name}")
    return f"Sorry, I don't know how to handle {name}."


# ── Business logic helpers ────────────────────────────────────────────────────

async def _check_availability(service: str, stylist: str, date: str,
                               business_id: str) -> str:
    from integrations.kitomba import get_availability as kitomba_avail

    print(f"[PLAYWRIGHT] check_availability → service={service} stylist={stylist} date={date}")
    try:
        result = await kitomba_avail(
            service=service,
            stylist=stylist or "(anyone)",
            date=date,
        )
        if result:
            return result
    except Exception as e:
        print(f"[PLAYWRIGHT] failed, falling back: {e}")

    # Direct fallback
    return await _direct_availability(date=date, stylist=stylist, business_id=business_id)


async def _direct_availability(date: str, stylist: str, business_id: str) -> str:
    AVAIL = {
        0: [], 6: [],
        1: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","13:00","13:15","13:30","14:00","14:15","14:30","15:00","15:15"],
        2: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","13:00","13:15","13:30","14:00","14:15","15:00","15:15","16:00","17:00","17:15","17:30","18:00","18:15"],
        3: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","13:00","13:15","13:30","14:00","14:15","15:00","15:15","16:00","17:00","17:30","18:00","18:15","18:30","19:00","19:15"],
        4: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","12:00","12:15","13:00","13:15","14:00","14:15","14:30","15:00"],
        5: ["9:30","9:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","13:00","13:15","14:00","14:15","14:30","15:00","15:15"],
    }
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        dow = date_obj.weekday() + 1
        if dow == 7:
            dow = 0
    except Exception:
        return "Sorry, I couldn't parse that date. Could you try again?"

    base = AVAIL.get(dow, [])
    if not base:
        return f"The salon is closed on {date_obj.strftime('%A')}s. Would you like to try a weekday?"

    booked = await get_booked_slots(date=date, business_id=business_id, stylist=stylist)
    available = [s for s in base if s not in booked]
    if not available:
        return f"Nothing left on {date_obj.strftime('%A %d %B')} unfortunately. Want to try another day?"

    def to_12hr(t):
        h, m = map(int, t.split(":"))
        period = "am" if h < 12 else "pm"
        h = h % 12 or 12
        return f"{h}:{m:02d}{period}" if m else f"{h}{period}"

    options = [to_12hr(s) for s in available[:5]]
    suffix = ", and more after that" if len(available) > 5 else ""
    return f"On {date_obj.strftime('%A %d %B')} we've got {', '.join(options)}{suffix}."


async def _book_appointment(service: str, stylist: str, date: str, time: str,
                            customer_phone: str, customer_name: str,
                            business_id: str) -> str:
    time_24 = _parse_time_24(time)
    booked = await get_booked_slots(date=date, business_id=business_id, stylist=stylist)
    if time_24 in booked:
        return (
            f"Oh no, looks like {time} on {date} just got snapped up. "
            f"Want to pick another time?"
        )

    duration = _duration(service)
    await create_booking(
        business_id=business_id,
        service=service,
        staff_name=stylist or "(anyone)",
        date=date,
        time=time_24,
        duration_mins=duration,
        customer_phone=customer_phone,
        customer_name=customer_name,
        source="voice",
    )

    # Upsert customer record for returning caller recognition
    if customer_phone and customer_name:
        try:
            await upsert_customer(
                phone=customer_phone,
                name=customer_name,
                business_id=business_id,
            )
        except Exception as e:
            print(f"[DB] upsert_customer failed: {e}")

    booking_link = BOOKING_CONFIRM_URL
    try:
        send_booking_sms(phone=customer_phone, booking_link=booking_link)
    except Exception as e:
        print(f"[SMS] Failed: {e}")

    try:
        date_str = datetime.strptime(date, "%Y-%m-%d").strftime("%A %d %B")
    except Exception:
        date_str = date

    stylist_display = (
        stylist if stylist and stylist.lower() not in ["(anyone)", "anyone"]
        else "one of our stylists"
    )
    return (
        f"You're all locked in! {service} on {date_str} at {time} "
        f"with {stylist_display}. I'm sending you a text now with a link "
        f"to complete your $50 deposit — just tap it and you're good to go. "
        f"See you then!"
    )


async def _reschedule(customer_phone: str, new_date: str,
                      new_time: str, business_id: str) -> str:
    if not customer_phone:
        return "I'm not able to find your booking without a phone number — can you call back from your registered number?"

    upcoming = await find_booking_by_customer(customer_phone, business_id, upcoming_only=True)
    if not upcoming:
        return "I can't find any upcoming bookings for your number. Would you like to make a new booking instead?"

    booking = upcoming[0]
    new_time_24 = _parse_time_24(new_time)

    booked = await get_booked_slots(date=new_date, business_id=business_id)
    if new_time_24 in booked:
        return (
            f"Sorry, {new_time} on {new_date} isn't available. "
            f"Would you like me to check what else is free that day?"
        )

    await update_booking_status(booking["id"], "cancelled", "rescheduled")
    new_booking = await create_booking(
        business_id=business_id,
        service=booking["service"],
        staff_name=booking["staff_name"],
        date=new_date,
        time=new_time_24,
        duration_mins=booking.get("duration_mins", 60),
        customer_phone=customer_phone,
        customer_name=booking["customer_name"],
        source="voice",
    )

    try:
        date_str = datetime.strptime(new_date, "%Y-%m-%d").strftime("%A %d %B")
    except Exception:
        date_str = new_date

    try:
        send_sms(
            customer_phone,
            f"Your booking has been moved to {date_str} at {new_time}. See you then!",
        )
    except Exception as e:
        print(f"[SMS] Failed: {e}")

    return (
        f"Done! I've moved your {booking['service']} to {date_str} at {new_time}. "
        f"I'll send you a text to confirm."
    )


async def _cancel(customer_phone: str, reason: str, business_id: str) -> str:
    if not customer_phone:
        return "I can't find your booking without a phone number — could you call back from your registered number?"

    upcoming = await find_booking_by_customer(customer_phone, business_id, upcoming_only=True)
    if not upcoming:
        return "I can't find any upcoming bookings for your number."

    booking = upcoming[0]
    await update_booking_status(booking["id"], "cancelled", reason or "customer request")

    try:
        send_sms(customer_phone, "Your booking has been cancelled. We hope to see you again soon!")
    except Exception as e:
        print(f"[SMS] Failed: {e}")

    try:
        date_str = datetime.strptime(booking["date"], "%Y-%m-%d").strftime("%A %d %B")
    except Exception:
        date_str = booking["date"]

    return (
        f"All sorted — your {booking['service']} on {date_str} at {booking['time']} "
        f"has been cancelled. We'd love to see you again sometime!"
    )
