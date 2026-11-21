"""CLI entry point: a thin layer over ResearchSession, PriceMonitor and the watchlist.

    shopping-assistant              interactive menu
    shopping-assistant db migrate   create or upgrade the database schema (US-28)
    shopping-assistant db status    show applied and pending migrations
    shopping-assistant db import-v1 [PATH]  bring a v1 watchlist.db across (US-27)
    shopping-assistant api serve    run the HTTP API for the web app (127.0.0.1:API_PORT)
    shopping-assistant api openapi  write the OpenAPI spec for the TypeScript client
    shopping-assistant worker       run scheduled price checks in the background (US-34)
"""

from __future__ import annotations

import logging
import os
import sys

from .config import ConfigError, load_settings
from .database import describe_url, get_database, open_store

USAGE = (
    "Usage: shopping-assistant [db migrate | db status | db import-v1 [PATH] | api serve | api openapi [PATH] | worker]"
)

MENU = """
Shopping Research Assistant
  1. Start / continue product research (and set up price tracking)
  2. View / manage watchlist
  3. Run price check now
  4. Start background monitor (checks every {hours}h while running)
  0. Quit
"""

CHAT_HELP = "Type your message. Commands: /exit returns to the menu."


def _prompt(text: str) -> str:
    try:
        return input(text)
    except EOFError:
        return "0"


def _choose_thread(session) -> str | None:
    threads = session.list_threads(limit=10)
    if not threads:
        return session.new_thread_id()
    print("\n  n. New research")
    for i, t in enumerate(threads, start=1):
        done = f"  [chose: {t['finalized_product']}]" if t.get("finalized_product") else ""
        print(f"  {i}. {t['title']}{done}  ({t['updated_at'].astimezone().strftime('%Y-%m-%d %H:%M')})")
    choice = _prompt("Pick a conversation (n for new, Enter to cancel): ").strip().lower()
    if choice in ("", "q"):
        return None
    if choice == "n":
        return session.new_thread_id()
    if choice.isdigit() and 1 <= int(choice) <= len(threads):
        thread_id = threads[int(choice) - 1]["thread_id"]
        for role, text in session.history(thread_id)[-4:]:
            print(f"\n{'You' if role == 'user' else 'Assistant'}: {text}")
        return thread_id
    print("Not a valid choice.")
    return None


# Printed when a graph node FINISHES (stream_mode="updates"), so name what comes next.
PROGRESS = {
    "finalize_product": "(finding Canadian retailer listings and checking prices; this can take a minute...)",
}


def _progress(node: str) -> None:
    msg = PROGRESS.get(node)
    if msg:
        print(msg, flush=True)


def _ask_tracking(session, thread_id: str, pending: dict):
    """FR-4 prompts: which listings, which target price. Returns the confirm() turn."""
    from .models import TrackingDecision
    from .tracking import default_target_price, parse_selection, parse_target

    listings = pending["listings"]
    while True:
        answer = _prompt(
            "\nWhich listings should I track? (e.g. 1,3 or 'all'; 'c' to cancel): "
        )
        decision = parse_selection(answer, len(listings))
        if isinstance(decision, TrackingDecision):
            break
        print(decision)

    if decision.action == "track":
        chosen = [listings[n - 1]["current_price"] for n in decision.selected]
        suggested = default_target_price(chosen, pending.get("discount", 0.10))
        while True:
            answer = _prompt(f"Alert me at or below what price? [Enter = CA${suggested:,.2f}]: ")
            target = parse_target(answer)
            if not isinstance(target, str):
                break
            print(target)
        decision = decision.model_copy(update={"target_price": target})

    return session.confirm(thread_id, decision, on_progress=_progress)


def _show_turn(session, thread_id: str, turn) -> None:
    print(f"\nAssistant: {turn.reply}")
    while turn.pending_confirmation:
        turn = _ask_tracking(session, thread_id, turn.pending_confirmation)
        print(f"\nAssistant: {turn.reply}")


