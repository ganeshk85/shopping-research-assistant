# CLAUDE.md — Shopping Research Assistant

Conversational shopping assistant that helps a user research and finalize the best product for a need, then tracks its price at Canadian retailers and alerts on price drops.

**Hard rule:** the agent must NEVER execute purchases, handle payment details, or add items to shopping carts. Do not write code that does any of these.

## Key documents
- [docs/project-proposal.md](docs/project-proposal.md) — original specification
- [docs/BRD.md](docs/BRD.md) — business requirements
- [docs/FRD.md](docs/FRD.md) — functional requirements (authoritative where it corrects the proposal)
- [docs/user-stories.md](docs/user-stories.md): user stories US-01…US-23 with acceptance criteria
- [docs/sprint-plan.md](docs/sprint-plan.md): sprints 0–5, Definition of Done
- [MEMORY.md](MEMORY.md) — living plan, build progress, and decisions log. **Read it at the start of every session.**

## Tech stack
| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Orchestration | `langgraph` with `SqliteSaver` checkpointing (`langgraph-checkpoint-sqlite`) |
| LLM | `langchain` + `langchain-anthropic` (latest Claude model, configurable via `LLM_MODEL`) |
| Schemas | `pydantic` v2 |
| Graph 1 search | `tavily-python` (product/review discovery, retail listing lookup) |
| Graph 2 scraping | `crawl4ai` (`AsyncWebCrawler`; schema.org JSON-LD first, CSS/regex fallback) |
| Database | SQLite via stdlib `sqlite3` |
| Scheduler | `APScheduler` 3.x (default every 6 hours) |
| Notifications | Console, Webhook (Discord/Slack/Telegram), Email (Resend/SMTP) |
| Interface | Interactive CLI, decoupled from graphs |
| Tests | `pytest`, `pytest-asyncio` |

## Layout
All Python code lives under `source/` (the Python project root):
```
source/
├── pyproject.toml
├── .env.example
├── README.md
├── shopping_assistant/
│   ├── config.py      # settings from .env
│   ├── models.py      # Pydantic schemas + LangGraph state TypedDicts
│   ├── database.py    # SQLite schema + CRUD
│   ├── tools/         # search.py (Tavily), scraper.py (Crawl4AI), notifier.py
│   ├── graphs/        # research_graph.py (Graph 1), monitor_graph.py (Graph 2)
│   └── main.py        # CLI entry point
└── tests/
```

## Commands (run from `source/`)
```powershell
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\crawl4ai-setup          # installs Playwright Chromium
.venv\Scripts\pytest                   # run tests
.venv\Scripts\shopping-assistant       # run the CLI
```

## Repo rules
1. **Monitor path stays deterministic.** Graph 2 scraping and drop evaluation must not call an LLM; only `generate_and_send_alert` may.
2. **Secrets only in `.env`** (gitignored). Keep `.env.example` in sync when adding settings. Never commit keys or `*.db` files.
3. **No network in unit tests.** Mock Tavily, Crawl4AI, LLM and notifier calls.
4. **CLI is a thin layer.** Graphs and tools must not import from `main.py` or use `input()`/`print()` for business logic, so a web UI/API can be attached later.
5. **Typed boundaries.** Type hints everywhere; Pydantic models for data crossing module boundaries.
6. **Currency defaults to CAD.** Prices are stored as `REAL` in the listing currency.
7. **Follow the build order** in MEMORY.md; one step at a time.
8. **Update MEMORY.md** after completing a step or making a design decision.
9. **Git:** commit only when the user asks; branch first if on `main`.
