"""
core/sms.py — Twilio SMS sending.
business_name is passed in so this works for any client, not just Dalliance.
"""
from twilio.rest import Client
from core.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER


def send_booking_sms(phone: str, booking_link: str, business_name: str = "the salon"):
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=(
            f"Hi! Your {business_name} booking is confirmed. "
            f"Tap here to complete your $50 deposit: {booking_link}"
        ),
        from_=TWILIO_PHONE_NUMBER,
        to=phone,
    )
    return message.sid


def send_sms(phone: str, body: str):
    """Generic SMS — for reminders, waitlist alerts, callbacks, etc."""
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=body,
        from_=TWILIO_PHONE_NUMBER,
        to=phone,
    )
    return message.sid
