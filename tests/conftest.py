"""Fixtures: configuration, browser lifecycle, tracing and the flow under test."""

from __future__ import annotations

import re

import allure
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


def _launch_browser(playwright, config: Config):
    """Prefer installed Chrome over bundled Chromium — eBay flags the latter more often."""
    browser_type = getattr(playwright, config.browser)
    kwargs = {"headless": config.headless, "slow_mo": config.slow_mo_ms}
    if config.browser == "chromium":
        kwargs["args"] = ["--disable-blink-features=AutomationControlled"]
        kwargs["ignore_default_args"] = ["--enable-automation"]
        try:
            return browser_type.launch(channel="chrome", **kwargs)
        except Exception:
            pass
    return browser_type.launch(**kwargs)


@pytest.fixture(scope="session")
def browser(config: Config):
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, config)
        yield browser
        browser.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach failure evidence while the test — not its teardown — is still the open item.

    Allure files an attachment against whatever is currently running, so doing this from
    a fixture finalizer buries the screenshot under "Tear down". Here the page is still
    alive and the test body is still open, so the evidence lands on the test itself.
    """
    outcome = yield
    report = outcome.get_result()
    # Skips are captured too: the scenario skips when eBay yields no usable listings,
    # and that is precisely the case where the page needs to be seen.
    if report.when == "call" and (report.failed or report.skipped):
        _attach_failure_evidence(item, report)


_BLOCK_TEXT = re.compile(r"please verify yourself|something went wrong on our end", re.I)

_SKIP_HINT = (
    "The scenario stopped early because a precondition was not met. Normally eBay\n"
    "returned no listing it could use. The screenshot shows the page the run was\n"
    "reading, which is the quickest way to tell a genuinely empty result set from\n"
    "eBay having served an error page instead."
)

# Plain-language reading of each error the suite can realistically produce, so the report
# explains the outcome instead of only quoting a traceback. Ordered specific to general:
# the first marker found in the message wins.
_DIAGNOSES = (
    (
        "SiteUnavailableError",
        "eBay answered with its bot challenge or 'Something went wrong on our end' page on\n"
        "every retry. This is the site refusing the session, not a defect in the scenario.\n"
        "Re-run headed ($env:ENV=\"local\"), wait a few minutes, or use a different network.",
    ),
    (
        "Executable doesn't exist",
        "The Playwright browser build is missing. Install it with\n"
        "  .\\.venv\\Scripts\\python.exe -m playwright install chromium",
    ),
    (
        "net::ERR_",
        "The browser could not reach eBay at all, so DNS, a proxy or the connection itself\n"
        "failed. Nothing in the scenario got to run. Check network access to ebay.com.",
    ),
    (
        "strict mode violation",
        "A locator matched more than one element and Playwright refused to guess. eBay\n"
        "often renders a control twice (main panel plus the sticky bar), so the locator\n"
        "needs narrowing or an explicit .first.",
    ),
    (
        "has been closed",
        "The page, context or browser went away mid-test, usually a crash or an outside\n"
        "kill. Re-run, and use ENV=local to watch it happen if it repeats.",
    ),
    (
        "Could not read the cart subtotal",
        "The cart page loaded but the subtotal row was not found, so eBay changed the cart\n"
        "layout or served something else entirely. The screenshot shows what was there.",
    ),
    (
        "Cart is empty",
        "Items were reported as added, yet the cart reads empty. Either the add-to-cart\n"
        "clicks did not stick, or the session cookies were dropped between pages.",
    ),
    (
        "JSONDecodeError",
        "data/scenarios.json is not valid JSON. Remember that JSON has no comments, so a\n"
        "// line is enough to break the file.",
    ),
    (
        "Unknown profile",
        "ENV names a profile that config/config.yaml does not define. Valid ones are the\n"
        "top-level keys in that file: default, local, ci.",
    ),
    (
        "Timeout",
        "An element never became available within the timeout. Either the page did not\n"
        "finish loading, or eBay changed the layout and the locator needs a new fallback.\n"
        "Open the attached trace to see the DOM exactly as it was.",
    ),
    (
        "AssertionError",
        "The scenario ran end to end, but an expectation did not hold. The message above\n"
        "carries the actual and expected values.",
    ),
)


def _crash_message(report) -> str:
    if report.skipped and isinstance(report.longrepr, tuple):
        reason = report.longrepr[2]  # (path, lineno, reason), reason already reads "Skipped: ..."
        return reason if reason.startswith("Skipped") else f"Skipped: {reason}"
    crash = getattr(report.longrepr, "reprcrash", None)
    return crash.message if crash is not None else str(report.longrepr)


def _page_state(page):
    """URL, title, and whether eBay's error page is what is on screen right now."""
    try:
        url, title = page.url, page.title()
    except Exception:  # the page may already be closed or crashed
        return None
    try:
        blocked = bool(_BLOCK_TEXT.search(page.inner_text("body")))
    except Exception:
        blocked = False
    return url, title, blocked


