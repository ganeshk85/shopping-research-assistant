# User Stories — v2 Web App
## Shopping Research Assistant

| Field | Value |
|---|---|
| Version | 1.1 (v2.1 stories US-44…US-47 added) |
| Date | 2026-11-21 (v1.0: 2026-11-20) |
| Builds on | [user-stories.md](user-stories.md) (v1, US-01…US-23, all done) |
| Sprint plan | [v2-sprint-plan.md](v2-sprint-plan.md) |
| Backlog | [backlog.md](backlog.md) (auth, multi-user, mobile, hosting) |

**Scope of v2:** a single-user web app for the owner, running locally.
- Next.js (App Router) + Tailwind CSS frontend.
- FastAPI backend in `source/` wrapping the existing `ResearchSession`, `PriceMonitor` and watchlist services. No business logic in Next.js.
- Local PostgreSQL 18 replaces SQLite for app data and LangGraph checkpoints.
- **Multi-user-ready data model, but no authentication** (BL-01) and no sign-up (BL-02).
- The v1 CLI keeps working on the same database.

**Personas:** as in v1. **Shopper** uses the web app; **Owner** installs and configures it (the same person in v2).
**Estimation:** Fibonacci story points. **Priority:** MoSCoW.

---

## Story map

| Epic | Stories | Points |
|---|---|---|
| E7 Data platform | US-24 – US-28 | 21 |
| E8 Backend API | US-29 – US-35 | 32 |
| E9 Web app | US-36 – US-42 | 28 |
| E10 Local run & release | US-43 | 2 |
| **Total v2.0** | **20 stories** | **83** |
| E11 Research quality & control (v2.1) | US-44 – US-47 | 15 |

---

## E7 — Data platform

### US-24 Store app data in Postgres ✅
**As an** owner, **I want** the watchlist, price history and research threads stored in Postgres, **so that** the app is ready for the web and, later, for more users.

| Priority | Points | Traces |
|---|---|---|
| Must | 8 | Decision 2026-11-20 (Postgres now) |

**Acceptance criteria**
- All tables from v1 (`tracked_items`, `price_history`, `research_threads`) exist in Postgres with the same rules: in-stock-only lowest price, `last_notified_price` semantics, check-health columns.
- The connection comes from `DATABASE_URL`; a missing or unreachable database gives a clear `ConfigError`-style message naming the setting.
- Schema changes are applied by numbered migrations, tracked in the database, and are safe to run twice.
- The CLI (all four menu options) works against Postgres with no change in behaviour.
- Database tests run against `TEST_DATABASE_URL` (localhost) and are skipped with a clear message if it is unreachable. Other tests stay offline with fakes.

### US-25 Keep conversations in Postgres ✅
**As a** shopper, **I want** research conversations saved in the same database, **so that** I can resume them from the web or the CLI.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | US-03 |

**Acceptance criteria**
- LangGraph checkpoints use `PostgresSaver` on `DATABASE_URL`; `checkpoints.db` is no longer used.
- A thread started in the CLI can be resumed after a restart, including a pending tracking confirmation.

### US-26 Data model ready for multiple users ✅
**As an** owner, **I want** every record to belong to a user, **so that** adding sign-in later (BL-01, BL-02) does not require reworking the data.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | Decision 2026-11-20 (multi-user-ready API) |

**Acceptance criteria**
- A `users` table exists, with one default user, `admin`, created by the migrations.
- Every owned table (`tracked_items`, `research_threads`, notification settings) has a `user_id NOT NULL` foreign key; price history is reached through its item.
- Every repository function takes a `user_id` and only reads or changes that user's rows.
- A test with two users shows neither can list, read, change or delete the other's threads, items or history.
- Watchlist URL de-duplication is per user, not global.

### US-27 Bring my v1 data across ✅
**As a** shopper, **I want** my existing watchlist and price history moved into Postgres, **so that** I don't lose what I'm already tracking.

| Priority | Points | Traces |
|---|---|---|
| Could | 3 | US-13, US-18 |

**Acceptance criteria**
- One command imports `watchlist.db` items and their full price history for the default user, preserving targets, status, lowest price, last notified price and timestamps.
- Running it twice does not create duplicates.
- It prints how many items and history rows were imported. Old research conversations are not imported; this is stated in the output and README.

### US-28 Database setup in one step ✅
**As an** owner, **I want** a single documented way to create the database and apply the schema, **so that** setup is quick and repeatable.

