"""
Playwright automation for the mock Kitomba booking page.
Used for full end-to-end browser testing. The voice agent's
check_availability_fn and book_appointment_fn in main.py use
direct API logic instead of this scraper — this is kept for
future integration with the real Kitomba site.
"""
from playwright.async_api import async_playwright
import os

MOCK_BOOKING_URL = os.getenv("MOCK_BOOKING_URL", "http://localhost:8080")


async def get_availability(service: str, stylist: str, date: str) -> str:
    """
    Opens mock booking page, navigates to service selection, picks date,
    and reads available time slots. Returns readable string for voice agent.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(MOCK_BOOKING_URL)

        # Click "Book Now" on landing page
        await page.click("button.btn-primary")  # "Book Now" button on page 1
        await page.wait_for_selector("#page2.active", timeout=5000)

        # Click matching service card (partial name match)
        if service:
            cards = await page.query_selector_all(".service-card")
            for card in cards:
                name_el = await card.query_selector(".service-name")
                if name_el:
                    name_text = await name_el.inner_text()
                    if service.lower()[:20] in name_text.lower():
                        await card.click()
                        break

        # Click "Choose staff & time"
        await page.click("#btn-choose-time")
        await page.wait_for_selector("#page3.active", timeout=5000)

        # Select stylist if specified
        if stylist and stylist != '(anyone)':
            staff_cards = await page.query_selector_all(".staff-card")
            for card in staff_cards:
                name_el = await card.query_selector(".staff-name")
                if name_el:
                    name_text = await name_el.inner_text()
                    if stylist.lower() in name_text.lower():
                        await card.click()
                        break

        # Click the matching date on calendar
        if date:
            # date is YYYY-MM-DD, calendar cells have data-date attribute
            cal_cell = await page.query_selector(f".calendar-day[data-date='{date}']")
            if cal_cell:
                await cal_cell.click()
                await page.wait_for_selector("#availability-results", timeout=5000)

        # Read available slot elements
        slots = await page.query_selector_all(".time-slot.available")
        slot_times = []
        for slot in slots:
            text = await slot.inner_text()
            slot_times.append(text.strip())

        await browser.close()

        if slot_times:
            return f"Available times: {', '.join(slot_times)}"
        else:
            return "No availability found for that date. Would you like to try another day?"


async def select_slot(service: str, stylist: str, date: str, time: str) -> str:
    """
    Full booking flow: navigate to service → date → click time slot → confirm.
    Returns booking confirmation URL.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False to watch during testing
        page = await browser.new_page()
        await page.goto(MOCK_BOOKING_URL)

        # Page 1 → 2
        await page.click("button.btn-primary")
        await page.wait_for_selector("#page2.active", timeout=5000)

        # Select service
        if service:
            cards = await page.query_selector_all(".service-card")
            for card in cards:
                name_el = await card.query_selector(".service-name")
                if name_el:
                    name_text = await name_el.inner_text()
                    if service.lower()[:20] in name_text.lower():
                        await card.click()
                        break

        await page.click("#btn-choose-time")
        await page.wait_for_selector("#page3.active", timeout=5000)

        # Select stylist
        if stylist and stylist != '(anyone)':
            staff_cards = await page.query_selector_all(".staff-card")
            for card in staff_cards:
                name_el = await card.query_selector(".staff-name")
                if name_el:
                    name_text = await name_el.inner_text()
                    if stylist.lower() in name_text.lower():
                        await card.click()
                        break

        # Click date on calendar
        if date:
            cal_cell = await page.query_selector(f".calendar-day[data-date='{date}']")
            if cal_cell:
                await cal_cell.click()
                await page.wait_for_selector("#availability-results", timeout=5000)

        # Click matching time slot
        slots = await page.query_selector_all(".time-slot.available")
        for slot in slots:
            text = await slot.inner_text()
            if time.lower().replace(' ', '') in text.lower().replace(' ', ''):
                await slot.click()
                break

        # Click Continue
        await page.click("#btn-continue")
        await page.wait_for_selector("#page4.active", timeout=5000)

        # Complete booking via Facebook login button (triggers completeBooking())
        await page.click(".btn-facebook")
        await page.wait_for_selector("#page5.active", timeout=8000)

        confirmation_url = page.url + "#confirmed"
        await browser.close()
        return confirmation_url
