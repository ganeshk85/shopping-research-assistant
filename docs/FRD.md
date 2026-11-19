# Functional Requirements Document (FRD)
## Shopping Research Assistant

| Field | Value |
|---|---|
| Version | 1.0 (draft) |
| Date | 2026-11-15 |
| Traces to | [BRD.md](BRD.md) |
| Source | [project-proposal.md](project-proposal.md). Where this FRD differs (see §9), this FRD is authoritative. |

---

## 1. System overview
Two independent LangGraph graphs share a local SQLite watchlist:

```
                ┌──────────────── Graph 1: Research & Finalization (interactive) ────────────────┐
 user ── CLI ──▶│ understand_intent ─┬─▶ research_and_compare ──▶ (reply, wait for next turn)    │
                │                    └─▶ locate_retail_listings ─▶ confirm_tracking_terms        │
                │                                                  (interrupt) ─▶ save_to_watchlist ──┐
                └─────────────────────────────────────────────────────────────────────────────────┘   │
                                                                                                    ▼
                                                                                         watchlist.db
                                                                                                    ▲
                ┌──────────────── Graph 2: Price Monitor (scheduled / manual) ────────────────────┐   │
 APScheduler ──▶│ fetch_active_trackers ─▶ scrape_current_prices ─▶ evaluate_drops ─┬─▶ END      │───┘
   or CLI       │                                                                  └─▶ generate_and_send_alert │
                └─────────────────────────────────────────────────────────────────────────────────┘
```

## 2. Functional requirements — Graph 1: Research & Finalization

### FR-1 Intent routing (`understand_intent`) — BR-1, BR-2, BR-3
- FR-1.1 Classify the latest user message, with conversation history, as `explore_or_refine` or `finalize_product`, using LLM structured output.
- FR-1.2 `finalize_product` requires an explicit choice (e.g. "Let's go with the Sony WH-1000XM5", "I've decided on option 2"). Ordinal references resolve against the most recent comparison.
- FR-1.3 If the choice is ambiguous (or an option number is out of range), ask the user to confirm instead of guessing (`confirm_choice`).
- FR-1.4 A question about options already shown that does not change the criteria (`ask_followup`, e.g. "how does comfort compare between 1 and 2?") gets a focused search and a direct answer. The numbered list is **not** replaced, so option numbers stay stable. _Added 2026-11-18 after a live run where a re-ranked list made "option 2" mean a different product._

**Acceptance:** "Option 2" after a 4-item comparison finalizes candidate #2; "what about battery life?" routes to research.

### FR-2 Research & compare (`research_and_compare`) — BR-1, BR-2
- FR-2.1 Build search queries from the accumulated criteria and query Tavily, favouring independent review sources (Wirecutter, RTINGS, Reddit, etc.).
- FR-2.2 Synthesize a `ResearchComparison` with 3–4 `ProductCandidate`s using structured output, grounded only in the search results.
- FR-2.3 Present a side-by-side comparison: name, brand, key specs, pros, cons, typical price range (CAD), best-for, plus a recommendation summary.
- FR-2.4 Optionally ask one clarifying question to narrow the choice.
- FR-2.5 Return control to the user; the loop repeats until finalization.

**Acceptance:** Each research turn shows 3–4 candidates with all fields populated; follow-up criteria change the results.

### FR-3 Locate retail listings (`locate_retail_listings`) — BR-4
- FR-3.1 Search Tavily for the finalized model across the supported Canadian retailers (Amazon.ca, Walmart.ca, Staples.ca, Costco.ca, Dell Canada, Newegg.ca, Canada Computers, Canadian Tire) and the official brand store. Run one combined search, then a targeted search for each retailer with no results. Each retailer has a product-URL pattern; only matching pages are listings. Best Buy Canada and RONA are excluded in v1 (they block the scraper) and must never be returned as listings.
- FR-3.2 Produce `RetailListing` objects with direct product URLs (not search/category pages). Strip query strings for known retailers so the same product isn't listed twice.
- FR-3.3 **Verify the current price and stock of each listing with the Crawl4AI scraper** (see FR-6). If verification fails, keep the search-derived price and flag it as unverified.
- FR-3.4 If no listings are found, tell the user and return to research.
- FR-3.5 **Listings must be the finalized product.** _Added 2026-11-18 after a live run listed unrelated earbuds and monitors._ A listing is dropped when:
  - its search title/URL doesn't match: names with a model number (e.g. `WH-1000XM5`) need every model token; other names (e.g. "Soundcore Liberty 5 Pro") need every identifying word, ignoring generic words like "wireless";
  - the product name on the scraped page itself doesn't match; or
  - its price is under 40% or over 250% of the research estimate (accessories, bundles, bad snippets).
  The reply says how many results were skipped.