| Priority | Points | Traces |
|---|---|---|
| Must | 2 | US-23 |

**Acceptance criteria**
- The README shows how to create the dedicated `shopping_assistant` login and the two databases (app and test) on local PostgreSQL 18.
- One command (e.g. `shopping-assistant db migrate`) applies all migrations to `DATABASE_URL`.
- The app login can only access its own databases, not other databases on the server.

---

## E8 — Backend API

### US-29 Research chat over the API, with live progress ✅
**As a** shopper, **I want to** chat with the assistant from the web app and see what it's doing while it works, **so that** long research steps don't feel frozen.

| Priority | Points | Traces |
|---|---|---|
| Must | 8 | US-01 – US-04 |

**Acceptance criteria**
- Endpoints to create a thread, list my threads (title, finalized product, last updated) and get a thread's message history.
- Sending a message streams Server-Sent Events: progress events (e.g. "Searching reviews", "Checking Staples.ca"), then one final event with the turn result (reply text, comparison with numbered candidates, finalized product, or pending confirmation).
- Errors from search or the LLM arrive as an error event; the conversation is unchanged and the message can be retried.
- A purchase request gets the same fixed decline as the CLI (US-21).

### US-30 Confirm or cancel tracking over the API ✅
**As a** shopper, **I want to** pick listings and a target from the web app, **so that** I can finish tracking setup without the CLI.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | US-05 – US-08 |

**Acceptance criteria**
- An endpoint returns a thread's pending confirmation: listings (retailer, price, currency, stock, URL, verified flag) and the suggested target.
- Confirming with selected listings and an optional target resumes the graph and returns the saved items; cancelling saves nothing.
- Invalid input (no listings, unknown listing, non-positive target) returns a validation error and leaves the confirmation pending.

### US-31 Manage the watchlist over the API ✅
**As a** shopper, **I want** watchlist actions available to the web app, **so that** I can manage tracking from the browser.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | US-18 – US-20 |

**Acceptance criteria**
- List items with latest price, stock, lowest seen, target, status, last check and failure warning.
- Get one item, pause, resume, change target, and delete (with its history).
- Get an item's price history, oldest first, with the lowest in-stock entry flagged.
- An unknown item, or another user's item, returns 404.

### US-32 Run a price check from the API ✅
**As a** shopper, **I want to** start a price check from the web app and see the result, **so that** I don't have to wait for the schedule.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | US-10 |

**Acceptance criteria**
- Starting a check returns immediately with a check id; a status endpoint reports running/finished and the summary (checked, failed, alerts sent, alerts retried).
- If a check is already running (from the API, worker or CLI), the request is refused with a clear message instead of running twice.
- The API also reports when the last check ran and when the next scheduled one is due.

### US-33 A clean, typed API contract ✅
**As a** developer, **I want** a versioned, documented API with a generated TypeScript client, **so that** the web app (and later the mobile app) stay in sync with the backend.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | BL-05 (reuse) |

**Acceptance criteria**
- All endpoints live under `/api/v1`; the OpenAPI spec is served and exported to a file in the repo.
- Errors use one JSON shape (code, message, details).
- A TypeScript client and types are generated from the spec into `source/packages/api-client`; one command regenerates it.
- CORS allows only the local web app origin. The API listens on localhost only.
- No endpoint accepts a `user_id` from the client; the current user comes from one dependency (the default user in v2).

### US-34 Price checks keep running in the background ✅
**As a** shopper, **I want** scheduled checks to run while the app is running, without keeping a CLI open, **so that** I get alerts on time.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | US-09 |

**Acceptance criteria**
- A separate worker process runs a check at start-up and every `CHECK_INTERVAL_HOURS`.
- Only one check runs at a time across the worker, API and CLI (a database lock); a second attempt is skipped and logged.
- The worker records each run (start, end, summary) so the API can report it.
- Stopping the worker waits for a check in progress; errors in one run never stop the schedule.
- The scraping and drop logic still make no LLM calls (repo rule 1).

### US-35 Notification settings in the app ✅
**As a** shopper, **I want** my alert channel saved with my account, **so that** I can change it without editing `.env`.

| Priority | Points | Traces |
|---|---|---|
| Should | 5 | US-16 |

