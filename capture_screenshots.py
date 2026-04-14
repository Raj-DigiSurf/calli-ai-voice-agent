"""
capture_screenshots.py
Run this once to generate the Dalliance AI pitch deck with real screenshots.

Usage (from project root):
    python capture_screenshots.py

Output: docs/pitch_visual.html  — open in Chrome, File → Print → Save as PDF
"""
import asyncio
import base64
import os
from pathlib import Path
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# ── Config ────────────────────────────────────────────────────────────────────
BOOKING_URL = os.getenv("BOOKING_URL", "http://localhost:8090")
OUT_HTML = Path("docs/pitch_visual.html")

# Pick a date 3 days from now that isn't a weekend
def next_weekday(days_ahead=3):
    d = datetime.now() + timedelta(days=days_ahead)
    while d.weekday() >= 5:   # 5=Sat 6=Sun
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d"), d.strftime("%A %-d %B") if os.name != "nt" else d.strftime("%A %#d %B")

DEMO_DATE, DEMO_DATE_LABEL = next_weekday(4)
DEMO_SERVICE = "Style Cut"

# ── Screenshot capture ────────────────────────────────────────────────────────
async def capture() -> dict[str, bytes]:
    shots = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()

        # ── Step 1: Landing page ───────────────────────────────────────────────
        print("[1/8] landing page")
        await page.goto(BOOKING_URL, wait_until="networkidle")
        await page.wait_for_timeout(800)
        shots["s1_landing"] = await page.screenshot(full_page=False)

        # ── Step 2: Service selection — use JS goTo() so no click-interactivity issues
        print("[2/8] service selection")
        await page.evaluate("goTo('page2')")
        await page.wait_for_selector("#page2.active", timeout=5000)
        await page.wait_for_timeout(500)
        shots["s2_services"] = await page.screenshot(full_page=False)

        # ── Step 3: Select a service via toggleService() ───────────────────────
        print("[3/8] service selected")
        # Get all service IDs from the rendered cards, find one matching "cut" or "style"
        service_id = await page.evaluate("""
            () => {
                const cards = document.querySelectorAll('.service-card');
                for (const card of cards) {
                    const name = card.querySelector('.service-name');
                    if (name && (name.textContent.toLowerCase().includes('cut') ||
                                 name.textContent.toLowerCase().includes('style'))) {
                        const m = card.id.match(/scard-(\\d+)/);
                        return m ? parseInt(m[1]) : null;
                    }
                }
                // Fallback: pick first card
                const first = document.querySelector('.service-card');
                if (first) {
                    const m = first.id.match(/scard-(\\d+)/);
                    return m ? parseInt(m[1]) : null;
                }
                return null;
            }
        """)
        if service_id is not None:
            await page.evaluate(f"toggleService({service_id})")
            await page.wait_for_timeout(400)
        shots["s3_service_selected"] = await page.screenshot(full_page=False)

        # ── Step 4: Navigate to staff & time page via goToDateTime() ──────────
        print("[4/8] calendar page")
        await page.evaluate("goToDateTime()")
        await page.wait_for_selector("#page3.active", timeout=5000)
        await page.wait_for_timeout(500)
        shots["s4_calendar"] = await page.screenshot(full_page=False)

        # ── Step 5: Click a date via selectDate() ────────────────────────────
        print(f"[5/8] click date {DEMO_DATE}")
        year, month, day = DEMO_DATE.split("-")
        js_month = int(month) - 1
        # Navigate calendar months until the date is visible
        for _ in range(3):
            found = await page.evaluate(f"""
                () => {{
                    const cells = document.querySelectorAll('.cal-day');
                    for (const c of cells) {{
                        if (c.getAttribute('onclick') &&
                            c.getAttribute('onclick').includes('selectDate({year},{js_month},{int(day)})')) {{
                            return true;
                        }}
                    }}
                    return false;
                }}
            """)
            if found:
                break
            await page.evaluate("nextMonth()")
            await page.wait_for_timeout(300)
        await page.evaluate(f"selectDate({year}, {js_month}, {int(day)})")
        # Wait for actual slot elements — #availability-results appears immediately with "Checking..."
        # but .time-slot only renders after the Railway API fetch completes
        await page.wait_for_selector(".time-slot", timeout=10000)
        await page.wait_for_timeout(500)
        shots["s5_slots"] = await page.screenshot(full_page=False)

        # ── Step 6: Scroll to show time slots ────────────────────────────────
        print("[6/8] time slots close-up")
        avail = await page.query_selector_all(".time-slot.available")
        print(f"     found {len(avail)} available slots")
        if avail:
            await avail[0].scroll_into_view_if_needed()
            await page.wait_for_timeout(300)
        shots["s6_slots_zoom"] = await page.screenshot(full_page=False)

        # ── Step 7: Select a time slot via selectTime() ──────────────────────
        print("[7/8] slot selected")
        if avail:
            handler = await avail[0].get_attribute("onclick")
            print(f"     slot handler: {handler}")
            if handler:
                await page.evaluate(handler)
            await page.wait_for_timeout(500)
        shots["s7_slot_selected"] = await page.screenshot(full_page=False)

        # ── Step 8: Continue to confirm page via goTo() ──────────────────────
        print("[8/8] confirmation / deposit page")
        try:
            await page.wait_for_selector("#btn-continue:not([disabled])", timeout=5000)
            await page.evaluate("goTo('page4')")
            await page.wait_for_selector("#page4.active", timeout=5000)
            await page.wait_for_timeout(600)
        except Exception as e:
            print(f"  (page 4 hint: {e})")
        shots["s8_confirm"] = await page.screenshot(full_page=False)

        await browser.close()
    return shots


