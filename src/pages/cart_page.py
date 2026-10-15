"""Shopping cart: reads the subtotal as displayed by the site."""

from __future__ import annotations

from typing import Optional

from src.pages.base_page import BasePage
from src.utils.prices import parse_price


class CartPage(BasePage):
    # The label carries no digits, so the whole row can be handed to the price parser.
    # Matching on text rather than on a currency symbol keeps this locale independent.
    SUBTOTAL = (
        "[data-test-id='SUBTOTAL']",
        "xpath=//*[normalize-space()='Subtotal']/..",
    )
    EMPTY_CART = "text=/your shopping cart is empty/i"
    HEADER_CART_LINK = "a[href*='cart.ebay.com']"

    def open(self) -> "CartPage":
        """Reach the cart through the header link, which keeps the session continuous.

        A direct navigation to the cart host is far more likely to trigger the bot
        challenge, so it is only the fallback.
        """
        header_link = self.first_visible(self.HEADER_CART_LINK, timeout_ms=3000)
        if header_link:
            self.click(header_link)
            self.page.wait_for_load_state("domcontentloaded")
            self.raise_if_blocked()
        else:
            self.goto(self.config.cart_url)
        return self

    def subtotal(self) -> Optional[float]:
        """Return the cart subtotal, or ``None`` when the cart is empty."""
        if self.page.locator(self.EMPTY_CART).first.is_visible():
            return None

        row = self.first_visible(*self.SUBTOTAL, timeout_ms=8000)
        if row is None:
            raise AssertionError(f"Could not read the cart subtotal on {self.page.url}")

        text = row.inner_text().replace("\n", " ").strip()
        self.log.info("Cart subtotal reads '%s'", text)
        return parse_price(text)
