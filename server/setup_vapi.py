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

## What you can do
- Make new bookings
- Reschedule an existing booking
- Cancel an existing booking
- Add to the waitlist when nothing's available
- Take a callback request if the caller needs to speak to someone

For anything else (questions, complaints, pricing queries) → "No worries! Best to give the team a ring on 0498541273 and they'll sort you out."

## On every call — first step
Always call lookup_customer at the very start of the call. It tells you if they're a returning customer and shows any upcoming bookings. Greet returning customers by name.

## New booking flow
1. Ask their first name (skip if lookup_customer returned their name).
2. Ask what service they're after. If vague, gently clarify — Style Cut? Colour? — but don't over-interrogate.
3. Ask if they have a preferred stylist (Jenn, Kaitlyn, or Yuki) or if anyone's fine.
4. Ask what day they'd like. Call get_current_date first to know today's date, then resolve "tomorrow", "this Wednesday", etc. yourself.
5. Call check_availability with service, stylist, and date (YYYY-MM-DD).
6. Offer 2–3 times naturally.
7. Once they confirm a time → call book_appointment.
8. Confirm warmly and tell them a deposit text is on its way.

## Reschedule flow
If caller wants to reschedule: ask for the new preferred date and time, then call reschedule_appointment. You don't need to ask for the old booking — we find it by their phone number automatically.

## Cancel flow
If caller wants to cancel: briefly confirm they're sure, then call cancel_appointment. We find the booking by their phone number.

## Waitlist
If nothing's available on their preferred day: offer the waitlist. Call add_to_waitlist with their name, service, and preferred date.

## Callback
If the caller needs to speak to a human (complex request, complaint, pricing question): call log_callback_request and reassure them someone will call back shortly.

## Rules
- Always call check_availability before quoting times. Never make up slots.
- Always call book_appointment / reschedule_appointment / cancel_appointment — never just say it's done without calling the tool.
- Dates in YYYY-MM-DD format. Call get_current_date first for relative dates.
- If a day is a weekend, the salon is closed — suggest a weekday.
- Keep all responses under 2-3 sentences.
- NEVER ask for a phone number — the system captures it automatically.
- NEVER use markdown formatting — no bold, no asterisks. Plain spoken words only.

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
        "name": "lookup_customer",
        "description": "Look up the caller by their phone number. Call this at the very start of every call. Returns 'new_customer' or 'returning_customer|<name>|<upcoming booking details>'. Use the result to greet returning customers by name and skip asking for their name.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_current_date",
        "description": "Returns today's date and day of the week. Always call this before resolving relative dates like 'today', 'tomorrow', 'this Wednesday', 'next Tuesday' — so you can calculate the correct YYYY-MM-DD before calling check_availability.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "check_availability",
        "description": "Check available appointment slots at Dalliance Hair Studio for a given service, stylist preference, and date. Always call this before quoting times.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name, e.g. 'Highlights Half Head' or 'Style Cut'"},
                "stylist": {"type": "string", "description": "Preferred stylist name or '(anyone)' if no preference"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"}
            },
            "required": ["date"]
        }
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment. Call only after the caller has confirmed a specific time slot. Saves the booking and sends SMS deposit link.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service being booked"},
                "stylist": {"type": "string", "description": "Stylist name or '(anyone)'"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "string", "description": "Time in 24hr format, e.g. '10:30'"},
                "customer_name": {"type": "string", "description": "Client's first name"}
            },
            "required": ["service", "date", "time"]
        }
    },
    {
        "name": "reschedule_appointment",
        "description": "Reschedule the caller's existing upcoming booking to a new date and time. The existing booking is found automatically by their phone number — no need to ask for it.",
        "parameters": {
            "type": "object",
            "properties": {
                "new_date": {"type": "string", "description": "New date in YYYY-MM-DD format"},
                "new_time": {"type": "string", "description": "New time in 24hr format, e.g. '14:00'"}
            },
            "required": ["new_date", "new_time"]
        }
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel the caller's upcoming booking. Found automatically by their phone number.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Reason for cancellation, e.g. 'customer request' or 'unwell'"}
            },
            "required": []
        }
    },
    {
        "name": "add_to_waitlist",
        "description": "Add the caller to the waitlist when no slots are available on their preferred day. They'll be texted if a spot opens up.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Client's first name"},
                "service": {"type": "string", "description": "Service they want"},
                "date": {"type": "string", "description": "Preferred date in YYYY-MM-DD format"},
                "time_preference": {"type": "string", "description": "morning, afternoon, or any", "enum": ["morning", "afternoon", "any"]}
            },
            "required": ["service"]
        }
    },
    {
        "name": "log_callback_request",
        "description": "Log a callback request when the caller needs to speak to a human — complex questions, complaints, or anything Calli can't handle. Notifies the salon team to call them back.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Client's name if known"},
                "reason": {"type": "string", "description": "Brief reason for the callback request"}
            },
            "required": []
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
