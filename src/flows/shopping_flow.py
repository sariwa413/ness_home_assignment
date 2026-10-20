"""Business-level actions of the exercise, composed from page objects.

Page objects know *how* to talk to a screen; this flow knows *what* the scenario does.
"""

from __future__ import annotations

import logging
import random
from typing import List

import allure
from playwright.sync_api import Page

from src.config import Config
from src.pages.cart_page import CartPage
from src.pages.home_page import HomePage
from src.pages.item_page import ItemPage
from src.pages.login_page import LoginPage
from src.utils.artifacts import Artifacts


class ShoppingFlow:
    def __init__(self, page: Page, config: Config, artifacts: Artifacts) -> None:
        self.config = config
        self.artifacts = artifacts
        self.rng = random.Random(config.random_seed)
        self.log = logging.getLogger(type(self).__name__)

        self.home = HomePage(page, config, artifacts)
        self.login_page = LoginPage(page, config, artifacts)
        self.item = ItemPage(page, config, artifacts)
        self.cart = CartPage(page, config, artifacts)

    def login(self) -> str:
        """Establish the session identity and return the mode that was used.

        ``guest`` is the default because eBay protects the real login with a bot
        challenge; set ``AUTH_MODE=credentials`` plus ``EBAY_USERNAME``/``EBAY_PASSWORD``
        to exercise the real form.
        """
        with allure.step("Establish session"):
            mode = self.config.auth.mode
            if mode == "credentials" and self.config.auth.username:
                self.login_page.open().sign_in(self.config.auth.username, self.config.auth.password)
                self.home.open()
            else:
                mode = "guest"
                self.home.open()

            self.log.info("Session established as %s (signed in: %s)", mode, self.home.is_signed_in())
            self.artifacts.screenshot(self.home.page, f"login-{mode}")
            return mode

    def search_items_by_name_under_price(self, query: str, max_price: float, limit: int = 5) -> List[str]:
        """Return up to ``limit`` item URLs priced at or below ``max_price``.

        Fewer results (including none) is a valid outcome when the catalogue runs out.
        """
        with allure.step(f"Search '{query}' for up to {limit} items at or below {max_price}"):
            results = self.home.open().search(query)
            results.apply_max_price_filter(max_price)
            urls = results.collect_item_urls(max_price, limit)

            self.artifacts.screenshot(results.page, f"search-{query}-under-{max_price}")
            self.log.info("Found %s/%s items for '%s' under %s", len(urls), limit, query, max_price)
            return urls

    def add_items_to_cart(self, urls: List[str]) -> List[str]:
        """Add every URL to the cart, choosing variants at random. Returns the URLs added."""
        added: List[str] = []
        for index, url in enumerate(urls, start=1):
            with allure.step(f"Add item {index}/{len(urls)} to cart"):
                self.item.open(url)
                title = self.item.title()
                self.item.select_random_variants(self.rng)

                if not self.item.add_to_cart():
                    self.log.warning("Skipped (no add-to-cart): %s", title)
                    continue

                added.append(url)
                self.artifacts.screenshot(self.item.page, f"added-{title}")
                self.log.info("Added to cart: %s", title)

        self.log.info("Added %s/%s items to the cart", len(added), len(urls))
        return added

    def assert_cart_total_not_exceeds(self, budget_per_item: float, items_count: int) -> None:
        """Fail the test when the cart subtotal exceeds ``budget_per_item * items_count``."""
        threshold = budget_per_item * items_count
        with allure.step(f"Verify cart subtotal does not exceed {threshold} ({items_count} x {budget_per_item})"):
            self.cart.open()
            total = self.cart.subtotal()
            self.artifacts.screenshot(self.cart.page, "cart-total")

            assert total is not None, "Cart is empty, there is no total to verify"
            self.log.info("Cart subtotal %.2f vs budget %.2f", total, threshold)
            assert total <= threshold, (
                f"Cart subtotal {total:.2f} exceeds the budget {threshold:.2f} "
                f"({items_count} items x {budget_per_item})"
            )