**Acceptance criteria**
- Per-user settings: channel (console, webhook, email), webhook URL, and alert email address.
- Server secrets (Resend key, SMTP credentials, LLM and Tavily keys) stay in `.env` and are never returned by the API.
- Endpoints to read and update settings, and to send a test alert through the chosen channel; a failed test returns the error.
- With no saved settings, the `.env` values are used, so v1 behaviour is unchanged.

---

## E9 — Web app

### US-36 Web app shell ✅
**As a** shopper, **I want** a clean web app with clear navigation, **so that** I can move between research, watchlist and settings.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | — |

**Acceptance criteria**
- Next.js (App Router, TypeScript) with Tailwind CSS in `source/apps/web`, inside an npm-workspaces monorepo with `source/packages/api-client`.
- Navigation to Research, Watchlist and Settings; works at phone width as well as desktop; light and dark themes.
- If the API is unreachable, a banner says so and explains how to start it.
- `npm run lint`, type-check and `npm run build` pass.

### US-37 Research chat in the browser ✅
**As a** shopper, **I want to** research products in a chat page, **so that** comparisons are easier to read than in a terminal.

| Priority | Points | Traces |
|---|---|---|
| Must | 8 | US-01 – US-04, US-29 |

**Acceptance criteria**
- A thread list (new thread, resume an existing one) beside the conversation.
- Comparisons show as numbered cards: name, brand, key specs, pros, cons, estimated CAD price, best-for, plus the recommendation and sources.
- Live progress shows while a turn runs; the input is disabled until it finishes.
- I can finalize by typing ("option 2") or by a "Choose this" button on a card.
- An error shows inline with a Retry button; no message is lost.

### US-38 Confirm tracking in the browser ✅
**As a** shopper, **I want to** choose listings and a target on a form, **so that** setting up tracking is quick and clear.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | US-05 – US-08, US-30 |

**Acceptance criteria**
- After finalizing, listings show with retailer, price, stock, a "verified" or "estimated" label, and a link to the retailer page.
- I can tick one or more listings; the target field is pre-filled with the suggestion and validated.
- Confirm shows each tracked retailer with its target and a link to the watchlist; Cancel returns to the chat and saves nothing.
- Re-opening the thread while a confirmation is pending shows the form again.

### US-39 Watchlist page ✅
**As a** shopper, **I want to** see and manage everything I track on one page, **so that** I stay in control.

| Priority | Points | Traces |
|---|---|---|
| Must | 5 | US-18, US-19, US-31, US-32 |

**Acceptance criteria**
- Each item shows product, retailer, latest price (or out of stock), lowest seen, target, status, last check (relative time), a warning after 2+ failed checks, and a non-CAD flag.
- Pause/resume, edit target inline, and delete with a confirmation dialog.
- A "Check now" button shows progress and then the summary; it is disabled while a check runs.
- Empty state links to Research.

### US-40 Price history chart ✅
**As a** shopper, **I want to** see an item's price over time on a chart, **so that** I can tell if today's price is a real deal.

| Priority | Points | Traces |
|---|---|---|
| Should | 3 | US-20 |

**Acceptance criteria**
- A line chart of price over time with the target shown as a reference line and the lowest in-stock price marked; out-of-stock checks are visibly different.
- A table below lists every check, oldest first.
- Readable in light and dark themes and at phone width.

### US-41 Notification settings page ✅
**As a** shopper, **I want to** choose and test my alert channel in the browser, **so that** I know alerts will reach me.

| Priority | Points | Traces |
|---|---|---|
| Should | 3 | US-16, US-35 |

**Acceptance criteria**
- Choose console, webhook or email; enter the webhook URL or alert email; save with validation.
- "Send test alert" shows success or the error message.
- Never shows server secrets.

### US-42 The web app never buys anything ✅
**As a** shopper, **I want** the web app to only link out to retailers, **so that** I can trust it the same way as the CLI.

| Priority | Points | Traces |
|---|---|---|
| Must | 1 | US-21, BR-10 |

**Acceptance criteria**
- Retailer links open the product page in a new tab (`rel="noopener noreferrer"`); there are no buy, cart or checkout buttons or wording.
- Asking to buy in the chat shows the decline message and offers tracking.

---

## E10 — Local run & release

### US-43 Run the whole app locally ✅
**As an** owner, **I want** clear steps to start everything on my laptop, **so that** I can use the web app day to day.

| Priority | Points | Traces |
|---|---|---|
| Must | 2 | US-23 |

