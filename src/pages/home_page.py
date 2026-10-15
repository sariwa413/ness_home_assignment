"""Landing page: entry point for search and sign-in."""

from __future__ import annotations

from src.pages.base_page import BasePage
from src.pages.search_results_page import SearchResultsPage


class HomePage(BasePage):
    SEARCH_INPUT = "input[name='_nkw']"
    SEARCH_BUTTON = "#gh-search-btn, input[type='submit'][value='Search'], button[type='submit']"
    SIGN_IN_LINK = "a[href*='signin.ebay']"

    def open(self) -> "HomePage":
        self.goto(self.config.base_url)
        return self

    def is_signed_in(self) -> bool:
        return self.first_visible(self.SIGN_IN_LINK, timeout_ms=3000) is None

    def search(self, query: str) -> SearchResultsPage:
        self.page.fill(self.SEARCH_INPUT, query)
        button = self.first_visible(self.SEARCH_BUTTON)
        if button:
            self.click(button)
        else:
            self.page.press(self.SEARCH_INPUT, "Enter")
        self.page.wait_for_load_state("domcontentloaded")
        self.log.info("Searched for '%s'", query)
        return SearchResultsPage(self.page, self.config, self.artifacts)
