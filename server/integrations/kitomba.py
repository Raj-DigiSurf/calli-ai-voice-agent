"""
integrations/kitomba.py — Playwright browser automation for Kitomba booking pages.

Works against the mock page (localhost / GitHub Pages) in test mode and the
real Kitomba URL in production. Swap MOCK_BOOKING_URL env var to go live.

Flow:
  get_availability(service, stylist, date)
    → Opens page → selects service → navigates to Page 3 → clicks date
    → Reads available time slots → returns readable string for voice agent

  select_slot(service, stylist, date, time)
    → Full booking navigation → stops at Page 4 (Facebook login)
    → Returns the Page 4 URL to send to the customer via SMS
"""
from playwright.async_api import async_playwright
from core.config import MOCK_BOOKING_URL


async def get_availability(service: str, stylist: str, date: str) -> str:
    """
    Navigate the booking page and read available time slots for a given date.
    Returns a natural-language string the voice agent can read to the caller.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(MOCK_BOOKING_URL, wait_until="domcontentloaded")

            # Page 1 → click "Book now"
            await page.click("button.btn-outline:has-text('Book now'), button.btn-primary")
            await page.wait_for_selector("#page2.active", timeout=5000)

            # Page 2 → select matching service card
            await _select_service(page, service)

            # Page 2 → click "Choose staff & time"
            await page.click("#btn-choose-time")
            await page.wait_for_selector("#page3.active", timeout=5000)

            # Page 3 → select stylist if specified
            if stylist and stylist.lower() not in ["(anyone)", "anyone", ""]:
                await _select_stylist(page, stylist)

            # Page 3 → click the matching date on the calendar
            clicked = await _click_date(page, date)
            if not clicked:
                await browser.close()
                return f"Sorry, I couldn't find {date} on the calendar. It may be in a different month — would you like to try another date?"

            # Wait for time slots to render (the page fetches from the API)
            await page.wait_for_selector("#availability-results", timeout=7000)
            await page.wait_for_timeout(800)  # let the fetch complete

            # Read available slots
            slots = await page.query_selector_all(".time-slot.available")
            slot_times = []
            for slot in slots:
                text = (await slot.inner_text()).strip()
                if text:
                    slot_times.append(text)

            await browser.close()

            if not slot_times:
                # Check if there's a "fully booked" or "closed" message
                results_text = await page.query_selector("#availability-results")
                if results_text:
                    msg = (await results_text.inner_text()).strip()
                    if "closed" in msg.lower():
                        return "The salon is closed on that day. Would you like to try a weekday instead?"
                    if "fully booked" in msg.lower() or "all slots taken" in msg.lower():
                        return "That day is fully booked. Would you like to try a different date?"
                return "There's no availability on that date. Would you like to try another day?"

            # Offer up to 5 slots in natural language
            display = slot_times[:5]
            if len(slot_times) > 5:
                suffix = f" — and a few more after that"
            else:
                suffix = ""
            return f"We've got availability at {', '.join(display)}{suffix}. Which time works best for you?"

        except Exception as e:
            print(f"[SCRAPER] get_availability error: {e}")
            await browser.close()
            return "Sorry, I had trouble checking availability right now. Let me try that again — what date were you after?"


async def select_slot(service: str, stylist: str, date: str, time: str) -> str:
    """
    Navigate the full booking flow, select the chosen slot, and stop at Page 4
    (the Facebook login / deposit page). Returns the URL of Page 4 to send
    to the customer via SMS so they can complete the booking themselves.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(MOCK_BOOKING_URL, wait_until="domcontentloaded")

            # Page 1 → Book now
            await page.click("button.btn-outline:has-text('Book now'), button.btn-primary")
            await page.wait_for_selector("#page2.active", timeout=5000)

            # Page 2 → select service
            await _select_service(page, service)

            # Page 2 → Choose staff & time
            await page.click("#btn-choose-time")
            await page.wait_for_selector("#page3.active", timeout=5000)

            # Page 3 → select stylist
            if stylist and stylist.lower() not in ["(anyone)", "anyone", ""]:
                await _select_stylist(page, stylist)

            # Page 3 → click date
            clicked = await _click_date(page, date)
            if not clicked:
                await browser.close()
                return ""

            await page.wait_for_selector("#availability-results", timeout=7000)
            await page.wait_for_timeout(800)

            # Page 3 → click matching time slot
            booked = await _click_time_slot(page, time)
            if not booked:
                await browser.close()
                return ""

            # Page 3 → Continue
            await page.click("#btn-continue")
            await page.wait_for_selector("#page4.active", timeout=5000)

            # We are now on Page 4 (Facebook login / sign up to book)
            # Capture the current URL — this is what gets sent to the customer
            booking_url = page.url
            if "#" not in booking_url:
                booking_url = booking_url + "#page4"

            await browser.close()
            return booking_url

        except Exception as e:
            print(f"[SCRAPER] select_slot error: {e}")
            await browser.close()
            return ""


