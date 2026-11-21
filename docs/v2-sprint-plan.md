# Sprint Plan
## Shopping Research Assistant (v2 — web app)

| Field | Value |
|---|---|
| Version | 1.0 (draft) |
| Date | 2026-11-20 |
| Stories | [v2-user-stories.md](v2-user-stories.md) (US-24…US-43) |
| Backlog | [backlog.md](backlog.md) |
| v1 plan | [sprint-plan.md](sprint-plan.md) |

## Assumptions
- **Team:** one developer working with Claude Code. **Sprint length:** 1 week (Monday–Sunday).
- **Velocity:** 14–19 points per sprint (v1 actual pace was faster; this keeps a buffer).
- **Scope:** 83 points across 20 stories.
- **Runs locally:** PostgreSQL 18 Windows service, plus three local processes (API, worker, web). No Docker.
- **Sequence:** data platform first, then the API, then the web app, so each layer is tested before the next is built on it. The CLI keeps working throughout.
- **Branch:** `add-nextjs-postgres-web-app` (created by the owner). No new branches without the owner's permission.

## Entry criteria (before Sprint 6)
- v1 committed and tagged `v1.0.0`, so there is a clean point to return to.
- Owner approves creating the `shopping_assistant` login and the `shopping_assistant` / `shopping_assistant_test` databases (agreed for the start of coding).

## Timeline

| Sprint | Dates | Theme | Points |
|---|---|---|---|
| 6 | 2026-11-23 → 11-29 | Data platform on Postgres | 18 ✅ (done early, 2026-11-20) |
| 7 | 2026-11-30 → 12-06 | Core API | 19 ✅ (done early, 2026-11-20) |
| 8 | 2026-12-07 → 12-13 | Worker, settings & web shell | 16 ✅ (done early, 2026-11-21) |
| 9 | 2026-12-14 → 12-20 | Research flow in the browser | 14 ✅ (done early, 2026-11-21) |
| 10 | 2026-12-21 → 12-27 | Watchlist, history, settings & release | 16 ✅ (done early, 2026-11-21; tag pending) |
| 11 | 2026-12-28 → 2027-01-03 | Research quality & control (v2.1) | 15 |

**Target v2 release:** 2026-12-27 (tag `v2.0.0`). Sprint 10 falls over the holidays; if it slips, US-27 (Could) moves out first.

---

## Sprint 6 — Data platform on Postgres ✅ (done 2026-11-20)
**Goal:** the CLI runs entirely on local Postgres, with every record owned by a user.

**Result:** all four stories done; 277 tests passing; live demo passed (research → track → restart → resume). Plain SQL migrations chosen over Alembic. See MEMORY.md for details.

| Story | Points |
|---|---|
| US-24 Store app data in Postgres | 8 |
| US-26 Data model ready for multiple users | 5 |
| US-25 Keep conversations in Postgres | 3 |
| US-28 Database setup in one step | 2 |
| **Total** | **18** |

**Technical tasks**
- Create the `shopping_assistant` login and the app and test databases; switch `.env` to the new login.
- Add `psycopg` 3 (+ `psycopg-pool`) and `langgraph-checkpoint-postgres`.
- Replace `database.py`'s `db_path` functions with a repository that takes a connection and `user_id`. Keep function names close to v1 so callers change little.
- Numbered SQL migration files plus a `schema_migrations` table (decide plain SQL vs Alembic at sprint start; plain SQL matches the "no ORM" decision).
- `users` table and the default `admin` user; `user_id` on owned tables; per-user unique URL.
- Test fixtures: a fresh schema per test run on `TEST_DATABASE_URL`; skip DB tests if unreachable.
- Update CLAUDE.md tech stack (SQLite → Postgres) and the FRD data model.

**Demo:** run the CLI end to end (research → confirm → watchlist → check → alert) on Postgres; restart and resume the thread.

---

## Sprint 7 — Core API ✅ (done 2026-11-20)
**Goal:** everything the CLI can do in a conversation and on the watchlist is available over a documented HTTP API.

**Result:** all four stories done; 308 tests passing; live demo over curl passed (streamed research, listing lookup, invalid choice rejected, confirm two listings, pause and retarget). The npm workspace and generated TypeScript client were set up here (planned for Sprint 8) because US-33 needs them.

