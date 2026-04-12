"""
Creates the Dalliance Hair Studio AI voice receptionist on Vapi.
Run once: python setup_vapi.py

It will print the assistant ID — save that for your Vapi dashboard / phone number config.
"""
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

VAPI_KEY = os.getenv("VAPI_PRIVATE_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/vapi/webhook")

SYSTEM_PROMPT = """You are the AI receptionist for Dalliance Hair Studio, a premium hair salon located in Oatley, NSW, Sydney Australia.

Your job is to answer calls, help clients book appointments, and answer questions about the salon — just like a warm, professional human receptionist would.

## Your personality
- Friendly, calm, and professional — with a natural Australian tone
- Always say "we" not "I" when referring to the salon (e.g. "We'd love to help")
- Keep responses concise. This is a phone call — no bullet points or long lists
- If you don't know something, say "I'll have someone from the team follow up with you"

## Salon details
- Name: Dalliance Hair Studio
- Address: Shop 3, 48 Mulga Road, Oatley NSW 2223
- Phone: (02) 9570 9011 | Mobile: 0492 954 210
- Instagram: @dalliance_hair_studio
- Hours:
  - Monday: 9:30am – 3:15pm
  - Tuesday: 9:30am – 6:15pm
  - Wednesday: 9:30am – 7:15pm
  - Thursday: 9:30am – 3:00pm
  - Friday: 9:30am – 3:15pm
  - Saturday & Sunday: Closed
- A $50 deposit is required to secure all bookings (charged on confirmation)
- Stylists: Jenn, Kaitlyn, Yuki (or "anyone available")

## Popular services (prices start from)
- Highlights Half Head Package (Long Hair): from $280, ~2.5 hrs
- Regrowth & Blowdry Long: from $152, ~2 hrs
- Colour & Shine Package Medium: from $242, ~2.5 hrs
- Full Head Highlights Long Hair: from $390, ~3.5 hrs
- Balayage / Ombre Long Hair: from $420, ~4 hrs
- Style Cut (no blow dry): from $50, ~30 min
- Blowdry Short: from $46, ~30 min

## Booking flow
1. Ask what service they'd like to book
2. Ask if they have a preferred stylist (or anyone is fine)
3. Ask what date they'd like (confirm it's a weekday)
4. Call check_availability to confirm open slots
5. Offer 2–3 time options from what's available
6. Once they choose a time, ask for their name and mobile number
7. Call book_appointment to lock in the booking
8. Confirm the booking details back to them clearly
9. Let them know a confirmation text is on its way

## Important rules
- Never make up availability — always call check_availability first
- Never confirm a booking without calling book_appointment
- If a slot conflict occurs, apologise and offer alternatives
- If they want to cancel or reschedule, let them know to call the salon directly on 0492 954 210
- Keep the call under 3 minutes where possible"""

FUNCTIONS = [
    {
        "name": "check_availability",
        "description": "Check available appointment slots at Dalliance Hair Studio for a given service, stylist preference, and date. Always call this before offering times to the caller.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service the client wants, e.g. 'Highlights Half Head' or 'Style Cut'"
                },
                "stylist": {
                    "type": "string",
                    "description": "Preferred stylist name or '(anyone)' if no preference"
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format, e.g. '2026-04-15'"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment at Dalliance Hair Studio. Call this only after the caller has confirmed a specific time slot. Sends SMS confirmation to the client.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service being booked"
                },
                "stylist": {
                    "type": "string",
                    "description": "Stylist name or '(anyone)'"
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format"
                },
                "time": {
                    "type": "string",
                    "description": "Time in 24hr format, e.g. '10:30' or '14:00'"
                },
                "customer_phone": {
                    "type": "string",
                    "description": "Client mobile number including country code, e.g. '+61412345678'"
                },
                "customer_name": {
                    "type": "string",
                    "description": "Client's first name"
                }
            },
            "required": ["service", "date", "time", "customer_phone"]
        }
    }
]

ASSISTANT_PAYLOAD = {
    "name": "Dalliance AI Receptionist",
    "model": {
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}
        ],
        "functions": FUNCTIONS,
        "temperature": 0.4,
        "maxTokens": 250
    },
    "voice": {
        "provider": "11labs",
        "voiceId": "Rachel",  # Will update to AU voice ID below
        "stability": 0.5,
        "similarityBoost": 0.75,
        "style": 0.0,
        "useSpeakerBoost": True
    },
    "firstMessage": "Hi, thanks for calling Dalliance Hair Studio in Oatley! This is the salon's AI receptionist. How can I help you today?",
    "serverUrl": WEBHOOK_URL,
    "serverUrlSecret": "",
    "endCallMessage": "Thanks for calling Dalliance! We look forward to seeing you. Bye!",
    "endCallPhrases": ["bye", "goodbye", "that's all", "thanks bye", "cheers"],
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "en-AU"
    },
    "silenceTimeoutSeconds": 20,
    "responseDelaySeconds": 0.4,
    "llmRequestDelaySeconds": 0.1,
    "maxDurationSeconds": 600,
    "backgroundSound": "office",
    "backchannelingEnabled": True,
    "backgroundDenoisingEnabled": True,
}