**Acceptance criteria**
- The README covers: Postgres setup (US-28), `.env` settings, starting the API, the worker and the web app, and opening the browser.
- Each process has one start command; the web app finds the API through one setting.
- A fresh-clone walkthrough following the README succeeds.

---

## E11 — Research quality & control (v2.1)
From the owner's review of the web app on 2026-11-21. Decisions: price sources use option A (cite where the estimate came from, no extra searches); RedFlagDeals is searched only after a product is chosen; website selection covers retailers only; items already tracked at a retailer that is turned off keep being checked.

### US-44 See where each price came from
**As a** shopper, **I want** each option's price to show which website it came from, **so that** I can judge how much to trust it.

| Priority | Points | Traces |
|---|---|---|
| Must | 3 | US-01, US-37 |

**Acceptance criteria**
- Each option card shows a "Price seen" line: the estimated price, the website it came from, and a link to that page (new tab). It is labelled as an estimate from search results, not checked on the retailer's page.
- A price is only shown with a source. The source must be one of the pages the assistant actually searched; if it can't cite one, the card says "No price found in the search results" instead of an unsourced number.
- Every price shows its currency explicitly ("CA$699.00", "US$698.99"); a non-CAD price also gets a "Not CAD" badge. A bare "$" is never shown.
- Product names contain only the brand and model, with no retailer names, product codes or listing text; review summaries don't refer to "your listing".
- Each comparison lists what was searched: the review sites and the sites the prices came from.
- The CLI shows the same source after the price (e.g. "about CA$699 (amazon.ca)").
- Comparisons saved before this change still display, marked "source not recorded".

### US-45 Quick Verdict
**As a** shopper, **I want** a short verdict on the single best option for my situation, **so that** I can decide without reading every card.

| Priority | Points | Traces |
|---|---|---|
| Should | 2 | US-01, US-37 |

**Acceptance criteria**
- Above the option cards, a "Quick Verdict" of at most two sentences names one option (by number and name) and says why it fits what I asked for (budget, use, must-haves).
- That option's card is marked "Top pick".
- If my needs are too unclear to pick one, the verdict says what it needs to know instead of guessing, and no card is marked.
- The verdict only names an option that exists in the comparison; otherwise it isn't shown.
- The existing longer recommendation stays below the cards. The CLI prints the Quick Verdict first.
- Comparisons saved before this change still display, without a verdict.

### US-46 Community deals from RedFlagDeals
**As a** shopper, **I want** to see recent RedFlagDeals posts about the product I chose, **so that** I know about current or upcoming sales before I set my target.

| Priority | Points | Traces |
|---|---|---|
| Should | 5 | US-05, US-38 |

**Acceptance criteria**
- After I choose a product, a "Community deals" panel appears with the retailer listings: up to 5 recent RedFlagDeals posts about that product, each with its title, date when known, the store and price when the post states them, and a link (new tab).
- The panel says these are posts by other shoppers, not checked, and may have expired.
- Only posts that match the chosen product are shown (same model matching as the listing lookup). With none, it says "No recent RedFlagDeals posts found for <product>."
- Posts are found through the search service limited to redflagdeals.com, with one search per chosen product. RedFlagDeals pages are not fetched directly.
- If the deals search fails, the listings and the tracking form still work; the panel says deals couldn't be loaded.
- The panel is part of the conversation, so it shows again when I reopen the thread. The CLI prints a short version.
- Links only; no buy, cart or checkout wording (US-42, BRL-1).

### US-47 Choose which retailers the assistant checks
**As the** admin, **I want to** choose which retailers the assistant looks up listings at, **so that** it only shows stores I'm willing to buy from.

| Priority | Points | Traces |
|---|---|---|
| Should | 5 | US-05, US-41 |

**Acceptance criteria**
- The Settings page has a "Retailers" section listing every supported retailer plus "Official brand stores", each with an on/off switch. Best Buy Canada and RONA are listed but can't be turned on, with the reason "Blocks automated price checks".
- All are on by default. At least one must stay on; trying to turn off the last one shows a message and saves nothing.
- The choice is saved with my account. When I choose a product, only the enabled retailers are searched and checked; changes apply to the next lookup without a restart.
- Items I already track at a retailer I turn off keep being checked and can still alert. The watchlist marks them "Retailer turned off for new lookups".
- Review sites and RedFlagDeals are not affected (retailers only for now).
- The API exposes read and update endpoints for this setting; the CLI's listing lookup uses the same setting.
