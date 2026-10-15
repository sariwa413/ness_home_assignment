"""Plumbing shared by every page object: navigation, resilient lookups, evidence."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from src.config import Config
from src.utils.artifacts import Artifacts

# Consent banners that steal clicks on first visit.
BANNER_SELECTORS = (
    "#gdpr-banner-accept",
    "button#accept-cookies",
    "button:has-text('Accept all')",
)


class SiteUnavailableError(RuntimeError):
    """Raised when eBay answers with a bot challenge or a throttling error instead of the page."""


class BasePage:
    # The header states the cart size either in the link's aria-label or in a badge.
    CART_SUMMARY = "a[aria-label*='shopping cart' i], #gh-cart-n, .gh-cart__count"
    BLOCKED = "text=/please verify yourself|something went wrong on our end/i"
    # Hidden dialogs stay in the DOM, so only visible ones are worth closing.
    MODAL = "[role='dialog'][aria-modal='true']:visible"
    MODAL_CLOSE = "button[aria-label*='Close' i], .lightbox-dialog__close, .dialog__close"
    MAX_OVERLAY_DISMISSALS = 3
    FIRST_CLICK_TIMEOUT_MS = 5000
    RETRY_BACKOFF_MS = 4000

    def __init__(self, page: Page, config: Config, artifacts: Artifacts) -> None:
        self.page = page
        self.config = config
        self.artifacts = artifacts
        self.log = logging.getLogger(type(self).__name__)

    def goto(self, url: str) -> None:
        """Navigate, retrying eBay's transient throttling and verification responses."""
        for attempt in range(1, self.config.navigation_retries + 1):
            self.page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
            if not self.is_blocked():
                self.dismiss_overlays()
                return
            self.log.warning("eBay refused %s (attempt %s), backing off", url, attempt)
            self.page.wait_for_timeout(self.RETRY_BACKOFF_MS * attempt)
        self.raise_if_blocked()

    def is_blocked(self) -> bool:
        return self.page.locator(self.BLOCKED).first.is_visible()

    def raise_if_blocked(self) -> None:
        """Turn eBay's bot challenge / throttling page into an explicit, actionable failure."""
        if not self.is_blocked():
            return
        self.screenshot("blocked")
        raise SiteUnavailableError(
            f"eBay refused to serve {self.page.url} (bot challenge or throttling). "
            "Re-run with ENV=local (headed), after a pause, or from a different network."
        )

    def cart_count(self) -> int:
        """Number of items the page header reports in the cart (0 when it says nothing)."""
        summary = self.page.locator(self.CART_SUMMARY).first
        if not summary.count():
            return 0
        text = summary.get_attribute("aria-label") or summary.text_content(timeout=1000) or ""
        match = re.search(r"\d+", text)
        return int(match.group()) if match else 0

    def dismiss_overlays(self) -> None:
        """Close consent banners and modal lightboxes (shipping address, newsletter, ...).

        eBay raises these at unpredictable moments and they swallow pointer events, so
        every page calls this before interacting.
        """
        try:
            for selector in BANNER_SELECTORS:
                banner = self.page.locator(selector).first
                if banner.is_visible():
                    banner.click(timeout=self.FIRST_CLICK_TIMEOUT_MS)
                    break

            for _ in range(self.MAX_OVERLAY_DISMISSALS):
                modal = self.page.locator(self.MODAL).first
                if not modal.count():
                    return
                close = modal.locator(self.MODAL_CLOSE).first
                if close.is_visible():
                    close.click(timeout=self.FIRST_CLICK_TIMEOUT_MS)
                else:
                    self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
        except PlaywrightTimeoutError:
            self.log.debug("An overlay refused to close; continuing anyway")

    def first_visible(self, *selectors: str, timeout_ms: int = 3000) -> Optional[Locator]:
        """Return the first of ``selectors`` that becomes visible.

        Marketplace layouts are A/B tested, so each element is described by several
        equivalent locators instead of one brittle selector.
        """
        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout_ms)
                return locator
            except PlaywrightTimeoutError:
                continue
        return None

    def click(self, locator: Locator) -> None:
        """Click, working around the two ways eBay makes a control unclickable.

        A modal can appear between page load and the click, and some actions are
        rendered twice — once in the main panel and once in an off-screen sticky bar
        that cannot be scrolled into view. Dispatching the event is the last resort.
        """
        try:
            locator.click(timeout=self.FIRST_CLICK_TIMEOUT_MS)
            return
        except PlaywrightTimeoutError:
            self.dismiss_overlays()

        try:
            locator.click(timeout=self.FIRST_CLICK_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            self.log.debug("Element is unreachable, dispatching the click directly")
            locator.dispatch_event("click")

    def screenshot(self, name: str) -> Path:
        return self.artifacts.screenshot(self.page, name)
