# MEMORY.md — Project Plan & Progress

Living tracker for the Shopping Research Assistant. Update after each step or decision.

_Last updated: 2026-11-21_

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
**Sprint 10 (branch `add-nextjs-postgres-web-app`, 2026-11-21, uncommitted): Watchlist, history, settings & release.** Stories US-39, US-40, US-41, US-27, US-43 (16 points). All five done; **v2 feature-complete**. Tag `v2.0.0` waits for the user's commit.
- [x] US-27 `v1_import.py` + `shopping-assistant db import-v1 [PATH]` (default `DATA_DIR/watchlist.db`): read-only SQLite, `UserStore.import_tracked_item` (one transaction per item: row with all fields + `executemany` history), skip URLs already on the watchlist, skip+report constraint failures, accepts pre-Sprint-5 files (no health columns), naive timestamps = UTC. Output says conversations aren't imported. The real `source/data/watchlist.db` is empty (0 items).
- [x] US-39 `components/watchlist/watchlist-app.tsx` + `check-now.tsx`: item cards (latest/out of stock, lowest, target, Active/Paused, last check, ⚠ after failures via `needs_attention`, "Priced in USD"), Pause/Resume, inline target edit, delete behind an in-card `alertdialog`, empty state → Research. Check now: POST, poll every 2 s, summary line (`describeRun`), reload list; on mount follows a running check (worker/CLI); a refused start follows the running one.
- [x] US-40 `price-history-chart.tsx`: **hand-built SVG, no chart library** (dataviz skill followed: single series → no legend box, 2px line, solid hairline grid, target as a labelled amber reference line, lowest in-stock point larger + labelled, out-of-stock points hollow + key, crosshair + tooltip on hover, `role="img"` summary, `HistoryTable` view). Width via ResizeObserver. `niceTicks()` for the y axis.
- [x] US-41 `components/settings/settings-app.tsx`: radio channel (email disabled with the .env hint when `email_available` is false), webhook URL (empty = keep saved; masked hint shown), email address, Save (disabled until changed), Send test alert (disabled while unsaved changes), "Use .env settings instead".
- [x] US-43 README rewritten around v2: "How it runs" table, numbered set-up (clone → venv → DB → .env → migrate → optional import → npm install/build → three windows → open localhost:3000), usage, configuration, CLI, troubleshooting (incl. Windows 260-char path limit), developer section. New script `npm run web:start`.
- [x] BRD v1.1 (v2 scope, constraints), FRD §4B web app + v1 import, CLAUDE.md commands/layout.
- [x] Tests: **354 Python** (+10 `test_v1_import.py`), **46 web** (+26: watchlist 11, chart 7, settings 8). Removed the unused `page-header.tsx`.
- [x] Live demo (test DB): imported a generated v1 file (2 items + 8 rows; 1 skipped as already present; second run 0), Check now (17 s, real scraping), retarget, pause/resume, history chart + tooltip, delete-cancel; settings: fake Slack webhook saved masked, test 502 shown, reset, console test OK. Phone dark, no h-scroll. Fix: history table rows were wrapping on phones (compact date, `whitespace-nowrap`).
- [x] **Fresh-copy walkthrough** (files `git ls-files -co --exclude-standard` would ship: 120, no `.env`, no `*.db`): followed the README in `C:\Users\gkaks\sra-fresh` (deleted afterwards; the scratchpad path was too long for pip on Windows → README note). venv + install, `.env` from the example, migrate, import-v1 (clear "not found" message), npm install + build, 354 + 46 tests, three processes; in the browser: researched a 65W USB-C GaN charger (27 s), chose option 1 → 4 listings (50 s), tracked Amazon.ca CA$24.69 with target CA$34.69; restarted the worker → its start-up check sent "Target price reached" (console). Settings test alert OK. No console errors.
- Gotcha: `subst` doesn't help with long paths for venvs (Python resolves the real path).

