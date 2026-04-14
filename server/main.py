"""
main.py — FastAPI app entry point.

Registers all routers. Business logic lives in routers/ and core/.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from core.config import PORT
from routers.vapi import router as vapi_router
from routers.bookings import router as bookings_router

app = FastAPI(title="Calli AI Voice Agent", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(vapi_router)
app.include_router(bookings_router)

# ── Dashboard static files ────────────────────────────────────────────────────
_dashboard = Path(__file__).parent.parent / "dashboard"
if _dashboard.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_dashboard), html=True), name="dashboard")

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "calli-ai-voice-agent", "version": "2.0.0"}


# ── Playwright debug ──────────────────────────────────────────────────────────
@app.get("/debug/playwright")
async def debug_playwright():
    import subprocess
    import os
    browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "not set")
    try:
        result = subprocess.run(
            ["playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=10,
        )
        dry_run = result.stdout + result.stderr
    except Exception as e:
        dry_run = str(e)
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("about:blank")
            await browser.close()
        launch_ok, launch_err = True, None
    except Exception as e:
        launch_ok, launch_err = False, str(e)
    return {
        "PLAYWRIGHT_BROWSERS_PATH": browsers_path,
        "chromium_launch": "OK" if launch_ok else "FAILED",
        "error": launch_err,
        "dry_run": dry_run[:500],
    }
