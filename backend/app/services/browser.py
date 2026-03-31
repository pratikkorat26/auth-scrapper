from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from ..core.config import get_settings
from .detector import AuthComponent
from .fetcher import FetchError, UpstreamTimeoutError

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    PlaywrightTimeoutError = TimeoutError
    async_playwright = None


@dataclass
class BrowserMarkupSnapshot:
    stage: str
    html: str
    interaction_used: bool
    typing_used: bool


@dataclass
class BrowserRenderResult:
    html: str
    interaction_used: bool
    typing_used: bool
    screenshot_base64: Optional[str] = None
    snapshots: list[BrowserMarkupSnapshot] = field(default_factory=list)


AUTH_TRIGGER_PATTERN = re.compile(
    r"(log in|login|sign in|sign-in|join|get started|continue with email|use email|continue as|sign in with|continue with)",
    re.IGNORECASE,
)
ACCOUNT_TRIGGER_PATTERN = re.compile(
    r"(my account|account|profile|avatar|user menu|menu|open account|open profile)",
    re.IGNORECASE,
)
CONTINUE_TRIGGER_PATTERN = re.compile(r"(continue|next|log in|login|sign in|sign-in)", re.IGNORECASE)


async def render_html(url: str) -> BrowserRenderResult:
    if async_playwright is None:
        raise FetchError("Browser fallback is unavailable. Install Playwright and browser binaries to enable it.")

    settings = get_settings()
    timeout_ms = int(settings.browser_timeout_seconds * 1000)
    logger.info("browser render start", extra={"url": url})

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=settings.browser_headless)
            page = await browser.new_page()
            try:
                snapshots: list[BrowserMarkupSnapshot] = []
                interaction_used, typing_used = await _prepare_page(page, url, timeout_ms, snapshots)
                html = await page.content()
                if not snapshots or snapshots[-1].html != html:
                    snapshots.append(
                        BrowserMarkupSnapshot(
                            stage="final",
                            html=html,
                            interaction_used=interaction_used,
                            typing_used=typing_used,
                        )
                    )
                screenshot_base64 = await _capture_screenshot(page) if settings.enable_ai_screenshot_context else None
            finally:
                await page.close()
                await browser.close()
    except PlaywrightTimeoutError as exc:
        logger.error("browser render timeout", extra={"url": url})
        raise UpstreamTimeoutError("Browser fallback timed out.") from exc
    except Exception as exc:
        logger.error("browser render failure", extra={"url": url})
        raise FetchError("Browser fallback failed.") from exc

    logger.info("browser render end", extra={"url": url, "snapshot_count": len(snapshots)})
    return BrowserRenderResult(
        html=html,
        interaction_used=interaction_used,
        typing_used=typing_used,
        screenshot_base64=screenshot_base64,
        snapshots=snapshots,
    )


async def enrich_components_with_browser(url: str, components: list[AuthComponent]) -> list[AuthComponent]:
    if async_playwright is None or not components:
        return components

    settings = get_settings()
    timeout_ms = int(settings.browser_timeout_seconds * 1000)

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=settings.browser_headless)
            page = await browser.new_page()
            try:
                await _prepare_page(page, url, timeout_ms, [])
                enriched = []
                for component in components:
                    snippet = await _extract_component_html(page, component)
                    enriched.append(
                        AuthComponent(
                            type=component.type,
                            surface_type=component.surface_type,
                            confidence=component.confidence,
                            selector_hint=component.selector_hint,
                            signals=component.signals,
                            providers=component.providers,
                            fields=component.fields,
                            snippet=snippet or component.snippet,
                            summary=component.summary,
                        )
                    )
                return enriched
            finally:
                await page.close()
                await browser.close()
    except Exception:
        return components