def get_elevenlabs_au_voice():
    """Try to find an Australian voice from ElevenLabs — falls back to Rachel."""
    el_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not el_key:
        return "Rachel"
    try:
        resp = httpx.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": el_key},
            timeout=10
        )
        voices = resp.json().get("voices", [])
        # Look for Australian English voices
        for v in voices:
            labels = v.get("labels", {})
            if "australian" in str(labels).lower() or "au" in str(labels).lower():
                print(f"  Found AU voice: {v['name']} ({v['voice_id']})")
                return v["voice_id"]
        # Fallback — Charlotte is a popular ElevenLabs voice that sounds neutral/natural
        for v in voices:
            if v.get("name", "").lower() in ["charlotte", "rachel", "jessica"]:
                print(f"  Using voice: {v['name']} ({v['voice_id']})")
                return v["voice_id"]
    except Exception as e:
        print(f"  ElevenLabs voice lookup failed: {e}")
    return "Rachel"


def create_assistant():
    print("Setting up Dalliance AI Receptionist on Vapi...")
    print(f"  Webhook URL: {WEBHOOK_URL}")

    # Get best available voice
    voice_id = get_elevenlabs_au_voice()
    ASSISTANT_PAYLOAD["voice"]["voiceId"] = voice_id
    print(f"  Voice ID: {voice_id}")

    headers = {
        "Authorization": f"Bearer {VAPI_KEY}",
        "Content-Type": "application/json"
    }

    resp = httpx.post(
        "https://api.vapi.ai/assistant",
        headers=headers,
        json=ASSISTANT_PAYLOAD,
        timeout=30
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        assistant_id = data.get("id")
        print(f"\n[OK] Assistant created successfully!")
        print(f"  Assistant ID: {assistant_id}")
        print(f"  Name: {data.get('name')}")
        print(f"\nNext step: Go to your Vapi dashboard -> Phone Numbers")
        print(f"  -> Assign assistant ID: {assistant_id} to your number +16414018386")
        print(f"\nSave this ID in your .env:")
        print(f"  VAPI_ASSISTANT_ID={assistant_id}")

        # Save assistant ID to .env automatically
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        with open(env_path, 'a') as f:
            f.write(f"\nVAPI_ASSISTANT_ID={assistant_id}\n")
        print(f"\n  [OK] Saved to .env")
        return assistant_id
    else:
        print(f"\n[FAIL] Failed to create assistant: {resp.status_code}")
        print(resp.text)
        return None


def list_assistants():
    """List existing Vapi assistants — useful to avoid creating duplicates."""
    headers = {"Authorization": f"Bearer {VAPI_KEY}"}
    resp = httpx.get("https://api.vapi.ai/assistant", headers=headers, timeout=10)
    if resp.status_code == 200:
        assistants = resp.json()
        if assistants:
            print("Existing assistants:")
            for a in assistants:
                print(f"  {a['id']} — {a.get('name', 'unnamed')}")
        else:
            print("No assistants found.")
    return resp.json() if resp.status_code == 200 else []


def assign_phone_number(assistant_id: str):
    """Assign the assistant to your Twilio phone number in Vapi."""
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER", "+16414018386")
    headers = {
        "Authorization": f"Bearer {VAPI_KEY}",
        "Content-Type": "application/json"
    }

    # First get the phone number ID from Vapi
    resp = httpx.get("https://api.vapi.ai/phone-number", headers=headers, timeout=10)
    if resp.status_code != 200:
        print(f"Could not list phone numbers: {resp.status_code}")
        print("  -> Manually assign the assistant in Vapi dashboard")
        return

    numbers = resp.json()
    target = None
    for n in numbers:
        if n.get("number") == twilio_number or n.get("twilioPhoneNumber") == twilio_number:
            target = n
            break

    if not target:
        print(f"Phone number {twilio_number} not found in Vapi.")
        print("  -> Import it first: Vapi dashboard -> Phone Numbers -> Import Twilio number")
        print(f"  -> Then assign assistant ID: {assistant_id}")
        return

    # Update the phone number to use this assistant
    phone_id = target["id"]
    patch_resp = httpx.patch(
        f"https://api.vapi.ai/phone-number/{phone_id}",
        headers=headers,
        json={"assistantId": assistant_id},
        timeout=10
    )
    if patch_resp.status_code == 200:
        print(f"  [OK] Phone number {twilio_number} assigned to assistant {assistant_id}")
    else:
        print(f"  [FAIL] Could not assign: {patch_resp.status_code} {patch_resp.text}")
        print(f"  -> Manually assign in Vapi dashboard")


if __name__ == "__main__":
    print("=" * 55)
    print("  Dalliance AI Receptionist — Vapi Setup")
    print("=" * 55)

    # Check for existing assistants first
    existing = list_assistants()

    # Check if one already exists with our name
    dalliance_exists = next(
        (a for a in existing if "dalliance" in a.get("name", "").lower()),
        None
    )

    if dalliance_exists:
        print(f"\nAssistant already exists: {dalliance_exists['id']}")
        print("Skipping creation. To recreate, delete it in the Vapi dashboard first.")
        assistant_id = dalliance_exists["id"]
    else:
        assistant_id = create_assistant()

    if assistant_id:
        print("\nAttempting to assign to phone number...")
        assign_phone_number(assistant_id)
        print("\n[OK] Setup complete.")
        print(f"\nTest by calling: {os.getenv('TWILIO_PHONE_NUMBER', '+16414018386')}")