**Sprint 9 (branch `add-nextjs-postgres-web-app`, 2026-11-21, uncommitted): Research flow in the browser.** Stories US-37, US-38, US-42 (14 points). All three done.
- [x] Backend: the comparison and listings messages carry their structured data in `AIMessage.additional_kwargs` (`comparison` / `listings`); `ResearchSession.snapshot()` returns message dicts and `ChatMessage` gained optional `comparison` and `listings`, so every past comparison renders as cards after a reload. langchain-anthropic never sends `additional_kwargs` to the model (test `test_attached_cards_are_never_sent_to_the_model` guards this). CLI unchanged (`history()` still returns text).
- [x] US-37 `apps/web/src/components/research/research-app.tsx`: client-side page at `/research`, thread kept in `?thread=` (read from `window.location`, so no Suspense needed under Cache Components). Thread list (sidebar; toggle at phone width), numbered comparison cards (`comparison-cards.tsx`: brand, about-price, best for, reviews, specs, pros/cons, recommendation, one source link per site), "Choose this" on the latest comparison sends "I'll go with option N: name". Live progress from SSE; input disabled during a turn; after `result` the page re-reads `GET /threads/{id}`. Errors (SSE `error` or refusal before streaming) show inline with Retry; the message is kept. Empty state with example prompts.
- [x] US-38 `tracking-form.tsx`: checkboxes per listing (retailer, price, stock, verified/estimated badge, link out); target pre-filled and following the selection (same rule as `default_target_price`) until edited; validates locally, shows the server's 422 message; warns if target ≥ current price; "Don't track" cancels. After confirm: "Go to your watchlist" link. Reload while pending shows the form again. While pending, the listings show only in the form (not repeated in the chat).
- [x] US-42: all outbound links go through `ExternalLink` (`target="_blank" rel="noopener noreferrer"`); a test asserts no buy/cart/checkout/purchase/order wording on any link or button and that the decline message shows.
- [x] `lib/api.ts`: `research` wrapper (listThreads/newThread/getThread/confirm/send) + `errorMessage`; component tests mock this one module.
- [x] Web tests: **Vitest 5.1 + Testing Library + jsdom** (`vitest.config.mts`, `vitest.setup.ts`), 20 tests in 3 files. `npm run web:test`; `web:check` now runs lint + typecheck + api-client typecheck + tests.
- [x] Python: **344 passing** (+2).
- [x] Live demo, 2026-11-21 (test DB, real Claude/Tavily/Crawl4AI, Playwright): "Noise-cancelling over-ear headphones for long flights, under $500 CAD" → 4 cards (22 s); follow-up on comfort answered (12 s); "Choose this" on option 2 (Bose QC Ultra 2nd Gen) → 4 verified listings (35 s); reload restored the form; confirmed Staples CA$299.99 + Amazon.ca CA$499.00 at CA$269.99 → both on `GET /watchlist`. No console errors; no horizontal scroll at 390 px.
- [x] Fixes from the demo: listings no longer shown twice while pending; auto-scroll anchor moved below the composer (last message was hidden behind it on phones); "cheapest  listing" double space.
- Notes for later: Staples listed the QC Ultra (2nd Gen) at CA$299.99, well below the ~CA$600 estimate but inside the 40–250% plausibility band; worth a look if it recurs. Out-of-stock listings are still offered (v1 behaviour).

