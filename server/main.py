from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from bookings_store import get_booked_slots, save_booking, get_all_bookings
import os

load_dotenv()

app = FastAPI()

# Allow mock HTML page (localhost:8080) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "digisurf-voice-agent"}


# ─── BOOKING ENDPOINTS (used by mock page + Playwright) ───────────────────────

@app.get("/availability")
async def availability(date: str, stylist: str = None):
    """
    Returns available time slots for a given date, minus already-booked ones.
    date: YYYY-MM-DD
    stylist: optional filter
    """
    from datetime import datetime

    # Base availability by day of week (24hr format)
    AVAIL = {
        0: [], 6: [],  # closed Sun/Sat
        1: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','12:30','13:00','13:15','13:30','14:00','14:15','14:30','15:00','15:15'],
        2: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','12:30','13:00','13:15','13:30','14:00','14:15','15:00','15:15','16:00','17:00','17:15','17:30','18:00','18:15'],
        3: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','12:30','13:00','13:15','13:30','14:00','14:15','15:00','15:15','16:00','17:00','17:30','18:00','18:15','18:30','19:00','19:15'],
        4: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','12:00','12:15','13:00','13:15','14:00','14:15','14:30','15:00'],
        5: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','13:00','13:15','14:00','14:15','14:30','15:00','15:15'],
    }

    date_obj = datetime.strptime(date, '%Y-%m-%d')
    dow = date_obj.weekday() + 1  # Python: Mon=0, we want Mon=1
    if dow == 7:
        dow = 0  # Sunday

    base_slots = AVAIL.get(dow, [])
    if not base_slots:
        return {"date": date, "available": [], "message": "Salon is closed on this day"}

    booked = get_booked_slots(date=date, stylist=stylist)
    available = [s for s in base_slots if s not in booked]

    return {
        "date": date,
        "day": date_obj.strftime('%A'),
        "available": available,
        "booked": booked
    }


@app.post("/book")
async def book(request: Request):
    """
    Save a booking. Called by mock page when user confirms, and by Playwright after slot selection.
    """
    body = await request.json()
    service = body.get("service", "")
    stylist = body.get("stylist", "(anyone)")
    date = body.get("date", "")
    time = body.get("time", "")
    customer_phone = body.get("customer_phone", "")
    customer_name = body.get("customer_name", "")

    if not all([service, date, time]):
        return JSONResponse({"error": "Missing required fields: service, date, time"}, status_code=400)

    # Check slot is still available
    booked = get_booked_slots(date=date, stylist=stylist)
    if time in booked:
        return JSONResponse({"error": f"Sorry, {time} on {date} is no longer available. Please choose another time."}, status_code=409)

    booking = save_booking(
        service=service,
        stylist=stylist,
        date=date,
        time=time,
        customer_phone=customer_phone,
        customer_name=customer_name
    )

    # Send SMS if phone provided
    if customer_phone:
        try:
            from sms import send_booking_sms
            send_booking_sms(phone=customer_phone, booking_link=f"http://localhost:8080#confirmed")
        except Exception as e:
            print(f"SMS failed: {e}")

    return {
        "success": True,
        "booking_id": booking["id"],
        "message": f"Booking confirmed! {service} on {date} at {time} with {stylist}.",
        "booking": booking
    }


@app.get("/bookings")
async def list_bookings():
    """View all bookings — for testing/review."""
    return {"bookings": get_all_bookings()}


@app.delete("/bookings/clear")
async def clear_bookings():
    """Clear all test bookings. Test environment only."""
    from bookings_store import _save
    _save([])
    return {"cleared": True}


# ─── VAPI WEBHOOK (voice agent function calls) ────────────────────────────────

@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})
    call_type = message.get("type")

    # Log every incoming webhook for debugging
    print(f"[VAPI WEBHOOK] type={call_type} keys={list(message.keys())}")

    # Extract caller's phone number from the Vapi payload automatically
    # so we never need to ask the customer to say their number out loud
    caller_phone = (
        message.get("call", {}).get("customer", {}).get("number")
        or body.get("call", {}).get("customer", {}).get("number")
        or ""
    )
    if caller_phone:
        print(f"[VAPI] caller phone: {caller_phone}")

    # ── New Vapi format: tool-calls ──────────────────────────────────────────
    if call_type == "tool-calls":
        tool_calls = message.get("toolCallList", [])
        results = []
        for tool_call in tool_calls:
            fn = tool_call.get("function", {})
            function_name = fn.get("name")
            parameters = fn.get("arguments", {})
            tool_call_id = tool_call.get("id", "")
            print(f"[VAPI] tool-call: {function_name} params={parameters}")
            result = await _dispatch_function(function_name, parameters, caller_phone)
            results.append({"toolCallId": tool_call_id, "result": result})
        return JSONResponse({"results": results})

    # ── Old Vapi format: function-call ───────────────────────────────────────
    if call_type == "function-call":
        function_name = message.get("functionCall", {}).get("name")
        parameters = message.get("functionCall", {}).get("parameters", {})
        print(f"[VAPI] function-call: {function_name} params={parameters}")
        result = await _dispatch_function(function_name, parameters, caller_phone)
        return JSONResponse({"result": result})

    # Other event types (call-start, call-end, transcript, etc.) — just ack
    return JSONResponse({"result": "ok"})


