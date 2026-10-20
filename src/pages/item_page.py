"""Item page: variant selection and add-to-cart."""

from __future__ import annotations

import random
import re
import time
from typing import Dict, List, Optional

from playwright.sync_api import Locator

from src.pages.base_page import BasePage


class ItemPage(BasePage):
    # Variant pickers come in two flavours. The legacy one is a native <select>; the
    # newer "msku-evo" layout is a button-plus-listbox. Both are scoped by CSS so they
    # never match eBay's unrelated header category dropdown, which is a functional need
    # rather than a styling choice.
    VARIANT_SELECTS = "select.x-msku__select-box, select[name^='msku']"
    VARIANT_CONTROLS = ".x-msku-evo .listbox-button__control, .x-msku .listbox-button__control"
    VARIANT_OPTION_VALUE = ".listbox__value"
    PLACEHOLDER_OPTION_LABEL = "select"
    PLACEHOLDER_OPTION_VALUES = {"", "-1", "0"}  # "Select size", "- Select -", ...
    ADD_TO_CART_TIMEOUT_S = 15

    def open(self, url: str) -> "ItemPage":
        self.goto(url)
        return self

    def title(self) -> str:
        heading = self.first_visible(
            self.page.get_by_role("heading", level=1),
            self.page.locator(".x-item-title__mainTitle"),
            self.page.locator("#itemTitle"),  # pre-redesign listings
            timeout_ms=5000,
        )
        return (heading.inner_text() if heading else "unknown item").strip()

    # --- variants ---------------------------------------------------------

    def select_random_variants(self, rng: random.Random) -> Dict[str, str]:
        """Pick a random available value for every variant picker (size, colour, ...)."""
        chosen: Dict[str, str] = {}
        chosen.update(self._pick_from_selects(rng))
        chosen.update(self._pick_from_listboxes(rng))
        if chosen:
            self.log.info("Selected variants: %s", chosen)
        return chosen

    def _pick_from_listboxes(self, rng: random.Random) -> Dict[str, str]:
        """Drive the button-plus-listbox pickers, re-reading options after every choice.

        Choosing a colour re-filters the available sizes, so the option list must be
        queried again for each picker rather than collected up front.
        """
        chosen: Dict[str, str] = {}
        controls = self.page.locator(self.VARIANT_CONTROLS)

        for index in range(controls.count()):
            control = controls.nth(index)
            if not control.is_visible():
                continue

            label = control.inner_text().split(":")[0].strip()
            self.click(control)

            options = self.page.get_by_role("option").locator("visible=true")
            selectable = [
                i
                for i in range(options.count())
                if options.nth(i).get_attribute("aria-disabled") != "true"
                and self._option_label(options.nth(i))
            ]
            if not selectable:
                self.page.keyboard.press("Escape")
                continue

            option = options.nth(rng.choice(selectable))
            chosen[label] = self._option_label(option)
            self.click(option)

        return chosen

    def _option_label(self, option: Locator) -> str:
        """Visible text of a listbox option, or an empty string for the placeholder."""
        value = option.locator(self.VARIANT_OPTION_VALUE).first
        text = (value.inner_text() if value.count() else option.inner_text()).strip()
        return "" if text.lower().startswith(self.PLACEHOLDER_OPTION_LABEL) else text

    def _pick_from_selects(self, rng: random.Random) -> Dict[str, str]:
        selects = self.page.locator(self.VARIANT_SELECTS)
        chosen: Dict[str, str] = {}

        for index in range(selects.count()):
            dropdown = selects.nth(index)
            if not dropdown.is_visible() or dropdown.is_disabled():
                continue

            options = dropdown.locator("option")
            values: List[str] = []
            for i in range(options.count()):
                option = options.nth(i)
                value = option.get_attribute("value") or ""
                if value in self.PLACEHOLDER_OPTION_VALUES or option.get_attribute("disabled") is not None:
                    continue
                values.append(value)

            if not values:
                continue

            value = rng.choice(values)
            dropdown.select_option(value)
            chosen[dropdown.get_attribute("name") or f"variant-{index}"] = value

        return chosen

    # --- add to cart ------------------------------------------------------

    def _add_to_cart_button(self) -> Optional[Locator]:
        # Prefer the stable ids, then the accessible role/name, then the id prefix eBay
        # uses for the sticky-bar variant.
        return self.first_visible(
            self.page.locator("#atcRedesignId"),
            self.page.locator("#isCartBtn_btn"),
            self.page.get_by_role("button", name=re.compile("add to cart", re.I)),
            self.page.locator("a[id^='atcBtn']"),
            timeout_ms=5000,
        )

    def add_to_cart(self) -> bool:
        """Click add-to-cart and wait for the cart to register the item.

        Returns ``False`` for listings that do not offer the action (auction-only
        listings) or whose add-to-cart request did not go through.
        """
        button = self._add_to_cart_button()
        if not button:
            self.log.warning("No add-to-cart control on %s", self.page.url)
            return False

        before = self.cart_count()
        self.click(button)
        self.page.wait_for_load_state("domcontentloaded")

        if self._wait_until_in_cart(before):
            return True
        self.log.warning("Add-to-cart was not confirmed for %s", self.page.url)
        return False

    def _wait_until_in_cart(self, previous_count: int) -> bool:
        """Poll for any of the signals eBay gives once the item is really in the cart.

        The click only opens an "Adding to your cart" spinner; depending on the listing
        the site then redirects to the cart, shows a confirmation, or just bumps the
        header badge.
        """
        confirmation = self.page.get_by_text(re.compile(r"added to (your )?cart|go to cart", re.I))
        deadline = time.monotonic() + self.ADD_TO_CART_TIMEOUT_S
        while time.monotonic() < deadline:
            if "cart.ebay.com" in self.page.url:
                return True
            if self.cart_count() > previous_count:
                return True
            if confirmation.first.is_visible():
                return True
            self.page.wait_for_timeout(500)
        return False
