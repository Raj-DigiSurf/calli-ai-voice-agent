"""
core/config.py — single source of truth for all environment variables.
Import from here everywhere; never call os.getenv() scattered through the codebase.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Vapi ──────────────────────────────────────────────────────────────────────
VAPI_PRIVATE_KEY     = os.getenv("VAPI_PRIVATE_KEY", "")
VAPI_ASSISTANT_ID    = os.getenv("VAPI_ASSISTANT_ID", "")
VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID", "")
WEBHOOK_URL          = os.getenv("WEBHOOK_URL", "")

# ── Twilio / SMS ──────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER  = os.getenv("TWILIO_PHONE_NUMBER", "")

# ── ElevenLabs ────────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY   = os.getenv("ELEVENLABS_API_KEY", "")

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY         = os.getenv("SUPABASE_KEY", "")   # anon/service role key

# ── Booking / integrations ────────────────────────────────────────────────────
MOCK_BOOKING_URL     = os.getenv("MOCK_BOOKING_URL", "http://localhost:8090")
BOOKING_CONFIRM_URL  = os.getenv("BOOKING_CONFIRM_URL", "https://kitomba.com/bookings/dalliancehair")

# ── Misc ──────────────────────────────────────────────────────────────────────
TEST_PHONE           = os.getenv("TEST_PHONE", "+61498541273")
PORT                 = int(os.getenv("PORT", "8000"))
