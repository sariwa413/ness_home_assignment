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
Copy-Item .env.example .env        # optional, see Configuration below
```

On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python` instead.

## Configuration

Settings come from three layers, each overriding the one before it:

1. **`config/config.yaml`** — the profiles (`default`, `local`, `ci`) committed to the repo.
2. **`.env`** — your local overrides, git-ignored. Start from `.env.example`, which
   documents every available variable.
3. **Real environment variables** — win over `.env`, so `$env:ENV="local"` still changes a
   single run without editing a file.

`.env` is where credentials belong (`EBAY_USERNAME` / `EBAY_PASSWORD`), which is precisely
why it is git-ignored and `config.yaml` is not.

## Run

The scenario itself is the `e2e` run:

```powershell
.\.venv\Scripts\python.exe -m pytest -m e2e
```

Variations:

```powershell
$env:ENV="local"; .\.venv\Scripts\python.exe -m pytest -m e2e        # headed, slow motion
```

A live run takes roughly five minutes: eBay is slow, and the suite deliberately backs off
and retries when the site answers with its error page.

Paging only kicks in when one result page cannot satisfy `limit`. To watch it against the
live site, raise `limit` in `data/scenarios.json` above one page of results.

## Report

The suite produces a single **Allure** report. Each new run writes raw results to
`artifacts/allure-results/` (cleared at the start of every run). Render them with the
helper script, which locates Java for the session and opens the report in a browser:

```powershell
.\scripts\allure.cmd            # serve the latest results
.\scripts\allure.cmd generate   # or write a static report to artifacts/allure-report
```

Equivalently, if the `allure` CLI and Java are already on your `PATH`:

```powershell
allure serve artifacts/allure-results
```

### Viewing the committed report (no test run needed)

A snapshot of a **passing** e2e run is in the repo. You do not need to run the suite, install
Java, or start a server.

