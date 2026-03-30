from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ..core.config import get_settings
from .fetcher import FetchError, UpstreamTimeoutError

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover - exercised in runtime environments without playwright
    PlaywrightTimeoutError = TimeoutError
    async_playwright = None


@dataclass
class BrowserRenderResult:
    html: str
    interaction_used: bool


AUTH_TRIGGER_PATTERN = re.compile(
    r"(log in|login|sign in|sign-in|my account|account|continue with email|use email)",
    re.IGNORECASE,
)


async def render_html(url: str) -> BrowserRenderResult:
    if async_playwright is None:
        raise FetchError(
            "Browser fallback is unavailable. Install Playwright and browser binaries to enable it."
        )

    settings = get_settings()
    timeout_ms = int(settings.browser_timeout_seconds * 1000)
    logger.info("browser render start", extra={"url": url})

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=settings.browser_headless)
            page = await browser.new_page()
            interaction_used = False
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await _wait_for_auth_markup(page, timeout_ms // 2)
                if settings.enable_limited_auth_reveal and not await _page_has_auth_surface(page):
                    interaction_used = await _attempt_auth_reveal(page, timeout_ms)
                if not await _page_has_auth_surface(page):
                    await _wait_for_auth_markup(page, timeout_ms)
                html = await page.content()
            finally:
                await page.close()
                await browser.close()
    except PlaywrightTimeoutError as exc:
        logger.error("browser render timeout", extra={"url": url})
        raise UpstreamTimeoutError("Browser fallback timed out.") from exc
    except Exception as exc:
        logger.error("browser render failure", extra={"url": url})
        raise FetchError("Browser fallback failed.") from exc

    logger.info("browser render end", extra={"url": url})
    return BrowserRenderResult(html=html, interaction_used=interaction_used)


async def _wait_for_auth_markup(page, timeout_ms: int) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass

    await page.wait_for_function(
        """
        () => {
          const selectors = [
            "form",
            "input[type='password']",
            "input[type='email']",
            "input[type='text']",
            "button",
            "[role='dialog']",
            "dialog"
          ];
          const authText = /log in|login|sign in|signin|continue with email|google|apple|facebook/i;
          const authNode = Array.from(document.querySelectorAll("button, a, div, section, dialog"))
            .find((node) => authText.test((node.innerText || "") + " " + (node.getAttribute("aria-label") || "")));
          return selectors.some((selector) => document.querySelector(selector)) || Boolean(authNode);
        }
        """,
        timeout=timeout_ms,
    )


async def _page_has_auth_surface(page) -> bool:
    return await page.evaluate(
        """
        () => {
          const selectors = [
            "input[type='password']",
            "input[type='email']",
            "form",
            "[role='dialog']",
            "dialog"
          ];
          const authText = /log in|login|sign in|signin|continue with email|google|apple|facebook|github|linkedin|microsoft/i;
          const authElement = Array.from(document.querySelectorAll("button, a, div, section, dialog, [role='button']"))
            .find((node) => authText.test((node.innerText || "") + " " + (node.getAttribute("aria-label") || "")));
          return selectors.some((selector) => document.querySelector(selector)) || Boolean(authElement);
        }
        """
    )


async def _attempt_auth_reveal(page, timeout_ms: int) -> bool:
    candidates = [
        page.get_by_role("button", name=AUTH_TRIGGER_PATTERN),
        page.get_by_role("link", name=AUTH_TRIGGER_PATTERN),
        page.locator("[aria-label*='login' i], [aria-label*='sign in' i], [title*='login' i], [title*='sign in' i]"),
        page.locator("a[href*='login'], a[href*='signin'], a[href*='sign-in'], a[href*='account'], button[data-testid*='login']"),
    ]

    for locator in candidates:
        count = await locator.count()
        for index in range(min(count, 4)):
            candidate = locator.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                await candidate.click(timeout=3000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
                except PlaywrightTimeoutError:
                    pass
                if await _page_has_auth_surface(page):
                    return True
            except Exception:
                continue

    return False
