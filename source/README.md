# Shopping Research Assistant

Helps you research and pick the best product for a need, then tracks its price at Canadian retailers and alerts you when it drops. Use it in the browser (web app) or in a terminal (CLI); both share the same data.

> **It never buys anything, never handles payment details, and never adds items to a cart.** Ask it to buy something and it declines and offers to track the price instead. Retailer links open the product page in a new tab.

Requirements and plans: [BRD](../docs/BRD.md), [FRD](../docs/FRD.md), [user stories](../docs/user-stories.md), [sprint plan](../docs/sprint-plan.md), [v2 stories](../docs/v2-user-stories.md), [v2 sprint plan](../docs/v2-sprint-plan.md), [backlog](../docs/backlog.md).

## How it runs
Everything runs on your own computer. There is no sign-in, so the API only accepts connections from this machine.

| Part | What it does | Start command (from `source/`) |
|---|---|---|
| PostgreSQL | Stores your watchlist, price history, conversations and settings | Runs as a Windows service |
| API | The assistant itself, used by the web app | `.venv\Scripts\shopping-assistant api serve` |
| Worker | Checks prices every 6 hours and sends alerts | `.venv\Scripts\shopping-assistant worker` |
| Web app | What you use in the browser | `npm run web:start` (or `npm run web:dev` while developing) |

## Set up and start (Windows PowerShell)
You need **Python 3.11+** (tested on 3.14), **Node.js 20.9+** (tested on 24), **PostgreSQL** (tested on 18) and **Git**.

### 1. Get the code and the Python parts
```powershell
git clone <repository-url> shopping-research-assistant
cd shopping-research-assistant\source        # every command below runs from here
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\crawl4ai-setup                 # installs the browser used to read retailer prices
# if crawl4ai-setup fails:  .venv\Scripts\python -m playwright install chromium
```

### 2. Create the database
Create a login for the app and two databases: one for the app and one for the tests. You'll be asked for the `postgres` superuser password you chose when installing PostgreSQL.

```powershell
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"   # adjust the version folder if needed
& $psql -h localhost -U postgres -c "CREATE ROLE shopping_assistant LOGIN PASSWORD 'choose-a-strong-password'"
& $psql -h localhost -U postgres -c "CREATE DATABASE shopping_assistant OWNER shopping_assistant"
& $psql -h localhost -U postgres -c "CREATE DATABASE shopping_assistant_test OWNER shopping_assistant"
& $psql -h localhost -U postgres -c "REVOKE ALL ON DATABASE shopping_assistant, shopping_assistant_test FROM PUBLIC"
```

### 3. Settings and keys
```powershell
Copy-Item .env.example .env
notepad .env
```
Fill in at least:
- `ANTHROPIC_API_KEY`: create one at https://platform.claude.com under Settings → API Keys, and add credits under Billing.
- `TAVILY_API_KEY`: from https://tavily.com. The free plan's monthly credits are enough for personal use.
- `DATABASE_URL` and `TEST_DATABASE_URL`: put the password from step 2 in both.

Then create the tables:
```powershell
.venv\Scripts\shopping-assistant db migrate    # safe to run again; applies only what's new
```

Used v1 before? Bring your watchlist across (optional, safe to run twice):
```powershell
.venv\Scripts\shopping-assistant db import-v1             # reads data\watchlist.db; or pass its path
```
It imports every tracked item with its full price history, targets, status and last alert. Items already on your watchlist are skipped. Old research conversations are **not** imported.

### 4. Install and build the web app
```powershell
npm install
npm run web:build
```

### 5. Start everything
Open three PowerShell windows in the `source` folder and run one command in each. Leave them running.

```powershell
.venv\Scripts\shopping-assistant api serve     # window 1: the API on http://127.0.0.1:8000
.venv\Scripts\shopping-assistant worker        # window 2: scheduled price checks and alerts
npm run web:start                              # window 3: the web app
```

Then open **http://localhost:3000**. To stop, press Ctrl+C in each window (the worker finishes a check in progress first).

If the web app shows "Can't reach the assistant's API", window 1 isn't running. A line under the top bar shows the last and next price check, or says the worker isn't running.

## Using the web app
- **Research**: describe what you need (budget, use, must-haves). You get 3–4 options as cards with pros, cons and estimated CAD prices from independent reviews. Ask follow-ups or refine, then press **Choose this** (or type "option 2"). The assistant finds Canadian listings and checks each price on the product page; tick the ones to track and set your target (pre-filled at 10% below the cheapest). Conversations are listed on the left and can be picked up later.
- **Watchlist**: every tracked item with its latest price, lowest seen, target, status and last check. Items whose checks keep failing are flagged. Pause/resume, edit the target, delete, open the **price history** chart and table, or press **Check now**.
- **Settings**: choose where alerts go (console, webhook or email), save, and **Send test alert**. Your webhook URL is only ever shown masked. Email needs a sender set up in `.env` (see Configuration).

### When do alerts fire?
When an item is **in stock** and its price **reaches your target** or **drops to a new low**. You won't be alerted twice at the same price; it alerts again only if the price falls further. If an alert can't be delivered, it's retried at the next check. Only one price check runs at a time across the worker, the web app and the CLI: a check started while another is running is skipped (the web app shows the running one instead).

