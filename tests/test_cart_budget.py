"""End-to-end scenario: search under a price cap, fill the cart, verify the total."""

from __future__ import annotations

import pytest

from src.flows.shopping_flow import ShoppingFlow
from src.utils.datasets import load_scenarios


@pytest.mark.e2e
@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s["id"])
def test_cart_total_stays_within_budget(flow: ShoppingFlow, scenario: dict) -> None:
    flow.login()

    urls = flow.search_items_by_name_under_price(
        query=scenario["query"],
        max_price=scenario["max_price"],
        limit=scenario["limit"],
    )
    assert len(urls) <= scenario["limit"], "The search returned more items than requested"
    if not urls:
        pytest.skip(f"No listing under {scenario['max_price']} for '{scenario['query']}'")

    added = flow.add_items_to_cart(urls)
    if not added:
        pytest.skip("None of the matching listings offered an add-to-cart action")

    flow.assert_cart_total_not_exceeds(scenario["max_price"], len(added))
