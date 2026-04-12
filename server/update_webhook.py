"""
Update the Vapi assistant's webhook URL to your current ngrok URL.

Usage:
  python update_webhook.py https://abc123.ngrok.io
"""
import sys
import os
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

VAPI_KEY = os.getenv("VAPI_PRIVATE_KEY")
ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "503bb983-94d0-4c07-a883-538a8572228a")

def update(public_url: str):
    # Strip trailing slash
    public_url = public_url.rstrip("/")
    # Force https
    if public_url.startswith("http://"):
        public_url = "https://" + public_url[7:]

    webhook_url = f"{public_url}/vapi/webhook"
    headers = {
        "Authorization": f"Bearer {VAPI_KEY}",
        "Content-Type": "application/json"
    }
    resp = httpx.patch(
        f"https://api.vapi.ai/assistant/{ASSISTANT_ID}",
        headers=headers,
        json={"serverUrl": webhook_url},
        timeout=15
    )
    if resp.status_code == 200:
        print(f"[OK] Webhook updated to: {webhook_url}")
        print(f"     Call +1 (641) 401-8386 to test!")
    else:
        print(f"[FAIL] {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_webhook.py https://your-ngrok-url.ngrok.io")
        sys.exit(1)
    update(sys.argv[1])
