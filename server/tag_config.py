"""Site tag mapping — makes Ops Reporter deployable at any FT View SE plant.

The active profile lives in config/plant.json under "tag_config". When absent
(or empty), the built-in Chalk River defaults from chalk_defaults.py apply, so
the original deployment keeps working unchanged.

Profile schema (all keys optional; missing keys fall back to Chalk defaults
only when the profile is *absent* — a saved profile fully replaces the rows):

  tag_config = {
    "sections": [{"id": "flows", "title": "Flows"}, ...],
    "trend": [{"tag": "FIT101", "description": "...", "historian": "...",
               "section": "flows", "units": "L/s", "totalize": true,
               "total_units": "m3", "scale_a": 1.0, "scale_b": 0.0,
               "total_factor": 1.0}, ...],
    "motors": [{"tag": "P1", "description": "...", "historian": "..."}],
    "feedback": [{"tag": "FB1", "description": "...", "historian": "...",
                  "units": "%"}],
    "roles": {"raw_flow": "HIST", "treated_flow": "HIST",
              "distribution_flow": "HIST", "clearwell_level": "HIST",
              "tower_level": "HIST", "treated_cl2": "HIST",
              "treated_ph": "HIST", "filter_turbidity": ["HIST", ...],
              "high_lift_pumps": ["SHORT", ...]},
    "ct": {"enabled": true, "clearwell_volume_m3": ..., "pipe_volume_m3": ...,
           "tower_volume_m3": ..., "tower_volume_offset_m3": ...,
           "baffle_clearwell": ..., "baffle_tower": ..., "baffle_pipe": ...,
           "target_giardia_log": ..., "target_virus_log": ...,
           "inputs": {"tower_level": ["HIST", "min"], ...}},
  }
"""
from __future__ import annotations

import json
from typing import Any

import chalk_defaults as _chalk
from plant_settings import load_config, save_config

# Sections every profile always has (runtime/feedback are synthetic)
BUILTIN_SECTION_IDS = ("runtime", "feedback")

ANALOG_SECTION_CHOICES = [
    ("flows", "Flows"),
    ("levels", "Level Transmitters"),
    ("chlorine", "Free Chlorine Analyzers"),
    ("fluoride", "Fluoride Analyzer"),
    ("ph", "pH Analyzers"),
    ("turbidity", "Turbidity Analyzers"),
    ("temp", "Temperature Transmitter"),
    ("pressure", "Pressure Transmitters"),
    ("other", "Other Analog"),
]

CT_INPUT_ROLES = [
    ("treated_cl2", "Treated water chlorine residual", "min"),
    ("treated_flow", "Treated water flow", "max"),
    ("treated_ph", "Treated water pH", "max"),
    ("clearwell_level", "Clearwell level %", "min"),
    ("temperature", "Water temperature", "min"),
    ("pre_chem_flow", "Flow before chemical injection", "max"),
    ("tower_level", "Tower / reservoir level %", "min"),
    ("tower_cl2", "Tower / reservoir chlorine", "min"),
    ("tower_ph", "Tower / reservoir pH", "max"),
    ("distribution_flow", "Distribution flow", "max"),
]

INSIGHT_ROLES = [
    ("raw_flow", "Raw water flow", "single"),
    ("treated_flow", "Treated water flow", "single"),
    ("distribution_flow", "Distribution flow", "single"),
    ("clearwell_level", "Clearwell level", "single"),
    ("tower_level", "Tower / reservoir level", "single"),
    ("treated_cl2", "Treated chlorine residual", "single"),
    ("treated_ph", "Treated water pH", "single"),
    ("filter_turbidity", "Filter effluent turbidity (per filter)", "multi"),
    ("high_lift_pumps", "High-lift / distribution pump group (short tags)", "multi"),
]


