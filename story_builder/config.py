from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "StoryBuilder"
DEFAULT_MODEL = "openai/gpt-4o-mini"
MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-3.5-sonnet",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct",
]


def config_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / APP_NAME / "config.json"


def load_config() -> dict:
    path = config_path()
    data = {
        "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
        "model": DEFAULT_MODEL,
        "strip_markdown": False,
    }
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for key, value in saved.items():
                    if value or isinstance(value, bool):
                        data[key] = value
        except (OSError, json.JSONDecodeError):
            pass
    if not data.get("api_key"):
        data["api_key"] = os.environ.get("OPENROUTER_API_KEY", "")
    data["strip_markdown"] = bool(data.get("strip_markdown"))
    return data


def save_config(api_key: str, model: str, strip_markdown: bool = False) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "api_key": api_key.strip(),
        "model": model.strip() or DEFAULT_MODEL,
        "strip_markdown": bool(strip_markdown),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
