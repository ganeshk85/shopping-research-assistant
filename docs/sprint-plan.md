# Sprint Plan
## Shopping Research Assistant (v1)

| Field | Value |
|---|---|
| Version | 1.0 (draft) |
| Date | 2026-11-15 |
| Stories | [user-stories.md](user-stories.md) |
| Requirements | [BRD.md](BRD.md), [FRD.md](FRD.md) |

## Assumptions
- **Team:** one developer working with Claude Code.
- **Sprint length:** 1 week (Monday–Sunday).
- **Planned velocity:** about 15–19 points per sprint. Sprint 5 is deliberately lighter, leaving room for hardening and buffer.
- **Scope:** 84 points across 23 stories. 3 points are done in Sprint 0, leaving 81.
- **Sequence:** follows the proposal's build order: tools, then the research graph, then the monitor graph, then the CLI. Each sprint ends with something working end to end.

## Timeline

| Sprint | Dates | Theme | Build step | Points |
|---|---|---|---|---|
| 0 | 2026-11-15 | Foundation | Step 1 | 3 ✅ |
| 1 | 2026-11-16 → 11-22 | Tools layer | Step 2 | 18 |
| 2 | 2026-11-23 → 11-29 | Research conversation | Step 3 (part 1) | 19 |
| 3 | 2026-11-30 → 12-06 | Listings & tracking setup | Step 3 (part 2) | 18 |
| 4 | 2026-12-07 → 12-13 | Monitor & alerts | Step 4 | 14 |
| 5 | 2026-12-14 → 12-20 | CLI, watchlist & release | Step 5 | 12 + hardening |

**Target v1 release:** 2026-12-20.

---

## Sprint 0 — Foundation ✅ (done 2026-11-15)
**Goal:** repo, docs, and data layer ready for feature work.

| Story | Points | Status |
|---|---|---|
| US-23 One-command developer setup | 3 | Done |

Also completed:
- `CLAUDE.md`, `MEMORY.md`, BRD, and FRD.
- `.gitignore` / `.claudeignore` fixes.
- SQLite schema and CRUD, including `record_price_check`, which returns the previous lowest price (the data layer for US-13).
- 8 database tests passing.

---

## Sprint 1 — Tools layer
**Goal:** the building blocks work on their own. Search returns results, the scraper extracts prices from real pages, and alerts reach every channel.

| Story | Points |
|---|---|
| US-11 Reliable price extraction | 8 |
| US-12 Graceful handling of failed checks | 3 |
| US-16 Choose my notification channel | 5 |
| US-22 Clear configuration errors | 2 |
| **Total** | **18** |

**Technical tasks**
- Run `crawl4ai-setup` (Playwright Chromium) and confirm it works on Python 3.14.
- `tools/scraper.py`: `AsyncWebCrawler` wrapper, JSON-LD parser (`Product`/`Offer`/`AggregateOffer`/`@graph`), CSS/regex fallback, returns `ScrapedPriceResult`.
- Save HTML fixtures for the parser tests; no network in unit tests.
- `tools/search.py`: Tavily wrapper with `research_products(query)` and `find_retail_listings(product)` restricted to Canadian domains. Supports US-01 and US-05 in later sprints.
- `tools/notifier.py`: `Notifier` protocol with Console, Webhook, and Email (Resend/SMTP) implementations, plus a factory driven by `Settings`.
- Spike: manually scrape one Amazon.ca and one Best Buy Canada page and record the results in MEMORY.md (anti-bot risk). **Result:** Amazon.ca OK (CSS fallback); Best Buy blocked (Akamai 403), so it is dropped from v1.

**Demo:** run a script that scrapes 2–3 real product URLs and sends a test alert to the console and a webhook.

---

## Sprint 2 — Research conversation
**Goal:** a user can hold a multi-turn research chat and finalize a product.

| Story | Points |
|---|---|
| US-01 Get a researched comparison | 8 |
| US-02 Refine my criteria over several turns | 5 |
| US-03 Resume a previous research session | 3 |
| US-04 Finalize my chosen product | 3 |
| **Total** | **19** |

**Technical tasks**
- `graphs/research_graph.py`: `understand_intent` router (structured output), `research_and_compare` node, conditional edges, and `SqliteSaver` on `checkpoints.db`.
- Prompt design so the comparison stays grounded in search results.
- Temporary CLI chat loop to drive the graph (replaced in Sprint 5).
- Tests: intent routing with a mocked LLM (option number, name, ambiguous choice, follow-up question).

