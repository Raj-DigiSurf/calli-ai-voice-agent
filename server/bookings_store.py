import json
import os
from datetime import datetime

BOOKINGS_FILE = os.path.join(os.path.dirname(__file__), 'bookings.json')


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


def get_booked_slots(date: str, stylist: str = None):
    """
    Returns list of booked time strings for a given date (and optionally stylist).
    date format: YYYY-MM-DD
    """
    bookings = _load()
    booked = []
    for b in bookings:
        if b['date'] == date and b['status'] != 'cancelled':
            if stylist is None or stylist == '(anyone)' or b['stylist'] == stylist or b['stylist'] == '(anyone)':
                booked.append(b['time'])
    return booked


def save_booking(service: str, stylist: str, date: str, time: str, customer_phone: str, customer_name: str = ''):
    bookings = _load()
    booking = {
        'id': len(bookings) + 1,
        'service': service,
        'stylist': stylist,
        'date': date,
        'time': time,
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
