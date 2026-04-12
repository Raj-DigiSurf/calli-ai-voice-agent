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


# ─── VAPI WEBHOOK (voice agent function calls) ────────────────────────────────

@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})
    call_type = message.get("type")

    if call_type == "function-call":
        function_name = message.get("functionCall", {}).get("name")
        parameters = message.get("functionCall", {}).get("parameters", {})

        if function_name == "check_availability":
            result = await check_availability_fn(
                service=parameters.get("service"),
                stylist=parameters.get("stylist"),
                date=parameters.get("date")
            )
            return JSONResponse({"result": result})

        elif function_name == "book_appointment":
            result = await book_appointment_fn(
                service=parameters.get("service"),
                stylist=parameters.get("stylist"),
                date=parameters.get("date"),
                time=parameters.get("time"),
                customer_phone=parameters.get("customer_phone")
            )
            return JSONResponse({"result": result})

    return JSONResponse({"result": "ok"})


async def check_availability_fn(service: str, stylist: str, date: str):
    """
    Used by Vapi voice agent. Returns available slots as a readable string.
    Calls the same logic as the /availability endpoint directly.
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
        return "Sorry, I couldn't understand that date. Please say it like: April 15th."

    base_slots = AVAIL.get(dow, [])
    if not base_slots:
        return f"The salon is closed on {date_obj.strftime('%A')}s. Would you like to try a different day?"

    booked = get_booked_slots(date=date, stylist=stylist)
    available = [s for s in base_slots if s not in booked]

    if not available:
        return f"Unfortunately there are no available slots on {date_obj.strftime('%A, %d %B')}. Would you like to check another date?"

    # Convert 24hr to 12hr for natural speech
    def to_12hr(t):
        h, m = map(int, t.split(':'))
        period = 'am' if h < 12 else 'pm'
        h = h % 12 or 12
        return f"{h}:{m:02d}{period}" if m else f"{h}{period}"

    readable = [to_12hr(s) for s in available]
    return f"On {date_obj.strftime('%A, %d %B')}, we have availability at: {', '.join(readable[:8])}{'...' if len(readable) > 8 else ''}. Which time suits you best?"


async def book_appointment_fn(service: str, stylist: str, date: str, time: str, customer_phone: str, customer_name: str = ''):
    """
    Used by Vapi voice agent. Saves booking directly to JSON and sends SMS confirmation.
    """
    from sms import send_booking_sms
    from datetime import datetime

    # Normalise time: if voice agent says "2pm" or "2:00pm", convert to 24hr for storage
    def parse_time(t: str) -> str:
        t = t.strip().lower().replace(' ', '')
        try:
            if 'am' in t or 'pm' in t:
                for fmt in ('%I:%M%p', '%I%p'):
                    try:
                        return datetime.strptime(t, fmt).strftime('%H:%M')
                    except ValueError:
                        continue
        except Exception:
            pass
        return t  # already 24hr

    time_24 = parse_time(time)

    # Check slot still available
    booked = get_booked_slots(date=date, stylist=stylist)
    if time_24 in booked:
        return f"Sorry, {time} on {date} has just been taken. Would you like to choose another time?"

    booking = save_booking(
        service=service,
        stylist=stylist if stylist else '(anyone)',
        date=date,
        time=time_24,
        customer_phone=customer_phone,
        customer_name=customer_name
    )

    booking_link = f"http://localhost:8080#confirmed"
    if customer_phone:
        try:
            send_booking_sms(phone=customer_phone, booking_link=booking_link)
        except Exception as e:
            print(f"SMS failed: {e}")

    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        date_str = date_obj.strftime('%A, %d %B')
    except Exception:
        date_str = date

    return f"Perfect! Your {service} is booked for {date_str} at {time} with {stylist or 'one of our stylists'}. We've sent a confirmation to your phone. See you then!"
