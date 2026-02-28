"""Runtime-mutable settings with JSON file persistence.

Stores user-configurable settings in settings.json alongside .env.
Thread-safe read/write with file-based persistence.
"""

import json
from pathlib import Path
from threading import Lock

_SETTINGS_FILE = Path(__file__).parent / "settings.json"
_lock = Lock()

DEFAULTS: dict = {
    "temperature": 0.3,
    "top_p": 1.0,
    "max_response_tokens": 4096,
    "max_history_tokens": 2000,
    "system_prompt": "",
    "tool_call_max_iterations": 8,
    "tool_call_timeout": 120,
}


def _load() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULTS, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULTS)
    return dict(DEFAULTS)


def _save(data: dict) -> None:
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_settings() -> dict:
    with _lock:
        return _load()


def update_settings(patch: dict) -> dict:
    with _lock:
        current = _load()
        for key, value in patch.items():
            if key in DEFAULTS:
                current[key] = value
        _save(current)
        return current
