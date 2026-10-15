"""Search results: price faceting, XPath harvesting of listings, and paging."""

from __future__ import annotations

from typing import List, Set

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pages.base_page import BasePage
from src.utils.prices import parse_price
from src.utils.urls import canonical_item_url, with_query


class SearchResultsPage(BasePage):
    # Result cards are addressed by XPath, as required by the exercise. Both the legacy
    # (`s-item`) and the current (`s-card`) result markup are accepted.
    RESULT_CARDS = "xpath=//li[contains(@class,'s-item') or contains(@class,'s-card')][.//a[contains(@href,'/itm/')]]"
    CARD_LINK = "a[href*='/itm/']"
    CARD_PRICE = ".s-item__price, .s-card__price, [data-testid='x-price-primary']"
    NEXT_PAGE = "xpath=//a[@type='next' or @aria-label='Go to next search page']"

    MAX_PRICE_INPUT = "input[aria-label^='Maximum Value'], input[aria-label^='Maximum value']"
    PRICE_SUBMIT = "button[aria-label='Submit price range'], input[aria-label='Submit price range']"

    READ_CARDS = """(cards, selectors) => cards.map(card => ({
        href: card.querySelector(selectors.link)?.href ?? null,
        price: card.querySelector(selectors.price)?.textContent ?? null,
    }))"""

    def apply_max_price_filter(self, max_price: float) -> bool:
        """Narrow the result set by price. Returns ``True`` when the on-page facet was used.

        When the facet is absent (it is hidden for some categories and viewports) the
        equivalent server-side filter is applied through the ``_udhi`` query parameter.
        """
        max_input = self.first_visible(self.MAX_PRICE_INPUT, timeout_ms=4000)
        if max_input:
            max_input.fill(str(max_price))
            submit = self.first_visible(self.PRICE_SUBMIT, timeout_ms=2000)
            self.click(submit) if submit else max_input.press("Enter")
            self.page.wait_for_load_state("domcontentloaded")
            self.log.info("Applied on-page max price facet: %s", max_price)
            return True

        self.goto(with_query(self.page.url, _udhi=max_price))
        self.log.info("Price facet unavailable, applied _udhi=%s via URL", max_price)
        return False

    def collect_item_urls(self, max_price: float, limit: int) -> List[str]:
        """Walk result pages until ``limit`` listings priced at or below ``max_price`` are found."""
        urls: List[str] = []
        seen: Set[str] = set()

        for page_number in range(1, self.config.max_result_pages + 1):
            urls.extend(self._harvest_page(max_price, limit - len(urls), seen))
            self.log.info("Page %s: %s/%s matching items collected", page_number, len(urls), limit)
            if len(urls) >= limit or not self.go_to_next_page():
                break

        return urls

    def go_to_next_page(self) -> bool:
        next_link = self.first_visible(self.NEXT_PAGE, timeout_ms=2000)
        if not next_link or next_link.get_attribute("aria-disabled") == "true":
            return False
        self.click(next_link)
        self.page.wait_for_load_state("domcontentloaded")
        return True

    def _harvest_page(self, max_price: float, needed: int, seen: Set[str]) -> List[str]:
        cards = self.page.locator(self.RESULT_CARDS)
        try:
            cards.first.wait_for(state="attached", timeout=self.config.timeout_ms)
        except PlaywrightTimeoutError:
            self.log.warning("No result cards rendered on %s", self.page.url)
            return []

        # Read every card in one DOM pass: the result list keeps re-rendering while
        # filters and lazy images settle, so locator-per-card round-trips race with it.
        cards_data = cards.evaluate_all(self.READ_CARDS, {"link": self.CARD_LINK, "price": self.CARD_PRICE})

        found: List[str] = []
        for card in cards_data:
            if len(found) >= needed:
                break

            price = parse_price(card["price"])
            if price is None or price > max_price:
                continue

            url = canonical_item_url(card["href"], self.config.base_url)
            if url is None or url in seen:
                continue

            seen.add(url)
            found.append(url)
            self.log.info("Match: %.2f <= %.2f | %s", price, max_price, url)

        return found
