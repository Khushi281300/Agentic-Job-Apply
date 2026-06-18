"""Browser automation service - Playwright wrapper."""

import logging
from pathlib import Path

from playwright.async_api import Browser, Page, async_playwright

from job_agent_contracts.interfaces import BrowserAutomation

logger = logging.getLogger(__name__)


class PlaywrightBrowser(BrowserAutomation):
    """Playwright-based browser automation for form filling."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._page: Page | None = None
        self._browser: Browser | None = None
        self._playwright = None

    async def __aenter__(self) -> "PlaywrightBrowser":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = await context.new_page()

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def navigate(self, url: str) -> None:
        if not self._page:
            await self.start()
        await self._page.goto(url, wait_until="networkidle", timeout=30000)

    async def fill_form(self, field_mapping: dict[str, str]) -> bool:
        if not self._page:
            return False
        filled_count = 0
        for selector, value in field_mapping.items():
            try:
                field = self._page.locator(selector).first
                if await field.is_visible(timeout=2000):
                    await field.fill(value)
                    filled_count += 1
            except Exception as e:
                logger.debug("Could not fill %s: %s", selector, e)
        return filled_count > 0

    async def click(self, selector: str) -> bool:
        if not self._page:
            return False
        try:
            elem = self._page.locator(selector).first
            if await elem.is_visible(timeout=3000):
                await elem.click()
                return True
        except Exception:
            pass
        return False

    async def upload_file(self, selector: str, file_path: str) -> bool:
        if not self._page:
            return False
        try:
            await self._page.locator(selector).first.set_input_files(file_path)
            return True
        except Exception as e:
            logger.warning("File upload failed: %s", e)
            return False

    async def screenshot(self, path: str) -> None:
        if not self._page:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        await self._page.screenshot(path=path, full_page=True)

    async def get_page_content(self) -> str:
        if not self._page:
            return ""
        return await self._page.content()

    async def get_form_html(self) -> str:
        if not self._page:
            return ""
        try:
            if await self._page.locator("form").count() > 0:
                return await self._page.locator("form").first.inner_html()
        except Exception:
            pass
        return await self.get_page_content()

    async def find_and_click(self, text_options: list[str]) -> bool:
        if not self._page:
            return False
        for text in text_options:
            selectors = [
                f'button:has-text("{text}")',
                f'a:has-text("{text}")',
                f'[data-testid*="apply"]',
            ]
            for sel in selectors:
                if await self.click(sel):
                    await self._page.wait_for_load_state("networkidle", timeout=10000)
                    return True
        return False