def _chalk_profile() -> dict[str, Any]:
    """Chalk River constants expressed in profile schema."""
    sections = [
        {"id": sid, "title": title}
        for sid, title in _chalk.SECTION_TITLES.items()
        if sid not in BUILTIN_SECTION_IDS
    ]
    trend = [
        {
            "tag": tag,
            "description": desc,
            "historian": hist,
            "section": sec,
            "units": units,
            "totalize": kind == "minmax_total",
            "total_units": tot,
        }
        for sec, kind, tag, desc, hist, units, tot in _chalk.TREND_ROWS
    ]
    motors = [
        {"tag": t, "description": d, "historian": h} for t, d, h in _chalk.MOTOR_ROWS
    ]
    feedback = [
        {"tag": t, "description": d, "historian": h, "units": u}
        for t, d, h, u in _chalk.FEEDBACK_ROWS
    ]
    ct = {
        **_chalk.CT_DEFAULTS,
        "inputs": {k: list(v) for k, v in _chalk.CT_INPUTS.items()},
    }
    return {
        "profile_name": "Chalk River WTP",
        "sections": sections,
        "trend": trend,
        "motors": motors,
        "feedback": feedback,
        "roles": json.loads(json.dumps(_chalk.ROLE_DEFAULTS)),
        "ct": ct,
    }


