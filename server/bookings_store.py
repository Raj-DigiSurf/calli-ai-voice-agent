import json
import os
from datetime import datetime, timedelta

BOOKINGS_FILE = os.path.join(os.path.dirname(__file__), 'bookings.json')

# Service duration lookup (minutes) — used to block slots for the full appointment length
SERVICE_DURATIONS = {
    'style cut': 45,
    'stylecut': 45,
    'blowdry': 45,
    'blow dry': 45,
    'regrowth & blowdry': 120,
    'regrowth and blowdry': 120,
    'regrowth': 120,
    'highlights half head': 150,
    'highlights': 150,
    'colour & shine': 150,
    'color & shine': 150,
    'colour and shine': 150,
    'classic colour': 135,
    'classic color': 135,
    'balayage': 240,
    'ombre': 240,
    'full head': 210,
}

DEFAULT_DURATION = 60  # fallback if service not matched


def get_service_duration(service: str) -> int:
    """Return the duration in minutes for a given service name."""
    service_lower = service.lower()
    for key, mins in SERVICE_DURATIONS.items():
        if key in service_lower:
            return mins
    return DEFAULT_DURATION


def get_blocked_slots(start_time: str, duration_mins: int) -> list:
    """
    Given a start time (HH:MM) and duration, return all 15-min slots
    that fall within the appointment window.
    e.g. 10:00 + 45 min → ['10:00', '10:15', '10:30']
    """
    try:
        start = datetime.strptime(start_time, '%H:%M')
        slots = []
        t = start
        end = start + timedelta(minutes=duration_mins)
        while t < end:
            slots.append(t.strftime('%H:%M'))
            t += timedelta(minutes=15)
        return slots
    except Exception:
        return [start_time]


def _load():
    if not os.path.exists(BOOKINGS_FILE):
        return []
    with open(BOOKINGS_FILE, 'r') as f:
        return json.load(f)


def _save(data):
    with open(BOOKINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_all_bookings():
    return _load()


def get_booked_slots(date: str, stylist: str = None) -> list:
    """
    Returns all blocked time slots for a given date (and optionally stylist),
    taking service duration into account so the full appointment window is marked unavailable.
    """
    bookings = _load()
    booked = set()

    for b in bookings:
        if b['date'] != date or b.get('status') == 'cancelled':
            continue

        # Stylist match: a booking with stylist X blocks slots for X and for "(anyone)" searches
        b_stylist = b.get('stylist', '(anyone)')
        if stylist and stylist != '(anyone)' and b_stylist != '(anyone)' and b_stylist != stylist:
            continue

        duration = b.get('duration_mins', get_service_duration(b.get('service', '')))
        for slot in get_blocked_slots(b['time'], duration):
            booked.add(slot)

    return list(booked)


def save_booking(service: str, stylist: str, date: str, time: str,
                 customer_phone: str, customer_name: str = '') -> dict:
    bookings = _load()
    duration = get_service_duration(service)
    booking = {
        'id': len(bookings) + 1,
        'service': service,
        'stylist': stylist,
        'date': date,
        'time': time,
        'duration_mins': duration,
        'customer_phone': customer_phone,
        'customer_name': customer_name,
        'status': 'confirmed',
        'created_at': datetime.now().isoformat()
    }
    bookings.append(booking)
    _save(bookings)
    return booking


def cancel_booking(booking_id: int):
    bookings = _load()
    for b in bookings:
        if b['id'] == booking_id:
            b['status'] = 'cancelled'
    _save(bookings)