1. **Open the hosted report** (nothing to install):
   [https://sariwa413.github.io/ness_home_assignment/](https://sariwa413.github.io/ness_home_assignment/)
2. **Or clone and double-click** [`docs/index.html`](https://github.com/sariwa413/ness_home_assignment/blob/main/docs/index.html).
   That file is a self-contained Allure report (screenshots inlined), so it works from disk.

The multi-file copy under `artifacts/allure-report/` is also committed, but that flavour
must be served over `http://` (`.\scripts\allure.cmd` or `python -m http.server`) or it
renders blank. The Playwright trace zip is not committed (it is tens of megabytes).

The report shows one test per scenario, titled with its query and budget, broken into clear
steps — **Establish session → Search → Add item N/M → Verify cart subtotal** — with a
screenshot attached to each step and the full Playwright trace attached to the test. Open an
attached trace in the Playwright viewer with
`.\.venv\Scripts\python.exe -m playwright show-trace <trace.zip>`.

### When a test fails or skips

Two further attachments are added to the test itself (not hidden under "Tear down"):

- **`failure-screenshot`** / **`skip-screenshot`** — a full-page capture of the browser at
  the moment the test stopped, so the state that caused it is visible without re-running
  anything.
- **`what happened`** — a plain-language note giving the error, the URL and page title at
  the time, and what the outcome actually means. The cases the suite knows about are
  distinguished: eBay refusing the session (`SiteUnavailableError`), an element never
  appearing (`TimeoutError`, pointing at the trace), a genuine budget breach
  (`AssertionError`, where the message carries the actual and expected totals), and a skip.

Skips carry the same evidence deliberately. The scenario skips when the search yields no
usable listing, and the screenshot is the fastest way to tell a genuinely empty result set
from eBay having quietly served an error page instead.

Allure separates these by status: a budget breach is **failed**, while an unexpected error
such as eBay blocking the run is **broken** — so a site-side block is never mistaken for the
cart exceeding its budget.

Installing the Allure CLI (one-time): `npm install -g allure-commandline`, `scoop install
allure`, or download it from the
[Allure releases](https://github.com/allure-framework/allure2/releases). The CLI is a Java
program and needs a JDK/JRE 8+; `scripts\allure.cmd` auto-detects a locally installed one.

The helper is a `.cmd` batch file rather than PowerShell on purpose. If your machine's
execution policy is `AllSigned` or `Restricted` (check with `Get-ExecutionPolicy -List`),
PowerShell refuses every unsigned `.ps1` — including the `allure.ps1` shim that npm
installs — which surfaces as `UnauthorizedAccess`. Invoking `allure.cmd` avoids the policy
entirely, so no machine-wide settings need changing.

## Architecture

```
.env.example                 every overridable variable, documented; copy to .env
config/config.yaml           profiles: default | local | ci
data/scenarios.json          the e2e inputs (query, max_price, limit)
src/config.py                typed Config, YAML profile + env overrides
src/utils/                   pure helpers: price parsing, URL canonicalisation, artifacts, datasets
src/pages/                   Page Object Model, one class per screen
src/flows/shopping_flow.py   the four business actions, composed from page objects
tests/                       pytest fixtures + the data-driven e2e scenario
scripts/allure.cmd           renders a fresh Allure report after a local run
docs/index.html              self-contained snapshot — open in a browser, no test run
artifacts/allure-report/     same run as a multi-file report (needs an http server)
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

Utilities (`src/utils`) are pure functions with no browser dependency.

### Data-driven inputs

The scenario lives in `data/scenarios.json` and is injected via `pytest.mark.parametrize`.
Change the query, budget or limit there — no code change required.

Configuration comes from `config/config.yaml`, which defines the `default`, `local` and `ci`
profiles. Pick one with `ENV=<profile>`. Every field can be overridden per-run by an environment
variable: `BASE_URL`, `CART_URL`, `BROWSER`, `HEADLESS`, `LOCALE`, `USER_AGENT`, `TIMEOUT_MS`,
`SLOW_MO_MS`, `RANDOM_SEED`, `ARTIFACTS_DIR`, `AUTH_MODE`, `EBAY_USERNAME`, `EBAY_PASSWORD`.

### Robustness

- **Smart locators.** Elements are described by several equivalent selectors and resolved with
  `first_visible`, so an A/B-tested layout does not break the run. The order follows the
  Playwright guidance: a stable `#id` first, then role, label or placeholder, and only then
  CSS or XPath. Each chain ends with something eBay is unlikely to rename — the `_udhi` form
  field behind the price facet, the `/itm/` href pattern — rather than a styling class.
  Result cards are matched by XPath (as the exercise requires) and accept both eBay's legacy
  `s-item` and current `s-card` markup; eBay has already completed that migration, which is
  why the card's price is read through a priority-ordered list ending in a deliberately loose
  `[class*='price']`.
- **Reads that race the page.** Values polled while eBay re-renders — the header cart badge
  after an add-to-cart, the pager's disabled state — are read with a short deadline and
  treated as unknown on timeout, instead of blocking for the full 30s on a node that has just
  been replaced.
- **Overlays.** Consent banners and modal lightboxes (shipping address, promotions) appear at
  unpredictable moments and swallow pointer events. `BasePage.click` retries after dismissing
  them, and as a last resort dispatches the click directly (eBay renders add-to-cart twice —
  once in an off-screen sticky bar that cannot be scrolled into view).
- **Price parsing.** `parse_price` keys on the number written next to a currency, so a whole
  row can be handed to it: `"Subtotal (6 items) ILS 478.99"` reads as 478.99 and not as 6.
  It covers symbols and ISO codes on either side (`$29.99`, `US $1,499.00`, `478.99 ₪`),
  both thousands conventions (`1,234.50` and `1.234,50`), non-breaking spaces as eBay emits
  them, and ranges like `$20.00 to $35.00` (judged by the lowest value). Text with no
  amount, such as `"Free"`, returns `None` rather than guessing.
- **Price filtering.** The on-page min/max facet is used when present. If it is hidden for the
  category or viewport, cards are still dropped when their listed price is above the budget —
  a second `/sch` navigation just to inject `_udhi` is what trips eBay's bot challenge.
- **Paging.** When a page yields fewer matches than `limit`, the run follows "Next" until the
  limit is filled or eBay has no further page. Returning fewer items — including zero — is a
  valid outcome and skips rather than fails the test.
- **De-duplication.** Item links are canonicalised to `/itm/<id>`, which strips tracking
  parameters so the same listing is never counted twice across pages, and drops ads and eBay's
  "Shop on eBay" placeholder card.
- **Add-to-cart confirmation.** The click is not trusted on its own; the run waits for the cart
  to actually register the item before counting it.

## Assumptions and limitations

- **Guest session.** `login()` runs as a guest by default. eBay guards the real sign-in with a
  bot challenge that cannot be automated reliably, and the scenario does not need an account.
  Set `AUTH_MODE=credentials` with `EBAY_USERNAME`/`EBAY_PASSWORD` to drive the real form.
- **Anti-bot challenge and the "Sorry" page.** eBay occasionally answers with "Please verify
  yourself to continue" or its "Something went wrong on our end" error page, especially from
  headless browsers and after several runs in quick succession. It serves that error *at the
  requested URL*, so `BasePage.wait_until_available` reloads with an increasing backoff
  (`navigation_retries`, default 4) until the real page arrives. Every navigation funnels
  through it — including the click-driven ones (search submit, next page, the cart header
  link), where the triggering control no longer exists on the error page and so the click
  cannot simply be repeated. Only if the block persists across all attempts does the suite
  raise `SiteUnavailableError` with a clear message instead of a confusing missing-locator
  error. Re-run with `ENV=local` (headed), after a pause, or from a different network.
- **Quantity is always 1.** Variants (size, colour) are chosen at random from the available
  options, but quantity is left at 1 — a random quantity would make the
  `budget_per_item * items_count` threshold meaningless.
- **Variant pickers.** Both the legacy `<select>` pickers and eBay's newer button-plus-listbox
  widget are automated, re-reading the available options after each pick (choosing a colour
  re-filters the sizes). A rare custom button grid is added with its default selection.
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