# ─── HELPERS ──────────────────────────────────────────────────────────────────

async def _select_service(page, service: str):
    """Click the service card whose name best matches the requested service."""
    # Try "All" tab first so every service is visible
    try:
        await page.click(".tab:has-text('All')")
        await page.wait_for_timeout(300)
    except Exception:
        pass

    cards = await page.query_selector_all(".service-card")
    best_card = None
    service_lower = service.lower()

    for card in cards:
        name_el = await card.query_selector(".service-name")
        if name_el:
            name_text = (await name_el.inner_text()).lower()
            # Exact keyword match
            if any(word in name_text for word in service_lower.split()):
                best_card = card
                break

    if best_card:
        await best_card.click()
        await page.wait_for_timeout(300)
    else:
        # Fall back: just click the first available service card
        if cards:
            await cards[0].click()
            await page.wait_for_timeout(300)


async def _select_stylist(page, stylist: str):
    """Click the matching staff card on Page 3."""
    try:
        staff_cards = await page.query_selector_all(".staff-card")
        for card in staff_cards:
            name_el = await card.query_selector(".staff-name")
            if name_el:
                name_text = (await name_el.inner_text()).lower()
                if stylist.lower() in name_text:
                    await card.click()
                    await page.wait_for_timeout(200)
                    return
    except Exception as e:
        print(f"[SCRAPER] _select_stylist error: {e}")


async def _click_date(page, date: str) -> bool:
    """
    Click the calendar cell for the given date (YYYY-MM-DD).
    Navigates forward months if needed. Returns True if found and clicked.
    """
    for _ in range(3):  # look across up to 3 months
        # Try to find the cell with a data-date attribute or onclick matching the date
        try:
            # The calendar generates onclick="selectDate(y,m,d)" — look for the date parts
            year, month, day = date.split("-")
            # month in JS is 0-indexed
            js_month = int(month) - 1
            selector = f".cal-day[onclick*='selectDate({year},{js_month},{int(day)})']"
            cell = await page.query_selector(selector)
            if cell:
                cls = await cell.get_attribute("class") or ""
                if "past" in cls or "closed" in cls or "fully-booked" in cls:
                    return False
                await cell.click()
                return True

            # Try next month
            await page.click(".cal-nav:has-text('›')")
            await page.wait_for_timeout(300)
        except Exception as e:
            print(f"[SCRAPER] _click_date error: {e}")
            return False

    return False


async def _click_time_slot(page, time: str) -> bool:
    """
    Click the available time slot matching the requested time.
    Handles both 12hr (2pm, 2:00pm) and 24hr (14:00) formats.
    """
    slots = await page.query_selector_all(".time-slot.available")
    time_clean = time.lower().replace(" ", "").replace(":", "")

    for slot in slots:
        text = (await slot.inner_text()).strip().lower().replace(":", "").replace(" ", "")
        if time_clean in text or text in time_clean:
            await slot.click()
            await page.wait_for_timeout(300)
            return True

    return False
