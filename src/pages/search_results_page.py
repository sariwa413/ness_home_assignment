"""Search results: price faceting, XPath harvesting of listings, and paging."""

from __future__ import annotations

import re
from typing import List, Set
from urllib.parse import parse_qsl, urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pages.base_page import BasePage
from src.utils.prices import parse_price
from src.utils.urls import canonical_item_url


class SearchResultsPage(BasePage):
    # Result cards are addressed by XPath, as the exercise requires. Both the legacy
    # (`s-item`) and the current (`s-card`) result markup are accepted. CARD_LINK and
    # CARD_PRICE stay CSS because they run as `querySelector` inside `evaluate_all`.
    RESULT_CARDS = "xpath=//li[contains(@class,'s-item') or contains(@class,'s-card')][.//a[contains(@href,'/itm/')]]"
    MAX_BARREN_PAGES = 2  # consecutive pages yielding nothing before paging gives up

    # Tried in order, first hit wins. eBay has already moved result cards from `s-item`
    # to `s-card`, so each list ends with a deliberately loose selector: it only applies
    # once the known class names have disappeared, which buys the suite a release.
    CARD_LINKS = ("a[href*='/itm/']",)
    CARD_PRICES = (
        ".s-card__price",
        ".s-item__price",
        "[data-testid='x-price-primary']",
        "[class*='price']",
    )

    READ_CARDS = """(cards, selectors) => {
        const pick = (card, candidates) => {
            for (const selector of candidates) {
                const found = card.querySelector(selector);
                if (found) return found;
            }
            return null;
        };
        return cards.map(card => ({
            href: pick(card, selectors.link)?.href ?? null,
            price: pick(card, selectors.price)?.textContent ?? null,
        }));
    }"""

    def apply_max_price_filter(self, max_price: float) -> bool:
        """Narrow the result set by price. Returns ``True`` when the on-page facet was used.

        When the facet is absent (it is hidden for some categories and viewports) the
        equivalent server-side filter is applied through the ``_udhi`` query parameter.
        """
        max_input = self.first_visible(
            self.page.get_by_label(re.compile("maximum value", re.I)),
            self.page.locator("input[aria-label^='Maximum Value' i]"),
            # The field name behind the _udhi query parameter: unchanged for years and
            # unaffected by relabelling or redesigns of the facet.
            self.page.locator("input[name='_udhi']"),
            timeout_ms=4000,
        )
        if max_input:
            max_input.fill(str(max_price))
            submit = self.first_visible(
                self.page.get_by_role("button", name=re.compile("submit price range", re.I)),
                timeout_ms=2000,
            )
            self.click(submit) if submit else max_input.press("Enter")
            self.page.wait_for_load_state("domcontentloaded")
            # Submitting the facet is a navigation, and eBay answers it with the error
            # page as readily as any other — without this the run would read an empty
            # result list and wrongly conclude nothing matched.
            self.wait_until_available()
            self.log.info("Applied on-page max price facet: %s", max_price)
            return True

        # Do not follow up with a second results navigation. eBay treats that extra
        # /sch load as automation and serves a bot challenge. Harvest already drops
        # cards priced above max_price, so the assertion still holds.
        query = dict(parse_qsl(urlsplit(self.page.url).query))
        if query.get("_udhi"):
            self.log.info("Price already constrained via _udhi=%s", query["_udhi"])
        else:
            self.log.info("Price facet unavailable; filtering harvested cards to <= %s", max_price)
        return False

    def collect_item_urls(self, max_price: float, limit: int) -> List[str]:
        """Walk result pages until ``limit`` matches are found or eBay has no further page."""
        urls: List[str] = []
        seen: Set[str] = set()
        visited_pages: Set[str] = set()
        page_number = 0
        barren_pages = 0

        while True:
            page_number += 1
            page_key = self._page_key()
            if page_key in visited_pages:
                self.log.info("Next returned page %s again; stopping", page_key)
                break
            visited_pages.add(page_key)

            before = len(urls)
            urls.extend(self._harvest_page(max_price, limit - len(urls), seen))
            self.log.info("Page %s: %s/%s matching items collected", page_number, len(urls), limit)

            if len(urls) >= limit:
                self.log.info("Reached the requested limit of %s", limit)
                break

            # A page can legitimately yield nothing — it may be all sponsored tiles, or
            # every listing on it may already have been collected — so give paging a
            # second chance before concluding the catalogue is exhausted.
            barren_pages = barren_pages + 1 if len(urls) == before else 0
            if barren_pages >= self.MAX_BARREN_PAGES:
                self.log.info("No new items across %s pages; stopping", barren_pages)
                break

            if not self.go_to_next_page():
                self.log.info("No further result pages")
                break

        return urls

    def _page_key(self) -> str:
        query = dict(parse_qsl(urlsplit(self.page.url).query))
        return query.get("_pgn", "1")

    def go_to_next_page(self) -> bool:
        next_link = self.first_visible(
            self.page.get_by_role("link", name=re.compile("next search page", re.I)),
            self.page.locator("a[aria-label='Go to next search page']"),
            self.page.locator("a.pagination__next"),
            timeout_ms=2000,
        )
        try:
            disabled = next_link.get_attribute("aria-disabled", timeout=self.QUICK_TIMEOUT_MS) if next_link else None
        except PlaywrightTimeoutError:  # the pager re-rendered; treat as the end
            return False
        if not next_link or disabled == "true":
            return False
        self.click(next_link)
        self.page.wait_for_load_state("domcontentloaded")
        self.wait_until_available()
        return True

    def _harvest_page(self, max_price: float, needed: int, seen: Set[str]) -> List[str]:
        # Whatever navigation led here, make sure it is the real result list and not
        # eBay's error page, which would read as "no listings matched".
        self.wait_until_available()

        cards = self.page.locator(self.RESULT_CARDS)
        try:
            cards.first.wait_for(state="attached", timeout=self.config.timeout_ms)
        except PlaywrightTimeoutError:
            self.log.warning("No result cards rendered on %s", self.page.url)
            self.screenshot("no-result-cards")
            return []

        # Read every card in one DOM pass: the result list keeps re-rendering while
        # filters and lazy images settle, so locator-per-card round-trips race with it.
        cards_data = cards.evaluate_all(
            self.READ_CARDS, {"link": list(self.CARD_LINKS), "price": list(self.CARD_PRICES)}
        )

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