- FR-3.6 Scrape at most 8 listings (one per retailer first, at most 3 per retailer), 3 at a time.

### FR-4 Confirm tracking terms (`confirm_tracking_terms`) — BR-5
- FR-4.1 Pause execution with LangGraph `interrupt()` and show the listings: retailer, price, stock, verified flag, URL.
- FR-4.2 The user selects one or more listings to monitor.
- FR-4.3 The user sets a target price; the default is 10% below the lowest selected current price (rounded to 2 decimals).
- FR-4.4 The user may cancel; nothing is saved. Sending a new chat message while a confirmation is pending cancels it explicitly. An invalid answer saves nothing.
- FR-4.5 A pending confirmation survives restarts. Resuming the thread shows it again.

### FR-4A Purchase requests (`decline_purchase`) — BR-10, BRL-1
- FR-4A.1 Requests to buy, order, check out, pay or add to cart are routed to a fixed reply that declines and offers price tracking instead. No search or tracking runs.

### FR-5 Save to watchlist (`save_to_watchlist`) — BR-5, BR-7
- FR-5.1 Insert one `tracked_items` row per selected listing with `initial_price = lowest_price_seen = current price`, `target_price`, `status = 'active'`, and `last_notified_price = NULL`.
- FR-5.2 Insert an initial `price_history` row.
- FR-5.3 Confirm to the user that monitoring is active.
- FR-5.4 A URL that is already on the watchlist is not added again. The reply says it's already tracked.

### FR-5A Conversation persistence — BR-2
- FR-5A.1 Checkpoint Graph 1 state with `SqliteSaver` in `checkpoints.db`, keyed by a thread ID.
- FR-5A.2 The user can continue a previous research thread or start a new one.

## 3. Functional requirements — Graph 2: Price Monitor

### FR-6 Fetch & scrape (`fetch_active_trackers`, `scrape_current_prices`) — BR-6, BR-7
- FR-6.1 Load all `tracked_items` with `status = 'active'`.
- FR-6.2 For each URL, render with Crawl4AI `AsyncWebCrawler` (headless Chromium, realistic user agent). Run asynchronously.
- FR-6.3 Extraction order: (1) `application/ld+json` schema.org `Product`/`Offer` (`price`, `priceCurrency`, `availability`); (2) CSS/regex fallback. Record `extraction_method` as `json-ld`, `css-fallback`, or `failed`.
- FR-6.4 **No LLM calls** in this step.
- FR-6.5 For every successful check, insert a `price_history` row.
- FR-6.6 **Capture `previous_lowest = lowest_price_seen` before updating**, then set `lowest_price_seen = min(lowest_price_seen, current_price)` **only when the item is in stock**. An out-of-stock price is recorded in history but never becomes the low, so it can't block a "new low" alert when stock returns.
- FR-6.8 A scrape whose page now shows a different product (title mismatch) or a different currency counts as a failed check: nothing is recorded and nothing alerts.
- FR-6.7 Failed scrapes are logged and skipped; they never trigger alerts or change prices.

### FR-7 Drop evaluation (`evaluate_drops`, conditional edge) — BR-8
An item qualifies for an alert when:
```
in_stock
AND (current_price <= target_price OR current_price < previous_lowest)
AND current_price < COALESCE(last_notified_price, +∞)
```
- FR-7.1 If no item qualifies, end without any LLM call.
- FR-7.2 If any items qualify, route to `generate_and_send_alert`.

**Acceptance (unit-tested):** price at target → alert; new low above target → alert; out of stock → no alert; same price as last notified → no alert; first alert with NULL last_notified → alert.

### FR-8 Alert (`generate_and_send_alert`) — BR-8
- FR-8.1 Generate concise alert text with the LLM: product, retailer, previous vs. new price, % discount vs. initial price, historical low, and direct link. All numbers are precomputed in code and passed as facts; the LLM only words them.
- FR-8.2 If LLM generation fails, refuses, returns empty text, or omits the actual new price, send a deterministic template message instead. If the link is missing, it is appended.
- FR-8.3 Send via the configured channel (FR-10).
- FR-8.4 On successful send, set `last_notified_price = current_price`.

