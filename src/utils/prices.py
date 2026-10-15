"""Parsing of free-text marketplace prices into comparable floats."""

from __future__ import annotations

import re
from typing import Optional

# Matches the first number in a price string: 29, 29.99, 1,234.50, 1.234,50
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def parse_price(text: Optional[str]) -> Optional[float]:
    """Return the lowest price found in ``text``, or ``None`` when there is none.

    Listings expose values such as ``"$29.99"``, ``"ILS 1,234.50"`` or the range
    ``"$20.00 to $35.00"``. For a range the first (lowest) value is returned, which is
    the price the budget filter must be evaluated against.
    """
    if not text:
        return None

    match = _NUMBER.search(text.replace("\u00a0", " "))
    if not match:
        return None

    raw = match.group()
    if "," in raw and "." in raw:
        # The right-most separator is the decimal one.
        raw = raw.replace(",", "") if raw.rindex(".") > raw.rindex(",") else raw.replace(".", "").replace(",", ".")
    elif re.search(r",\d{1,2}$", raw):
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")

    try:
        return float(raw)
    except ValueError:
        return None