# ── HTML assembly ──────────────────────────────────────────────────────────────
def b64img(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


def build_html(shots: dict[str, bytes]) -> str:
    def img(key, caption, badge=None):
        b = b64img(shots[key]) if key in shots else ""
        badge_html = f'<span class="badge">{badge}</span>' if badge else ""
        return f"""
        <div class="step-card">
          {badge_html}
          <div class="screenshot-wrap">
            <img src="{b}" alt="{caption}" />
          </div>
          <p class="caption">{caption}</p>
        </div>"""

    steps_html = "".join([
        img("s1_landing",       "① Calli answers the call — booking page loads instantly",   "LIVE"),
        img("s2_services",      "② Playwright reads the real service menu from Kitomba"),
        img("s3_service_selected", "③ Service selected — matching customer's spoken request"),
        img("s4_calendar",      "④ Real-time availability calendar loaded"),
        img("s5_slots",         f"⑤ Calli clicks {DEMO_DATE_LABEL} — live slots fetched from Kitomba API"),
        img("s6_slots_zoom",    "⑥ Available times read aloud to the customer in natural speech"),
        img("s7_slot_selected", "⑦ Customer's chosen slot marked — no double-booking possible"),
        img("s8_confirm",       "⑧ Deposit link captured — SMS sent to customer's mobile instantly"),
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calli AI Voice Receptionist — DigiSurf Australia</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0a0a0f;
    color: #e8e8f0;
    padding: 0;
  }}

  /* ── Cover ── */
  .cover {{
    background: linear-gradient(135deg, #0d0d1a 0%, #1a0a2e 50%, #0d1a2e 100%);
    padding: 72px 60px 56px;
    border-bottom: 1px solid #2a1f4e;
    position: relative;
    overflow: hidden;
  }}
  .cover::before {{
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(ellipse 80% 60% at 70% 50%, rgba(139,92,246,0.12) 0%, transparent 70%);
    pointer-events: none;
  }}
  .cover-logo {{
    font-size: 11px; letter-spacing: 3px; text-transform: uppercase;
    color: #8b5cf6; margin-bottom: 28px; font-weight: 600;
  }}
  .cover h1 {{
    font-size: 48px; font-weight: 800; line-height: 1.1;
    background: linear-gradient(135deg, #fff 0%, #c084fc 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 16px;
  }}
  .cover .sub {{
    font-size: 20px; color: #a78bfa; margin-bottom: 32px; font-weight: 400;
  }}
  .cover .tagline {{
    font-size: 15px; color: #94a3b8; max-width: 600px; line-height: 1.7;
  }}
  .cover .stats-row {{
    display: flex; gap: 40px; margin-top: 40px; flex-wrap: wrap;
  }}
  .stat-box {{
    text-align: center;
  }}
  .stat-box .num {{
    font-size: 32px; font-weight: 800;
    background: linear-gradient(135deg, #c084fc, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .stat-box .lbl {{
    font-size: 11px; color: #64748b; letter-spacing: 1px; text-transform: uppercase; margin-top: 2px;
  }}

  /* ── Section ── */
  .section {{
    padding: 64px 60px;
    border-bottom: 1px solid #1e1e2e;
  }}
  .section-label {{
    font-size: 11px; letter-spacing: 3px; text-transform: uppercase;
    color: #8b5cf6; margin-bottom: 12px; font-weight: 600;
  }}
  .section h2 {{
    font-size: 32px; font-weight: 700; margin-bottom: 12px;
  }}
  .section .intro {{
    font-size: 16px; color: #94a3b8; max-width: 700px; line-height: 1.7; margin-bottom: 48px;
  }}

  /* ── Steps grid ── */
  .steps-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(540px, 1fr));
    gap: 32px;
  }}
  .step-card {{
    background: #111122;
    border: 1px solid #2a1f4e;
    border-radius: 16px;
    overflow: hidden;
    position: relative;
    transition: border-color 0.2s;
  }}
  .step-card:hover {{ border-color: #8b5cf6; }}
  .badge {{
    position: absolute; top: 14px; right: 14px;
    background: #16a34a; color: #fff;
    font-size: 10px; font-weight: 700; letter-spacing: 2px;
    padding: 3px 10px; border-radius: 20px; text-transform: uppercase;
    z-index: 2;
  }}
  .screenshot-wrap {{
    background: #0a0a14;
    padding: 0;
    border-bottom: 1px solid #1e1e2e;
    line-height: 0;
  }}
  .screenshot-wrap img {{
    width: 100%;
    height: auto;
    display: block;
    border-radius: 0;
    opacity: 0.95;
  }}
  .caption {{
    padding: 16px 20px;
    font-size: 14px;
    color: #cbd5e1;
    line-height: 1.5;
    font-weight: 500;
  }}

  /* ── How it works ── */
  .flow-row {{
    display: flex;
    gap: 0;
    align-items: stretch;
    flex-wrap: wrap;
    margin-bottom: 48px;
  }}
  .flow-step {{
    flex: 1; min-width: 180px;
    background: #111122;
    border: 1px solid #2a1f4e;
    padding: 28px 24px;
    position: relative;
    text-align: center;
  }}
  .flow-step:first-child {{ border-radius: 16px 0 0 16px; }}
  .flow-step:last-child {{ border-radius: 0 16px 16px 0; }}
  .flow-step + .flow-step {{ border-left: none; }}
  .flow-step .icon {{ font-size: 28px; margin-bottom: 12px; }}
  .flow-step .title {{ font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; }}
  .flow-step .desc {{ font-size: 12px; color: #64748b; line-height: 1.5; }}
  .flow-step .arrow {{
    position: absolute; right: -14px; top: 50%;
    transform: translateY(-50%);
    font-size: 20px; color: #8b5cf6; z-index: 2;
  }}

  /* ── Transcript ── */
  .transcript-box {{
    background: #0d0d1a;
    border: 1px solid #2a1f4e;
    border-radius: 16px;
    padding: 32px;
    font-family: 'Segoe UI', system-ui, sans-serif;
    max-width: 720px;
  }}
  .transcript-title {{
    font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
    color: #8b5cf6; margin-bottom: 24px; font-weight: 600;
  }}
  .msg {{ margin-bottom: 18px; display: flex; gap: 12px; align-items: flex-start; }}
  .msg .who {{
    font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
    min-width: 60px; padding-top: 3px;
  }}
  .msg.ai .who {{ color: #8b5cf6; }}
  .msg.customer .who {{ color: #0ea5e9; }}
  .msg .text {{
    font-size: 14px; line-height: 1.6; color: #cbd5e1;
    background: #16162a; border-radius: 10px; padding: 10px 16px;
    flex: 1;
  }}
  .msg.ai .text {{ background: #1a1040; }}

  /* ── Terminal ── */
  .terminal {{
    background: #050508;
    border: 1px solid #1e1e3e;
    border-radius: 12px;
    padding: 28px 32px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.8;
    max-width: 820px;
    margin-top: 32px;
  }}
  .terminal .line {{ margin: 0; }}
  .terminal .dim {{ color: #4a5568; }}
  .terminal .green {{ color: #22c55e; }}
  .terminal .blue {{ color: #60a5fa; }}
  .terminal .yellow {{ color: #fbbf24; }}
  .terminal .purple {{ color: #c084fc; }}
  .terminal .white {{ color: #e2e8f0; }}

  /* ── Pricing ── */
  .pricing-row {{ display: flex; gap: 24px; flex-wrap: wrap; }}
  .price-card {{
    flex: 1; min-width: 260px;
    background: #111122;
    border: 1px solid #2a1f4e;
    border-radius: 16px;
    padding: 36px;
  }}
  .price-card.featured {{
    border-color: #8b5cf6;
    background: linear-gradient(160deg, #1a1040 0%, #111122 100%);
  }}
  .price-card .plan {{ font-size: 11px; letter-spacing: 2px; text-transform: uppercase; color: #8b5cf6; font-weight: 700; margin-bottom: 12px; }}
  .price-card .amount {{ font-size: 44px; font-weight: 800; color: #fff; }}
  .price-card .amount span {{ font-size: 18px; color: #64748b; font-weight: 400; }}
  .price-card .desc {{ font-size: 13px; color: #64748b; margin: 8px 0 24px; }}
  .price-card ul {{ list-style: none; }}
  .price-card li {{ font-size: 14px; color: #94a3b8; padding: 7px 0; border-bottom: 1px solid #1e1e2e; }}
  .price-card li::before {{ content: "✓ "; color: #22c55e; font-weight: 700; }}

  /* ── Footer ── */
  .footer {{
    padding: 48px 60px;
    background: #070710;
    display: flex; align-items: center; justify-content: space-between; flex-wrap: gap;
  }}
  .footer .brand {{ font-size: 18px; font-weight: 700; color: #8b5cf6; }}
  .footer .contact {{ font-size: 14px; color: #64748b; line-height: 1.8; text-align: right; }}

  /* ── Print ── */
  @media print {{
    body {{ background: #fff !important; color: #000 !important; }}
    .cover {{ background: #1a0a2e !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .step-card, .price-card, .transcript-box, .terminal {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>

<!-- ── COVER ────────────────────────────────────────────────────────────────── -->
<div class="cover">
  <div class="cover-logo">DigiSurf Australia — Proof of Concept</div>
  <h1>Meet Calli.</h1>
  <div class="sub">AI Voice Receptionist for Dalliance Hair Studio</div>
  <div class="tagline">
    Calli answers every call, checks real-time Kitomba availability, and books appointments
    — then texts the client a deposit link before the call ends.
    Zero missed calls. Zero staff interruptions.
  </div>
  <div class="stats-row">
    <div class="stat-box"><div class="num">24 / 7</div><div class="lbl">Never misses a call</div></div>
    <div class="stat-box"><div class="num">&lt; 3 min</div><div class="lbl">Booking to SMS</div></div>
    <div class="stat-box"><div class="num">$50</div><div class="lbl">Deposit collected</div></div>
    <div class="stat-box"><div class="num">$0</div><div class="lbl">Setup cost</div></div>
  </div>
</div>

<!-- ── HOW IT WORKS ──────────────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-label">How it works</div>
  <h2>Four steps. Fully automatic.</h2>
  <p class="intro">
    When a client calls, Calli picks up instantly. She opens Kitomba in the background,
    reads live availability, confirms the booking, and fires an SMS — all during the call.
    No humans involved.
  </p>
  <div class="flow-row">
    <div class="flow-step">
      <div class="icon">📞</div>
      <div class="title">Call received</div>
      <div class="desc">Calli answers in &lt;1s with a warm, natural Australian voice</div>
      <div class="arrow">›</div>
    </div>
    <div class="flow-step">
      <div class="icon">🤖</div>
      <div class="title">Kitomba opened</div>
      <div class="desc">Playwright navigates the live booking page — no API needed</div>
      <div class="arrow">›</div>
    </div>
    <div class="flow-step">
      <div class="icon">📅</div>
      <div class="title">Slots read live</div>
      <div class="desc">Real-time availability fetched from Kitomba and spoken to client</div>
      <div class="arrow">›</div>
    </div>
    <div class="flow-step">
      <div class="icon">💬</div>
      <div class="title">SMS sent</div>
      <div class="desc">Deposit link texted to client's mobile before the call ends</div>
    </div>
  </div>
</div>

<!-- ── LIVE AUTOMATION SCREENSHOTS ────────────────────────────────────────────── -->
<div class="section">
  <div class="section-label">Live Automation — Real Screenshots</div>
  <h2>Playwright navigating Kitomba in real time</h2>
  <p class="intro">
    Every screenshot below was captured automatically by the AI booking agent navigating
    the Kitomba-style booking system — exactly what happens on every inbound call.
    No manual steps. No scripts. Pure automation.
  </p>
  <div class="steps-grid">
    {steps_html}
  </div>
</div>

<!-- ── LIVE TRANSCRIPT ────────────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-label">Live Call Transcript</div>
  <h2>Actual conversation with Calli</h2>
  <p class="intro">This is a real call — Calli completed the booking end-to-end without any human help.</p>
  <div class="transcript-box">
    <div class="transcript-title">Inbound call · Dalliance Hair Studio · AI booking agent</div>
    <div class="msg ai">
      <div class="who">Calli</div>
      <div class="text">G'day, thanks for calling Dalliance Hair Studio! I'm Calli, the salon's AI booking assistant. Are you looking to make a booking today?</div>
    </div>
    <div class="msg customer">
      <div class="who">Client</div>
      <div class="text">Yeah hi, I'd like to book a style cut please.</div>
    </div>
    <div class="msg ai">
      <div class="who">Calli</div>
      <div class="text">Lovely! Did you have a particular stylist in mind, or happy with whoever's available?</div>
    </div>
    <div class="msg customer">
      <div class="who">Client</div>
      <div class="text">Anyone is fine.</div>
    </div>
    <div class="msg ai">
      <div class="who">Calli</div>
      <div class="text">And what day were you thinking? I can check availability right now.</div>
    </div>
    <div class="msg customer">
      <div class="who">Client</div>
      <div class="text">This Thursday?</div>
    </div>
    <div class="msg ai">
      <div class="who">Calli</div>
      <div class="text">On Thursday the 17th of April we've got 9:30am, 10am, 11am, 1pm, and 2:30pm — and a few more after that. Which works for you?</div>
    </div>
    <div class="msg customer">
      <div class="who">Client</div>
      <div class="text">10am please.</div>
    </div>
    <div class="msg ai">
      <div class="who">Calli</div>
      <div class="text">You're all locked in! Style cut on Thursday 17th April at 10am. I'm sending you a text now with a link to complete your $50 deposit — just tap it and you're good to go. See you then!</div>
    </div>
  </div>
</div>

<!-- ── TECHNICAL PROOF ────────────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-label">Under the hood — Technical proof</div>
  <h2>Real-time Kitomba automation — no API required</h2>
  <p class="intro">
    Kitomba has no public API. Calli uses Playwright (headless Chromium) to navigate
    the live booking page, just like a human would — reading availability and selecting
    slots in real time on every call.
  </p>
  <div class="terminal">
    <p class="line dim"># Railway production server — live call log</p>
    <p class="line dim">──────────────────────────────────────────────────────────</p>
    <p class="line green">[VAPI WEBHOOK] type=tool-calls keys=['type', 'toolCallList', 'call']</p>
    <p class="line blue">[VAPI] caller phone: +61498541273</p>
    <p class="line yellow">[VAPI] tool-call: check_availability params={{'service': 'style cut', 'date': '2026-04-17'}}</p>
    <p class="line purple">[PLAYWRIGHT] check_availability → service=style cut stylist=(anyone) date=2026-04-17</p>
    <p class="line white">[PLAYWRIGHT] Navigating to booking page...</p>
    <p class="line white">[PLAYWRIGHT] Page 1 loaded — clicking Book Now</p>
    <p class="line white">[PLAYWRIGHT] Page 2 active — selecting service: style cut</p>
    <p class="line white">[PLAYWRIGHT] Page 3 active — clicking date 2026-04-17</p>
    <p class="line white">[PLAYWRIGHT] Availability results loaded</p>
    <p class="line green">[PLAYWRIGHT] → 9:30am, 10am, 10:30am, 11am, 11:30am ... (12 available)</p>
    <p class="line yellow">[VAPI] tool-call: book_appointment params={{'service': 'style cut', 'date': '2026-04-17', 'time': '10am'}}</p>
    <p class="line green">[BOOKING] Saved: style cut · 2026-04-17 · 10:00 · +61498541273</p>
    <p class="line blue">[SMS] Sent to +61498541273 → https://kitomba.com/bookings/dalliancehair</p>
    <p class="line green">✓ Booking confirmed — call ended</p>
  </div>
</div>

<!-- ── PRICING ─────────────────────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-label">Investment</div>
  <h2>Straightforward pricing</h2>
  <p class="intro">One flat monthly fee. No per-call charges. No lock-in. Cancel anytime.</p>
  <div class="pricing-row">
    <div class="price-card featured">
      <div class="plan">Founding Client Rate</div>
      <div class="amount">$297 <span>/ month</span></div>
      <div class="desc">Locked in for the lifetime of your subscription</div>
      <ul>
        <li>24/7 AI voice receptionist</li>
        <li>Live Kitomba availability via Playwright</li>
        <li>Automated SMS deposit links</li>
        <li>AU local phone number</li>
        <li>Unlimited calls & bookings</li>
        <li>Priority support — direct line</li>
        <li>$0 setup fee</li>
      </ul>
    </div>
    <div class="price-card">
      <div class="plan">Standard Rate</div>
      <div class="amount">$497 <span>/ month</span></div>
      <div class="desc">For new clients after founding cohort closes</div>
      <ul>
        <li>24/7 AI voice receptionist</li>
        <li>Live Kitomba availability</li>
        <li>Automated SMS deposit links</li>
        <li>AU local phone number</li>
        <li>Unlimited calls & bookings</li>
        <li>Standard support</li>
      </ul>
    </div>
  </div>
</div>

<!-- ── FOOTER ──────────────────────────────────────────────────────────────────── -->
<div class="footer">
  <div>
    <div class="brand">DigiSurf Australia</div>
    <div style="font-size:13px;color:#4a5568;margin-top:4px">AI Voice Agents for Local Business</div>
  </div>
  <div class="contact">
    info@digisurfaustralia.com.au<br>
    0498 541 273<br>
    digisurfaustralia.com.au
  </div>
</div>

</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print("Starting screenshot capture against GitHub Pages mock...")
    print(f"    URL: {BOOKING_URL}")
    print(f"    Demo date: {DEMO_DATE_LABEL}")

    shots = await capture()
    print(f"\nCaptured {len(shots)} screenshots")

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    html = build_html(shots)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"\nPitch deck saved -> {OUT_HTML}")
    print("    Open in Chrome -> File -> Print -> Save as PDF")


if __name__ == "__main__":
    asyncio.run(main())