| Story | Points |
|---|---|
| US-33 A clean, typed API contract | 3 |
| US-29 Research chat over the API, with live progress | 8 |
| US-30 Confirm or cancel tracking over the API | 3 |
| US-31 Manage the watchlist over the API | 5 |
| **Total** | **19** |

**Technical tasks**
- FastAPI app in `source/shopping_assistant/api/` with `uvicorn`; `current_user` dependency returning the default user.
- SSE endpoint bridging `ResearchSession.send`'s `on_progress` callback to the event stream (the session is synchronous, so run it in a worker thread).
- Map watchlist and history responses to Pydantic response models (reuse `models.py` where it fits).
- Common error handler and error schema; CORS for `http://localhost:3000`; bind to `127.0.0.1`.
- Export `openapi.json`; tests with FastAPI `TestClient` and the existing fakes (no network).

**Demo:** from the interactive API docs, research a product with streamed progress, confirm two listings, then pause and retarget one.

---

## Sprint 8 — Worker, settings & web shell ✅ (done 2026-11-21)
**Goal:** checks run in the background without the CLI, alerts use saved settings, and the web app skeleton talks to the API.

**Result:** all four stories done; 342 tests passing; web lint, type-check and build pass; live demo passed (worker checked on start and reported its next run, API check started and a second one refused, settings saved with the webhook masked, test alert, API-down banner at phone and desktop width). At the owner's request all code now lives under `source/`, so the npm workspace is `source/package.json` with `source/apps/web` and `source/packages/api-client`.

| Story | Points |
|---|---|
| US-34 Price checks keep running in the background | 5 |
| US-35 Notification settings in the app | 5 |
| US-32 Run a price check from the API | 3 |
| US-36 Web app shell | 3 |
| **Total** | **16** |

**Technical tasks**
- Worker entry point (`shopping-assistant worker`) using APScheduler; Postgres advisory lock shared by worker, API and CLI checks; `monitor_runs` table.
- Notifier factory reads per-user settings, falling back to `.env`.
- npm workspaces in `source/`: `apps/web` (Next.js, TypeScript, Tailwind CSS, ESLint) and `packages/api-client` (generated from `openapi.json`).
- API base URL in one web setting; "API unreachable" banner.

**Demo:** start API, worker and web app; the worker runs a check on start; the web shell shows navigation and the API status.

---

## Sprint 9 — Research flow in the browser ✅ (done 2026-11-21)
**Goal:** research, finalize and start tracking a product entirely in the browser.

**Result:** all three stories done; 344 Python tests and 20 web component tests (Vitest + Testing Library) passing; lint, type-check and build pass. Live demo in a real browser: three turns on headphones, option 2 chosen by button, the pending form survived a reload, two listings confirmed and visible on the API's watchlist.

| Story | Points |
|---|---|
| US-37 Research chat in the browser | 8 |
| US-38 Confirm tracking in the browser | 5 |
| US-42 The web app never buys anything | 1 |
| **Total** | **14** |

**Technical tasks**
- SSE client for streamed turns; comparison cards; thread list.
- Tracking confirmation form with validation; pending-confirmation recovery on reload.
- Component tests for the cards and form with a mocked API client.

**Demo:** research headphones over three turns in the browser, choose option 2 by button, confirm two listings, and see them on the API's watchlist.

---

## Sprint 10 — Watchlist, history, settings & release ✅ (done 2026-11-21; `v2.0.0` tag waits for the owner's commit)
**Goal:** a complete, documented v2 web app.

**Result:** all five stories done; 354 Python tests and 46 web component tests passing; lint, type-check and build pass. Chart: hand-built SVG (no chart library). Fresh-copy walkthrough (the files a clone would contain, into a new folder, following the README): install, migrate, build, start API + worker + web, research and track a USB-C charger in the browser, then the worker's start-up check sent a background "target reached" alert.

| Story | Points |
|---|---|
| US-39 Watchlist page | 5 |
| US-40 Price history chart | 3 |
| US-41 Notification settings page | 3 |
| US-27 Bring my v1 data across | 3 |
| US-43 Run the whole app locally | 2 |
| **Total** | **16** |

**Technical tasks and hardening**
- Watchlist page with inline actions and "Check now" polling the check status.
- History chart (choose the chart library at sprint start).
- `shopping-assistant db import-v1` for `watchlist.db`.
- README for v2; live end-to-end run on real retailers; update BRD scope (web UI was out of scope in v1) and FRD.
- Buffer for bugs carried over.

