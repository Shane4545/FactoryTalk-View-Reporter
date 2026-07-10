"""Operator report / Insights item preferences — hide unused mixers, etc."""
from __future__ import annotations

from typing import Any

from plant_settings import load_config, save_config
from tag_config import feedback_rows, motor_rows, section_titles, trend_rows

DEFAULT_PREFS: dict[str, Any] = {
    "hidden_trend_tags": [],
    "hidden_motor_tags": [],
    "hidden_feedback_tags": [],
    "hidden_sections": [],
}


def default_prefs() -> dict[str, Any]:
    import json

    return json.loads(json.dumps(DEFAULT_PREFS))


def get_prefs() -> dict[str, Any]:
    cfg = load_config()
    out = default_prefs()
    raw = cfg.get("report_prefs")
    if isinstance(raw, dict):
        for k in DEFAULT_PREFS:
            if k in raw and isinstance(raw[k], list):
                out[k] = [str(x) for x in raw[k]]
    return out


def save_prefs(updates: dict[str, Any]) -> dict[str, Any]:
    current = get_prefs()
    for k, v in (updates or {}).items():
        if k in DEFAULT_PREFS and isinstance(v, list):
            # de-dupe preserve order
            seen: set[str] = set()
            clean: list[str] = []
            for x in v:
                s = str(x).strip()
                if s and s not in seen:
                    seen.add(s)
                    clean.append(s)
            current[k] = clean
    save_config({"report_prefs": current})
    return current


def hide_tag(kind: str, tag: str) -> dict[str, Any]:
    prefs = get_prefs()
    key = {
        "trend": "hidden_trend_tags",
        "motor": "hidden_motor_tags",
        "feedback": "hidden_feedback_tags",
        "section": "hidden_sections",
    }.get(kind)
    if not key:
        raise ValueError("kind must be trend|motor|feedback|section")
    tag = str(tag).strip()
    if tag and tag not in prefs[key]:
        prefs[key] = [*prefs[key], tag]
    return save_prefs(prefs)


def show_tag(kind: str, tag: str) -> dict[str, Any]:
    prefs = get_prefs()
    key = {
        "trend": "hidden_trend_tags",
        "motor": "hidden_motor_tags",
        "feedback": "hidden_feedback_tags",
        "section": "hidden_sections",
    }.get(kind)
    if not key:
        raise ValueError("kind must be trend|motor|feedback|section")
    tag = str(tag).strip()
    prefs[key] = [t for t in prefs[key] if t != tag]
    return save_prefs(prefs)


def catalog(prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """All reportable items with hidden flags — for Manage Items UI."""
    prefs = prefs or get_prefs()
    ht = set(prefs.get("hidden_trend_tags") or [])
    hm = set(prefs.get("hidden_motor_tags") or [])
    hf = set(prefs.get("hidden_feedback_tags") or [])
    hs = set(prefs.get("hidden_sections") or [])

    titles = section_titles()
    instruments = [
        {
            "kind": "trend",
            "tag": short,
            "description": desc,
            "section": section,
            "sectionTitle": titles.get(section, section),
            "hidden": short in ht or section in hs,
        }
        for section, _k, short, desc, _h, _u, _t in trend_rows()
    ]
    motors = [
        {
            "kind": "motor",
            "tag": short,
            "description": desc,
            "hidden": short in hm or "runtime" in hs,
        }
        for short, desc, _h in motor_rows()
    ]
    feedback = [
        {
            "kind": "feedback",
            "tag": short,
            "description": desc,
            "hidden": short in hf or "feedback" in hs,
        }
        for short, desc, _h, _u in feedback_rows()
    ]
    sections = [
        {
            "kind": "section",
            "tag": sid,
            "description": title,
            "hidden": sid in hs,
        }
        for sid, title in titles.items()
    ]
    return {
        "prefs": prefs,
        "instruments": instruments,
        "motors": motors,
        "feedback": feedback,
        "sections": sections,
    }


def hidden_sets(prefs: dict[str, Any] | None = None) -> dict[str, set[str]]:
    prefs = prefs or get_prefs()
    return {
        "trend": set(prefs.get("hidden_trend_tags") or []),
        "motor": set(prefs.get("hidden_motor_tags") or []),
        "feedback": set(prefs.get("hidden_feedback_tags") or []),
        "section": set(prefs.get("hidden_sections") or []),
    }
