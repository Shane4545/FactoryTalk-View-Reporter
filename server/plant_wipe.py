"""Wipe plant-local runtime data when resetting to a blank vanilla install.

Used by Connect → Default / Setup → Load blank template so a colleague PC
(or a handoff kit) does not keep prior plant archives, day caches, site
memory, or HMI CSV imports.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app_paths import PROJECT_FOLDERS, app_home, ensure_runtime_dirs

# Folders whose *contents* are plant-specific (keep the folder + README).
_WIPE_CONTENT_DIRS = (
    "cache/days",
    "cache/series",
    "archive",
    "PDF",
    "Web",
    "Trends",
)

# Config sidecars that must not travel with a blank handoff.
_WIPE_CONFIG_FILES = (
    "schedule_log.jsonl",
    "schedule_state.json",
    "backfill_state.json",
    "day_notes.json",
    "hmi_tag_export.json",
    "plant.json.bak",
)

_KEEP_NAMES = {"readme.txt", "readme.md", ".gitkeep"}


def _clear_dir_contents(folder: Path) -> int:
    """Remove files/subdirs under folder; keep README / .gitkeep. Returns count removed."""
    if not folder.is_dir():
        return 0
    n = 0
    for child in list(folder.iterdir()):
        if child.name.lower() in _KEEP_NAMES:
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            n += 1
        except OSError:
            pass
    return n


def wipe_runtime_artifacts() -> dict[str, Any]:
    """Clear disk cache, archives, PDF/Web/Trends outputs, and config sidecars."""
    ensure_runtime_dirs()
    home = app_home()
    removed: dict[str, int] = {}

    for rel in _WIPE_CONTENT_DIRS:
        removed[rel] = _clear_dir_contents(home / rel)

    # Top-level cache leftovers (anything not days/series)
    cache = home / "cache"
    if cache.is_dir():
        for child in list(cache.iterdir()):
            if child.name in ("days", "series"):
                continue
            if child.name.lower() in _KEEP_NAMES:
                continue
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
                removed["cache/other"] = removed.get("cache/other", 0) + 1
            except OSError:
                pass

    cfg = home / "config"
    for name in _WIPE_CONFIG_FILES:
        p = cfg / name
        if p.is_file():
            try:
                p.unlink()
                removed[f"config/{name}"] = 1
            except OSError:
                pass

    try:
        from ftview_tags_csv import clear_export

        clear_export()
    except Exception:
        pass

    try:
        from day_cache import clear_series_mem

        clear_series_mem()
    except Exception:
        pass

    # Re-create empty runtime dirs after wipe
    for name in PROJECT_FOLDERS:
        (home / name).mkdir(parents=True, exist_ok=True)

    return {"ok": True, "removed": removed, "home": str(home)}


def empty_report_prefs() -> dict[str, list]:
    return {
        "hidden_trend_tags": [],
        "hidden_motor_tags": [],
        "hidden_feedback_tags": [],
        "hidden_sections": [],
    }


def disabled_schedule() -> dict[str, Any]:
    """Scheduler off — blank installs should not auto-produce until configured."""
    return {
        "enabled": False,
        "daily": {"enabled": False, "time": "06:00", "print": False, "offset_days": 1},
        "weekly": {
            "enabled": False,
            "weekday": 0,
            "time": "06:20",
            "print": False,
            "offset_weeks": 1,
        },
        "monthly": {"enabled": False, "day": 1, "time": "06:30", "print": False},
        "yearly": {
            "enabled": False,
            "month": 1,
            "day": 2,
            "time": "07:00",
            "print": False,
        },
        "trends": {
            "enabled": False,
            "time": "06:15",
            "preset": "1d",
            "print": False,
            "tags": [],
        },
        "printer": "",
        "log_retention": {"max_entries": 1000, "max_days": 90},
    }