**Sprint 8 (branch `add-nextjs-postgres-web-app`, 2026-11-21, uncommitted): Worker, settings & web shell.** Stories US-32, US-34, US-35, US-36 (16 points). All four done.
- [x] **All code under `source/`** (user request): the npm workspace moved from the repo root into `source/` (`source/package.json`, `source/package-lock.json`, `source/packages/api-client`, `source/apps/web`, `source/node_modules`). `DEFAULT_OPENAPI_PATH` = `source/packages/api-client/openapi.json`. Run npm commands from `source/`. The repo root now holds only docs, `CLAUDE.md`, `MEMORY.md` and git/Claude config.
- [x] Migration `0003_checks_and_notification_settings.sql`: `monitor_runs` (per user: trigger schedule/api/cli, status running/finished/failed, counts, error), `worker_status` (process-level heartbeat, interval, next run), `notification_settings` (per user: channel, webhook_url, alert_email).
- [x] `checks.py`: `CheckLock` = `pg_try_advisory_lock(CHECK_LOCK_CLASS, user_id)` on its **own** connection (not the pool), so it spans processes and is freed if a process dies. `begin_check` (lock + record; refusal raises `CheckAlreadyRunning` and logs) / `complete_check` (run, record, always release) / `run_check`. A run left `running` by a dead process is closed as failed by the next check to get the lock. Monitor is built **after** the lock in `run_check`, so a setup error is recorded.
- [x] US-34 `worker.py` `PriceCheckWorker` + `shopping-assistant worker`: wraps `MonitorScheduler`; fresh `PriceMonitor` per run (saved settings apply without restart); heartbeat every 60s into `worker_status` (API treats >3 min as stopped); `stop()` waits for a check in progress. CLI options 3 and 4 also go through `run_check` (trigger `cli`). Ctrl+C: main loop sleeps 1s at a time because a long blocking wait ignores Ctrl+C on Windows.
- [x] US-35: `notifier.with_saved_settings(settings, saved)` overlays channel / webhook URL / alert email on `.env`; sender, Resend key and SMTP login stay in `.env`. `PriceMonitor` reads the store's saved settings (store is now opened before the notifier). API returns the webhook URL **masked** (`https://host/…last4`) and redacts its path/query from delivery errors; PUT omits = keep, null = clear.
- [x] US-32 API: `POST /checks` (202 + run; 409 `check_running` with `running_check_id`; 503 if alerts/DB not set up, nothing recorded), `GET /checks`, `GET /checks/status` (running, last ended, worker schedule), `GET /checks/{id}`. API checks run on a 1-thread executor in `Services`; shut down (waits) in the lifespan. Settings: `GET/PUT/DELETE /settings/notifications`, `POST /settings/notifications/test` (502 `notification_failed`). `Services` takes `monitor_factory` and `notifier_factory` for tests. CORS now allows PUT.
- [x] US-36 `source/apps/web` (`@shopping-assistant/web`): Next.js **16.4.6** (create-next-app defaults: App Router, Turbopack, Cache Components + Partial Prefetching on, React 19.3), Tailwind CSS 4.3, ESLint 9. System font stack (no Google font download at build). Header nav + bottom tab bar at phone width; light/dark follow the system. `useBackendStatus` polls `/health` + `/checks/status` every 15s and on focus: amber banner when the API is unreachable (with the start command) or the DB is down; otherwise a line "Last price check … · next in …" or "Background checks are off". The one web setting: `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8000`, read at build). Research / Watchlist / Settings are placeholders until Sprints 9-10. Workspace packages are transpiled automatically by Turbopack (no `transpilePackages`). `typecheck` = `next typegen && tsc --noEmit` (`LayoutProps` is a generated type).
- [x] Scripts (from `source/`): `npm run web:dev`, `web:build`, `web:check` (lint + typecheck + api-client typecheck). Lint, type-check and production build pass.
- [x] Tests: **342 passing** (34 new: `tests/test_checks.py` 13 for lock/runs/worker/settings repo; `tests/test_api_checks_settings.py` 20; `test_monitor_graph` +1 saved-settings test).
- [x] Live demo, 2026-11-21 (test DB): API + worker + built web app. The worker checked on start (2 leftover test items: 1 checked, 1 blocked) and reported next run +6h; `POST /checks` → 202, an immediate second POST → 409; email rejected (not set up on the server); a fake Slack webhook saved and masked, its test → 502 with the token redacted; reset → console test → 200. Playwright screenshots: desktop light and phone dark, no horizontal scroll; API-down banner shown after stopping the API.
- [x] Fixes from the demo: "Last price check now" → "just now"; the start command in the banner is its own scrollable line (it broke mid-word on phones).
- Notes for later: the worker checks only the default user (all users with BL-02); the masked hint shows the last 4 characters of the webhook URL.

