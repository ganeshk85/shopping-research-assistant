# User Stories
## Shopping Research Assistant

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-15 (status updated 2026-11-20) |
| Status | **All 23 stories done** (84/84 points); 266 offline tests passing |
| Traces to | [BRD.md](BRD.md), [FRD.md](FRD.md) |
| Sprint plan | [sprint-plan.md](sprint-plan.md) |

**Personas**
- **Shopper:** an individual Canadian shopper using the CLI on their own machine.
- **Owner:** the person who installs and configures the app (API keys, notification channel). Often the same person.

**Estimation:** story points on a Fibonacci scale (1, 2, 3, 5, 8). **Priority:** MoSCoW (Must / Should / Could).

---

## Story map

| Epic | Stories | Points | BR | Status |
|---|---|---|---|---|
| E1 Product research | US-01 – US-04 | 19 | BR-1, BR-2, BR-3 | ✅ Done |
| E2 Listings & tracking setup | US-05 – US-08 | 16 | BR-4, BR-5 | ✅ Done |
| E3 Price monitoring | US-09 – US-13 | 20 | BR-6, BR-7 | ✅ Done |
| E4 Price-drop alerts | US-14 – US-17 | 15 | BR-8 | ✅ Done |
| E5 Watchlist management | US-18 – US-20 | 7 | BR-9 | ✅ Done |
| E6 Safety & platform | US-21 – US-23 | 7 | BR-10, NFRs | ✅ Done |
| **Total** | **23 stories** | **84** | | **84/84** |

**Completed by sprint**

| Sprint | Stories | Commit |
|---|---|---|
| 0 Foundation | US-23 | `18a0c86` |
| 1 Tools layer | US-11, US-12, US-16, US-22 | `18a0c86` |
| 2 Research conversation | US-01 – US-04 | `3b35c2f` |
| 3 Listings & tracking setup | US-05 – US-08, US-21 | `3b35c2f` |
| 4 Monitor & alerts | US-10, US-13 – US-15, US-17 | `861544d` |
| 5 CLI, watchlist & release | US-09, US-18 – US-20 | `861544d` |

---

## E1 — Product research

### US-01 Get a researched comparison ✅
**As a** shopper, **I want to** describe what I need in plain language and get a comparison of the top products, **so that** I don't have to read dozens of reviews myself.

| Priority | Points | Traces |
|---|---|---|
| Must | 8 | BR-1 · FR-2.1–FR-2.4 |

**Acceptance criteria**
- **Given** I type "noise-cancelling headphones under $400", **when** the assistant replies, **then** it shows 3–4 candidates, each with name, brand, key specs, pros, cons, typical CAD price range, and best-for.
- The reply includes a recommendation summary, and at most one clarifying question.
- Candidates are grounded in search results from independent review sources (e.g. Wirecutter, RTINGS, Reddit).
- If search or the LLM fails, I see a clear error and can retry without losing the conversation.
- _Done in Sprint 2._

### US-02 Refine my criteria over several turns ✅
**As a** shopper, **I want to** add or change requirements (budget, specs, use case) in follow-up messages, **so that** the comparison narrows to what fits me.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | BR-2 · FR-1.1, FR-2.5 |

**Acceptance criteria**
- **Given** a comparison is shown, **when** I say "I mostly use them on flights, battery life matters most", **then** the next comparison reflects that criterion.
- Earlier criteria (e.g. budget) are kept unless I change them.
- Questions like "what about battery life?" never finalize a product.
- A follow-up question about the options shown is answered directly and does not renumber the list (FR-1.4).
- _Done in Sprint 2._

### US-03 Resume a previous research session ✅
**As a** shopper, **I want to** continue a research conversation after closing the app, **so that** I don't have to start over.

| Priority | Points | Traces |
|---|---|---|
| Should | 3 | BR-2 · FR-5A.1–FR-5A.2 |

**Acceptance criteria**
- I can start a new thread or pick an existing one from a list.
- **Given** I resume a thread, **when** I send a message, **then** the assistant remembers the earlier criteria and the last comparison.
- Conversation state is stored in `checkpoints.db`, separate from the watchlist.
- _Done in Sprint 2._

### US-04 Finalize my chosen product ✅
**As a** shopper, **I want to** tell the assistant which product I've picked, by name or by option number, **so that** it moves on to finding where to buy it.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | BR-3 · FR-1.2–FR-1.3 |

**Acceptance criteria**
- "Let's go with the Sony WH-1000XM5" finalizes that product.
- "Option 2" finalizes the second candidate of the most recent comparison.
- If my choice is ambiguous, the assistant asks me to confirm instead of guessing.
- _Done in Sprint 2._

---

## E2 — Listings & tracking setup

### US-05 See current Canadian retail listings ✅
**As a** shopper, **I want to** see where my chosen product is sold in Canada and at what price, **so that** I know the current market price.