**Demo:** research headphones over 3–4 turns, quit, resume the thread, and finalize "option 2".

---

## Sprint 3 — Listings & tracking setup
**Goal:** a finalized product becomes tracked watchlist items after the user confirms.

| Story | Points |
|---|---|
| US-05 See current Canadian retail listings | 8 |
| US-06 Choose listings and a target price | 5 |
| US-07 Cancel tracking setup | 1 |
| US-08 Get confirmation that tracking is active | 2 |
| US-21 The assistant never buys anything | 2 |
| **Total** | **18** |

**Technical tasks**
- `locate_retail_listings` node: Tavily lookup, URL validation (reject search, category, and cart URLs), and price verification through the Sprint 1 scraper.
- `confirm_tracking_terms` node using `interrupt()` and resume with `Command(resume=...)`; default target = −10%.
- `save_to_watchlist` node writes through `database.add_tracked_item`.
- Guardrails: system-prompt rule against purchasing, plus a URL blocklist test.

**Demo:** finalize a product, see verified listings, pick two, accept the default target, and see them in the database.

---

## Sprint 4 — Monitor & alerts
**Goal:** price checks run end to end and alert correctly, with no duplicates.

| Story | Points |
|---|---|
| US-13 Keep a price history (graph wiring) | 2 |
| US-14 Alert when the price hits my target or a new low | 5 |
| US-15 No duplicate alerts | 3 |
| US-17 Alerts still arrive if the LLM fails | 2 |
| US-10 Run a price check on demand | 2 |
| **Total** | **14** |

**Technical tasks**
- `graphs/monitor_graph.py` (async): `fetch_active_trackers`, then `scrape_current_prices`, then the `evaluate_drops` conditional edge, then `generate_and_send_alert`.
- A pure function `should_alert(price, in_stock, target, previous_lowest, last_notified)` with a full test table (`tests/test_price_logic.py`).
- Template fallback for alert text; update `last_notified_price` only after a successful send.
- Check summary result (checked / failed / alerts).

**Demo:** seed an item with a target above the current price, run a manual check, receive one alert, run again, and get no second alert.

---

## Sprint 5 — CLI, watchlist & release
**Goal:** a complete, documented v1 CLI.

| Story | Points |
|---|---|
| US-09 Automatic price checks | 5 |
| US-18 View my watchlist | 2 |
| US-19 Pause, resume, delete, or retarget items | 3 |
| US-20 View price history | 2 |
| **Total** | **12** |

**Technical tasks and hardening**
- `main.py` menu (options 1–4, 0); replaces the temporary chat loop.
- APScheduler `BackgroundScheduler` at `CHECK_INTERVAL_HOURS`, with clean shutdown.
- End-to-end smoke test: research, then track, then check, then alert, with mocks.
- Live validation against real retailer pages; record the per-retailer success rate (target ≥ 80%).
- Update the README, and the BRD/FRD if scope changed.
- Buffer for bugs carried over from earlier sprints.

**Demo / release:** a full walkthrough from a fresh clone following the README. Tag `v1.0.0`.

---

## Definition of Ready
- The story has acceptance criteria and traces to an FR.
- Dependencies (keys, tools from earlier sprints) are available.
- The story is estimated.

## Definition of Done
- All acceptance criteria are met.
- Unit tests are added and `pytest` passes, with no network calls in unit tests.
- No LLM calls in the monitor path except alert text (NFR-2).
- No purchase, cart, or payment code paths (NFR-1).
- `.env.example`, README, and `MEMORY.md` are updated.
- The sprint demo scenario runs successfully.

## Risks to the plan
| Risk | Sprint | Mitigation |
|---|---|---|
| Retailers block headless scraping | 1, 3 | Best Buy dropped from v1 after the spike; Amazon.ca uses CSS fallback; accept `failed` and still track other retailers |
| Python 3.14 incompatibility (Playwright or Crawl4AI) | 1 | Validate early; fall back to Python 3.12 |
| Tavily returns non-product URLs or stale prices | 3 | URL validation and scrape verification (FR-3.3) |
| LLM output drifts from the schema | 2 | Structured output with Pydantic; retry once, then show an error |
| Scope creep (web UI, more retailers) | All | Out of scope per BRD §6; log ideas in MEMORY.md |

## Ceremonies (lightweight, solo)
- **Planning (Monday):** confirm the sprint stories and update `MEMORY.md`.
- **Daily:** tick tasks off in `MEMORY.md`.
- **Review and retro (Sunday):** run the demo scenario, note what to adjust, and re-estimate the remaining stories.
