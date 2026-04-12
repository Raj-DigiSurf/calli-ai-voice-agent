"""
Dalliance AI Receptionist — Full Test Launcher
Starts: FastAPI server + ngrok tunnel + updates Vapi webhook URL automatically

Run: python start.py
Then call +1 (641) 401-8386 to test the voice agent!
"""
import os
import sys
import time
import threading
import subprocess
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

VAPI_KEY = os.getenv("VAPI_PRIVATE_KEY")
ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "503bb983-94d0-4c07-a883-538a8572228a")
PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "+16414018386")


def update_vapi_webhook(public_url: str):
    """Update the Vapi assistant's serverUrl to the ngrok public URL."""
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
        print(f"[OK] Vapi webhook updated: {webhook_url}")
    else:
        print(f"[WARN] Could not update Vapi webhook: {resp.status_code}")
        print(f"  -> Manually set webhook in Vapi dashboard to: {webhook_url}")


def start_mock_page():
    """Serve the mock booking page on port 8080."""
    mock_dir = os.path.join(os.path.dirname(__file__), '..', 'mock-booking')
    subprocess.Popen(
        [sys.executable, "-m", "http.server", "8080"],
        cwd=mock_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print("[OK] Mock booking page running at http://localhost:8080")


def start_ngrok():
    """Start ngrok tunnel to FastAPI on port 8000."""
    try:
        from pyngrok import ngrok, conf

        # Use free ngrok (no auth token needed for basic HTTP tunnel)
        tunnel = ngrok.connect(8000, "http")
        public_url = tunnel.public_url
        if public_url.startswith("http://"):
            public_url = "https://" + public_url[7:]
        print(f"[OK] ngrok tunnel active: {public_url}")
        return public_url
    except Exception as e:
        print(f"[WARN] ngrok failed: {e}")
        print("  -> If you have ngrok installed, run: ngrok http 8000")
        print("  -> Then update Vapi webhook URL manually in the dashboard")
        return None


def wait_for_server(url: str, max_wait: int = 15):
    """Poll until the FastAPI server is up."""
    for i in range(max_wait):
        try:
            resp = httpx.get(f"{url}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


if __name__ == "__main__":
    print("=" * 55)
    print("  Dalliance AI Receptionist — Starting Up")
    print("=" * 55)

    # Start mock booking page
    start_mock_page()

    # Start FastAPI in background
    print("Starting FastAPI server on port 8000...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=os.path.dirname(__file__),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    # Wait for server to come up
    if wait_for_server("http://localhost:8000"):
        print("[OK] FastAPI server running at http://localhost:8000")
    else:
        print("[WARN] FastAPI server may not be ready yet, continuing...")

    # Start ngrok tunnel
    public_url = start_ngrok()

    if public_url:
        # Update Vapi with the new public URL
        update_vapi_webhook(public_url)

    print()
    print("=" * 55)
    print("  READY TO TEST!")
    print("=" * 55)
    print(f"  Call this number to test the voice agent:")
    print(f"  {PHONE_NUMBER}")
    print()
    print("  Local endpoints:")
    print("  Mock booking page: http://localhost:8080")
    print("  FastAPI server:    http://localhost:8000")
    print("  Bookings log:      http://localhost:8000/bookings")
    print("  Availability test: http://localhost:8000/availability?date=2026-04-14")
    if public_url:
        print(f"  Public webhook:    {public_url}/vapi/webhook")
    print()
    print("  Press Ctrl+C to stop all services.")
    print("=" * 55)

    # Stream FastAPI logs
    try:
        for line in server_proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server_proc.terminate()
        try:
            from pyngrok import ngrok
            ngrok.kill()
        except Exception:
            pass
        print("All services stopped.")
