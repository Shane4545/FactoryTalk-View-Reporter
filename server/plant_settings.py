"""Plant / DLGLOG settings — editable so Ops Reporter works at any site."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app_paths import app_home  # noqa: E402

CONFIG_PATH = app_home() / "config" / "plant.json"

_DEFAULTS: dict[str, Any] = {
    "product": "Ops Reporter",
    "version": "1.0.0",
    "plant": {
        "id": "plant-1",
        "name": "Water Treatment Plant",
        "municipality": "",
    },
    "dlglog_path": "",
    "dlglog_candidates": [],
    "models": {
        "trend": "WTP_TREND",
        "motors": "WTP_MOTORS",
        "feedback": "WTP_FEEDBACK",
    },
    "api_port": 8787,
}


def load_config() -> dict[str, Any]:
    cfg = json.loads(json.dumps(_DEFAULTS))
    if CONFIG_PATH.is_file():
        try:
            # utf-8-sig: tolerate BOM from Notepad/PowerShell edits of plant.json
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                cfg.update({k: v for k, v in raw.items() if v is not None})
                if isinstance(raw.get("plant"), dict):
                    cfg["plant"] = {**_DEFAULTS["plant"], **raw["plant"]}
                if isinstance(raw.get("models"), dict):
                    cfg["models"] = {**_DEFAULTS["models"], **raw["models"]}
        except (OSError, ValueError):
            pass
    return cfg


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = load_config()
    for k, v in cfg.items():
        if k == "plant" and isinstance(v, dict):
            merged["plant"] = {**merged.get("plant", {}), **v}
        elif k == "models" and isinstance(v, dict):
            merged["models"] = {**merged.get("models", {}), **v}
        elif k == "schedule" and isinstance(v, dict):
            prev = merged.get("schedule") if isinstance(merged.get("schedule"), dict) else {}
            daily = {**(prev.get("daily") or {}), **(v.get("daily") or {})} if isinstance(v.get("daily"), dict) or prev.get("daily") else v.get("daily", prev.get("daily"))
            monthly = {**(prev.get("monthly") or {}), **(v.get("monthly") or {})} if isinstance(v.get("monthly"), dict) or prev.get("monthly") else v.get("monthly", prev.get("monthly"))
            merged["schedule"] = {**prev, **v}
            if isinstance(daily, dict):
                merged["schedule"]["daily"] = daily
            if isinstance(monthly, dict):
                merged["schedule"]["monthly"] = monthly
        elif k == "outputs" and isinstance(v, dict):
            prev = merged.get("outputs") if isinstance(merged.get("outputs"), dict) else {}
            merged["outputs"] = {**prev, **v}
        elif k == "report_prefs" and isinstance(v, dict):
            prev = (
                merged.get("report_prefs")
                if isinstance(merged.get("report_prefs"), dict)
                else {}
            )
            merged["report_prefs"] = {**prev, **v}
        else:
            merged[k] = v
    CONFIG_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


def discover_models(dlglog: Path) -> list[str]:
    """Subfolders that look like FT View log models (have Float.DAT)."""
    if not dlglog.is_dir():
        return []
    names: list[str] = []
    for child in sorted(dlglog.iterdir()):
        if not child.is_dir():
            continue
        if any(child.glob("* (Float).DAT")):
            names.append(child.name)
    return names


def auto_assign_models(model_folders: list[str]) -> dict[str, str]:
    """
    Map roles from FactoryTalk datalog model folder names.
    User only points at DLGLOG; we pick TREND / MOTORS / FEEDBACK by name.
    Extra models (e.g. WTP_REPORTS) are listed but not required.
    """
    upper = {n: n.upper() for n in model_folders}

    def pick(*needles: str) -> str | None:
        for name, u in upper.items():
            if any(n in u for n in needles):
                return name
        return None

    trend = pick("TREND", "ANALOG", "PROCESS")
    motors = pick("MOTOR", "RUNTIME", "PUMP")
    feedback = pick("FEEDBACK", "FEED", "CMP")

    # Fallbacks if naming differs: first remaining folders
    leftover = [n for n in model_folders if n not in {trend, motors, feedback}]
    if not trend and leftover:
        trend = leftover.pop(0)
    if not motors and leftover:
        motors = leftover.pop(0)
    if not feedback and leftover:
        feedback = leftover.pop(0)

    out = {
        "trend": trend or _DEFAULTS["models"]["trend"],
        "motors": motors or _DEFAULTS["models"]["motors"],
        "feedback": feedback or _DEFAULTS["models"]["feedback"],
    }
    return out


def validate_dlglog(path: str | Path) -> dict[str, Any]:
    root = Path(str(path).strip().strip('"'))
    if not root.is_dir():
        return {
            "ok": False,
            "path": str(root),
            "error": f"Folder not found: {root}",
            "models": [],
            "assigned": {},
        }
    models = discover_models(root)
    if not models:
        return {
            "ok": False,
            "path": str(root),
            "error": "No datalog model folders with Float.DAT found inside this DLGLOG",
            "models": [],
            "assigned": {},
        }
    assigned = auto_assign_models(models)
    return {
        "ok": True,
        "path": str(root.resolve()),
        "error": None,
        "models": models,
        "assigned": assigned,
    }


def resolve_dlglog_root(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    primary = (cfg.get("dlglog_path") or "").strip()
    if primary:
        p = Path(primary)
        if p.is_dir():
            return p.resolve()
        raise FileNotFoundError(f"Configured DLGLOG path not found: {primary}")

    for cand in cfg.get("dlglog_candidates") or []:
        p = Path(cand)
        if p.is_dir() and discover_models(p):
            return p.resolve()

    raise FileNotFoundError(
        "No DLGLOG path configured. Open Connect and set the FactoryTalk DLGLOG folder."
    )


def model_name(cfg: dict[str, Any], key: str) -> str:
    models = cfg.get("models") or {}
    return str(models.get(key) or _DEFAULTS["models"][key])
