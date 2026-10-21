"""Local preferences. Explicit recognition profiles are stored separately."""

import json
import os
from pathlib import Path
import sys
import hashlib


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    source = Path(__file__).resolve().parent.parent / name
    if source.exists():
        return source
    return Path(sys.prefix) / name


def preferences_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / ".config")
    return Path(base) / "LootLizard" / "settings.json"


def legacy_preferences_path() -> Path:
    """The previous product's directory is read-only compatibility input."""
    return preferences_path().parent.parent / "BasementCompanion" / "settings.json"


def legacy_profile_directory(map_id: str) -> Path:
    identifier = hashlib.sha256(map_id.encode("utf-8")).hexdigest()[:24]
    return legacy_preferences_path().parent / "profiles" / identifier


def read_preferences(path: Path | None = None) -> dict:
    target = path if path is not None else preferences_path()
    # A present new file takes precedence, even if invalid. Explicit custom
    # settings paths never import another application's configuration.
    if path is None and not target.exists():
        target = legacy_preferences_path()
    try:
        if target.stat().st_size > 128 * 1024:
            return {}
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(data: dict, path: Path | None = None) -> None:
    target = path or preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)
