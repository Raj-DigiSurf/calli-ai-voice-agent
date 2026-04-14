"""
core/database.py — unified data layer.

If SUPABASE_URL + SUPABASE_KEY are set  → uses Supabase (Postgres).
Otherwise                               → falls back to local JSON files.

All callers use the same async interface regardless of which backend is active.
This means development works without Supabase configured, and production
transparently switches to the real DB once the env vars are present.
"""
from __future__ import annotations
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.config import SUPABASE_URL, SUPABASE_KEY

# ── Backend selection ─────────────────────────────────────────────────────────
_USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

if _USE_SUPABASE:
    from supabase import create_client, Client as SupabaseClient
    _sb: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("[DB] Using Supabase backend")
else:
    _sb = None
    print("[DB] Supabase not configured — using JSON fallback")

# ── JSON fallback paths ───────────────────────────────────────────────────────
_DATA_DIR  = Path(__file__).parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

_BOOKINGS_FILE  = _DATA_DIR / "bookings.json"
_CUSTOMERS_FILE = _DATA_DIR / "customers.json"
_WAITLIST_FILE  = _DATA_DIR / "waitlist.json"
_CALLBACKS_FILE = _DATA_DIR / "callbacks.json"

def _load(path: Path) -> list:
    try:
        return json.loads(path.read_text()) if path.exists() else []
    except Exception:
        return []

def _save(path: Path, data: list):
    path.write_text(json.dumps(data, indent=2, default=str))


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════════

async def get_customer_by_phone(phone: str, business_id: str = "default") -> Optional[dict]:
    """Look up a customer by phone number. Returns None if not found."""
    if _USE_SUPABASE:
        res = _sb.table("customers")\
            .select("*")\
            .eq("phone", phone)\
            .eq("business_id", business_id)\
            .limit(1)\
            .execute()
        return res.data[0] if res.data else None
    else:
        customers = _load(_CUSTOMERS_FILE)
        for c in customers:
            if c.get("phone") == phone and c.get("business_id", "default") == business_id:
                return c
        return None


async def upsert_customer(phone: str, name: str, business_id: str = "default",
                          email: str = "") -> dict:
    """Create customer if new, update name/email if existing. Returns record."""
    if _USE_SUPABASE:
        existing = await get_customer_by_phone(phone, business_id)
        if existing:
            res = _sb.table("customers")\
                .update({"name": name, "email": email, "last_seen_at": datetime.utcnow().isoformat()})\
                .eq("id", existing["id"])\
                .execute()
            return res.data[0]
        else:
            res = _sb.table("customers").insert({
                "id": str(uuid.uuid4()),
                "phone": phone,
                "name": name,
                "email": email,
                "business_id": business_id,
                "created_at": datetime.utcnow().isoformat(),
                "last_seen_at": datetime.utcnow().isoformat(),
            }).execute()
            return res.data[0]
    else:
        customers = _load(_CUSTOMERS_FILE)
        for c in customers:
            if c["phone"] == phone and c.get("business_id", "default") == business_id:
                c["name"] = name
                if email:
                    c["email"] = email
                c["last_seen_at"] = datetime.utcnow().isoformat()
                _save(_CUSTOMERS_FILE, customers)
                return c
        record = {
            "id": str(uuid.uuid4()),
            "phone": phone,
            "name": name,
            "email": email,
            "business_id": business_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_seen_at": datetime.utcnow().isoformat(),
        }
        customers.append(record)
        _save(_CUSTOMERS_FILE, customers)
        return record


# ══════════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ══════════════════════════════════════════════════════════════════════════════

async def get_bookings(business_id: str = "default", date: str = None,
                       status: str = None) -> list[dict]:
    """Fetch bookings, optionally filtered by date and/or status."""
    if _USE_SUPABASE:
        q = _sb.table("bookings").select("*").eq("business_id", business_id)
        if date:
            q = q.eq("date", date)
        if status:
            q = q.eq("status", status)
        return q.order("time").execute().data
    else:
        bookings = _load(_BOOKINGS_FILE)
        result = [b for b in bookings if b.get("business_id", "default") == business_id
                  and b.get("status") != "cancelled"]
        if date:
            result = [b for b in result if b.get("date") == date]
        if status:
            result = [b for b in result if b.get("status") == status]
        return sorted(result, key=lambda b: b.get("time", ""))


async def get_booked_slots(date: str, business_id: str = "default",
                           stylist: str = None) -> list[str]:
    """
    Return list of time strings (HH:MM) that are already occupied on a given date,
    accounting for appointment duration so overlapping slots are blocked too.
    """
    bookings = await get_bookings(business_id=business_id, date=date, status="confirmed")
    booked = []
    for b in bookings:
        if stylist and stylist.lower() not in ["(anyone)", "anyone", ""] \
                and b.get("staff_name", "").lower() != stylist.lower():
            continue
        start = b.get("time", "")
        duration = b.get("duration_mins", 45)
        if start:
            booked.extend(_expand_slots(start, duration))
    return booked


def _expand_slots(start_time: str, duration_mins: int) -> list[str]:
    """Return all 15-min interval slots occupied by an appointment."""
    try:
        start = datetime.strptime(start_time, "%H:%M")
        slots = []
        t = start
        end = start + timedelta(minutes=duration_mins)
        while t < end:
            slots.append(t.strftime("%H:%M"))
            t += timedelta(minutes=15)
        return slots
    except Exception:
        return [start_time]