## 4. CLI requirements — BR-9
| Menu option | Behaviour |
|---|---|
| 1. Start / continue product research | Choose a new or existing thread; chat loop; handles the confirmation interrupt prompts; `exit` returns to menu |
| 2. View / manage watchlist | List items (product, retailer, initial, current-low, target, status, last checked); pause, resume, delete, edit target; view price history |
| 3. Run price check now | Runs Graph 2 once and prints a summary (checked / failed / alerts) |
| 4. Start background monitor | Starts APScheduler at `CHECK_INTERVAL_HOURS`; runs until stopped |
| 0. Quit | Exits cleanly |

## 5. Data model

### Pydantic schemas
- `ProductCandidate`: name, brand, estimated_price, currency="CAD", rating_summary, key_specs[], pros[], cons[], best_for
- `ResearchComparison`: candidates[], recommendation_summary, clarifying_question?
- `RetailListing`: product_name, retailer, url, current_price, currency="CAD", in_stock=True, price_verified=False
- `ScrapedPriceResult`: url, current_price?, currency="CAD", in_stock=False, extraction_method, error?
- `TrackedItem`: mirrors the `tracked_items` row

### SQLite (`watchlist.db`)
**tracked_items**: id PK, product_name TEXT, retailer TEXT, url TEXT, currency TEXT DEFAULT 'CAD', initial_price REAL, target_price REAL, lowest_price_seen REAL, last_notified_price REAL NULL, status TEXT CHECK IN ('active','paused'), created_at DATETIME

**price_history**: id PK, item_id FK → tracked_items.id ON DELETE CASCADE, price REAL, in_stock BOOLEAN, checked_at DATETIME

## 6. Configuration (`.env`)
| Key | Purpose | Default |
|---|---|---|
| ANTHROPIC_API_KEY | LLM access | — |
| LLM_MODEL | Claude model ID | latest Claude model |
| TAVILY_API_KEY | Search | — |
| NOTIFIER | `console` / `webhook` / `email` | console |
| WEBHOOK_URL | Discord/Slack/Telegram webhook | — |
| RESEND_API_KEY or SMTP_HOST/PORT/USER/PASSWORD | Email transport | — |
| ALERT_EMAIL_FROM / ALERT_EMAIL_TO | Email addresses | — |
| DATA_DIR | SQLite location | `./data` |
| CHECK_INTERVAL_HOURS | Monitor cadence | 6 |
| DEFAULT_TARGET_DISCOUNT | Suggested target discount | 0.10 |

## 7. Notifications — FR-10
- FR-10.1 A common notifier interface with Console, Webhook, and Email implementations, selected by config.
- FR-10.2 A send failure is logged and leaves `last_notified_price` unchanged, so the alert retries next run.

## 8. Error handling
| Situation | Behaviour |
|---|---|
| Missing API key | Clear startup error naming the key |
| Tavily/LLM error during research | Tell the user, keep the conversation state, allow retry |
| Scrape blocked/timeout | `extraction_method="failed"`, logged, no DB price change |
| Price found but out of stock | History recorded with `in_stock=false`; no alert |
| Currency differs from CAD | Store as-is; flag in watchlist view |

## 9. Corrections to the proposal
1. `lowest_price_seen` is updated **after** capturing the previous value (FR-6.6); otherwise the new-low condition can never be true.
2. NULL `last_notified_price` is treated as +∞ (FR-7).
3. Operator grouping of the alert condition is explicit (FR-7).
4. Baseline prices from Tavily are verified by scraping (FR-3.3).
5. Graph 2 runs async because Crawl4AI is async (FR-6.2).

## 10. Non-functional requirements
| ID | Requirement |
|---|---|
| NFR-1 | **Safety:** no code paths for purchase, cart, or payment. |
| NFR-2 | **Cost:** no LLM tokens in the monitor path unless an alert is generated. |
| NFR-3 | **Privacy:** all data stored locally; secrets only in `.env`. |
| NFR-4 | **Extensibility:** graphs and tools are UI-agnostic so a web UI/API can be added. |
| NFR-5 | **Testability:** drop logic, JSON-LD parsing, and DB CRUD are unit-tested without network. |
| NFR-6 | **Politeness:** sequential or low-concurrency scraping at a ≥ 6h default interval. |