def _clean_str(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _clean_float(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def normalize_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate/clean a profile dict; drops rows without tag+historian."""
    out: dict[str, Any] = {
        "profile_name": _clean_str(raw.get("profile_name")) or "Custom plant",
        "sections": [],
        "trend": [],
        "motors": [],
        "feedback": [],
        "roles": {},
        "ct": {},
    }

    seen_sec: set[str] = set()
    for s in raw.get("sections") or []:
        if not isinstance(s, dict):
            continue
        sid = _clean_str(s.get("id")).lower().replace(" ", "_")
        title = _clean_str(s.get("title"))
        if sid and sid not in BUILTIN_SECTION_IDS and sid not in seen_sec:
            seen_sec.add(sid)
            out["sections"].append({"id": sid, "title": title or sid})
    if not out["sections"]:
        out["sections"] = [{"id": "other", "title": "Process Values"}]
    valid_secs = {s["id"] for s in out["sections"]}
    default_sec = out["sections"][0]["id"]

    seen_tag: set[str] = set()
    for r in raw.get("trend") or []:
        if not isinstance(r, dict):
            continue
        tag = _clean_str(r.get("tag"))
        hist = _clean_str(r.get("historian"))
        if not tag or not hist or tag in seen_tag:
            continue
        seen_tag.add(tag)
        sec = _clean_str(r.get("section")).lower() or default_sec
        if sec not in valid_secs:
            sec = default_sec
        row: dict[str, Any] = {
            "tag": tag,
            "description": _clean_str(r.get("description")) or tag,
            "historian": hist,
            "section": sec,
            "units": _clean_str(r.get("units")),
            "totalize": bool(r.get("totalize")),
            "total_units": _clean_str(r.get("total_units")) or None,
        }
        a = _clean_float(r.get("scale_a"))
        b = _clean_float(r.get("scale_b"))
        if a is not None and (a != 1.0 or (b or 0.0) != 0.0):
            row["scale_a"] = a
            row["scale_b"] = b if b is not None else 0.0
        tf = _clean_float(r.get("total_factor"))
        if tf is not None and tf != 1.0:
            row["total_factor"] = tf
        out["trend"].append(row)

    seen_m: set[str] = set()
    for r in raw.get("motors") or []:
        if not isinstance(r, dict):
            continue
        tag = _clean_str(r.get("tag"))
        hist = _clean_str(r.get("historian"))
        if not tag or not hist or tag in seen_m:
            continue
        seen_m.add(tag)
        out["motors"].append(
            {
                "tag": tag,
                "description": _clean_str(r.get("description")) or tag,
                "historian": hist,
            }
        )

    seen_f: set[str] = set()
    for r in raw.get("feedback") or []:
        if not isinstance(r, dict):
            continue
        tag = _clean_str(r.get("tag"))
        hist = _clean_str(r.get("historian"))
        if not tag or not hist or tag in seen_f:
            continue
        seen_f.add(tag)
        out["feedback"].append(
            {
                "tag": tag,
                "description": _clean_str(r.get("description")) or tag,
                "historian": hist,
                "units": _clean_str(r.get("units")) or "%",
            }
        )

    roles_in = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    for key, _label, kind in INSIGHT_ROLES:
        v = roles_in.get(key)
        if kind == "multi":
            if isinstance(v, list):
                clean = [_clean_str(x) for x in v if _clean_str(x)]
                if clean:
                    out["roles"][key] = clean
        else:
            s = _clean_str(v)
            if s:
                out["roles"][key] = s

    ct_in = raw.get("ct") if isinstance(raw.get("ct"), dict) else {}
    ct: dict[str, Any] = {"enabled": bool(ct_in.get("enabled"))}
    for key, dflt in _chalk.CT_DEFAULTS.items():
        if key == "enabled":
            continue
        ct[key] = _clean_float(ct_in.get(key), float(dflt))
    inputs_in = ct_in.get("inputs") if isinstance(ct_in.get("inputs"), dict) else {}
    inputs: dict[str, list[str]] = {}
    for role, _label, dflt_which in CT_INPUT_ROLES:
        v = inputs_in.get(role)
        if isinstance(v, (list, tuple)) and len(v) >= 1 and _clean_str(v[0]):
            which = _clean_str(v[1]).lower() if len(v) > 1 else dflt_which
            inputs[role] = [_clean_str(v[0]), which if which in ("min", "max") else dflt_which]
        elif isinstance(v, str) and v.strip():
            inputs[role] = [v.strip(), dflt_which]
    ct["inputs"] = inputs
    out["ct"] = ct

    return out


def is_configured() -> bool:
    """True when a custom tag_config profile has been saved."""
    cfg = load_config()
    tc = cfg.get("tag_config")
    return isinstance(tc, dict) and bool(tc.get("trend") or tc.get("motors"))


def get_profile() -> dict[str, Any]:
    """Active profile: saved custom profile, else Chalk River defaults."""
    cfg = load_config()
    tc = cfg.get("tag_config")
    if isinstance(tc, dict) and (tc.get("trend") or tc.get("motors")):
        prof = normalize_profile(tc)
        prof["builtin"] = False
        return prof
    prof = _chalk_profile()
    prof["builtin"] = True
    return prof


def save_profile(raw: dict[str, Any]) -> dict[str, Any]:
    prof = normalize_profile(raw)
    save_config({"tag_config": prof})
    _bust_runtime_caches()
    out = get_profile()
    return out


def reset_profile() -> dict[str, Any]:
    """Remove custom profile → back to built-in Chalk River defaults."""
    save_config({"tag_config": {}})
    _bust_runtime_caches()
    return get_profile()


def _bust_runtime_caches() -> None:
    """Tag map changes invalidate scaled aggregates + lru caches."""
    apply_scaling_overrides()
    try:
        import main

        main.clear_data_caches()
    except Exception:
        pass


# ---------------------------------------------------------------- accessors
# Legacy tuple shapes so existing report/insights code needs minimal changes.


def trend_rows() -> list[tuple[str, str, str, str, str, str, str | None]]:
    """(section, kind, tag, description, historian, units, total_units)"""
    prof = get_profile()
    return [
        (
            r["section"],
            "minmax_total" if r.get("totalize") else "minmax_avg",
            r["tag"],
            r["description"],
            r["historian"],
            r.get("units") or "",
            r.get("total_units"),
        )
        for r in prof["trend"]
    ]


def motor_rows() -> list[tuple[str, str, str]]:
    prof = get_profile()
    return [(r["tag"], r["description"], r["historian"]) for r in prof["motors"]]


def feedback_rows() -> list[tuple[str, str, str, str]]:
    prof = get_profile()
    return [
        (r["tag"], r["description"], r["historian"], r.get("units") or "%")
        for r in prof["feedback"]
    ]


def section_titles() -> dict[str, str]:
    prof = get_profile()
    titles = {s["id"]: s["title"] for s in prof["sections"]}
    titles.setdefault("runtime", "Equipment Runtime Summary")
    titles.setdefault("feedback", _chalk.SECTION_TITLES["feedback"])
    return titles


def roles() -> dict[str, Any]:
    return get_profile().get("roles") or {}


def ct_config() -> dict[str, Any]:
    return get_profile().get("ct") or {}


def ct_enabled() -> bool:
    return bool(ct_config().get("enabled"))


def flow_tag_config() -> tuple[set[str], dict[str, float]]:
    """(historians integrated as flow totals, per-tag total factor)."""
    prof = get_profile()
    flows: set[str] = set()
    factors: dict[str, float] = {}
    for r in prof["trend"]:
        if r.get("totalize"):
            flows.add(r["historian"])
            tf = r.get("total_factor")
            if tf is not None:
                factors[r["historian"]] = float(tf)
    return flows, factors


def scaling_overrides() -> dict[str, tuple[float, float]]:
    prof = get_profile()
    out: dict[str, tuple[float, float]] = {}
    for r in prof["trend"]:
        if "scale_a" in r:
            out[r["historian"]] = (float(r["scale_a"]), float(r.get("scale_b") or 0.0))
    return out


def apply_scaling_overrides() -> None:
    """Push custom profile scaling/flow config into eu_scale (identity default).

    Built-in Chalk profile keeps the calibrated eu_scale constants untouched.
    Custom profiles replace them: unlisted tags read raw (a=1, b=0).
    """
    import eu_scale

    prof = get_profile()
    if prof.get("builtin"):
        eu_scale.EU_SCALE.clear()
        eu_scale.EU_SCALE.update(eu_scale.CHALK_EU_SCALE)
        eu_scale.FLOW_TAGS.clear()
        eu_scale.FLOW_TAGS.update(eu_scale.CHALK_FLOW_TAGS)
        eu_scale.FLOW_TOTAL_FACTOR.clear()
        eu_scale.FLOW_TOTAL_FACTOR.update(eu_scale.CHALK_FLOW_TOTAL_FACTOR)
        return

    flows, factors = flow_tag_config()
    eu_scale.EU_SCALE.clear()
    eu_scale.EU_SCALE.update(scaling_overrides())
    eu_scale.FLOW_TAGS.clear()
    eu_scale.FLOW_TAGS.update(flows)
    eu_scale.FLOW_TOTAL_FACTOR.clear()
    eu_scale.FLOW_TOTAL_FACTOR.update(factors)


def cache_fingerprint() -> str:
    """Short hash of scaling-relevant profile parts — versions the day cache."""
    import hashlib

    prof = get_profile()
    if prof.get("builtin"):
        return "chalk"
    payload = json.dumps(
        {
            "scale": sorted(scaling_overrides().items()),
            "flows": sorted(flow_tag_config()[0]),
            "factors": sorted(flow_tag_config()[1].items()),
        },
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()[:10]


# ------------------------------------------------------------ suggestions

_SECTION_PATTERNS = [
    ("flows", ("FIT", "FLOW", "FT_", "_FT")),
    ("levels", ("LIT", "LEVEL", "LVL", "LT_", "_LT")),
    ("chlorine", ("FRC", "CL2", "CHLOR", "CLR")),
    ("fluoride", ("FL0", "FLUOR")),
    ("ph", ("PH",)),
    ("turbidity", ("TUR", "NTU", "TURB")),
    ("temp", ("TEM", "TEMP", "TT_")),
    ("pressure", ("PIT", "PRESS", "PSI", "PT_")),
]

_UNIT_BY_SECTION = {
    "flows": "L/s",
    "levels": "%",
    "chlorine": "mg/L",
    "fluoride": "mg/L",
    "ph": "pH",
    "turbidity": "NTU",
    "temp": "C",
    "pressure": "kPa",
    "other": "",
}

_MOTOR_PATTERNS = ("_RUNNING", "_RUN", "_STATUS", "_ON")
_FEEDBACK_PATTERNS = ("_ACTUAL", "_SC_", "_OUT", "_SPEED", "_PCT", "_CMD")


def short_from_historian(hist: str) -> str:
    """WTP_FIT101_VALUE -> FIT101; LOW_LLP1_RUNNING -> LLP1."""
    s = hist
    for suffix in ("_VALUE", "_RUNNING", "_RUN", "_STATUS", "_ACTUAL", "_OUT"):
        if s.upper().endswith(suffix):
            s = s[: -len(suffix)]
            break
    parts = s.split("_")
    return parts[-1] if len(parts) > 1 else s


def suggest_for_tag(hist: str) -> dict[str, Any]:
    """Pattern-based pre-fill for one historian tag."""
    u = hist.upper()
    if any(p in u for p in _MOTOR_PATTERNS) and "_ACTUAL" not in u:
        return {
            "kind": "motor",
            "tag": short_from_historian(hist),
            "description": f"{short_from_historian(hist)} Run time",
        }
    if any(p in u for p in _FEEDBACK_PATTERNS):
        return {
            "kind": "feedback",
            "tag": short_from_historian(hist),
            "description": hist,
            "units": "%",
        }
    section = "other"
    for sec, needles in _SECTION_PATTERNS:
        if any(n in u for n in needles):
            section = sec
            break
    return {
        "kind": "trend",
        "tag": short_from_historian(hist),
        "description": hist,
        "section": section,
        "units": _UNIT_BY_SECTION.get(section, ""),
        "totalize": section == "flows",
        "total_units": "m3" if section == "flows" else None,
    }
