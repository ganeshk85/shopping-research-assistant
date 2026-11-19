# MEMORY.md — Project Plan & Progress

Living tracker for the Shopping Research Assistant. Update after each step or decision.

_Last updated: 2026-11-19_

## Build progress
- [x] **Step 1 — Project setup & data layer:** `pyproject.toml`, `.env.example`, `README.md`, `config.py`, `models.py`, `database.py`, DB tests (8 passing; installs fine on Python 3.14). `database.record_price_check` returns the previous lowest price (spec fix #1).
- [x] **Step 2 — Tools layer:** `tools/search.py` (Tavily), `tools/scraper.py` (Crawl4AI + JSON-LD), `tools/notifier.py`. 63 tests passing, all offline.
- [x] **Step 3 — Research graph:** `graphs/research_graph.py` (Sprints 2-3): the multi-turn loop, intent routing, follow-up answers, finalization, purchase decline, retail lookup with verification, the `interrupt()` confirmation, saving to the watchlist, and SqliteSaver.
- [x] **Step 4 — Monitor graph:** `graphs/monitor_graph.py` (Sprint 4): async scrape, drop evaluation, LLM alert with template fallback. Service: `monitor.PriceMonitor`.
- [x] **Step 5 — CLI & tests:** all four menu options work. Watchlist management (`watchlist.py`), APScheduler (`scheduler.py`), and `tests/test_price_logic.py`, `tests/test_e2e.py`.

## Repo foundation (done 2026-11-15)
- [x] Renamed `. claudeignore` → `.claudeignore`; added `*.db`, `*.sqlite*`, `source/data/` to `.gitignore`
- [x] `CLAUDE.md`, `MEMORY.md`
- [x] `docs/BRD.md`, `docs/FRD.md`
- [x] `docs/user-stories.md` (23 stories, 84 points), `docs/sprint-plan.md` (1-week sprints; v1 target 2026-12-20)

## Current sprint
**Sprint 5 (branch `sprint-4-monitor`, uncommitted together with Sprint 4; the user will commit): CLI, watchlist and release.** Stories US-09, US-18, US-19, US-20 (12 points).
- [x] US-09 Background monitor: `scheduler.MonitorScheduler` wraps APScheduler `BackgroundScheduler`. It runs now, then every `CHECK_INTERVAL_HOURS`, with `max_instances=1` and `coalesce=True`. Errors are reported and never stop the schedule; stopping waits for a check in progress. CLI option 4: Enter or Ctrl+C stops it.
  - Gotcha: in APScheduler 3.x, `next_run_time=None` adds the job **paused**, so the argument is only passed when running immediately.
- [x] US-18 View: `watchlist.render_watchlist` shows latest price (`*` = out of stock), lowest, target and last check (relative time); warns after 2+ consecutive failures; flags non-CAD items.
- [x] US-19 Manage: `p/r/t/h/d/b` commands via `parse_watchlist_command` and `apply_command`; delete asks for confirmation in the CLI.
- [x] US-20 History: oldest first, with the lowest **in-stock** price marked.
- [x] Check health: new columns `last_check_at`, `last_check_error`, `consecutive_failures`. They're added by an idempotent `ALTER TABLE` migration in `init_db`, so existing DBs upgrade in place. The monitor calls `mark_check_ok` / `mark_check_failed`.
- [x] End-to-end offline test (`tests/test_e2e.py`): research → finalize → confirm → watchlist → alert → no duplicate → pause → skipped.
- [x] Live retailer validation, 2026-11-19: **18/18 (100%)**, 9 stores × 2 passes (Amazon and Newegg via CSS fallback, the rest via JSON-LD). Target was ≥80%. Walmart is still noted as intermittent from earlier runs.
- [x] README rewritten for v1: setup, keys, options, alert rules, retailers, troubleshooting.
- [x] Live CLI smoke test (throwaway pre-Sprint-5 DB): the migration worked, list/history/retarget/pause/cancelled-delete all worked, and the background monitor skipped the paused item and stopped cleanly. Three polish fixes followed: no "Next check: ?" while stopping; only the first equal lowest is marked; "last check" falls back to history for pre-upgrade items.
- [x] Tests: 266 passing, offline.
- [ ] Tag `v1.0.0`: after the user commits.

**Sprint 4 (branch `sprint-4-monitor`): Monitor and alerts.** Stories US-10, US-13, US-14, US-15, US-17 (14 points).
- [x] US-14/15 Alert rule: `alerts.alert_reason` is the single source: in stock AND (target reached OR new low) AND below the last alerted price (NULL = +∞). It returns `target_reached` or `new_low`. Table-tested in `tests/test_price_logic.py`.
- [x] US-13 History: `scrape_current_prices` records every usable check. **Change:** `record_price_check` only lowers `lowest_price_seen` for in-stock prices (FRD FR-6.6). `db.latest_price` gives "previous price" for alerts.
- [x] Failed checks: a scrape failure, a page title showing a different product, or a currency change records nothing and never alerts (FR-6.8).
- [x] US-17 Alert text: the LLM (low effort, fallback beta) only words facts precomputed by `alerts.alert_facts`. The template is used if the LLM is missing, errors, refuses, returns empty text, or omits the real new price; the link is appended if missing.
- [x] US-15 Delivery: `last_notified_price` is set only after a successful send. A failed send is retried next run, and the summary says so.
- [x] US-10 CLI option 3: `PriceMonitor.run_once_sync()` → `MonitorSummary.render()`.
- [x] Tests: 223 passing, offline.
- [x] Live demo, 2026-11-19 (throwaway DB, 3 real XM6 listings): the first check alerted for Staples (CA$479.99 vs CA$490 target) with accurate LLM text; the second check sent no duplicate. 0 failures; no LLM calls for unchanged items.

**Sprint 3 (committed `3b35c2f` with Sprint 2): Listings and tracking setup.** Stories US-05 to US-08, US-21 (18 points).
- [x] US-05 Listings: `locate_retail_listings` runs `find_retail_listings`, then `select_for_verification` (≤8, retailer-diverse), then the scraper (3 at a time), then `build_listings`. Scraped prices win over snippets; unverified prices are labelled.
- [x] US-06 Confirm: `confirm_tracking_terms` calls `interrupt()` with the listings and a suggested target. `ResearchSession.confirm(TrackingDecision)` resumes it. The default target is 10% below the lowest *selected* price.
- [x] US-07 Cancel: cancel, an invalid answer, or a new chat message while pending all save nothing.
- [x] US-08 Save: one item per listing plus a baseline history row; URLs already on the watchlist are skipped. The confirmation names each retailer, price and target.
- [x] US-21 Never buys: a `purchase_request` intent goes to a fixed decline reply; cart/checkout URLs are dropped in `build_listings` as well as in search.
- [x] CLI: progress line during the listing lookup; selection and target prompts with validation; resumed threads show a pending confirmation again.
- [x] **Live-run fixes, 2026-11-18:**
  - **Wrong products:** "Soundcore Liberty 5 Pro" listed iCan earbuds at CA$9.88 and Dell monitors. `matches_model` now uses name words when there's no model number, plus a page-title check (`ScrapedPriceResult.page_title`) and a price plausibility check (40-250% of the estimate). FRD FR-3.5.
  - **Speed:** the listing step went from 118s to ~43s (parallel per-retailer searches, scraping concurrency 3).
  - **Duplicates:** the same Walmart item was listed twice; `canonical_listing_url` strips query strings for known retailers.
- [x] Live CLI run (Sony WH-1000XM6): 8 listings from 6 retailers, 5 verified; invalid input re-prompted; custom target saved.
- [x] Tests: 189 passing, offline.

**Sprint 2 (committed `3b35c2f`): Research conversation.** Stories US-01, US-02, US-03, US-04 (19 points).
- [x] US-01 Comparison: `research_and_compare` builds a grounded `ResearchComparison` (3-4 candidates, sources, at most one question) from Tavily review results. Rendered as plain text for the CLI.
- [x] US-02 Refine: the intent LLM sees the full history plus the numbered options and writes a combined `search_query`.
  - **Live-run fix:** follow-up questions now route to `answer_followup`, which leaves the list's numbering unchanged (FRD FR-1.4).
- [x] US-03 Resume: SqliteSaver on `checkpoints.db`, plus a `research_threads` table (title, finalized product). The CLI lists threads and shows recent history.
- [x] US-04 Finalize: `resolve_choice` is deterministic. It maps option numbers and names; out-of-range numbers or ambiguous choices ask instead of guessing.
- [x] `research.ResearchSession` is the UI-facing service. `main.py` has a temporary chat loop on menu option 1.
- [x] Tests: 124 passing, offline (fake LLM and search).
- [x] Live demo, 2026-11-18 (4 turns plus a restart): research ~17-21s per turn, follow-up ~9s, finalize ~2s. The thread resumed with its chosen product after the restart.

**Sprint 1 (done 2026-11-16, commit `18a0c86`): Tools layer.** Stories US-11, US-12, US-16, US-22 (18 points). See [docs/sprint-plan.md](docs/sprint-plan.md).
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
| 2026-11-18 | Structured output uses `with_structured_output(..., method="json_schema", include_raw=True)` (native structured outputs). Never the default `function_calling`: Sonnet 5.5 rejects forced `tool_choice` with a 400. `call_structured` checks for `stop_reason == "refusal"` and parse errors. |
| 2026-11-18 | Server-side refusal fallback on by default: `betas=["server-side-fallback-2026-07-01"]` with `model_kwargs={"fallbacks": "default"}`. Live-verified through LangChain. |
| 2026-11-18 | Effort: intent routing `low` (max_tokens 4k); research and follow-ups `medium` (max_tokens 16k). The model stays `LLM_MODEL` (currently `claude-sonnet-5-5`, the user's choice to confirm; Opus 5.5 is the alternative). |
| 2026-11-18 | Graph state stores comparisons and products as plain dicts (`model_dump()`), not Pydantic objects, so checkpoints serialize safely. |
| 2026-11-18 | Each terminal node sets `last_action` (researched / answered / finalized / asked / error); callers use this, not `intent`, to see what a turn did. |

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
- Walmart blocking is intermittent (PerimeterX). **Handled 2026-11-19:** repeated failures show as a watchlist warning (`consecutive_failures`).
- Amazon.ca works through CSS selectors; these may break when the layout changes.
- One finalized product can map to several Amazon ASINs (colour variants). Sprint 3 confirmation lets the user pick.
- APScheduler only runs while the CLI process is alive (acceptable for v1; documented).

## Next action
1. The user commits Sprints 4-5, merges into `main` (the repo has no `main` branch yet; the first commit was made on a sprint branch), and tags `v1.0.0`.
2. Post-v1 ideas (not scheduled):
   - Run the monitor as an OS scheduled task so checks happen without the CLI open.
   - Web UI on top of `ResearchSession`, `PriceMonitor` and `watchlist`.
   - Retry blocked retailers later.