async def _prepare_page(page, url: str, timeout_ms: int, snapshots: list[BrowserMarkupSnapshot]) -> tuple[bool, bool]:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    await _record_snapshot(page, snapshots, "initial_dom", False, False)
    await _wait_for_auth_markup(page, timeout_ms // 2)
    await _record_snapshot(page, snapshots, "settled_dom", False, False)

    checkpoint = await _page_auth_checkpoint(page)
    if checkpoint:
        logger.info("browser reveal checkpoint", extra={"url": url, "checkpoint": checkpoint, "stage": "settled_dom"})
        return False, False

    interaction_used = False
    typing_used = False
    if get_settings().enable_limited_auth_reveal:
        interaction_used, typing_used = await _attempt_auth_reveal(page, timeout_ms, snapshots)

    if not await _page_auth_checkpoint(page):
        await _wait_for_auth_markup(page, timeout_ms)
        await _record_snapshot(page, snapshots, "final_auth_state", interaction_used, typing_used)
    return interaction_used, typing_used


async def _capture_screenshot(page) -> Optional[str]:
    try:
        image_bytes = await page.screenshot(type="jpeg", quality=60, full_page=False)
        return base64.b64encode(image_bytes).decode("ascii")
    except Exception:
        return None


async def _extract_component_html(page, component: AuthComponent) -> Optional[str]:
    selectors: list[str] = []
    if component.selector_hint:
        selectors.append(component.selector_hint)

    if component.type == "traditional":
        selectors.extend(
            [
                "form:has(input[type='password'])",
                "[role='dialog']:has(input[type='password'])",
                "dialog:has(input[type='password'])",
            ]
        )
    elif component.type == "oauth":
        for provider in component.providers:
            selectors.extend(
                [
                    f"button:has-text('Continue with {provider}')",
                    f"button:has-text('Sign in with {provider}')",
                    f"a:has-text('Continue with {provider}')",
                    f"[data-provider='{provider.lower()}']",
                ]
            )
    elif component.type == "passwordless":
        selectors.extend(
            [
                "button:has-text('Passkey')",
                "button:has-text('Magic link')",
                "input[inputmode='numeric']",
            ]
        )
    elif component.type == "multi_step":
        selectors.extend(
            [
                "form:has(input[type='email'])",
                "[role='dialog']:has(input[type='email'])",
                "dialog:has(input[type='email'])",
                "section:has(input[type='email'])",
            ]
        )

    for selector in selectors:
        html = await _try_selector(page, selector)
        if html:
            return _truncate(html)
    return None


async def _try_selector(page, selector: str) -> Optional[str]:
    try:
        loc = page.locator(selector).first
        await loc.wait_for(state="visible", timeout=2000)
        if await loc.count() == 0:
            return None
        return await loc.evaluate("(el) => el.outerHTML")
    except Exception:
        return None


async def _wait_for_auth_markup(page, timeout_ms: int) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass

    await page.wait_for_function(
        """
        () => {
          const blockedText = /blocked by network security|access denied|captcha|unusual activity|verify you are human|request blocked/i;
          const bodyText = document.body?.innerText || "";
          const authSelectors = [
            "form",
            "input[type='password']",
            "input[type='email']",
            "button",
            "[role='dialog']",
            "dialog"
          ];
          const authText = /log in|login|sign in|signin|continue with email|continue with google|passkey|magic link|verification code/i;
          const authNode = Array.from(document.querySelectorAll("button, a, div, section, dialog, nav, header, input, textarea"))
            .find((node) => authText.test((node.innerText || "") + " " + (node.getAttribute("aria-label") || "") + " " + (node.getAttribute("title") || "")));
          return blockedText.test(bodyText) || authSelectors.some((selector) => document.querySelector(selector)) || Boolean(authNode);
        }
        """,
        timeout=timeout_ms,
    )


async def _page_auth_checkpoint(page) -> Optional[str]:
    return await page.evaluate(
        """
        () => {
          const bodyText = (document.body?.innerText || "");
          if (/blocked by network security|access denied|captcha|unusual activity|verify you are human|request blocked/i.test(bodyText)) {
            return "challenge";
          }
          if (document.querySelector("input[type='password']")) {
            return "password_field";
          }
          if (document.querySelector("[role='dialog'], dialog")) {
            return "dialog";
          }
          const providerButtons = Array.from(document.querySelectorAll("button, a, [role='button']"))
            .filter((node) => /continue with|sign in with|google|apple|facebook|github|linkedin|microsoft/i.test((node.innerText || "") + " " + (node.getAttribute("aria-label") || "")));
          if (providerButtons.length > 0) {
            return "provider_cluster";
          }
          const emailField = document.querySelector("input[type='email'], input[name*='email' i], input[id*='email' i], input[autocomplete='username']");
          const passwordlessButton = Array.from(document.querySelectorAll("button, a, [role='button']"))
            .find((node) => /passkey|magic link|email me a link|use email/i.test((node.innerText || "") + " " + (node.getAttribute("aria-label") || "")));
          const continueButton = Array.from(document.querySelectorAll("button, a, [role='button']"))
            .find((node) => /continue|next|use email|email me a link|verification code/i.test((node.innerText || "") + " " + (node.getAttribute("aria-label") || "")));
          if (passwordlessButton) {
            return "passwordless";
          }
          if (emailField && continueButton) {
            return "email_first";
          }
          return null;
        }
        """
    )


async def _attempt_auth_reveal(page, timeout_ms: int, snapshots: list[BrowserMarkupSnapshot]) -> tuple[bool, bool]:
    interaction_used = False
    typing_used = False

    checkpoint = await _page_auth_checkpoint(page)
    if checkpoint:
        logger.info("browser reveal checkpoint", extra={"stage": "pre_reveal", "checkpoint": checkpoint})
        return interaction_used, typing_used

    stages = [
        ("reveal_auth_trigger", _auth_reveal_locators(page)),
        ("reveal_account_trigger", _account_reveal_locators(page)),
    ]

    for stage_name, locators in stages:
        stage_clicked = await _click_reveal_locators(page, locators, stage_name, timeout_ms, snapshots)
        interaction_used = interaction_used or stage_clicked
        checkpoint = await _page_auth_checkpoint(page)
        if checkpoint:
            logger.info("browser reveal checkpoint", extra={"stage": stage_name, "checkpoint": checkpoint})
            return interaction_used, typing_used

    typed = await _advance_identity_step(page, snapshots)
    typing_used = typing_used or typed
    interaction_used = interaction_used or typed
    checkpoint = await _page_auth_checkpoint(page)
    if checkpoint:
        logger.info("browser reveal checkpoint", extra={"stage": "identity_step", "checkpoint": checkpoint})
        return interaction_used, typing_used

    return interaction_used, typing_used


def _auth_reveal_locators(page) -> list:
    return [
        page.get_by_role("button", name=AUTH_TRIGGER_PATTERN),
        page.get_by_role("link", name=AUTH_TRIGGER_PATTERN),
        page.locator("[aria-label*='login' i], [aria-label*='sign in' i], [title*='login' i], [title*='sign in' i]"),
        page.locator("a[href*='login'], a[href*='signin'], a[href*='sign-in'], button[data-testid*='login'], button[data-testid*='signin']"),
        page.locator("header a, nav a, header button, nav button").filter(has_text=AUTH_TRIGGER_PATTERN),
    ]


def _account_reveal_locators(page) -> list:
    return [
        page.get_by_role("button", name=ACCOUNT_TRIGGER_PATTERN),
        page.get_by_role("link", name=ACCOUNT_TRIGGER_PATTERN),
        page.locator("[aria-label*='account' i], [aria-label*='profile' i], [title*='account' i], [title*='profile' i]"),
        page.locator("[data-testid*='account'], [data-testid*='profile'], [data-testid*='avatar'], button[class*='avatar'], button[class*='profile']"),
    ]


async def _click_reveal_locators(page, locators: list, stage_name: str, timeout_ms: int, snapshots: list[BrowserMarkupSnapshot]) -> bool:
    clicked = False
    for locator in locators:
        try:
            count = await locator.count()
        except Exception:
            continue

        for index in range(min(count, 4)):
            candidate = locator.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                await candidate.click(timeout=3000)
                clicked = True
                logger.info("browser reveal click", extra={"stage": stage_name, "index": index})
                try:
                    await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 4000))
                except PlaywrightTimeoutError:
                    pass
                await _record_snapshot(page, snapshots, f"{stage_name}_snapshot", True, False)
                checkpoint = await _page_auth_checkpoint(page)
                if checkpoint:
                    return clicked
            except Exception:
                continue
    return clicked


