"""URL helpers for building filtered search URLs and de-duplicating item links."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# eBay item links look like /itm/<title-slug>/<12-digit-id>?<tracking params>
_ITEM_ID = re.compile(r"/itm/(?:[^/]+/)?(\d{6,})")


def with_query(url: str, **params: object) -> str:
    """Return ``url`` with ``params`` added or replaced."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update({k: str(v) for k, v in params.items()})
    return urlunsplit(parts._replace(query=urlencode(query)))


def canonical_item_url(href: Optional[str], base_url: str) -> Optional[str]:
    """Strip tracking parameters from an item link so the same listing is never collected twice.

    Returns ``None`` for links that are not item pages (ads, category tiles, the
    "Shop on eBay" placeholder card that carries the fake id 123456).
    """
    if not href:
        return None
    match = _ITEM_ID.search(href)
    if not match or match.group(1) == "123456":
        return None
    return f"{base_url}/itm/{match.group(1)}"
