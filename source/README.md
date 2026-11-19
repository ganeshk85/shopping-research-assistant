# Shopping Research Assistant

A conversational CLI assistant that helps you research and pick the best product for a need, then tracks its price at Canadian retailers and alerts you when it drops.

> **It never buys anything, never handles payment details, and never adds items to a cart.** Ask it to buy something and it declines and offers to track the price instead.

Requirements and plans: [BRD](../docs/BRD.md), [FRD](../docs/FRD.md), [user stories](../docs/user-stories.md), [sprint plan](../docs/sprint-plan.md).

## Setup (Windows PowerShell, from this `source/` folder)

```powershell
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\crawl4ai-setup                 # installs Playwright + Chromium
# if crawl4ai-setup fails:
.venv\Scripts\python -m playwright install chromium
Copy-Item .env.example .env                  # then fill in your keys
```

macOS/Linux: use `python3 -m venv .venv` and `.venv/bin/...`. Tested on Python 3.14; requires 3.11+.

You need two API keys:
- **Anthropic** (research and alert wording): create one at https://platform.claude.com under Settings → API Keys, and add credits under Billing.
- **Tavily** (web search): https://tavily.com. The free plan's monthly credits are enough for personal use.

## Configuration
Edit `.env`:

| Key | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | Claude access and model (default `claude-sonnet-5-5`) |
| `TAVILY_API_KEY` | Product research and retailer lookup |
| `NOTIFIER` | `console` (default), `webhook`, or `email` |
| `WEBHOOK_URL` | Discord or Slack webhook URL; for Telegram use `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>` |
| `RESEND_API_KEY` or `SMTP_*`, plus `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | Email alerts (Resend is used if its key is set) |
| `DATA_DIR` | Where `watchlist.db` and `checkpoints.db` live (default `./data`) |
| `CHECK_INTERVAL_HOURS` | Background check interval (default 6) |
| `DEFAULT_TARGET_DISCOUNT` | Suggested target below the current price (default 0.10, i.e. 10%) |

## Usage
```powershell
.venv\Scripts\shopping-assistant
```

| Option | What it does |
|---|---|
| **1. Research** | Describe what you need. You get 3-4 options with pros, cons and estimated CAD prices, based on independent reviews. Ask follow-up questions or refine your needs, then pick one by number or name. The assistant then finds Canadian listings, checks each price on the product page, and asks which to track and at what target price (Enter accepts 10% below the cheapest). Conversations are saved; pick one up later from this option. |
| **2. Watchlist** | See every tracked item: latest price, lowest seen, target, and when it was last checked. Items whose checks keep failing are flagged. Commands: `p 3` pause, `r 3` resume, `t 3 399.99` change target, `h 3` price history, `d 3` delete, `b` back. |
| **3. Check now** | Check every active item once and show a summary. Alerts are sent through your `NOTIFIER`. |
| **4. Background monitor** | Check now and then every `CHECK_INTERVAL_HOURS` until you press Enter. **Checks only run while this window is open.** |

### When do alerts fire?
When an item is **in stock** and its price **reaches your target** or **drops to a new low**. You won't be alerted twice at the same price; it alerts again only if the price falls further. If an alert can't be delivered, it's retried at the next check.

### Supported retailers (v1)
Amazon.ca, Walmart.ca, Staples.ca, Costco.ca, Dell Canada (dell.com/en-ca), Newegg.ca, Canada Computers, Canadian Tire, plus official brand stores.

Best Buy Canada and RONA are **not supported**: they block automated price checks. Walmart sometimes blocks checks too. A failed check changes nothing and is retried next time; repeated failures show as a warning in the watchlist.

## Troubleshooting
- **"Setup needed: Missing required configuration: X"**: add key `X` to `.env`.
- **A price check failed**: the retailer blocked or timed out the page. It's retried next check; if it keeps failing, consider pausing that item (`p <#>`).
- **Browser errors**: re-run `.venv\Scripts\crawl4ai-setup`.
- **Start over**: delete the `data` folder. This removes your watchlist and saved conversations.

## Tests
```powershell
.venv\Scripts\pytest
```
All tests run offline; search, AI, scraping and notifications are faked.
