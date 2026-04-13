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

SYSTEM_PROMPT = """You are Calli, the AI booking assistant for Dalliance Hair Studio — a premium hair salon in Oatley, Sydney.

## Personality
Warm, natural, and Australian. You sound like a real person — not a robot reading a script. Light Aussie expressions are welcome ("no worries", "beauty", "ripper") but keep it professional. Short responses only — this is a phone call.

## Your only job
New bookings. Nothing else. For anything else (questions, complaints, reschedules, cancellations) → "No worries! Best to give the team a ring on 0498541273 and they'll sort you out."

## Conversation flow — keep it natural, don't rush
1. Confirm they want to make a booking. If not → redirect to 0498541273.
2. Ask their first name.
3. Ask what service they're after. If vague (e.g. "haircut"), gently clarify — Style Cut? Colour? — but don't over-interrogate.
4. Ask if they have a preferred stylist (Jenn, Kaitlyn, or Yuki) or if anyone's fine.
5. Ask what day they'd like. You understand natural language — "tomorrow", "this Wednesday", "the 15th" are all fine. But before calling check_availability, always call get_current_date first so you know today's actual date and can calculate the correct calendar date. The salon is closed Saturdays and Sundays.
6. Call check_availability with the service, stylist, and date (YYYY-MM-DD format).
7. Offer 2–3 times naturally. Don't read a full list.
8. Once they confirm a time → call book_appointment.
9. Confirm the booking back to them warmly and let them know a text is on its way with a deposit link.

## Important
- Always call check_availability before quoting times. Never make up slots.
- Always call book_appointment to confirm. Never just say "you're booked" without calling it.
- Dates go to the tool in YYYY-MM-DD format. Call get_current_date first, then resolve relative dates yourself.
- If a day is a weekend, gently let them know the salon is closed and suggest a weekday.
- Keep all responses under 2-3 sentences.
- NEVER ask for a phone number. The system captures it automatically. Do not mention it.
- NEVER use markdown formatting — no bold, no asterisks, no bullet points. Plain spoken words only. This is a voice call.

## Salon hours (Mon–Fri only)
Mon 9:30am–3:15pm | Tue 9:30am–6:15pm | Wed 9:30am–7:15pm | Thu 9:30am–3:00pm | Fri 9:30am–3:15pm

## Services (for reference)
- Style Cut & Finish Short/Med: $75–$90, 45 min
- Style Cut & Finish Long: $95–$110, 45 min
- Blowdry Long: $66, 45 min
- Regrowth & Blowdry Medium: from $144, 2 hrs
- Regrowth & Blowdry Long: from $152, 2 hrs
- Highlights Half Head Short/Med: from $255, 2.5 hrs
- Highlights Half Head Long: from $280, 2.5 hrs
- Colour & Shine Package Medium: from $242, 2.5 hrs
- Classic Colour Package: from $203, 2.25 hrs

## Stylists: Jenn, Kaitlyn, Yuki
## $50 deposit required to confirm all bookings"""

FUNCTIONS = [
    {
        "name": "get_current_date",
        "description": "Returns today's date and day of the week. Always call this first whenever the caller uses relative dates like 'today', 'tomorrow', 'this Wednesday', 'next Tuesday', etc. so you can calculate the correct calendar date before calling check_availability.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
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
                    "description": "Client mobile number — only include if explicitly provided by the caller. Do not ask for it."
                },
                "customer_name": {
                    "type": "string",
                    "description": "Client's first name"
                }
            },
            "required": ["service", "date", "time"]
        }
    }
]

ASSISTANT_PAYLOAD = {
    "name": "Calli — Dalliance AI Booking Assistant",
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
        "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Rachel — natural, warm female voice
        "stability": 0.5,
        "similarityBoost": 0.75,
        "style": 0.0,
        "useSpeakerBoost": True
    },
    "firstMessage": "G'day, thanks for calling Dalliance Hair Studio! I'm Calli, the salon's AI booking assistant — think of me as the world's most organised receptionist who never loses a pen. Are you looking to make a booking today?",
    "serverUrl": WEBHOOK_URL,
    "serverUrlSecret": "",
    "endCallMessage": "Beauty! Thanks for calling Dalliance — we'll see you then. Have a ripper day, bye!",
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
    """Kept for reference. Voice is now Azure en-AU-NatashaNeural — no ElevenLabs needed."""
    return "en-AU-NatashaNeural"


def create_assistant():
    print("Setting up Calli — Dalliance AI Booking Assistant on Vapi...")
    print(f"  Webhook URL: {WEBHOOK_URL}")
    print(f"  Voice: {ASSISTANT_PAYLOAD['voice']['provider']} / {ASSISTANT_PAYLOAD['voice']['voiceId']}")

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


def update_assistant(assistant_id: str):
    """Push the latest system prompt, first message, and settings to an existing Vapi assistant."""
    print(f"Updating assistant {assistant_id}...")
    print(f"  Voice: {ASSISTANT_PAYLOAD['voice']['provider']} / {ASSISTANT_PAYLOAD['voice']['voiceId']}")

    headers = {
        "Authorization": f"Bearer {VAPI_KEY}",
        "Content-Type": "application/json"
    }
    resp = httpx.patch(
        f"https://api.vapi.ai/assistant/{assistant_id}",
        headers=headers,
        json=ASSISTANT_PAYLOAD,
        timeout=30
    )
    if resp.status_code == 200:
        print(f"[OK] Assistant {assistant_id} updated successfully.")
    else:
        print(f"[FAIL] {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    import sys
    print("=" * 55)
    print("  Calli — Dalliance AI Booking Assistant Setup")
    print("=" * 55)

    # Check for existing assistants first
    existing = list_assistants()

    calli_exists = next(
        (a for a in existing if "dalliance" in a.get("name", "").lower() or "calli" in a.get("name", "").lower()),
        None
    )

    # --update flag: push latest config to existing assistant
    if "--update" in sys.argv:
        if calli_exists:
            update_assistant(calli_exists["id"])
        else:
            print("No existing assistant found to update. Run without --update to create one.")
        sys.exit(0)

    if calli_exists:
        print(f"\nAssistant already exists: {calli_exists['id']}")
        print("To update it with latest config, run: python setup_vapi.py --update")
        assistant_id = calli_exists["id"]
    else:
        assistant_id = create_assistant()

    if assistant_id:
        print("\nAttempting to assign to phone number...")
        assign_phone_number(assistant_id)
        print("\n[OK] Setup complete.")
        print(f"\nTest by calling: {os.getenv('TWILIO_PHONE_NUMBER', '+16414018386')}")
