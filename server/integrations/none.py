"""
integrations/none.py — Calli Starter integration.

For businesses with NO existing booking system. We ARE their booking system.
Availability is determined purely from the business's configured hours + staff
schedule stored in our own database. No Playwright, no external API.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from core.database import get_booked_slots

# Standard 15-minute slot grid for a full day (09:00–19:00)
_ALL_SLOTS = [
    f"{h:02d}:{m:02d}"
    for h in range(9, 19)
    for m in (0, 15, 30, 45)
]

# Default weekly schedule if business hasn't configured custom hours yet
# Key = Python weekday (0=Mon … 6=Sun), Value = list of open HH:MM slots
_DEFAULT_SCHEDULE: dict[int, list[str]] = {
    0: [s for s in _ALL_SLOTS if "09:" <= s <= "17:"],   # Mon
    1: [s for s in _ALL_SLOTS if "09:" <= s <= "17:"],   # Tue
    2: [s for s in _ALL_SLOTS if "09:" <= s <= "17:"],   # Wed
    3: [s for s in _ALL_SLOTS if "09:" <= s <= "17:"],   # Thu
    4: [s for s in _ALL_SLOTS if "09:" <= s <= "17:"],   # Fri
    5: [],   # Sat — closed by default
    6: [],   # Sun — closed by default
}


async def get_availability(service: str, stylist: str, date: str,
                           business_id: str = "default",
                           schedule: dict = None) -> str:
    """
    Return a natural-language availability string for Calli to read aloud.
    Uses the business's configured schedule (or default) minus already-booked slots.
    """
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return "Sorry, I couldn't parse that date. Could you try again?"

    dow = date_obj.weekday()   # 0=Mon … 6=Sun
    sched = schedule or _DEFAULT_SCHEDULE
    base_slots = sched.get(dow, [])

    if not base_slots:
        return (
            f"We're not open on {date_obj.strftime('%A')}s. "
            f"Would you like to try a weekday instead?"
        )

    booked = await get_booked_slots(date=date, business_id=business_id, stylist=stylist)
    available = [s for s in base_slots if s not in booked]

    if not available:
        return (
            f"{date_obj.strftime('%A %d %B')} is fully booked. "
            f"Would you like to try another day?"
        )

    display = [_to_12hr(s) for s in available[:5]]
    suffix = ", and more after that" if len(available) > 5 else ""
    return (
        f"On {date_obj.strftime('%A %d %B')} we've got "
        f"{', '.join(display)}{suffix}. Which time works best for you?"
    )


def _to_12hr(t: str) -> str:
    h, m = map(int, t.split(":"))
    period = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{period}" if m else f"{h12}{period}"
