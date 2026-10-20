"""Shopping cart: reads the subtotal as displayed by the site."""

from __future__ import annotations

import re
from typing import Optional

from playwright.sync_api import Locator

from src.pages.base_page import BasePage
from src.utils.prices import parse_price


class CartPage(BasePage):
    def open(self) -> "CartPage":
        """Reach the cart through the header link, which keeps the session continuous.

        A direct navigation to the cart host is far more likely to trigger the bot
        challenge, so it is only the fallback.
        """
        header_link = self.first_visible(
            self.page.get_by_role("link", name=re.compile("shopping cart", re.I)),
            self.page.locator("a[href*='cart.ebay.com']"),
            timeout_ms=3000,
        )
        if header_link:
            self.click(header_link)
            self.page.wait_for_load_state("domcontentloaded")
            self.wait_until_available()
        else:
            self.goto(self.config.cart_url)
        return self

    def _subtotal_row(self) -> Optional[Locator]:
        # eBay tags the figure with a test id; the text-anchored row is the fallback.
        # The whole row can be handed to the parser either way: it keys on the amount
        # next to the currency, so an item count in the label cannot be mistaken for
        # the total, and the currency itself does not need to be known in advance.
        return self.first_visible(
            self.page.locator("[data-test-id='SUBTOTAL']"),
            self.page.locator("[data-testid='SUBTOTAL']"),  # the newer spelling
            self.page.get_by_text("Subtotal", exact=True).locator("xpath=.."),
            timeout_ms=8000,
        )

    def subtotal(self) -> Optional[float]:
        """Return the cart subtotal, or ``None`` when the cart is empty."""
        empty = self.page.get_by_text(re.compile(r"your shopping cart is empty", re.I))
        if empty.first.is_visible():
            return None

        row = self._subtotal_row()
        if row is None:
            raise AssertionError(f"Could not read the cart subtotal on {self.page.url}")

        text = row.inner_text().replace("\n", " ").strip()
        self.log.info("Cart subtotal reads '%s'", text)
        return parse_price(text)