def _diagnose(report, page) -> str:
    """Build the human-readable 'what happened' note attached next to the screenshot."""
    message = _crash_message(report)
    if report.skipped:
        hint = _SKIP_HINT
    else:
        hint = next(
            (text for marker, text in _DIAGNOSES if marker in message),
            "Unexpected error, so the suite has no specific reading of it. The traceback\n"
            "above and the attached trace carry the detail.",
        )
    heading = "WHAT WAS SKIPPED" if report.skipped else "WHAT FAILED"
    shot = "skip-screenshot" if report.skipped else "failure-screenshot"

    state = _page_state(page)
    if state is None:
        location, note = "The page could not be inspected; it was already gone.", ""
    else:
        url, title, blocked = state
        location = f"URL:   {url}\nTitle: {title}"
        # Worth calling out separately: a timeout or a missing element reads very
        # differently once you know eBay was serving its error page at the time.
        note = (
            "\nNOTE\n"
            "eBay's error or bot-challenge page was on screen when this happened, so the\n"
            "site refusing the session is the likely cause rather than the scenario.\n"
            if blocked else ""
        )

    return (
        f"{heading}\n{report.nodeid}\n\n"
        f"ERROR\n{message}\n\n"
        f"WHAT THIS MEANS\n{hint}\n"
        f"{note}\n"
        f"PAGE WHEN THE RUN STOPPED\n{location}\n\n"
        "ATTACHMENTS\n"
        f"{shot}  - the page exactly as it looked when the test stopped\n"
        "playwright-trace.zip - full timeline; open with\n"
        "  .\\.venv\\Scripts\\python.exe -m playwright show-trace <trace.zip>"
    )


def _attach_failure_evidence(item, report) -> None:
    """Attach a screenshot and a diagnosis to the report, but never mask the real failure."""
    page = item.funcargs.get("page")
    artifacts = item.funcargs.get("artifacts")
    if page is None or artifacts is None:  # setup never got that far
        return

    name = "skip-screenshot" if report.skipped else "failure-screenshot"
    try:
        artifacts.screenshot(page, name, full_page=True)
    except Exception as exc:  # a crashed page must not replace the original error
        allure.attach(f"Could not capture a screenshot: {exc}", name=f"{name} (unavailable)")

    try:
        allure.attach(_diagnose(report, page), name="what happened", attachment_type=allure.attachment_type.TEXT)
    except Exception as exc:  # pragma: no cover
        allure.attach(f"Could not build the failure diagnosis: {exc}", name="what happened (unavailable)")


@pytest.fixture
def page(browser, config: Config, artifacts: Artifacts, request):
    """A fresh, isolated context per test, with a Playwright trace saved on teardown."""
    context = browser.new_context(
        locale=config.locale,
        user_agent=config.user_agent,
        viewport={"width": 1440, "height": 900},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    context.set_default_timeout(config.timeout_ms)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    new_page = context.new_page()
    try:
        yield new_page
    finally:
        trace_file = artifacts.trace_path(request.node.name)
        context.tracing.stop(path=str(trace_file))
        context.close()
        if trace_file.exists():
            allure.attach.file(str(trace_file), name="playwright-trace.zip", extension="zip")


@pytest.fixture
def flow(page, config: Config, artifacts: Artifacts) -> ShoppingFlow:
    return ShoppingFlow(page, config, artifacts)
