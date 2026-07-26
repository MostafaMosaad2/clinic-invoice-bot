from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from .config import Settings


@contextmanager
def open_browser(settings: Settings) -> Iterator[tuple[Playwright, Browser, Page]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not settings.headed,
            slow_mo=settings.slow_mo_ms,
        )
        context = browser.new_context(
            locale="ar",
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(30000)
        try:
            yield playwright, browser, page
        finally:
            context.close()
            browser.close()