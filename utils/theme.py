"""Theme configuration shared by every stage.

The tracked universe and its theme live in config/tickers.json:

    {
      "_comment": "...",
      "theme": {
        "name": "broad market",
        "description": "global equities and macro drivers (...)"
      },
      "tickers": ["SPY", ...]
    }

Prompts must never hardcode the theme -- they use {{theme}} /
{{theme_description}} placeholders filled from here, so re-pointing the
whole pipeline at a new sector is a pure config edit.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "tickers.json"

DEFAULT_THEME = {
    "name": "market",
    "description": "the broad market",
}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_theme() -> dict:
    """Return {"name": ..., "description": ...}, with sane fallbacks."""
    cfg = load_config()
    theme = cfg.get("theme") or {}
    name = str(theme.get("name") or DEFAULT_THEME["name"]).strip()
    description = str(theme.get("description") or DEFAULT_THEME["description"]).strip()
    return {"name": name, "description": description}
