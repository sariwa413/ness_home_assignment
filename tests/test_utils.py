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
        # --- the plain cases ---
        ("$29.99", 29.99),
        ("29.99", 29.99),
        ("$0.99", 0.99),
        ("ILS 1,234.50", 1234.50),
        ("1.234,50 €", 1234.50),
        ("US $1,499.00", 1499.00),
        ("C $45.00", 45.00),
        ("478.99 ₪", 478.99),
        ("29,99 €", 29.99),
        ("EUR 1.234,50", 1234.50),
        # --- thousands separator with no decimals, both conventions ---
        ("$1,234", 1234.0),
        ("€1.234", 1234.0),
        ("$1,234,567.89", 1234567.89),
        # --- ranges are judged by their lowest price ---
        ("$20.00 to $35.00", 20.00),
        ("ILS 50.00 - ILS 90.00", 50.00),
        # --- the amount must be the one next to the currency ---
        ("Subtotal (6 items) ILS 478.99", 478.99),
        ("Subtotal (1 item)\n$29.99", 29.99),
        ("$29.99 +$5.99 shipping", 29.99),
        ("Was $80.00, now $19.95", 80.00),
        # --- non-breaking spaces, as eBay renders them ---
        ("ILS\u00a01,234.50", 1234.50),
        ("$\u00a029.99", 29.99),
        # --- nothing to read ---
        ("Free", None),
        ("", None),
        (None, None),
        ("Best offer", None),
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