async def _advance_identity_step(page, snapshots: list[BrowserMarkupSnapshot]) -> bool:
    if not get_settings().enable_safe_identity_typing:
        return False

    identity_locators = [
        page.locator("input[type='email']"),
        page.locator("input[name*='email' i], input[id*='email' i], input[placeholder*='email' i]"),
        page.locator("input[name*='user' i], input[id*='user' i], input[placeholder*='username' i], input[autocomplete='username']"),
    ]

    typed_any = False
    for locator in identity_locators:
        try:
            count = await locator.count()
        except Exception:
            continue
        for index in range(min(count, 2)):
            field = locator.nth(index)
            try:
                if not await field.is_visible():
                    continue
                if await field.input_value():
                    continue
                await field.fill("test@example.com", timeout=2000)
                typed_any = True
                logger.info("browser reveal typed identity", extra={"field_index": index})
                await _click_continue_after_typing(page)
                await _record_snapshot(page, snapshots, "identity_reveal_snapshot", True, True)
                break
            except Exception:
                continue
        if typed_any:
            break
    return typed_any


async def _click_continue_after_typing(page) -> None:
    continue_candidates = [
        page.get_by_role("button", name=CONTINUE_TRIGGER_PATTERN),
        page.get_by_role("link", name=CONTINUE_TRIGGER_PATTERN),
    ]

    for locator in continue_candidates:
        try:
            count = await locator.count()
        except Exception:
            continue
        for index in range(min(count, 3)):
            candidate = locator.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                await candidate.click(timeout=2000)
                logger.info("browser reveal continue click", extra={"index": index})
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except PlaywrightTimeoutError:
                    pass
                return
            except Exception:
                continue


async def _record_snapshot(
    page,
    snapshots: list[BrowserMarkupSnapshot],
    stage: str,
    interaction_used: bool,
    typing_used: bool,
) -> None:
    try:
        html = await page.content()
    except Exception:
        return
    if snapshots and snapshots[-1].html == html:
        return
    snapshots.append(
        BrowserMarkupSnapshot(
            stage=stage,
            html=html,
            interaction_used=interaction_used,
            typing_used=typing_used,
        )
    )


def _truncate(html: str) -> str:
    max_length = get_settings().max_snippet_length
    return html if len(html) <= max_length else html[:max_length].rstrip() + "..."