### Supported retailers
Amazon.ca, Walmart.ca, Staples.ca, Costco.ca, Dell Canada (dell.com/en-ca), Newegg.ca, Canada Computers, Canadian Tire, plus official brand stores.

Best Buy Canada and RONA are **not supported**: they block automated price checks. Walmart sometimes blocks checks too. A failed check changes nothing and is retried next time; repeated failures show as a warning on the watchlist.

## Configuration
Edit `source/.env`. Restart the API and the worker after changes.

| Key | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | Claude access and model (default `claude-sonnet-5-5`) |
| `TAVILY_API_KEY` | Product research and retailer lookup |
| `NOTIFIER`, `WEBHOOK_URL` | Default alert channel (`console`, `webhook` or `email`) and webhook. A channel saved on the Settings page takes precedence. For Telegram use `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>` |
| `RESEND_API_KEY` or `SMTP_*`, plus `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | Email alerts (Resend is used if its key is set). These stay in `.env`; the Settings page only chooses the address alerts go to |
| `DATABASE_URL` | The app database, e.g. `postgresql://shopping_assistant:<password>@localhost:5432/shopping_assistant` |
| `TEST_DATABASE_URL` | The test database; its name must end in `_test` (the tests empty its tables) |
| `API_PORT`, `WEB_ORIGINS` | API port (default 8000) and the browser addresses allowed to call it (default `http://localhost:3000`) |
| `CHECK_INTERVAL_HOURS` | How often the worker checks prices (default 6) |
| `DEFAULT_TARGET_DISCOUNT` | Suggested target below the current price (default 0.10, i.e. 10%) |
| `DATA_DIR` | Folder of the v1 `watchlist.db`, used only by `db import-v1` (default `./data`) |

The web app has one setting: if the API runs somewhere other than `http://127.0.0.1:8000`, put `NEXT_PUBLIC_API_BASE_URL=<address>` in `apps/web/.env.local` and rebuild (`npm run web:build`).

## The CLI
The terminal version works alongside the web app, on the same data:
```powershell
.venv\Scripts\shopping-assistant
```

| Option | What it does |
|---|---|
| **1. Research** | The research chat. Pick an option by number or name, then choose listings (e.g. `1,3` or `all`) and a target (Enter accepts the suggestion). |
| **2. Watchlist** | `p 3` pause, `r 3` resume, `t 3 399.99` change target, `h 3` price history, `d 3` delete, `b` back. |
| **3. Check now** | Check every active item once and show a summary. |
| **4. Background monitor** | Check now and then every `CHECK_INTERVAL_HOURS` until you press Enter (only while the window is open; the worker does this without the menu). |

Other commands: `db migrate`, `db status`, `db import-v1 [PATH]`, `api serve`, `api openapi [PATH]`, `worker`.

## Troubleshooting
- **"Setup needed: Missing required configuration: X"**: add key `X` to `.env`.
- **"Can't connect to the database at …"**: check that the PostgreSQL service is running (`Get-Service postgresql*`) and that the login, password and database name in `DATABASE_URL` are right.
- **"The database isn't set up yet"**: run `.venv\Scripts\shopping-assistant db migrate`.
- **Web app says it can't reach the API**: start `shopping-assistant api serve`, then press **Try again**. If you changed `API_PORT`, set `NEXT_PUBLIC_API_BASE_URL` (see Configuration).
- **"Background checks are off"**: start `shopping-assistant worker`.
- **"A price check is already running"**: another check (worker, web app or CLI) is in progress; wait for it. If a process was killed mid-check, the lock is released automatically and the next check marks the old run as interrupted.
- **A price check failed**: the retailer blocked or timed out the page. It's retried next check; if it keeps failing, consider pausing that item.
- **Test alert fails**: the message says why (e.g. a wrong webhook URL). Fix it on the Settings page and send another.
- **Browser errors during price checks**: re-run `.venv\Scripts\crawl4ai-setup`.
- **Port 3000 or 8000 already in use**: stop the other program, or change `API_PORT` / run the web app with `npm run web:start -- -p 3001` (then add that address to `WEB_ORIGINS`).
- **`pip install` fails with "No such file or directory" on a very long path**: Windows limits paths to 260 characters. Clone into a short folder (e.g. `C:\dev\shopping-research-assistant`) or enable long paths (`LongPathsEnabled` in the registry, as administrator).
- **Start over**: drop and recreate the `shopping_assistant` database (as `postgres`), then run `db migrate`. This removes your watchlist, conversations and settings.

macOS/Linux: use `python3 -m venv .venv`, `.venv/bin/...`, and your system's way of running PostgreSQL.

## For developers
```powershell
.venv\Scripts\pytest           # Python tests
npm run web:check              # web: lint, type-check and component tests
npm run web:dev                # web app with live reload on http://localhost:3000
```
Search, AI, scraping and notifications are faked, so tests never use the internet. Python database tests use the local test database in `TEST_DATABASE_URL` and empty its tables first; if it can't be reached they're skipped with the reason. Web tests run in a simulated browser with the API mocked.

After changing the API, regenerate the spec and the typed client:
```powershell
.venv\Scripts\shopping-assistant api openapi    # writes packages/api-client/openapi.json
npm run api:generate                            # regenerates packages/api-client/src/schema.ts
```
API reference: run the API and open http://127.0.0.1:8000/docs.
