from twilio.rest import Client
import os

def send_booking_sms(phone: str, booking_link: str):
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    message = client.messages.create(
        body=f"Hi! Your Dalliance Hair Studio booking is almost confirmed. Tap here to complete your $50 deposit: {booking_link}",
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        to=phone
    )
    return message.sid