async def _dispatch_function(function_name: str, parameters: dict, caller_phone: str = "") -> str:
    """Route a Vapi function call to the correct handler."""
    if function_name == "get_current_date":
        from datetime import datetime
        now = datetime.now()
        return f"Today is {now.strftime('%A, %d %B %Y')}. In YYYY-MM-DD format: {now.strftime('%Y-%m-%d')}."

    if function_name == "check_availability":
        return await check_availability_fn(
            service=parameters.get("service", ""),
            stylist=parameters.get("stylist", "(anyone)"),
            date=parameters.get("date", "")
        )
    elif function_name == "book_appointment":
        # Use caller's phone from Vapi payload; fall back to anything the AI collected
        phone = caller_phone or parameters.get("customer_phone", "")
        return await book_appointment_fn(
            service=parameters.get("service", ""),
            stylist=parameters.get("stylist", "(anyone)"),
            date=parameters.get("date", ""),
            time=parameters.get("time", ""),
            customer_phone=phone,
            customer_name=parameters.get("customer_name", "")
        )
    else:
        print(f"[VAPI] Unknown function: {function_name}")
        return f"Sorry, I don't know how to handle {function_name}."


async def check_availability_fn(service: str, stylist: str, date: str):
    """
    Returns available time slots for a given date/stylist from the bookings store.
    Playwright-based page navigation will replace this once the mock page is publicly hosted.
    """
    from datetime import datetime

    AVAIL = {
        0: [], 6: [],
        1: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','12:30','13:00','13:15','13:30','14:00','14:15','14:30','15:00','15:15'],
        2: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','12:30','13:00','13:15','13:30','14:00','14:15','15:00','15:15','16:00','17:00','17:15','17:30','18:00','18:15'],
        3: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','12:30','13:00','13:15','13:30','14:00','14:15','15:00','15:15','16:00','17:00','17:30','18:00','18:15','18:30','19:00','19:15'],
        4: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','12:00','12:15','13:00','13:15','14:00','14:15','14:30','15:00'],
        5: ['9:30','9:45','10:00','10:15','10:30','10:45','11:00','11:15','11:30','11:45','12:00','12:15','13:00','13:15','14:00','14:15','14:30','15:00','15:15'],
    }

    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        dow = date_obj.weekday() + 1
        if dow == 7:
            dow = 0
    except Exception:
        return "Sorry, I couldn't parse that date. Could you try again with something like the 15th of April?"

    base_slots = AVAIL.get(dow, [])
    if not base_slots:
        return f"The salon is closed on {date_obj.strftime('%A')}s. Would you like to try a weekday?"

    booked = get_booked_slots(date=date, stylist=stylist)
    available = [s for s in base_slots if s not in booked]

    if not available:
        return f"Unfortunately there's nothing left on {date_obj.strftime('%A %d %B')}. Would you like to try another day?"

    def to_12hr(t):
        h, m = map(int, t.split(':'))
        period = 'am' if h < 12 else 'pm'
        h = h % 12 or 12
        return f"{h}:{m:02d}{period}" if m else f"{h}{period}"

    readable = [to_12hr(s) for s in available]
    # Offer up to 5 slots naturally
    options = readable[:5]
    suffix = f", and more after that" if len(readable) > 5 else ""
    return f"On {date_obj.strftime('%A %d %B')} we've got {', '.join(options)}{suffix}."


async def book_appointment_fn(service: str, stylist: str, date: str, time: str, customer_phone: str, customer_name: str = ''):
    """
    Saves the booking and sends SMS confirmation with the deposit link.
    """
    from sms import send_booking_sms
    from datetime import datetime

    def parse_time_24(t: str) -> str:
        t = t.strip().lower().replace(' ', '')
        if 'am' in t or 'pm' in t:
            for fmt in ('%I:%M%p', '%I%p'):
                try:
                    return datetime.strptime(t, fmt).strftime('%H:%M')
                except ValueError:
                    continue
        return t

    time_24 = parse_time_24(time)

    booked = get_booked_slots(date=date, stylist=stylist)
    if time_24 in booked:
        return f"Oh no, looks like {time} on {date} just got snapped up. Want to pick another time?"

    save_booking(
        service=service,
        stylist=stylist if stylist else '(anyone)',
        date=date,
        time=time_24,
        customer_phone=customer_phone,
        customer_name=customer_name
    )

    booking_link = os.getenv("BOOKING_CONFIRM_URL", "https://kitomba.com/bookings/dalliancehair")
    # Normalise AU mobile numbers: 04xx → +614xx
    def normalise_phone(p: str) -> str:
        p = p.strip().replace(" ", "").replace("-", "")
        if p.startswith("04") and len(p) == 10:
            return "+61" + p[1:]
        if p.startswith("61") and not p.startswith("+"):
            return "+" + p
        return p

    raw_phone = customer_phone or os.getenv("TEST_PHONE", "+61498541273")
    sms_to = normalise_phone(raw_phone)
    try:
        send_booking_sms(phone=sms_to, booking_link=booking_link)
    except Exception as e:
        print(f"[SMS] Failed: {e}")

    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        date_str = date_obj.strftime('%A %d %B')
    except Exception:
        date_str = date

    stylist_display = stylist if stylist and stylist.lower() not in ["(anyone)", "anyone"] else "one of our stylists"
    return f"You're all locked in! {service} on {date_str} at {time} with {stylist_display}. I'm sending you a text now with a link to complete your $50 deposit — just tap it and you're good to go. See you then!"
