# CLAUDE.md — Shopping Research Assistant

Conversational shopping assistant that helps a user research and finalize the best product for a need, then tracks its price at Canadian retailers and alerts on price drops.

**Hard rule:** the agent must NEVER execute purchases, handle payment details, or add items to shopping carts. Do not write code that does any of these.

## Key documents
- [docs/project-proposal.md](docs/project-proposal.md) — original specification
- [docs/BRD.md](docs/BRD.md) — business requirements
- [docs/FRD.md](docs/FRD.md) — functional requirements (authoritative where it corrects the proposal)
- [docs/user-stories.md](docs/user-stories.md): user stories US-01…US-23 with acceptance criteria
- [docs/sprint-plan.md](docs/sprint-plan.md): sprints 0–5, Definition of Done
- [docs/v2-user-stories.md](docs/v2-user-stories.md) and [docs/v2-sprint-plan.md](docs/v2-sprint-plan.md): v2 web app, US-24…US-43, sprints 6–10
- [docs/backlog.md](docs/backlog.md): unscheduled items BL-01… (auth, multi-user, mobile, hosting)
- [MEMORY.md](MEMORY.md) — living plan, build progress, and decisions log. **Read it at the start of every session.**

## Tech stack
| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Orchestration | `langgraph` with `PostgresSaver` checkpointing (`langgraph-checkpoint-postgres`) |
| LLM | `langchain` + `langchain-anthropic` (latest Claude model, configurable via `LLM_MODEL`) |
| Schemas | `pydantic` v2 |
| Graph 1 search | `tavily-python` (product/review discovery, retail listing lookup) |
| Graph 2 scraping | `crawl4ai` (`AsyncWebCrawler`; schema.org JSON-LD first, CSS/regex fallback) |
| Database | Local PostgreSQL 18 via `psycopg` 3 + `psycopg-pool` (no ORM); numbered SQL migrations in `shopping_assistant/migrations/` |
| Scheduler | `APScheduler` 3.x (default every 6 hours), run by the `shopping-assistant worker` process; one check at a time per user via a Postgres advisory lock (`checks.py`) |
| Notifications | Console, Webhook (Discord/Slack/Telegram), Email (Resend/SMTP); per-user channel saved in the DB, falling back to `.env` |
| Interface | Interactive CLI, plus the HTTP API (`fastapi` + `uvicorn`, `/api/v1`, SSE for chat turns) for the web app; both decoupled from graphs |
| Web app | `apps/web`: Next.js 16 (App Router, TypeScript), Tailwind CSS 4, ESLint |
| API client | `packages/api-client` (npm workspaces): `openapi-typescript` types + `openapi-fetch`, generated from `openapi.json` |
| Tests | `pytest`, `pytest-asyncio`, FastAPI `TestClient`; web: Vitest + Testing Library (jsdom, `@/lib/api` mocked) |

## Layout
**All code lives under `source/`.** The repo root holds only docs, this file and `MEMORY.md`.
```
source/
├── pyproject.toml, .env.example, README.md       # Python project
├── shopping_assistant/
│   ├── config.py      # settings from .env
│   ├── models.py      # Pydantic schemas + LangGraph state TypedDicts
│   ├── database.py    # Postgres pool, migrations, per-user repository (UserStore)
│   ├── migrations/    # NNNN_name.sql, applied by `shopping-assistant db migrate`
│   ├── tools/         # search.py (Tavily), scraper.py (Crawl4AI), notifier.py
│   ├── graphs/        # research_graph.py (Graph 1), monitor_graph.py (Graph 2)
│   ├── checks.py      # price-check runs: lock + record (used by worker, API, CLI)
│   ├── worker.py      # background price-check worker
│   ├── v1_import.py   # `db import-v1`: v1 SQLite watchlist -> Postgres
│   ├── api/           # FastAPI app: schemas (contract), deps (current user), routes_*, errors
│   └── main.py        # CLI entry point (+ `db`, `api` and `worker` subcommands)
├── tests/
├── package.json, package-lock.json               # npm workspaces root
├── packages/api-client/   # generated typed client (openapi.json -> src/schema.ts)
└── apps/web/              # Next.js web app
```

## Commands (run from `source/`)
```powershell
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\crawl4ai-setup          # installs Playwright Chromium
.venv\Scripts\shopping-assistant db migrate   # create/upgrade the Postgres schema
.venv\Scripts\pytest                   # run tests
.venv\Scripts\shopping-assistant       # run the CLI
.venv\Scripts\shopping-assistant api serve     # run the API on 127.0.0.1:8000 (/docs)
.venv\Scripts\shopping-assistant worker        # run scheduled price checks
.venv\Scripts\shopping-assistant api openapi   # after API changes; then: npm run api:generate
npm install                            # web app + API client
npm run web:dev                        # web app on http://localhost:3000
npm run web:check                      # lint + type-check (web and api-client) + Vitest component tests
npm run web:build                      # production build; npm run web:start serves it
.venv\Scripts\shopping-assistant db import-v1  # one-time import of a v1 data\watchlist.db
```

## Repo rules
1. **Monitor path stays deterministic.** Graph 2 scraping and drop evaluation must not call an LLM; only `generate_and_send_alert` may.
2. **Secrets only in `.env`** (gitignored). Keep `.env.example` in sync when adding settings. Never commit keys or `*.db` files.
3. **No network in unit tests.** Mock Tavily, Crawl4AI, LLM and notifier calls. Database tests use the local `TEST_DATABASE_URL` (via the `store` / `pg_database` fixtures) and skip if it's unreachable.
4. **CLI is a thin layer.** Graphs and tools must not import from `main.py` or use `input()`/`print()` for business logic, so a web UI/API can be attached later.
5. **Typed boundaries.** Type hints everywhere; Pydantic models for data crossing module boundaries.
6. **Currency defaults to CAD.** Prices are stored as `DOUBLE PRECISION` in the listing currency.
7. **Follow the build order** in MEMORY.md; one step at a time.
8. **Update MEMORY.md** after completing a step or making a design decision.
9. **Git:** commit only when the user asks. Never create a branch without the user's permission.
10. **Every owned row has a `user_id`.** Data access goes through `UserStore` (scoped to one user); never accept a `user_id` from a client.
