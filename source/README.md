# Shopping Research Assistant

A conversational CLI assistant that helps you research and pick the best product for a need, then tracks its price at Canadian retailers and alerts you when it drops.

> **It never buys anything, never handles payment details, and never adds items to a cart.**

See [../docs/BRD.md](../docs/BRD.md) and [../docs/FRD.md](../docs/FRD.md) for requirements.

## Setup (Windows PowerShell, from this `source/` folder)

```powershell
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\crawl4ai-setup                 # installs Playwright + Chromium
# if crawl4ai-setup fails:
.venv\Scripts\python -m playwright install chromium
Copy-Item .env.example .env                  # then fill in your keys
```

macOS/Linux: use `python3 -m venv .venv` and `.venv/bin/...`.

## Configuration
Edit `.env`:

| Key | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | Claude access and model |
| `TAVILY_API_KEY` | Product research and retailer lookup |
| `NOTIFIER` | `console`, `webhook`, or `email` |
| `WEBHOOK_URL` | Discord / Slack / Telegram webhook |
| `RESEND_API_KEY` or `SMTP_*`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | Email alerts |
| `DATA_DIR` | Where `watchlist.db` and `checkpoints.db` live (default `./data`) |
| `CHECK_INTERVAL_HOURS` | Background check cadence (default 6) |

## Usage
```powershell
.venv\Scripts\shopping-assistant
```
Menu:
1. Start / continue product research
2. View / manage watchlist
3. Run price check now
4. Start background monitor
0. Quit

Background checks only run while the CLI is running.

## Tests
```powershell
.venv\Scripts\pytest
```