| Priority | Points | Traces |
|---|---|---|
| Must | 8 | BR-4 · FR-3.1–FR-3.4 |

**Acceptance criteria**
- Listings come from the supported Canadian retailers (Amazon.ca, Walmart.ca, Staples.ca, Costco.ca, Dell Canada, Newegg.ca, Canada Computers, Canadian Tire) and the official brand store when available. Best Buy Canada and RONA are excluded in v1.
- Each listing shows retailer, price (CAD), stock status, direct product URL, and whether the price was **verified** by scraping the page.
- Search, category, or cart URLs are never shown as listings.
- If no listings are found, the assistant tells me and returns me to research.
- _Done in Sprint 3._

### US-06 Choose listings and a target price ✅
**As a** shopper, **I want to** pick which listings to watch and the price I'd be happy to pay, **so that** I only get alerts that matter to me.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | BR-5 · FR-4.1–FR-4.3, BRL-3, BRL-6 |

**Acceptance criteria**
- The assistant pauses and asks me to choose one or more listings.
- **Given** I don't enter a target, **then** it suggests 10% below the lowest selected price, rounded to 2 decimals.
- Nothing is saved until I confirm.
- _Done in Sprint 3._

### US-07 Cancel tracking setup ✅
**As a** shopper, **I want to** back out at the confirmation step, **so that** nothing gets tracked if I change my mind.

| Priority | Points | Traces |
|---|---|---|
| Should | 1 | BR-5 · FR-4.4 |

**Acceptance criteria**
- **Given** I'm at the confirmation prompt, **when** I cancel, **then** no rows are written and I'm returned to the conversation.
- _Done in Sprint 3._

### US-08 Get confirmation that tracking is active ✅
**As a** shopper, **I want** a clear confirmation once my product is on the watchlist, **so that** I know monitoring has started.

| Priority | Points | Traces |
|---|---|---|
| Must | 2 | BR-5 · FR-5.1–FR-5.3 |

**Acceptance criteria**
- One watchlist entry is created per selected listing, with initial price, target price, status `active`, and a first price-history record.
- The confirmation lists each tracked retailer and its target price.
- _Done in Sprint 3._

---

## E3 — Price monitoring

### US-09 Automatic price checks ✅
**As a** shopper, **I want** prices checked automatically on a schedule, **so that** I don't have to visit retailer sites.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | BR-6 · FR-6.1, CLI option 4 |

**Acceptance criteria**
- Starting the background monitor runs a check every `CHECK_INTERVAL_HOURS` (default 6) while the app is running.
- Only `active` items are checked; `paused` items are skipped.
- I can stop the monitor and return to the menu.
- _Done in Sprint 5._

### US-10 Run a price check on demand ✅
**As a** shopper, **I want to** trigger a price check now, **so that** I can see the latest prices without waiting.

| Priority | Points | Traces |
|---|---|---|
| Must | 2 | BR-6 · CLI option 3 |

**Acceptance criteria**
- The check runs once and prints a summary: items checked, items failed, alerts sent.
- _Done in Sprint 4._

### US-11 Reliable price extraction ✅
**As a** shopper, **I want** prices read accurately from retailer pages, **so that** my alerts are trustworthy.

| Priority | Points | Traces |
|---|---|---|
| Must | 8 | BR-6 · FR-6.2–FR-6.4, NFR-2 |

**Acceptance criteria**
- The scraper reads schema.org `Product`/`Offer` JSON-LD first (price, currency, availability), then falls back to CSS/regex.
- Each result records its method: `json-ld`, `css-fallback`, or `failed`.
- No LLM is called during scraping.
- Unit tests cover JSON-LD parsing with saved HTML fixtures (single offer, offer list, `@graph`, out of stock, missing price).
- _Done in Sprint 1._

### US-12 Graceful handling of failed checks ✅
**As a** shopper, **I want** blocked or broken pages handled quietly, **so that** one bad page doesn't stop monitoring or cause a false alert.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | BR-6 · FR-6.7, FRD §8 |

**Acceptance criteria**
- A timeout or blocked page is logged as `failed`. No price is changed, no alert fires, and the remaining items are still checked.
- Failures are counted in the check summary.
- _Done in Sprint 1._

### US-13 Keep a price history ✅
**As a** shopper, **I want** every price check recorded, with the lowest price tracked, **so that** I can judge whether a deal is really good.

| Priority | Points | Traces |
|---|---|---|
| Must | 2 | BR-7 · FR-6.5–FR-6.6 |

**Acceptance criteria**
- Each successful check adds a `price_history` row with price, stock, and timestamp.
- `lowest_price_seen` updates only on a lower **in-stock** price (FR-6.6), and the previous lowest is returned for drop evaluation.
- _Data layer done in Sprint 0 (`database.record_price_check`); wired into Graph 2 in Sprint 4._

---

## E4 — Price-drop alerts

