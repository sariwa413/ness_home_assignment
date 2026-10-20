"""Plumbing shared by every page object: navigation, resilient lookups, evidence.

Locator policy (per the Playwright docs): prefer a stable ``#id``; otherwise fall back
through role, label, placeholder, text and test-id before resorting to CSS/XPath. Where a
preferred locator is used, the previous working selector is kept as a fallback so a layout
change degrades gracefully instead of breaking the run.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from src.config import Config
from src.utils.artifacts import Artifacts


class SiteUnavailableError(RuntimeError):
    """Raised when eBay answers with a bot challenge or a throttling error instead of the page."""


class BasePage:
    MAX_OVERLAY_DISMISSALS = 3
    FIRST_CLICK_TIMEOUT_MS = 5000
    RETRY_BACKOFF_MS = 4000
    # Deadline for reads taken while the page is still settling, where waiting out the
    # default timeout on a node that has just been re-rendered away is never useful.
    QUICK_TIMEOUT_MS = 1500

    def __init__(self, page: Page, config: Config, artifacts: Artifacts) -> None:
        self.page = page
        self.config = config
        self.artifacts = artifacts
        self.log = logging.getLogger(type(self).__name__)

    # --- navigation -------------------------------------------------------

    def goto(self, url: str) -> None:
        """Navigate, retrying eBay's transient throttling and verification responses."""
        referer = self.page.url if self.page.url.startswith("http") else None
        kwargs = {"wait_until": "domcontentloaded", "timeout": self.config.timeout_ms}
        if referer:
            kwargs["referer"] = referer
        self.page.goto(url, **kwargs)
        self.wait_until_available()

    def wait_until_available(self) -> None:
        """Reload until eBay serves the real page instead of its error or challenge page.

        eBay intermittently answers a perfectly valid URL with "Something went wrong on
        our end", and it renders that at the requested URL — so a reload after a short
        pause is what clears it. Every navigation funnels through here, including the
        ones driven by a click: the control that triggered them no longer exists on the
        error page, so repeating the click is not an option.
        """
        for attempt in range(1, self.config.navigation_retries + 1):
            if not self.is_blocked():
                self.dismiss_overlays()
                return

            self.log.warning(
                "eBay refused %s (attempt %s/%s), reloading after backoff",
                self.page.url, attempt, self.config.navigation_retries,
            )
            self.page.wait_for_timeout(self.RETRY_BACKOFF_MS * attempt)
            try:
                self.page.reload(wait_until="domcontentloaded", timeout=self.config.timeout_ms)
            except PlaywrightTimeoutError:
                self.log.warning("Reload of %s timed out, retrying", self.page.url)

        self.raise_if_blocked()

    def is_blocked(self) -> bool:
        banner = self.page.get_by_text(
            re.compile(r"please verify yourself|something went wrong on our end", re.I)
        )
        return banner.first.is_visible()

    def raise_if_blocked(self) -> None:
        """Turn eBay's bot challenge / throttling page into an explicit, actionable failure."""
        if not self.is_blocked():
            return
        self.screenshot("blocked")
        raise SiteUnavailableError(
            f"eBay refused to serve {self.page.url} (bot challenge or throttling). "
            "Re-run with ENV=local (headed), after a pause, or from a different network."
        )

    # --- header cart ------------------------------------------------------

    def cart_count(self) -> int:
        """Number of items the page header reports in the cart (0 when it says nothing).

        Polled while eBay is re-rendering the header after an add-to-cart, so every read
        is given a short deadline: a detached node must report "unknown" straight away
        rather than blocking for the default timeout.
        """
        candidates = (
            self.page.get_by_role("link", name=re.compile("shopping cart", re.I)),
            self.page.locator("#gh-cart-n"),
        )
        for locator in candidates:
            node = locator.first
            try:
                if not node.count():
                    continue
                text = (
                    node.get_attribute("aria-label", timeout=self.QUICK_TIMEOUT_MS)
                    or node.text_content(timeout=self.QUICK_TIMEOUT_MS)
                    or ""
                )
            except PlaywrightTimeoutError:
                continue
            match = re.search(r"\d+", text)
            if match:
                return int(match.group())
        return 0

    # --- overlays ---------------------------------------------------------

    def dismiss_overlays(self) -> None:
        """Close consent banners and modal lightboxes (shipping address, newsletter, ...).

        eBay raises these at unpredictable moments and they swallow pointer events, so
        every page calls this before interacting.
        """
        banners = (
            self.page.locator("#gdpr-banner-accept"),
            self.page.locator("#accept-cookies"),
            self.page.get_by_role("button", name=re.compile("accept all", re.I)),
        )
        try:
            for banner in banners:
                if banner.first.is_visible():
                    banner.first.click(timeout=self.FIRST_CLICK_TIMEOUT_MS)
                    break

            for _ in range(self.MAX_OVERLAY_DISMISSALS):
                # Only visible modals matter; hidden dialogs linger in the DOM.
                modal = self.page.get_by_role("dialog").locator("visible=true").first
                if not modal.count():
                    return
                close = modal.get_by_role("button", name=re.compile("close", re.I)).first
                if close.is_visible():
                    close.click(timeout=self.FIRST_CLICK_TIMEOUT_MS)
                else:
                    self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
        except PlaywrightTimeoutError:
            self.log.debug("An overlay refused to close; continuing anyway")

    # --- resilient interaction -------------------------------------------

    def first_visible(self, *locators: Locator, timeout_ms: int = 3000) -> Optional[Locator]:
        """Return the first of ``locators`` that becomes visible.

        Marketplace layouts are A/B tested, so an element is described by a preferred
        locator plus equivalent fallbacks instead of one brittle selector.
        """
        for locator in locators:
            candidate = locator.first
            try:
                candidate.wait_for(state="visible", timeout=timeout_ms)
                return candidate
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
