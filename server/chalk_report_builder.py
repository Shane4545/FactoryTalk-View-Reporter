"""Build the Daily report JSON from DLGLOG aggregates.

Rows/sections come from tag_config (Setup page profile). The historical
Chalk River constants are re-exported from chalk_defaults for the proof
scripts that verify parity against legacy XLReporter screenshots.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

# Legacy re-exports (proof scripts + Chalk parity checks)
from chalk_defaults import (  # noqa: F401
    FEEDBACK_ROWS,
    MOTOR_ROWS,
    SECTION_TITLES,
    TREND_ROWS,
)
from ct_calculator import ct_from_trend, ct_to_report
from dlglog_reader import Aggregate, DigitalRuntime
from tag_config import (
    ct_config,
    ct_enabled,
    feedback_rows,
    motor_rows,
    section_titles,
    trend_rows,
)

# Flow TOTAL is already m³ from dlglog_reader (EU integral / 1000).
# Do not apply an extra *0.001 here.
FLOW_TOTAL_SCALE = 1.0


def ct_emphasize_map() -> dict[str, str]:
    """Short tag → min|max for CT worst-case white cells (profile-driven)."""
    if not ct_enabled():
        return {}
    cfg = ct_config()
    inputs = cfg.get("inputs") or {}
    hist_to_short = {hist: tag for _s, _k, tag, _d, hist, _u, _t in trend_rows()}
    out: dict[str, str] = {}
    for _role, spec in inputs.items():
        if isinstance(spec, (list, tuple)) and len(spec) >= 2:
            short = hist_to_short.get(str(spec[0]))
            if short:
                out[short] = str(spec[1])
    return out


def _agg_to_dict(a: Aggregate | None, *, flow_total: bool = False) -> dict[str, Any]:
    if a is None:
        return {
            "min": None,
            "max": None,
            "avg": None,
            "total": None,
            "timeOfMin": None,
            "timeOfMax": None,
            "count": 0,
        }
    total = a.total
    if flow_total and a.total is not None:
        total = a.total * FLOW_TOTAL_SCALE
    return {
        "min": a.min,
        "max": a.max,
        "avg": a.avg,
        "total": total,
        "timeOfMin": a.time_of_min,
        "timeOfMax": a.time_of_max,
        "count": a.count,
    }


def build_daily(
    day: datetime,
    trend: dict[str, Aggregate],
    motors: dict[str, Aggregate],
    feedback: dict[str, Aggregate] | None = None,
    motor_runtime: dict[str, DigitalRuntime] | None = None,
    *,
    live: bool = False,
    as_of: datetime | None = None,
    hidden_trend: set[str] | None = None,
    hidden_motor: set[str] | None = None,
    hidden_feedback: set[str] | None = None,
    hidden_sections: set[str] | None = None,
) -> dict[str, Any]:
    feedback = feedback or {}
    motor_runtime = motor_runtime or {}
    hidden_trend = hidden_trend or set()
    hidden_motor = hidden_motor or set()
    hidden_feedback = hidden_feedback or set()
    hidden_sections = hidden_sections or set()

    titles = section_titles()
    ct_marks = ct_emphasize_map()
    sections: dict[str, dict[str, Any]] = {}
    for sec_id, kind, tag, desc, hist, units, total_units in trend_rows():
        if sec_id in hidden_sections or tag in hidden_trend:
            continue
        if sec_id not in sections:
            sections[sec_id] = {
                "id": sec_id,
                "title": titles.get(sec_id, sec_id),
                "kind": kind,
                "rows": [],
            }
        a = trend.get(hist)
        flow = kind == "minmax_total"
        agg = _agg_to_dict(a, flow_total=flow)
        ct_which = ct_marks.get(tag)
        sections[sec_id]["rows"].append(
            {
                "tag": tag,
                "description": desc,
                "historianTag": hist,
                "emphasize": ct_which is not None,
                "ctCell": ct_which,  # "min" | "max" — white CT input on legacy Daily
                "aggregate": {
                    **agg,
                    "units": units,
                    "totalUnits": total_units,
                },
            }
        )

    runtime_rows = []
    if "runtime" not in hidden_sections:
        for tag, desc, hist in motor_rows():
            if tag in hidden_motor:
                continue
            rt = motor_runtime.get(hist)
            a = motors.get(hist)
            # Prefer edge/ON-duration from digital series; fall back to avg*24 only if missing
            if rt is not None:
                starts = rt.starts
                stops = rt.stops
                hours = rt.on_hours
                count = rt.count
            elif a and a.count:
                starts = None
                stops = None
                hours = (a.avg or 0) * 24.0
                count = a.count
            else:
                starts = stops = hours = None
                count = 0
            runtime_rows.append(
                {
                    "tag": tag,
                    "description": desc,
                    "historianTag": hist,
                    "aggregate": {
                        "min": starts,
                        "max": stops,
                        "avg": None,
                        "total": hours,
                        "starts": starts,
                        "stops": stops,
                        "timeOfMin": None,
                        "timeOfMax": None,
                        "units": "h",
                        "count": count,
                    },
                }
            )
        if runtime_rows:
            sections["runtime"] = {
                "id": "runtime",
                "title": titles.get("runtime", "Equipment Runtime Summary"),
                "kind": "runtime",
                "rows": runtime_rows,
            }

    fb_rows = []
    if "feedback" not in hidden_sections:
        for tag, desc, hist, units in feedback_rows():
            if tag in hidden_feedback:
                continue
            a = feedback.get(hist)
            agg = _agg_to_dict(a)
            fb_rows.append(
                {
                    "tag": tag,
                    "description": desc,
                    "historianTag": hist,
                    "aggregate": {**agg, "units": units},
                }
            )
        if fb_rows:
            sections["feedback"] = {
                "id": "feedback",
                "title": titles.get("feedback", "Pump & Compressor Feedback"),
                "kind": "minmax_avg",
                "rows": fb_rows,
            }

    day0 = datetime(day.year, day.month, day.day, 0, 0, 0)
    if live:
        end = as_of or datetime.now()
        if end.date() != day0.date():
            end = datetime(day.year, day.month, day.day, 23, 59, 59)
        period_label = (
            f"Live today {day0.strftime('%Y-%m-%d')} 00:00:00 -> "
            f"{end.strftime('%H:%M:%S')} (updates as DLGLOG grows)"
        )
    else:
        # Full calendar day — matches XLReporter-style 00:00:00 through 23:59:59
        end = datetime(day.year, day.month, day.day, 23, 59, 59)
        period_label = (
            f"Complete day {day0.strftime('%Y-%m-%d')} "
            f"00:00:00 -> 23:59:59"
        )

    # CT block only when enabled in Setup (plant-specific geometry)
    ct_block = (
        ct_to_report(ct_from_trend(trend, ct_config())) if ct_enabled() else {}
    )

    from plant_settings import load_config

    plant_cfg = (load_config().get("plant") or {})
    plant_name = str(plant_cfg.get("name") or "Water Treatment Plant")
    return {
        "plant": plant_name.upper(),
        "subtitle": "Daily Operations Report",
        "municipality": str(plant_cfg.get("municipality") or ""),
        "periodLabel": period_label,
        "startDate": day0.strftime("%Y-%m-%d %H:%M:%S"),
        "endDate": end.strftime("%Y-%m-%d %H:%M:%S"),
        "live": live,
        "sections": list(sections.values()),
        **ct_block,
    }
