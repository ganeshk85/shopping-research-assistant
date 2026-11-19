"""CLI entry point. Thin layer over ResearchSession; menu options 2-4 arrive in later sprints."""

from __future__ import annotations

import logging
import os
import sys

from .config import ConfigError, load_settings
from .database import init_db

MENU = """
Shopping Research Assistant
  1. Start / continue product research (and set up price tracking)
  2. View / manage watchlist        (coming in Sprint 5)
  3. Run price check now            (coming in Sprint 4)
  4. Start background monitor       (coming in Sprint 5)
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
        print(f"  {i}. {t['title']}{done}  ({t['updated_at'][:16].replace('T', ' ')})")
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


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    settings = load_settings()
    init_db(settings.watchlist_db_path)
    while True:
        print(MENU)
        choice = _prompt("Choose an option: ").strip()
        if choice == "1":
            try:
                research_chat(settings)
            except ConfigError as exc:
                print(f"\nSetup needed: {exc}")
        elif choice in ("2", "3", "4"):
            print("\nThat option isn't available yet.")
        elif choice == "0":
            return
        else:
            print("\nPlease choose 0-4.")


if __name__ == "__main__":
    main()
