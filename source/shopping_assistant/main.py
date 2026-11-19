"""CLI entry point. Full menu is implemented in Build Step 5."""

from __future__ import annotations

from .config import load_settings
from .database import init_db

MENU = """
Shopping Research Assistant
  1. Start / continue product research
  2. View / manage watchlist
  3. Run price check now
  4. Start background monitor
  0. Quit
"""


def main() -> None:
    settings = load_settings()
    db_path = init_db(settings.watchlist_db_path)
    print(MENU)
    print(f"(Setup only - features arrive in later build steps. Watchlist DB: {db_path})")


if __name__ == "__main__":
    main()
