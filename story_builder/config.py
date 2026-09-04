from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

APP_NAME = "StoryBuilder"
DEFAULT_MODEL = "openai/gpt-4o-mini"
CONFIG_NAME = "config.yaml"
EXAMPLE_CONFIG_NAME = "config.example.yaml"
MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-3.5-sonnet",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct",
]


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return project_root() / CONFIG_NAME


def example_config_path() -> Path:
    return project_root() / EXAMPLE_CONFIG_NAME


def _legacy_config_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / APP_NAME / "config.json"


def _defaults() -> dict:
    return {
        "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
        "model": DEFAULT_MODEL,
        "strip_markdown": False,
    }


def _merge(saved: dict, data: dict) -> dict:
    for key, value in saved.items():
        if value or isinstance(value, bool):
            data[key] = value
    return data


def _read_yaml(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _read_legacy_json(path: Path) -> dict:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _migrate_legacy() -> dict:
    legacy = _legacy_config_path()
    if not legacy.exists():
        return {}
    try:
        return _read_legacy_json(legacy)
    except (OSError, json.JSONDecodeError):
        return {}


def load_config() -> dict:
    data = _defaults()
    path = config_path()
    if path.exists():
        try:
            data = _merge(_read_yaml(path), data)
        except (OSError, yaml.YAMLError):
            pass
    else:
        migrated = _migrate_legacy()
        if migrated:
            data = _merge(migrated, data)
            save_config(data.get("api_key", ""), data.get("model", DEFAULT_MODEL), bool(data.get("strip_markdown")))
    if not data.get("api_key"):
        data["api_key"] = os.environ.get("OPENROUTER_API_KEY", "")
    data["strip_markdown"] = bool(data.get("strip_markdown"))
    data["model"] = str(data.get("model") or DEFAULT_MODEL)
    data["api_key"] = str(data.get("api_key") or "")
    return data


def save_config(api_key: str, model: str, strip_markdown: bool = False) -> None:
    path = config_path()
    payload = {
        "api_key": api_key.strip(),
        "model": model.strip() or DEFAULT_MODEL,
        "strip_markdown": bool(strip_markdown),
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
