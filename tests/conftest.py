"""Fixtures: configuration, browser lifecycle, tracing and the flow under test."""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from src.config import Config
from src.flows.shopping_flow import ShoppingFlow
from src.utils.artifacts import Artifacts


@pytest.fixture(scope="session")
def config() -> Config:
    return Config.load()


@pytest.fixture(scope="session")
def artifacts(config: Config) -> Artifacts:
    return Artifacts(config.artifacts_dir)


@pytest.fixture(scope="session")
def browser(config: Config):
    with sync_playwright() as playwright:
        browser = getattr(playwright, config.browser).launch(
            headless=config.headless,
            slow_mo=config.slow_mo_ms,
            # Hides the navigator.webdriver flag eBay's bot challenge looks for.
            args=["--disable-blink-features=AutomationControlled"] if config.browser == "chromium" else [],
        )
        yield browser
        browser.close()


@pytest.fixture
def page(browser, config: Config, artifacts: Artifacts, request):
    """A fresh, isolated context per test, with a Playwright trace saved on teardown."""
    context = browser.new_context(
        locale=config.locale,
        user_agent=config.user_agent,
        viewport={"width": 1440, "height": 900},
    )
    context.set_default_timeout(config.timeout_ms)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    try:
        yield context.new_page()
    finally:
        context.tracing.stop(path=str(artifacts.trace_path(request.node.name)))
        context.close()


@pytest.fixture
def flow(page, config: Config, artifacts: Artifacts) -> ShoppingFlow:
    return ShoppingFlow(page, config, artifacts)