**Sprint 7 (branch `add-nextjs-postgres-web-app`, 2026-11-20, uncommitted): Core API.** Stories US-29, US-30, US-31, US-33 (19 points). All four done.
- [x] Default user renamed **`admin`** (user request): migration `0002_rename_default_user_to_admin.sql` renames `owner` in place (same id); `DEFAULT_USERNAME = "admin"`. Applied to app and test DBs.
- [x] Deps: `fastapi` 0.165, `uvicorn[standard]` 0.54 (Starlette 1.10).
- [x] `shopping_assistant/api/`: `schemas.py` (contract incl. `StreamEvent` discriminated union), `errors.py` (`ApiError`; one `{code,message,details}` shape), `deps.py` (`Services`: one `ResearchSession` per user, lazily; `claim_thread`/`release_thread` = one turn per thread; **`current_store` is the only place deciding the user**), `routes_threads.py`, `routes_watchlist.py`, `app.py` (`create_app(settings, session_factory=)`, CORS from `WEB_ORIGINS`, migrations on start-up, custom `openapi()` adds SSE models and maps 422 to ErrorBody).
- [x] US-29 SSE: `ResearchSession` got `on_step` (LangGraph `stream_mode=["updates","tasks"]`; a task event with `input` = node starting) and `snapshot()`. The route starts the turn in a worker thread immediately (so the busy flag is always released) and drains an asyncio queue. Progress is per graph step, not per retailer.
- [x] US-30: invalid decisions are validated in the API (`validate_decision` + duplicates) → 422 `invalid_decision`, confirmation stays pending.
- [x] US-31: watchlist endpoints reuse `watchlist.py` helpers (`load_row`, `last_checked_at`, `needs_attention`, `lowest_in_stock_entry`; the CLI uses them too).
- [x] US-33: `/api/v1`, `shopping-assistant api openapi` writes `packages/api-client/openapi.json`; root `package.json` (npm workspaces) + `@shopping-assistant/api-client` (openapi-typescript 7.13, openapi-fetch 0.13.8, TypeScript 5.9): `createApiClient()`, `streamMessage()` SSE generator, `ApiError`. `npm run api:generate`, `npm run api:typecheck` pass. A test fails if `openapi.json` is stale.
- [x] `shopping-assistant api serve` binds **127.0.0.1** only (no sign-in yet).
- [x] Tests: **308 passing** (31 new in `tests/test_api.py`: streaming, confirmation validation, watchlist CRUD/history, 404 for another user's data, CORS, missing keys, spec checks).
- [x] Live API demo, 2026-11-20 (test DB, port 8001, real Claude/Tavily/Crawl4AI over curl): "27-inch 4K monitor for photo editing under $600 CAD" streamed 2 progress events + 4 candidates; "option 3" streamed 4 progress events → Asus ProArt PA279CRV, 2 verified listings (Newegg CA$499.99, Amazon.ca CA$498.99 out of stock); invalid choice → 422; confirmed both at CA$470; pause, retarget, history and `/docs` worked.
- [x] Fix from the demo: the saved-tracking reply no longer mentions CLI "menu options 3 and 4" (UI-neutral wording).
- Notes for later: the out-of-stock Amazon listing was offered and saved (v1 behaviour); finer progress (per retailer) would need a LangGraph custom stream writer in `locate_retail_listings`.

**Sprint 6 (branch `add-nextjs-postgres-web-app`, started 2026-11-20, uncommitted): Data platform on Postgres.** Stories US-24, US-25, US-26, US-28 (18 points). All four done; code complete, awaiting the user's review/commit.
- [x] Setup: login `shopping_assistant` (random password, only in `.env`) owns databases `shopping_assistant` and `shopping_assistant_test`; `REVOKE ALL … FROM PUBLIC` on both. `.env` no longer holds the `postgres` superuser password. The app login can still *connect* to `expense_tracker` (PUBLIC has CONNECT there; not changed, it's another project) but sees none of its tables.
- [x] Deps: `psycopg[binary]` 3.3.9, `psycopg-pool` 3.3.3, `langgraph-checkpoint-postgres` 3.2.1 (langgraph 1.2.22) on Python 3.14; `langgraph-checkpoint-sqlite` removed.
- [x] US-24/US-26 `database.py` rewritten: `Database` (one `ConnectionPool` per URL via `get_database`, shared with `PostgresSaver`; kwargs autocommit + `prepare_threshold=0` + `dict_row`; repository uses explicit `conn.transaction()`), `UserStore` (v1 functions minus `db_path`, every query filtered by `user_id`; history scoped via join), `open_store(settings)` = seeded `owner`. Unreachable DB → `DatabaseError` (subclass of `ConfigError`) naming user@host:port/db without the password.
- [x] Migrations: `shopping_assistant/migrations/0001_initial.sql` (users + seeded owner, tracked_items with `UNIQUE (user_id, url)`, price_history, research_threads), `schema_migrations` table, `pg_advisory_xact_lock`; run on a plain (non-pool) connection because files hold several statements. `migrate()` also runs `PostgresSaver.setup()`.
- [x] US-25: `ResearchSession` uses `PostgresSaver(store.database.pool)`; `history` / `pending_confirmation` / `send` raise `ThreadAccessError` for another user's thread (upsert has `WHERE research_threads.user_id = EXCLUDED.user_id`). LLM keys are checked before the DB is opened.
- [x] `PriceMonitor` / `MonitorDeps` / `TrackingDeps` take a `UserStore`; notifier is built before the DB (config errors first). Monitor checks one user's items; all users arrives with BL-02.
- [x] US-28 CLI: `shopping-assistant db migrate` / `db status`; the menu applies pending migrations at start. README has the PostgreSQL setup steps; `.env.example` uses the app login.
- [x] Tests: **277 passing** (11 new: migrations, owner seed, connection errors, cross-user isolation for items/history/threads/sessions/watchlist commands). conftest: session `pg_database` (refuses a DB name not ending in `_test`), per-test `store` (TRUNCATE app + checkpoint tables, drop non-owner users). Unreachable test DB → 63 skipped with the reason, 214 pass.
- [x] Live demo, 2026-11-20 (against the **test** DB): research "wireless earbuds under $200 CAD" → EarFun Air Pro 4 → 3 verified Amazon.ca listings → tracked #1 at default target CA$63.89; restarted the CLI and resumed the thread with its history and chosen product (US-25). App DB is migrated and empty.
- [x] Docs: CLAUDE.md (tech stack, layout, commands, rules 3/6/9/10), FRD (§1, FR-5A, §5 data model, §6 config).
- Gotchas: PowerShell piping adds a BOM to the first stdin line (use bash `printf` for scripted CLI runs). `TRUNCATE … RESTART IDENTITY` keeps test item ids starting at 1.
- [ ] Entry criterion still open: tag `v1.0.0` (user).

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
- [x] `docs/user-stories.md` v1.1 (2026-11-20): all 23 stories marked ✅ with the sprint that finished each; US-13/US-20 wording aligned with the in-stock-only lowest price (FR-6.6).
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
| 2026-11-15 | Stdlib `sqlite3` (no SQLAlchemy). Separate DB files: `checkpoints.db` (LangGraph) and `watchlist.db` (tracked items + history), both in `source/data/`. **Superseded 2026-11-20 (Sprint 6) by Postgres;** the files stay only as the v1 import source (US-27). |
| 2026-11-15 | Plan/progress tracked in this repo file instead of the user-profile folder. |
| 2026-11-15 | Fallback extraction uses BeautifulSoup on the HTML returned by Crawl4AI (not `JsonCssExtractionStrategy`). It's deterministic, testable with fixtures, and retailer selectors live in one dict (`_RETAILER_CSS`). |
| 2026-11-15 | `search.looks_like_product_url` / `is_blocked_url` reject cart, checkout, login, search and category URLs (supports US-21). |
| 2026-11-15 | Notifier interface is `send(subject, body)` and raises `NotificationError`; monitor updates `last_notified_price` only on success. |
| 2026-11-18 | Structured output uses `with_structured_output(..., method="json_schema", include_raw=True)` (native structured outputs). Never the default `function_calling`: Sonnet 5.5 rejects forced `tool_choice` with a 400. `call_structured` checks for `stop_reason == "refusal"` and parse errors. |
| 2026-11-18 | Server-side refusal fallback on by default: `betas=["server-side-fallback-2026-07-01"]` with `model_kwargs={"fallbacks": "default"}`. Live-verified through LangChain. |
| 2026-11-18 | Effort: intent routing `low` (max_tokens 4k); research and follow-ups `medium` (max_tokens 16k). The model stays `LLM_MODEL` (currently `claude-sonnet-5-5`, the user's choice to confirm; Opus 5.5 is the alternative). |
| 2026-11-18 | Graph state stores comparisons and products as plain dicts (`model_dump()`), not Pydantic objects, so checkpoints serialize safely. |
| 2026-11-18 | Each terminal node sets `last_action` (researched / answered / finalized / asked / error); callers use this, not `intent`, to see what a turn did. |
| 2026-11-20 | **v2 = single-user web app** (user decision). Frontend: Next.js + **Tailwind CSS**. Backend: **FastAPI** in `source/` wrapping `ResearchSession`, `PriceMonitor` and `watchlist`; no business logic in Next.js API routes. Typed TS client generated from the OpenAPI spec. |
| 2026-11-20 | **API designed for multi-user from the start** (user decision): `users` table with a seeded default user; every table has `user_id`; all queries are scoped by user; endpoints never take `user_id` from the client. One `current_user` dependency returns the default user, so auth (BL-01) only swaps that dependency. |
| 2026-11-20 | **No authentication in v2** (user decision); backlogged as BL-01. Multi-user backlogged as BL-02. |
| 2026-11-20 | **Postgres now, even for single user** (user decision). Replaces SQLite for the watchlist and for LangGraph checkpoints (`PostgresSaver`). Supersedes the 2026-11-15 SQLite decision once implemented; update CLAUDE.md's tech stack then. |
| 2026-11-20 | Mobile: **Expo (React Native)** later (BL-05), reusing the monorepo's shared `api-client` and `core` packages; share logic, not UI components. |
| 2026-11-20 | Backlog lives in [docs/backlog.md](docs/backlog.md) (BL-xx items). Items become user stories when pulled into a sprint. |
| 2026-11-20 | Monorepo uses **npm workspaces** (Node 24 and npm 11 installed; pnpm is not). Layout: `apps/web`, `packages/api-client`. |
| 2026-11-21 | **All code lives under `source/`** (user request): the npm workspace root is `source/package.json`, with `source/apps/web` and `source/packages/api-client` next to the Python package. Supersedes "at the repo root" above. |
| 2026-11-21 | **v2.1 scope (owner decisions on the web-app review):** price sources = option A (cite the search result the estimate came from; per-option retailer price snapshot is BL-14); RedFlagDeals searched only after a product is chosen, via the search service (no direct page fetching); periodic deal watch → BL-11; retailer selection covers retailers only (not review sites or RFD); items already tracked at a turned-off retailer keep being checked. |
| 2026-11-21 | Sprint 9 design: structured comparison/listings travel on the chat message (`additional_kwargs`), not a separate table; the research page is one client component with the thread in `?thread=`; after each streamed turn the page re-reads the thread instead of patching state from the SSE result. Web component tests use Vitest + Testing Library with `@/lib/api` mocked. |
| 2026-11-21 | Sprint 8 design: one check at a time **per user** via a Postgres session advisory lock on a dedicated connection; every run recorded in `monitor_runs`; the worker is a separate process (`shopping-assistant worker`) that publishes a heartbeat; per-user notification settings overlay `.env`, server secrets never leave `.env` and the webhook URL is only returned masked. |
| 2026-11-20 | Sprint 6 design: plain numbered SQL migrations (no Alembic, matches "no ORM"); `psycopg` 3 sync pool shared by the repository and `PostgresSaver`; repository is a per-user object (`UserStore`) rather than functions taking `user_id`, so a caller can't forget the scope. Prices `DOUBLE PRECISION` (same float behaviour as v1), timestamps `TIMESTAMPTZ` set by `now()`. |
| 2026-11-20 | The single default user is **`admin`** (user decision), renamed from `owner` by migration 0002. |
| 2026-11-20 | Sprint 7 API design: SSE via `StreamingResponse` (no extra library); confirmation is plain JSON (saving is quick); `POST /threads` only mints an ID; another user's data is always 404 (never 403, so IDs don't leak). TS client = `openapi-typescript` + `openapi-fetch` (types only, tiny runtime). |
| 2026-11-20 | **v2 runs locally first** (user decision), on the laptop's installed **PostgreSQL 18** (Windows service `postgresql-x64-18`, running, automatic start). No Docker. Connection via `DATABASE_URL` in `.env`. Two databases: `shopping_assistant` (app + checkpoints) and `shopping_assistant_test` (pytest). Cloud hosting stays BL-08. |

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
- APScheduler only runs while the CLI process is alive (acceptable for v1; documented). The v2 worker (US-34) addresses this.
- Postgres must be running for the app and for the 63 database tests (they skip otherwise). The service starts automatically on this laptop.

## Next action
1. The user commits Sprints 4-5, merges into `main` (the repo has no `main` branch yet; the first commit was made on a sprint branch), and tags `v1.0.0`.
2. **v2 web app: Sprints 6–10 done, all 20 stories (uncommitted).** Remaining release step for the user: review, commit, and tag `v2.0.0` (and `v1.0.0` on the v1 commit if not done).
3. **v2.1 planned (not started; the user said not to code yet):** Sprint 11 "Research quality & control", US-44 price sources on cards (+ explicit currency, clean product names), US-45 Quick Verdict, US-46 RedFlagDeals community deals after choosing a product, US-47 retailer on/off in Settings (15 points). Start with the RFD coverage spike. Bugs seen in the owner's test, fixed by US-44: a US$ price shown as bare "$" on a card, and listing text ("Amazon.ca B0H293SPS2", "your listing") leaking into candidate fields. Branch `add-nextjs-postgres-web-app`. Stories in [docs/v2-user-stories.md](docs/v2-user-stories.md) (US-24…US-43, 20 stories, 83 points); sprints in [docs/v2-sprint-plan.md](docs/v2-sprint-plan.md):
   - Sprint 6 (11-23→11-29) Data platform on Postgres: US-24, US-25, US-26, US-28 (18)
   - Sprint 7 (11-30→12-06) Core API: US-29, US-30, US-31, US-33 (19)
   - Sprint 8 (12-07→12-13) Worker, settings & web shell: US-32, US-34, US-35, US-36 (16)
   - Sprint 9 (12-14→12-20) Research flow in the browser: US-37, US-38, US-42 (14)
   - Sprint 10 (12-21→12-27) Watchlist, history, settings & release: US-27, US-39, US-40, US-41, US-43 (16); tag `v2.0.0`
   - Database login and databases created 2026-11-20 (see Sprint 6). FRD updated in Sprint 6; BRD scope update in Sprint 10.
   - Tests: database tests use the local `shopping_assistant_test` DB (localhost only, so the no-network rule holds) and are skipped with a clear message if it's unreachable. Graph, service and API tests keep using fakes.
   - Local run = 3 processes from `source/`: `shopping-assistant api serve`, `shopping-assistant worker`, `npm run web:dev`; Postgres runs as a Windows service.
3. Unscheduled items: see [docs/backlog.md](docs/backlog.md) (auth, multi-user, mobile, push, hosting, blocked retailers).
