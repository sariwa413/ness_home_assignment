# eBay E2E Automation — Playwright + Python

End-to-end scenario on eBay: search for products, constrain them by price, add them to the
cart, and verify the cart total stays within budget.

```
searchItemsByNameUnderPrice("shoes", 220, 5)  ->  up to 5 item URLs priced <= 220
addItemsToCart(urls)                          ->  opens each item, picks variants, adds to cart
assertCartTotalNotExceeds(220, len(urls))     ->  cart subtotal <= 220 * number of items
```

## Prerequisites

- Python 3.9+
- Internet access to `ebay.com`

## Install

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python` instead.

## Run

```powershell
.\.venv\Scripts\python.exe -m pytest                 # everything
.\.venv\Scripts\python.exe -m pytest -m unit         # offline tests only, no browser
.\.venv\Scripts\python.exe -m pytest -m e2e          # the browser scenario
$env:ENV="local"; .\.venv\Scripts\python.exe -m pytest -m e2e   # headed, slow motion
$env:DATASET="regression"; .\.venv\Scripts\python.exe -m pytest -m e2e
```

## Reports

Every run writes to `artifacts/`:

| Artifact | Path |
| --- | --- |
| HTML report | `artifacts/report.html` |
| JUnit XML | `artifacts/junit.xml` |
| Allure results | `artifacts/allure-results/` |
| Screenshots | `artifacts/screenshots/` |
| Playwright traces | `artifacts/traces/*.zip` |

Open a trace with `.\.venv\Scripts\python.exe -m playwright show-trace artifacts\traces\<name>.zip`.
Render the Allure results with `allure serve artifacts/allure-results` (requires the Allure CLI).

## Architecture

```
config/config.yaml           profiles: default | local | ci
data/*.json                  external test inputs (scenarios)
src/config.py                typed Config, YAML profile + env overrides
src/utils/                   pure helpers: price parsing, URL canonicalisation, artifacts, datasets
src/pages/                   Page Object Model, one class per screen
src/flows/shopping_flow.py   the four business actions, composed from page objects
tests/                       pytest fixtures + the data-driven scenarios
```

Three layers, each with one responsibility:

- **Page objects** (`src/pages`) know *how* to talk to a screen — locators and interactions,
  nothing else. `BasePage` holds the plumbing they all share: navigation, overlay dismissal,
  the multi-locator `first_visible` fallback, the overlay-aware `click`, and evidence capture.
- **Flow** (`src/flows/shopping_flow.py`) knows *what* the scenario does. It owns the four
  functions the exercise asks for and composes page objects to deliver them. It contains no
  locators.
- **Tests** (`tests/`) know *which* data to run and *what* to assert. They read scenarios from
  JSON and never touch Playwright directly.

Utilities (`src/utils`) are pure functions with no browser dependency, which is why they can be
covered by fast offline tests.

### Data-driven inputs

Scenarios live in `data/smoke.json` and `data/regression.json` and are injected via
`pytest.mark.parametrize`; pick one with `DATASET=<name>`.

Configuration comes from `config/config.yaml`, which defines the `default`, `local` and `ci`
profiles. Pick one with `ENV=<profile>`. Every field can be overridden per-run by an environment
variable: `BASE_URL`, `CART_URL`, `BROWSER`, `HEADLESS`, `LOCALE`, `USER_AGENT`, `TIMEOUT_MS`,
`SLOW_MO_MS`, `MAX_RESULT_PAGES`, `RANDOM_SEED`, `ARTIFACTS_DIR`, `AUTH_MODE`, `EBAY_USERNAME`,
`EBAY_PASSWORD`.

### Robustness

- **Smart locators.** Elements are described by several equivalent selectors and resolved with
  `first_visible`, so an A/B-tested layout does not break the run. Result cards are matched by
  XPath (as the exercise requires) and accept both eBay's legacy `s-item` and current `s-card`
  markup.
- **Overlays.** Consent banners and modal lightboxes (shipping address, promotions) appear at
  unpredictable moments and swallow pointer events. `BasePage.click` retries once after
  dismissing them.
- **Price parsing.** `parse_price` handles currency symbols, thousands separators in both the
  `1,234.50` and `1.234,50` conventions, and ranges like `$20.00 to $35.00` (judged by the
  lowest value).
- **Price filtering.** The on-page min/max facet is used when present; otherwise the equivalent
  `_udhi` query parameter is applied, so filtering works in every category and viewport.
- **Paging.** When a page yields fewer than `limit` matches the run follows "Next" and keeps
  collecting, bounded by `max_result_pages`. Returning fewer items — including zero — is a valid
  outcome and skips rather than fails the test.
- **De-duplication.** Item links are canonicalised to `/itm/<id>`, which strips tracking
  parameters so the same listing is never counted twice across pages, and drops ads and eBay's
  "Shop on eBay" placeholder card.
- **Add-to-cart confirmation.** The click is not trusted on its own; the run waits for the cart
  to actually register the item before counting it.

## Assumptions and limitations

- **Guest session.** `login()` runs as a guest by default. eBay guards the real sign-in with a
  bot challenge that cannot be automated reliably, and the scenario does not need an account.
  Set `AUTH_MODE=credentials` with `EBAY_USERNAME`/`EBAY_PASSWORD` to drive the real form.
- **Anti-bot challenge.** eBay occasionally answers with "Please verify yourself to continue" or
  a generic error page, especially from headless browsers and after several runs in quick
  succession. The suite detects this page and raises `BotChallengeError` with a clear message
  instead of failing on a confusing missing-locator error. Re-run with `ENV=local` (headed) or
  from a different network.
- **Quantity is always 1.** Variants (size, colour) are chosen at random from the available
  options, but quantity is left at 1 — a random quantity would make the
  `budget_per_item * items_count` threshold meaningless.
- **Variant pickers.** Only `<select>`-based variant pickers are automated. A minority of
  listings use custom button grids; those are added with their default selection.
- **Currency.** eBay picks the displayed currency from the session's geography, so a run from
  Israel renders ILS. Prices are therefore compared as plain numbers in whatever currency the
  site shows; no conversion is performed. This is consistent — the listing prices used for
  filtering and the cart subtotal come from the same rendering — but it does mean `max_price`
  is expressed in the site's currency, not necessarily USD.
- **Subtotal includes shipping.** The assertion uses the figure eBay labels "Subtotal" in the
  order summary, which is items plus shipping, exactly as the exercise asks ("the sum as it
  appears on the site").
- **Live site.** The tests run against production eBay, so the catalogue changes between runs.
  Random variant selection is seeded (`random_seed`) to keep a run reproducible, but the
  listings themselves are not.

## AI bug-hunt exercise

Pending: `ReadMeAIBugs.md` will hold the static review of the AI-written test code once that
snippet is available.
