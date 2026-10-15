"""Offline coverage for the parsing helpers the e2e assertions depend on."""

from __future__ import annotations

import pytest

from src.utils.prices import parse_price
from src.utils.urls import canonical_item_url, with_query

BASE = "https://www.ebay.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "text, expected",
    [
        ("$29.99", 29.99),
        ("ILS 1,234.50", 1234.50),
        ("1.234,50 €", 1234.50),
        ("$20.00 to $35.00", 20.00),  # a range is judged by its lowest price
        ("Free", None),
        (None, None),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "href, expected",
    [
        (f"{BASE}/itm/nike-air/285123456789?hash=abc", f"{BASE}/itm/285123456789"),
        ("/itm/285123456789", f"{BASE}/itm/285123456789"),
        (f"{BASE}/itm/123456", None),  # the "Shop on eBay" placeholder card
        (f"{BASE}/b/Shoes/bn_123", None),
        (None, None),
    ],
)
def test_canonical_item_url(href, expected):
    assert canonical_item_url(href, BASE) == expected


@pytest.mark.unit
def test_with_query_replaces_existing_param():
    assert with_query(f"{BASE}/sch/i.html?_nkw=shoes&_udhi=50", _udhi=220) == (
        f"{BASE}/sch/i.html?_nkw=shoes&_udhi=220"
    )