**Demo / release:** fresh-clone walkthrough from the README, full flow in the browser, background alert received. Tag `v2.0.0`.

---

## Sprint 11 — Research quality & control (v2.1)
**Dates:** 2026-12-28 → 2027-01-03 (or as soon as the owner starts it). **Points:** 15.
**Entry criteria:** v2 committed and tagged `v2.0.0`.
**Goal:** comparisons say where prices came from and which option to pick; the owner sees community deals and controls which retailers are used.

| Story | Points |
|---|---|
| US-44 See where each price came from (incl. currency and product-name fixes) | 3 |
| US-45 Quick Verdict | 2 |
| US-47 Choose which retailers the assistant checks | 5 |
| US-46 Community deals from RedFlagDeals | 5 |
| **Total** | **15** |

**Technical tasks**
- Spike first (half a day): how well the search service covers RedFlagDeals threads (recency, dates, titles with price and store) for 3–4 real products. If coverage is poor, US-46 shrinks to "link to an RFD search for this product" and the rest moves to the backlog.
- `ResearchComparison`: per candidate `price_source_url` (+ derived site), optional price; comparison-level `quick_verdict` and `top_pick` (option number). After the AI call, drop any price whose source isn't among the search results, and any top pick that isn't a listed option. Old checkpoints load with the new fields empty.
- Research prompt: clean product names (brand + model only), verdict rules (≤ 2 sentences, tie to stated needs, say what's missing instead of guessing). `render_comparison` (CLI) updated.
- Web: always format prices with an explicit currency (`CA$`, `US$`), "Not CAD" badge, "Price seen" line, Quick Verdict box, "Top pick" marker, "Searched" list.
- Deals: `search.find_deals(product)` (search limited to redflagdeals.com, recent results, matched with `matches_model`), a `CommunityDeal` model, run beside the listing lookup; carried on the listings message and the confirmation payload; web panel and CLI lines.
- Retailers: migration `0004` (per-user retailer choices; absent = enabled), `UserStore` methods, `TrackingDeps` gets the enabled domains, `GET/PUT /settings/retailers` (catalog with names, enabled, selectable, reason), Settings section, watchlist note for items at a turned-off retailer.
- Regenerate `openapi.json` and the client; component tests for the new card parts, deals panel and retailer switches; Python tests with fakes.

**Demo:** research a product in the browser; read the Quick Verdict and each card's price source; turn off two retailers in Settings; choose a product and see listings only from the enabled ones, plus the community deals panel.

**Risks:** the AI cites a page that doesn't contain the price (mitigation: only search-result URLs are accepted, and the label says "estimate"); RedFlagDeals coverage in search is thin or stale (spike first); deal posts are noisy (model matching, cap of 5).

---

## Definition of Ready
- The story has acceptance criteria and traces to a v1 story, decision or backlog item.
- Dependencies from earlier sprints are done.
- The story is estimated.

## Definition of Done
Everything in the v1 Definition of Done, plus:
- `pytest` passes; database tests run against the local test database and nothing else needs network.
- New repository functions take a `user_id` and have a cross-user isolation test.
- New endpoints have `TestClient` tests, appear in `openapi.json`, and the TypeScript client is regenerated.
- Web: lint, type-check and production build pass; pages work at phone width and in light and dark themes.
- No secrets in the web app or API responses; `.env.example`, README and `MEMORY.md` are updated.

## Risks to the plan

| Risk | Sprint | Mitigation |
|---|---|---|
| Moving every query from SQLite to Postgres breaks v1 behaviour | 6 | Keep the v1 test suite green throughout; port tests before code |
| `PostgresSaver` behaves differently from `SqliteSaver` (interrupts, resume) | 6 | Test resume with a pending confirmation early in the sprint |
| Synchronous research session blocks the API | 7 | Run each turn in a worker thread; one turn per thread at a time |
| Two processes run checks at once (worker + CLI) | 8 | Postgres advisory lock (US-34) |
| Holidays reduce Sprint 10 capacity | 10 | US-27 is the first to drop; release date can move one week |
| Scope creep into auth, multi-user or mobile | All | Log it in [backlog.md](backlog.md) instead |

## Ceremonies (lightweight, solo)
As in v1: planning on Monday, tick tasks off in `MEMORY.md` daily, review and retro on Sunday with the sprint demo.