async def create_booking(business_id: str, service: str, staff_name: str,
                         date: str, time: str, duration_mins: int,
                         customer_phone: str, customer_name: str,
                         source: str = "voice") -> dict:
    """Insert a new confirmed booking. Returns the created record."""
    record = {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "service": service,
        "staff_name": staff_name or "(anyone)",
        "date": date,
        "time": time,
        "duration_mins": duration_mins,
        "customer_phone": customer_phone,
        "customer_name": customer_name,
        "status": "confirmed",
        "source": source,
        "deposit_paid": False,
        "created_at": datetime.utcnow().isoformat(),
    }
    if _USE_SUPABASE:
        res = _sb.table("bookings").insert(record).execute()
        return res.data[0]
    else:
        bookings = _load(_BOOKINGS_FILE)
        bookings.append(record)
        _save(_BOOKINGS_FILE, bookings)
        return record


async def update_booking_status(booking_id: str, status: str,
                                cancelled_reason: str = "") -> Optional[dict]:
    """Set booking status: confirmed | cancelled | completed | no_show."""
    if _USE_SUPABASE:
        payload = {"status": status}
        if status == "cancelled":
            payload["cancelled_at"] = datetime.utcnow().isoformat()
            payload["cancelled_reason"] = cancelled_reason
        res = _sb.table("bookings").update(payload).eq("id", booking_id).execute()
        return res.data[0] if res.data else None
    else:
        bookings = _load(_BOOKINGS_FILE)
        for b in bookings:
            if b["id"] == booking_id:
                b["status"] = status
                if status == "cancelled":
                    b["cancelled_at"] = datetime.utcnow().isoformat()
                    b["cancelled_reason"] = cancelled_reason
                _save(_BOOKINGS_FILE, bookings)
                return b
        return None


async def find_booking_by_customer(customer_phone: str, business_id: str = "default",
                                   upcoming_only: bool = True) -> list[dict]:
    """Find all bookings for a phone number, optionally only future ones."""
    if _USE_SUPABASE:
        q = _sb.table("bookings").select("*")\
            .eq("customer_phone", customer_phone)\
            .eq("business_id", business_id)\
            .eq("status", "confirmed")
        if upcoming_only:
            today = datetime.now().strftime("%Y-%m-%d")
            q = q.gte("date", today)
        return q.order("date").order("time").execute().data
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        bookings = _load(_BOOKINGS_FILE)
        result = [
            b for b in bookings
            if b.get("customer_phone") == customer_phone
            and b.get("business_id", "default") == business_id
            and b.get("status") == "confirmed"
            and (not upcoming_only or b.get("date", "") >= today)
        ]
        return sorted(result, key=lambda b: (b.get("date",""), b.get("time","")))


# ══════════════════════════════════════════════════════════════════════════════
# WAITLIST
# ══════════════════════════════════════════════════════════════════════════════

async def add_to_waitlist(business_id: str, customer_phone: str,
                          customer_name: str, service: str,
                          preferred_date: str, time_preference: str = "any") -> dict:
    record = {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "customer_phone": customer_phone,
        "customer_name": customer_name,
        "service": service,
        "preferred_date": preferred_date,
        "time_preference": time_preference,
        "status": "waiting",
        "created_at": datetime.utcnow().isoformat(),
    }
    if _USE_SUPABASE:
        res = _sb.table("waitlist").insert(record).execute()
        return res.data[0]
    else:
        waitlist = _load(_WAITLIST_FILE)
        waitlist.append(record)
        _save(_WAITLIST_FILE, waitlist)
        return record


async def get_waitlist(business_id: str, date: str) -> list[dict]:
    if _USE_SUPABASE:
        return _sb.table("waitlist").select("*")\
            .eq("business_id", business_id)\
            .eq("preferred_date", date)\
            .eq("status", "waiting")\
            .order("created_at").execute().data
    else:
        waitlist = _load(_WAITLIST_FILE)
        return [w for w in waitlist
                if w.get("business_id", "default") == business_id
                and w.get("preferred_date") == date
                and w.get("status") == "waiting"]


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

async def log_callback(business_id: str, customer_phone: str,
                       customer_name: str, reason: str = "") -> dict:
    record = {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "customer_phone": customer_phone,
        "customer_name": customer_name,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    if _USE_SUPABASE:
        res = _sb.table("callbacks").insert(record).execute()
        return res.data[0]
    else:
        callbacks = _load(_CALLBACKS_FILE)
        callbacks.append(record)
        _save(_CALLBACKS_FILE, callbacks)
        return record


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY
# ══════════════════════════════════════════════════════════════════════════════

async def clear_all_bookings(business_id: str = "default"):
    """Wipe bookings for a business — test/dev use only."""
    if _USE_SUPABASE:
        _sb.table("bookings").delete().eq("business_id", business_id).execute()
    else:
        bookings = _load(_BOOKINGS_FILE)
        remaining = [b for b in bookings if b.get("business_id", "default") != business_id]
        _save(_BOOKINGS_FILE, remaining)
