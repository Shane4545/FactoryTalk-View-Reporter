"""Resolve app paths for dev vs frozen (PyInstaller) SCADA kit."""
from __future__ import annotations

import sys
from pathlib import Path


def app_home() -> Path:
    """Writable folder next to the .exe (or apps/ops-reporter in dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Bundled read-only assets (dist UI, server modules when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def ensure_runtime_dirs() -> None:
    home = app_home()
    for name in (
        "config",
        "cache",
        "cache/days",
        "cache/series",
        "archive",
        "PDF",
        "Web",
    ):
        (home / name).mkdir(parents=True, exist_ok=True)
    cfg = home / "config" / "plant.json"
    if not cfg.is_file():
        cfg.write_text(
            """{
  "product": "Ops Reporter",
  "version": "1.0.0",
  "plant": {
    "id": "plant-1",
    "name": "Water Treatment Plant",
    "municipality": ""
  },
  "dlglog_path": "",
  "dlglog_candidates": [],
  "models": {
    "trend": "WTP_TREND",
    "motors": "WTP_MOTORS",
    "feedback": "WTP_FEEDBACK"
  },
  "api_port": 8787
}
""",
            encoding="utf-8",
        )
