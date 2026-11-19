# MEMORY.md — Project Plan & Progress

Living tracker for the Shopping Research Assistant. Update after each step or decision.

_Last updated: 2026-11-16_

## Build progress
- [x] **Step 1 — Project setup & data layer:** `pyproject.toml`, `.env.example`, `README.md`, `config.py`, `models.py`, `database.py`, DB tests (8 passing; installs fine on Python 3.14). `database.record_price_check` returns the previous lowest price (spec fix #1).
- [x] **Step 2 — Tools layer:** `tools/search.py` (Tavily), `tools/scraper.py` (Crawl4AI + JSON-LD), `tools/notifier.py`. 63 tests passing, all offline.
- [ ] **Step 3 — Research graph:** `graphs/research_graph.py` (multi-turn loop, intent routing, `interrupt()` confirmation, SqliteSaver)
- [ ] **Step 4 — Monitor graph:** `graphs/monitor_graph.py` (async scrape, drop evaluation, LLM alert)
- [ ] **Step 5 — CLI & tests:** `main.py` menu, APScheduler wiring, `tests/test_price_logic.py`

## Repo foundation (done 2026-11-15)
- [x] Renamed `. claudeignore` → `.claudeignore`; added `*.db`, `*.sqlite*`, `source/data/` to `.gitignore`
- [x] `CLAUDE.md`, `MEMORY.md`
- [x] `docs/BRD.md`, `docs/FRD.md`
- [x] `docs/user-stories.md` (23 stories, 84 points), `docs/sprint-plan.md` (1-week sprints; v1 target 2026-12-20)

## Current sprint
**Sprint 1 (2026-11-16 → 11-22): Tools layer.** Stories US-11, US-12, US-16, US-22 (18 points). See [docs/sprint-plan.md](docs/sprint-plan.md).
- [x] US-11 Reliable price extraction: `scraper.py` reads JSON-LD (Product/Offer/AggregateOffer/@graph/priceSpecification, repairs trailing commas), then falls back to meta tags / itemprop / retailer CSS (Amazon, Best Buy) / generic. Parses EN and FR-CA price formats.
- [x] US-12 Failed checks isolated: crawl errors, HTTP ≥400 and empty pages return `failed` without stopping other URLs.
- [x] US-16 Notifiers: Console, Webhook (Discord/Slack/Telegram `?chat_id=`/generic), Resend, SMTP (STARTTLS, or SSL on 465). Failures raise `NotificationError`.
- [x] US-22 `ConfigError` names missing keys (Tavily, webhook, email settings).
- [x] `crawl4ai-setup` done (Chromium installed, works on Python 3.14).
- [x] Live spike, 2026-11-15 (Sony WH-1000XM5):
  - **Amazon.ca** `/dp/B09XS7JWHH`: ✅ `css-fallback` returned CA$498.00, in stock. No Product JSON-LD on the page.
  - **Best Buy Canada**: ❌ HTTP 403, "Akamai block".
- [x] Best Buy dropped from v1 (user decision, 2026-11-16): `search.EXCLUDED_RETAILERS` filters it from results and Tavily `exclude_domains`; Best Buy CSS selectors removed; docs updated.
- [x] Live Tavily check, 2026-11-16 (Sony WH-1000XM5):
  - Review research now returns TechRadar, PCMag, CNET, Reddit and RTINGS.
  - Listings: 3 Amazon.ca ASINs and 2 sony.ca colour variants.
  - Scraper verified Amazon.ca at CA$498 (`css-fallback`) and sony.ca at CA$499.99 (`json-ld`).
  - Fixes from the first live run:
    - Review search restricted to trusted sites, topped up with open search only if fewer than 4 results.
    - Brand-store category, support and spec pages blocked.
    - `matches_model` rejects sibling models (WF- vs WH-1000XM5).
  - Tavily snippet price hints are unreliable (e.g. 45.0), which confirms verification is needed (FR-3.3).
- [x] **More retailers (user request, 2026-11-16).** `search.RETAILERS` is now one table of domain, display name, product-URL regex and aliases. Live scrape results, one product page each:

  | Retailer | Result | Method | Notes |
  |---|---|---|---|
  | Walmart.ca | ✅ / ⚠️ | json-ld | Worked twice, then **PerimeterX block (307)** on a third run. Intermittent. |
  | Staples.ca | ✅ | json-ld | |
  | Costco.ca | ✅ | json-ld | Stock flag comes from Costco's own JSON-LD |
  | Dell Canada | ✅ | json-ld | Store is `dell.com/en-ca/shop/.../apd|spd/`; `dell.ca` is an alias (support/community pages only) |
  | Newegg.ca | ✅ | css-fallback | No Product JSON-LD. Added a buy-box selector to avoid marketplace seller rows. Out-of-stock marketplace pages show no price, reported as "out of stock (no price shown)". |
  | Canada Computers | ✅ | json-ld | |
  | Canadian Tire | ✅ | json-ld | |
  | RONA | ❌ | n/a | **DataDome captcha 403**, same as Best Buy. **Dropped from v1** (user decision, 2026-11-16); in `EXCLUDED_RETAILERS`. |

  - `find_retail_listings`: the combined search (20 results) crowded out some retailers, so retailers with no hits now get a targeted "basic" search (1 Tavily credit each, once per finalization). Live run: 9 listings from 6 retailers for the Sony WH-1000XM5.
- [ ] Sprint 1 demo with a real webhook: optional, needs `WEBHOOK_URL` in `.env`. Console alerts are covered by tests.

## Decisions log
| Date | Decision |
|---|---|
| 2026-11-15 | Build in this repo; ignore the proposal's `shopping-agent/` folder name. |
| 2026-11-15 | Entire Python project lives in `source/` (pyproject, .env.example, README, package, tests). Package name `shopping_assistant`, so proposal paths like `src/config.py` map to `source/shopping_assistant/config.py`. |
| 2026-11-15 | LLM provider: Anthropic via `langchain-anthropic`; model configurable with `LLM_MODEL`. |
| 2026-11-15 | Stdlib `sqlite3` (no SQLAlchemy). Separate DB files: `checkpoints.db` (LangGraph) and `watchlist.db` (tracked items + history), both in `source/data/`. |
| 2026-11-15 | Plan/progress tracked in this repo file instead of the user-profile folder. |
| 2026-11-15 | Fallback extraction uses BeautifulSoup on the HTML returned by Crawl4AI (not `JsonCssExtractionStrategy`). It's deterministic, testable with fixtures, and retailer selectors live in one dict (`_RETAILER_CSS`). |
| 2026-11-15 | `search.looks_like_product_url` / `is_blocked_url` reject cart, checkout, login, search and category URLs (supports US-21). |
| 2026-11-15 | Notifier interface is `send(subject, body)` and raises `NotificationError`; monitor updates `last_notified_price` only on success. |

## Spec corrections (vs. project-proposal.md; see FRD)
1. Capture the previous `lowest_price_seen` **before** updating it; otherwise "new low" can never fire.
2. Treat NULL `last_notified_price` as +∞.
3. Alert condition: `(price <= target OR price < prev_lowest) AND in_stock AND price < last_notified`.
4. Verify Tavily-found prices with the Crawl4AI scraper when setting the baseline.
5. Graph 2 is async (Crawl4AI is async).

## Open questions / risks
- Python 3.14: all dependencies and Playwright Chromium work. langsmith prints DeprecationWarnings (harmless).
- **Resolved 2026-11-16:** Best Buy Canada blocks the headless browser (Akamai 403), so it is dropped from v1 (option b). Not pursuing anti-bot evasion (retailer ToS, BRD §11).
- v1 retailers: Amazon.ca, Walmart.ca, Staples.ca, Costco.ca, Dell Canada, Newegg.ca, Canada Computers, Canadian Tire, plus official brand stores.
- **Resolved 2026-11-16:** RONA is blocked by DataDome (403), so it is dropped from v1 (`EXCLUDED_RETAILERS`).
- Walmart blocking is intermittent (PerimeterX). Monitor should surface repeated failures per item (Sprint 4/5: e.g. show "last successful check" in the watchlist).
- Amazon.ca works through CSS selectors; these may break when the layout changes.
- One finalized product can map to several Amazon ASINs (colour variants). Sprint 3 confirmation lets the user pick.
- APScheduler only runs while the CLI process is alive (acceptable for v1; documented).

## Next action
Sprint 2: research graph (US-01 – US-04). `ANTHROPIC_API_KEY` is in `.env` and was verified 2026-11-18 with a test call through `langchain-anthropic` on `claude-sonnet-5-5`. Unit tests mock the LLM.