### US-14 Alert when the price hits my target or a new low ✅
**As a** shopper, **I want to** be notified when the price reaches my target or drops to a new low, **so that** I can buy at a good moment.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | BR-8 · FR-7, FR-8.1, BRL-4 |

**Acceptance criteria**
- An alert fires when `in_stock AND (price <= target OR price < previous_lowest) AND price < last_notified` (NULL last_notified counts as +∞).
- The alert includes the product, retailer, previous and new price, % below the initial price, historical low, and a direct link.
- Out-of-stock items never trigger alerts.
- The drop logic is unit-tested for: target hit, new low, out of stock, same as last notified, first alert.
- _Done in Sprint 4._

### US-15 No duplicate alerts ✅
**As a** shopper, **I don't want** repeated alerts for the same price, **so that** notifications stay meaningful.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | BR-8 · FR-8.4, BRL-5, FR-10.2 |

**Acceptance criteria**
- After a successful send, `last_notified_price` is set to the alerted price.
- No new alert fires unless the price falls below the last alerted price.
- If sending fails, `last_notified_price` is not updated, so the alert is retried next run.
- _Done in Sprint 4._

### US-16 Choose my notification channel ✅
**As an** owner, **I want to** receive alerts in the console, a Discord/Slack/Telegram webhook, or email, **so that** they reach me where I'll see them.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | BR-8 · FR-10.1 |

**Acceptance criteria**
- `NOTIFIER=console|webhook|email` selects the channel.
- Webhook payloads post successfully to Discord, Slack, and Telegram formats.
- Email sends through Resend if `RESEND_API_KEY` is set, otherwise through SMTP.
- A missing setting for the chosen channel produces a clear startup error.
- _Done in Sprint 1._ (Covered by offline tests; a live webhook demo is optional.)

### US-17 Alerts still arrive if the LLM fails ✅
**As a** shopper, **I want** to receive alerts even when the AI service is down, **so that** I never miss a deal.

| Priority | Points | Traces |
|---|---|---|
| Should | 2 | BR-8 · FR-8.2 |

**Acceptance criteria**
- If alert text generation fails, a deterministic template message with the same facts is sent instead.
- _Done in Sprint 4._

---

## E5 — Watchlist management

### US-18 View my watchlist ✅
**As a** shopper, **I want to** see everything I'm tracking at a glance, **so that** I know the current state of each item.

| Priority | Points | Traces |
|---|---|---|
| Must | 2 | BR-9 · CLI option 2 |

**Acceptance criteria**
- The list shows product, retailer, initial price, lowest seen, target, status, and last checked time.
- Items in a non-CAD currency are flagged.
- _Done in Sprint 5._

### US-19 Pause, resume, delete, or retarget items ✅
**As a** shopper, **I want to** manage tracked items, **so that** I stay in control of what's monitored.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | BR-9 · BRL-7 |

**Acceptance criteria**
- I can pause and resume an item; paused items are skipped by checks.
- I can change an item's target price.
- I can delete an item after confirming, and its price history is removed too.
- _Done in Sprint 5._

### US-20 View price history ✅
**As a** shopper, **I want to** see an item's price history, **so that** I can tell if the current price is a real deal.

| Priority | Points | Traces |
|---|---|---|
| Could | 2 | BR-7, BR-9 |

**Acceptance criteria**
- Shows timestamped prices and stock status, oldest to newest, with the lowest in-stock price highlighted.
- _Done in Sprint 5._

---

## E6 — Safety & platform

### US-21 The assistant never buys anything ✅
**As a** shopper, **I want** a guarantee that the assistant never purchases, handles payment, or adds to cart, **so that** I can trust it with my shopping.

| Priority | Points | Traces |
|---|---|---|
| Must | 2 | BR-10 · BRL-1, NFR-1 |

**Acceptance criteria**
- No tool or graph node interacts with cart, checkout, login, or payment pages or forms.
- If I ask the assistant to buy something, it declines and offers to track the price instead.
- A test checks that URLs containing cart/checkout paths are rejected as listings.
- _Done in Sprint 3._

### US-22 Clear configuration errors ✅
**As an** owner, **I want** clear messages when configuration is missing, **so that** I can fix setup quickly.

| Priority | Points | Traces |
|---|---|---|
| Should | 2 | FRD §6, §8 |

**Acceptance criteria**
- Starting a feature without its required key (e.g. `TAVILY_API_KEY`) names the missing key and says to set it in `.env`.
- _Done in Sprint 1._

### US-23 One-command developer setup ✅
**As an** owner, **I want** a documented setup with a virtual environment, editable install, and tests, **so that** I can run the project quickly.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | NFR-5 |

**Acceptance criteria**
- `pip install -e ".[dev]"` succeeds, and `pytest` passes.
- The README documents `crawl4ai-setup` and the `.env` keys.
- _Done in Sprint 0._
