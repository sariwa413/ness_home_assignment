"""Landing page: entry point for search and sign-in."""

from __future__ import annotations

import re

from playwright.sync_api import Locator

from src.pages.base_page import BasePage
from src.pages.search_results_page import SearchResultsPage


class HomePage(BasePage):
    def open(self) -> "HomePage":
        self.goto(self.config.base_url)
        return self

    def _search_box(self) -> Locator:
        # #gh-ac is eBay's long-standing id for the search field; the placeholder and the
        # form field name that drives the ``_nkw`` query parameter back it up.
        box = self.first_visible(
            self.page.locator("#gh-ac"),
            self.page.get_by_placeholder(re.compile("search", re.I)),
            self.page.locator("input[name='_nkw']"),
        )
        return box or self.page.locator("input[name='_nkw']").first

    def _sign_in_link(self) -> "Locator | None":
        return self.first_visible(
            self.page.get_by_role("link", name=re.compile(r"^\s*sign in", re.I)),
            self.page.locator("a[href*='signin.ebay']"),
        )

    def is_signed_in(self) -> bool:
        return self._sign_in_link() is None

    def search(self, query: str) -> SearchResultsPage:
        box = self._search_box()
        box.fill(query)

        button = self.first_visible(
            self.page.locator("#gh-search-btn"),
            self.page.locator("#gh-btn"),  # the id eBay used before the header redesign
            self.page.get_by_role("button", name=re.compile(r"^search$", re.I)),
        )
        if button:
            self.click(button)
        else:
            box.press("Enter")

        self.page.wait_for_load_state("domcontentloaded")
        self.wait_until_available()
        self.log.info("Searched for '%s'", query)
        return SearchResultsPage(self.page, self.config, self.artifacts)