def research_chat(settings) -> None:
    from .research import ResearchSession

    with ResearchSession(settings) as session:
        thread_id = _choose_thread(session)
        if thread_id is None:
            return
        pending = session.pending_confirmation(thread_id)
        if pending:  # resumed a thread that was waiting for tracking confirmation
            print("\nThis conversation was waiting for you to confirm tracking.")
            _show_turn(session, thread_id, _ask_tracking(session, thread_id, pending))
        print(f"\n{CHAT_HELP}")
        while True:
            text = _prompt("\nYou: ").strip()
            if text.lower() in ("/exit", "exit", "quit", "0"):
                return
            if not text:
                continue
            print("(working...)", flush=True)
            turn = session.send(thread_id, text, on_progress=_progress)
            _show_turn(session, thread_id, turn)


def run_price_check(settings) -> None:
    """US-10: check every active item once and print a summary (skipped if a check is running)."""
    from .checks import CheckAlreadyRunning, run_check
    from .monitor import PriceMonitor

    store = open_store(settings)
    print("\n(checking prices on each retailer page; this can take a minute...)", flush=True)
    try:
        _, summary = run_check(store, "cli", lambda: PriceMonitor(settings, store=store))
    except CheckAlreadyRunning as exc:
        print(f"\n{exc}")
        return
    print(f"\n{summary.render()}")


def watchlist_menu(settings) -> None:
    """US-18/19/20: view and manage tracked items."""
    from .watchlist import (
        WATCHLIST_HELP,
        WatchlistCommand,
        apply_command,
        load_watchlist,
        parse_watchlist_command,
        render_watchlist,
    )

    store = open_store(settings)
    print("\n" + render_watchlist(load_watchlist(store)))
    print("\n" + WATCHLIST_HELP)
    while True:
        cmd = parse_watchlist_command(_prompt("\nWatchlist> "))
        if isinstance(cmd, str):
            print(cmd)
            continue
        if cmd.action == "back":
            return
        if cmd.action == "help":
            print(WATCHLIST_HELP)
            continue
        if cmd.action == "refresh":
            print("\n" + render_watchlist(load_watchlist(store)))
            continue
        if cmd.action == "delete":
            item = store.get_tracked_item(cmd.item_id)
            if item is None:
                print(f"There's no item #{cmd.item_id} on your watchlist.")
                continue
            answer = _prompt(
                f"Delete #{item.id} {item.product_name} at {item.retailer} and its price history? "
                "This can't be undone. (y/N): "
            )
            if answer.strip().lower() not in ("y", "yes"):
                print("Not deleted.")
                continue
        print(apply_command(store, cmd))


def background_monitor(settings) -> None:
    """US-09: check prices now and every CHECK_INTERVAL_HOURS until the user stops it."""
    from datetime import datetime

    from .checks import CheckAlreadyRunning, run_check
    from .monitor import PriceMonitor
    from .scheduler import MonitorScheduler

    store = open_store(settings)
    PriceMonitor(settings, store=store)  # raises ConfigError before anything starts

    def stamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def check():
        try:  # a fresh monitor per run picks up changed notification settings
            return run_check(store, "cli", lambda: PriceMonitor(settings, store=store))[1]
        except CheckAlreadyRunning:
            return None

    def on_result(summary) -> None:
        nxt = scheduler.next_run_time()  # None while stopping
        tail = f"\nNext check: {nxt.astimezone().strftime('%Y-%m-%d %H:%M')}" if nxt else ""
        text = summary.render() if summary else "Skipped: another price check (worker or web app) is running."
        print(f"\n[{stamp()}] {text}{tail}", flush=True)

    def on_error(exc) -> None:
        print(f"\n[{stamp()}] Price check failed: {exc}. Will try again at the next interval.", flush=True)

    hours = settings.check_interval_hours
    scheduler = MonitorScheduler(check, hours * 3600, on_result=on_result, on_error=on_error)
    scheduler.start()
    print(
        f"\nBackground monitor started: checking now, then every {hours} hour(s).\n"
        "Checks only run while this window stays open (`shopping-assistant worker` runs them without the menu).\n"
        "Press Enter to stop and return to the menu."
    )
    try:
        _prompt("")
    except KeyboardInterrupt:
        pass
    print("Stopping the monitor (letting a check in progress finish)...", flush=True)
    scheduler.stop(wait=True)
    print(f"Monitor stopped after {scheduler.runs} check(s).")


