# Product Backlog
## Shopping Research Assistant

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-11-20 |
| Related | [user-stories.md](user-stories.md) (v1, done), [sprint-plan.md](sprint-plan.md), [MEMORY.md](../MEMORY.md) |

Items that are agreed but **not scheduled**. When an item is pulled into a sprint, write it as a user story with acceptance criteria, then set its status here to `Scheduled` and link the story.

**Status:** `Backlog` → `Ready` (refined, estimated) → `Scheduled` (in a sprint) → `Done`; `Dropped` if no longer wanted.
**Priority:** MoSCoW (Must / Should / Could), relative to the post-web-app roadmap.

---

## Current direction (context for this backlog)
- **v2 = single-user web app:** Next.js + Tailwind CSS frontend, FastAPI backend wrapping the existing services, Postgres from day one.
- **Built for multi-user from the start:** every table carries `user_id`. The API resolves the current user through a single dependency that returns a seeded default user for now. **No authentication in v2.**
- Everything below is deliberately out of v2 scope.

---

## Summary

| ID | Item | Area | Priority | Status | Depends on |
|---|---|---|---|---|---|
| BL-01 | Authentication | Platform | Must | Backlog | — |
| BL-02 | Multi-user support | Platform | Must | Backlog | BL-01 |
| BL-03 | Per-user usage limits and cost controls | Platform | Should | Backlog | BL-02 |
| BL-04 | Account data export and deletion | Platform | Should | Backlog | BL-02 |
| BL-05 | Native mobile app (iOS + Android) | Mobile | Must | Backlog | BL-01 |
| BL-06 | Mobile push notifications | Notifications | Must | Backlog | BL-05 |
| BL-07 | Browser (web push) notifications | Notifications | Could | Backlog | — |
| BL-08 | Public cloud hosting | Ops | Should | Backlog | BL-01 |
| BL-09 | Retry blocked retailers | Retailers | Could | Backlog | — |
| BL-10 | Live webhook demo | Notifications | Could | Backlog | — |

---

## Items

### BL-01 Authentication
Protect the API and web app with real sign-in.
- Use a hosted auth provider that issues JWTs (e.g. Clerk, Supabase Auth, Auth0); the FastAPI backend verifies tokens.
- Replace the default-user dependency with "user from verified token". No endpoint signatures should change, since endpoints never take a `user_id` from the client.
- Same tokens must work for the web app and the mobile app (BL-05).
- **Why deferred:** v2 is single-user and runs only for the owner.

### BL-02 Multi-user support
Let several people use one deployment.
- Sign-up and onboarding; create a `users` row on first sign-in.
- Audit every query and endpoint for `user_id` scoping, and add tests that one user can never read or change another user's threads, watchlist, history or settings.
- The monitor worker checks all users' active items and sends each alert through that user's own notification settings.
- Remove the seeded default user, or migrate the owner's data onto their real account.

### BL-03 Per-user usage limits and cost controls
Tavily and LLM calls are billed to the owner.
- Per-user limits on research turns and listing lookups per day; per-user cap on watchlist size.
- Clear message in the UI when a limit is reached.

### BL-04 Account data export and deletion
Needed before others use the app, and required by app stores.
- Export a user's threads, watchlist and price history (JSON/CSV).
- Delete an account and all of its data, including LangGraph checkpoints.

### BL-05 Native mobile app (iOS + Android)
- **Expo (React Native) + TypeScript**, one codebase for both platforms, built and submitted with EAS.
- Reuses the shared packages from the web monorepo (`packages/api-client` generated from OpenAPI, `packages/core` hooks and formatting). UI is built natively, not shared with the web app; NativeWind keeps styling close to Tailwind.
- Same screens as the web app: research chat with streamed progress, tracking confirmation, watchlist, price history, settings.
- Retailer links open in the system browser. The app never purchases or adds to cart (BR-10).
- Streaming needs an SSE library such as `react-native-sse`, or polling as a fallback.
- **Why after BL-01:** a phone app needs a publicly reachable, authenticated API.

### BL-06 Mobile push notifications
- New `PushNotifier` channel beside Console, Webhook and Email; same `send(subject, body)` interface, raises `NotificationError` on failure.
- Store Expo push tokens per user and device; remove tokens the push service reports as invalid.
- Tapping an alert opens the item's price history.

### BL-07 Browser (web push) notifications
- Optional alert channel for the web app using the Web Push API and a service worker.

### BL-08 Public cloud hosting
- v2 runs locally (Docker Compose: API, worker, Postgres, web).
- Hosting plan for later: API and monitor worker as Docker containers (Crawl4AI needs Playwright Chromium, so serverless won't work) on Fly.io, Railway, Render or a VM; managed Postgres; Next.js on Vercel.
- Needs HTTPS, secrets management, backups, and exactly one monitor worker instance.

### BL-09 Retry blocked retailers
- Best Buy Canada (Akamai 403) and RONA (DataDome 403) were dropped from v1; Walmart.ca is intermittently blocked (PerimeterX).
- Re-test periodically and look for official APIs or affiliate feeds. **No anti-bot evasion** (retailer ToS, BRD §11).

### BL-10 Live webhook demo
- Optional Sprint 1 leftover: send a real alert to Discord, Slack or Telegram with `WEBHOOK_URL` set. Offline tests already cover the webhook formats.
