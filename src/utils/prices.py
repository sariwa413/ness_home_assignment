"""Parsing of free-text marketplace prices into comparable floats."""

from __future__ import annotations

import re
from typing import Optional

# A bare number: 29, 29.99, 1,234.50, 1.234,50
_NUMBER = r"\d[\d.,]*\d|\d"

# Currency as eBay writes it, either as a symbol or an ISO-ish code, and on either side
# of the amount: "$29.99", "US $29.99", "ILS 1,234.50", "29,99 €", "478.99 ₪".
_CURRENCY = r"(?:[$€£¥₪]|(?:US|C|AU|NZ|CA)\s*\$|\b(?:ILS|NIS|USD|EUR|GBP|AUD|CAD|JPY|CHF|SEK|PLN)\b)"

# The amount that actually belongs to a currency, preferred over any other number in the
# string. This is what keeps "Subtotal (6 items) ILS 478.99" from being read as 6.
_CURRENCY_AMOUNT = re.compile(
    rf"{_CURRENCY}\s*({_NUMBER})|({_NUMBER})\s*{_CURRENCY}",
    re.IGNORECASE,
)

_FIRST_NUMBER = re.compile(_NUMBER)


def _to_float(raw: str) -> Optional[float]:
    """Normalise both thousands conventions, then convert.

    ``1,234.50`` and ``1.234,50`` are the same amount written for different locales, so
    the separator that appears last is the decimal one. A lone group of exactly three
    digits is a thousands separator in either convention: ``1,234`` and ``1.234`` are
    both 1234.
    """
    if "," in raw and "." in raw:
        decimal_is_dot = raw.rindex(".") > raw.rindex(",")
        raw = raw.replace(",", "") if decimal_is_dot else raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        raw = raw.replace(",", "").replace(".", "")
    elif re.search(r",\d{1,2}$", raw):
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")

    try:
        return float(raw)
    except ValueError:
        return None


def parse_price(text: Optional[str]) -> Optional[float]:
    """Return the price found in ``text``, or ``None`` when there is none.

    Listings expose values such as ``"$29.99"``, ``"ILS 1,234.50"`` or the range
    ``"$20.00 to $35.00"``. For a range the first (lowest) value is returned, which is
    the price the budget filter must be evaluated against.

    An amount written next to a currency wins over any other number in the string,
    because the text handed in is often a whole row rather than a bare figure — the
    cart's ``"Subtotal (6 items) ILS 478.99"`` must read as 478.99, not as 6.
    """
    if not text:
        return None

    cleaned = text.replace("\u00a0", " ")

    match = _CURRENCY_AMOUNT.search(cleaned)
    if match:
        return _to_float(match.group(1) or match.group(2))

    match = _FIRST_NUMBER.search(cleaned)
    return _to_float(match.group()) if match else None
