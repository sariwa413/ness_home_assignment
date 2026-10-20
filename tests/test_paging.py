"""Paging of the search results, driven against stubbed pages.

Proving paging against the live site would mean finding a query whose first page is
short enough to force a second one, and waiting minutes for it. These stubs pin the
behaviour exactly: how many pages are walked, when paging stops, and what comes back.
"""

from __future__ import annotations

from typing import List

import pytest

from src.pages.search_results_page import SearchResultsPage

SEARCH_URL = "https://www.ebay.com/sch/i.html?_nkw=piano"
FIRST_ITEM_ID = 200000001


def _results_page(page_number: int, prices: List[float], has_next: bool, first_id: int) -> str:
    """Render a result page shaped like eBay's: s-item cards plus a 'next page' link."""
    cards = "".join(
        f'<li class="s-item">'
        f'<a href="/itm/{first_id + offset}">Listing {first_id + offset}</a>'
        f'<span class="s-item__price">${price:.2f}</span>'
        f"</li>"
        for offset, price in enumerate(prices)
    )
    nxt = (
        f'<a aria-label="Go to next search page" '
        f'href="/sch/i.html?_nkw=piano&_pgn={page_number + 1}">Next</a>'
        if has_next
        else '<a aria-label="Go to next search page" aria-disabled="true" href="#">Next</a>'
    )
    return f"<html><body><ul>{cards}</ul>{nxt}</body></html>"


def _stub_results(page, pages: List[List[float]], duplicate_ids: bool = False):
    """Serve ``pages`` as consecutive result pages and record which ones were requested."""
    requested: List[int] = []

    def handler(route):
        query = route.request.url.split("_pgn=")
        number = int(query[1].split("&")[0]) if len(query) > 1 else 1
        requested.append(number)
        index = number - 1
        prices = pages[index] if index < len(pages) else []
        first_id = FIRST_ITEM_ID if duplicate_ids else FIRST_ITEM_ID + index * 100
        route.fulfill(
            status=200,
            content_type="text/html",
            body=_results_page(number, prices, has_next=index < len(pages) - 1, first_id=first_id),
        )

    page.route("https://www.ebay.com/sch/**", handler)
    return requested


@pytest.fixture
def results(page, config, artifacts) -> SearchResultsPage:
    return SearchResultsPage(page, config, artifacts)


@pytest.mark.integration
def test_pages_until_the_limit_is_filled(page, results):
    """Three cards per page and a limit of 7 must walk three pages and stop mid-page."""
    requested = _stub_results(page, [[10.0] * 3, [20.0] * 3, [30.0] * 3, [40.0] * 3])
    page.goto(SEARCH_URL)

    urls = results.collect_item_urls(max_price=220, limit=7)

    assert len(urls) == 7, "paging should stop as soon as the limit is reached"
    assert requested == [1, 2, 3], "the fourth page was not needed and must not be fetched"
    assert len(set(urls)) == 7, "collected URLs must be unique"


@pytest.mark.integration
def test_pages_until_the_catalogue_runs_out(page, results):
    """Asking for more than exists returns everything, without looping forever."""
    requested = _stub_results(page, [[10.0] * 3, [20.0] * 2])
    page.goto(SEARCH_URL)

    urls = results.collect_item_urls(max_price=220, limit=40)

    assert len(urls) == 5, "every listing across both pages should be collected"
    assert requested == [1, 2], "paging must stop when the last page offers no next link"


@pytest.mark.integration
def test_skips_listings_over_the_budget_while_paging(page, results):
    """The price filter keeps applying on every page, not just the first."""
    _stub_results(page, [[100.0, 900.0, 150.0], [800.0, 50.0, 700.0]])
    page.goto(SEARCH_URL)

    urls = results.collect_item_urls(max_price=220, limit=10)

    assert len(urls) == 3, "only the three listings at or below 220 qualify"


@pytest.mark.integration
def test_repeated_listings_are_counted_once(page, results):
    """A listing shown on two pages must not fill two slots of the limit."""
    _stub_results(page, [[10.0] * 3, [10.0] * 3], duplicate_ids=True)
    page.goto(SEARCH_URL)

    urls = results.collect_item_urls(max_price=220, limit=10)

    assert len(urls) == 3, "the second page repeats the same ids and adds nothing"
    assert len(set(urls)) == len(urls)


@pytest.mark.integration
def test_a_single_barren_page_does_not_end_paging(page, results):
    """One page of nothing usable is tolerated; the run continues to the next."""
    _stub_results(page, [[10.0] * 2, [900.0] * 3, [20.0] * 2])
    page.goto(SEARCH_URL)

    urls = results.collect_item_urls(max_price=220, limit=10)

    assert len(urls) == 4, "the barren middle page must not stop the walk"