def db_command(args: list[str]) -> int:
    """`db migrate` / `db status` (US-28) / `db import-v1 [PATH]` (US-27). Returns the exit code."""
    action = args[0] if args else ""
    valid = action in ("migrate", "status") and len(args) == 1 or action == "import-v1" and len(args) <= 2
    if not valid:
        print(USAGE)
        return 2
    settings = load_settings()
    try:
        database = get_database(settings.database_url)
        where = describe_url(database.url)
        if action == "import-v1":
            from pathlib import Path

            from .v1_import import import_v1

            database.migrate()
            path = Path(args[1]) if len(args) == 2 else settings.watchlist_db_path
            print(import_v1(database.default_store(), path).render())
        elif action == "migrate":
            applied = database.migrate()
            if applied:
                print(f"Applied {len(applied)} migration(s) to {where}: {', '.join(applied)}")
            else:
                print(f"Database {where} is up to date.")
        else:
            applied_versions = sorted(database.applied_migrations())
            pending = database.pending_migrations()
            print(f"Database: {where}")
            print(f"Applied: {', '.join(f'{v:04d}' for v in applied_versions) or 'none'}")
            print(f"Pending: {', '.join(m.name for m in pending) or 'none'}")
    except ConfigError as exc:
        print(f"Setup needed: {exc}")
        return 1
    return 0


def api_command(args: list[str]) -> int:
    """`api serve` (US-29..31) / `api openapi [PATH]` (US-33). Returns the process exit code."""
    action = args[0] if args else ""
    if action == "openapi" and len(args) <= 2:
        from pathlib import Path

        from .api.app import DEFAULT_OPENAPI_PATH, export_openapi

        path = export_openapi(Path(args[1]) if len(args) == 2 else DEFAULT_OPENAPI_PATH)
        print(f"Wrote {path}")
        return 0
    if action == "serve" and len(args) == 1:
        import uvicorn

        from .api import create_app

        settings = load_settings()
        print(f"API on http://127.0.0.1:{settings.api_port}/api/v1  (docs: http://127.0.0.1:{settings.api_port}/docs)")
        # 127.0.0.1 only: there is no sign-in yet (BL-01), so never expose it to the network.
        uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.api_port, log_level="info")
        return 0
    print(USAGE)
    return 2


def worker_command(args: list[str]) -> int:
    """`worker` (US-34): scheduled checks until Ctrl+C. Returns the process exit code."""
    if args:
        print(USAGE)
        return 2
    import time

    from .worker import PriceCheckWorker

    logging.getLogger("shopping_assistant").setLevel(logging.INFO)
    settings = load_settings()
    try:
        get_database(settings.database_url).migrate()
        worker = PriceCheckWorker(settings)
    except ConfigError as exc:
        print(f"Setup needed: {exc}")
        return 1
    worker.start()
    print(
        f"Price-check worker running: checking now, then every {settings.check_interval_hours} hour(s). "
        "Press Ctrl+C to stop.",
        flush=True,
    )
    try:
        while True:  # short sleeps: on Windows a long blocking wait ignores Ctrl+C
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    print("Stopping (letting a check in progress finish)...", flush=True)
    worker.stop()
    return 0


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["db"]:
        raise SystemExit(db_command(argv[1:]))
    if argv[:1] == ["api"]:
        raise SystemExit(api_command(argv[1:]))
    if argv[:1] == ["worker"]:
        raise SystemExit(worker_command(argv[1:]))
    if argv:
        print(USAGE)
        raise SystemExit(2)
    settings = load_settings()
    try:
        get_database(settings.database_url).migrate()  # idempotent: applies only what's pending
    except ConfigError as exc:
        print(f"Setup needed: {exc}")
        raise SystemExit(1)
    actions = {
        "1": research_chat,
        "2": watchlist_menu,
        "3": run_price_check,
        "4": background_monitor,
    }
    while True:
        print(MENU.format(hours=settings.check_interval_hours))
        choice = _prompt("Choose an option: ").strip()
        if choice == "0":
            return
        action = actions.get(choice)
        if action is None:
            print("\nPlease choose 0-4.")
            continue
        try:
            action(settings)
        except ConfigError as exc:
            print(f"\nSetup needed: {exc}")


if __name__ == "__main__":
    main()
