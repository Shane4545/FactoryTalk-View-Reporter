"""Site tag mapping — makes Plant Reporter deployable at any FT View SE plant.

Profile schema v2 (canonical): signals[] with per-signal source DLGLOG model,
revisions, and activation. See profile_v2.py.

Legacy v1 shape (trend/motors/feedback arrays) is still accepted on save and
projected from signals for Setup UI / report builders.

When no profile is activated, reports are blocked — Chalk River is no longer
a silent fallback. Use reset_to_example() to load the Chalk River template
explicitly, or import/activate a plant profile.
"""
from __future__ import annotations

import json
import re
from typing import Any

import chalk_defaults as _chalk
import profile_v2
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
    ("analyzers", "Water Quality Analyzers"),
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
    ("plant_efficiency", "Plant filter efficiency %", "single"),
    ("filter_turbidity", "Filter effluent turbidity (per filter)", "multi"),
    ("high_lift_pumps", "High-lift / distribution pump group (short tags)", "multi"),
]


def _models_from_config(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    return {
        "trend": str(models.get("trend") or ""),
        "motors": str(models.get("motors") or ""),
        "feedback": str(models.get("feedback") or ""),
    }


def _chalk_profile() -> dict[str, Any]:
    """Chalk River constants as an activated v2 profile (example template)."""
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
    raw = {
        "profile_name": "Chalk River WTP",
        "sections": sections,
        "trend": trend,
        "motors": motors,
        "feedback": feedback,
        "roles": json.loads(json.dumps(_chalk.ROLE_DEFAULTS)),
        "ct": ct,
        "status": "active",
        "revision": 1,
    }
    models = _models_from_config()
    if not models.get("trend"):
        models = {
            "trend": "WTP_TREND",
            "motors": "WTP_MOTORS",
            "feedback": "WTP_FEEDBACK",
        }
    prof = profile_v2.migrate_v1_to_v2(raw, models=models)
    prof["builtin"] = True
    prof["configured"] = True
    return prof


def _clean_str(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def normalize_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate/clean a profile (v1 or v2) → always returns v2 + projected v1 views."""
    models = _models_from_config()
    if isinstance(raw.get("ct"), dict) and raw["ct"].get("enabled"):
        ct = dict(raw["ct"])
        # Never inject Chalk River tank volumes into arbitrary plants.
        # Geometry must be set in Setup (blank plant keeps None/0 until filled).
        inputs_in = ct.get("inputs") if isinstance(ct.get("inputs"), dict) else {}
        inputs: dict[str, list[str]] = {}
        for role, _label, dflt_which in CT_INPUT_ROLES:
            v = inputs_in.get(role)
            if isinstance(v, (list, tuple)) and len(v) >= 1 and _clean_str(v[0]):
                which = _clean_str(v[1]).lower() if len(v) > 1 else dflt_which
                inputs[role] = [
                    _clean_str(v[0]),
                    which if which in ("min", "max") else dflt_which,
                ]
            elif isinstance(v, str) and v.strip():
                inputs[role] = [v.strip(), dflt_which]
        ct["inputs"] = inputs
        ct["reports"] = normalize_ct_reports(ct)
        raw = {**raw, "ct": ct}
    elif isinstance(raw.get("ct"), dict):
        ct = dict(raw["ct"])
        ct["reports"] = normalize_ct_reports(ct)
        raw = {**raw, "ct": ct}

    roles_in = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    roles: dict[str, Any] = {}
    for key, _label, kind in INSIGHT_ROLES:
        v = roles_in.get(key)
        if kind == "multi":
            if isinstance(v, list):
                clean = [_clean_str(x) for x in v if _clean_str(x)]
                if clean:
                    roles[key] = clean
        else:
            s = _clean_str(v)
            if s:
                roles[key] = s
    raw = {**raw, "roles": roles}

    if int(raw.get("schema_version") or 0) >= 2 or isinstance(raw.get("signals"), list):
        return profile_v2.normalize_v2(raw, models=models)
    return profile_v2.migrate_v1_to_v2(raw, models=models)


def is_configured() -> bool:
    """True when an activated plant profile with signals is saved."""
    cfg = load_config()
    tc = cfg.get("tag_config")
    if not isinstance(tc, dict):
        return False
    has_rows = bool(tc.get("signals") or tc.get("trend") or tc.get("motors"))
    if not has_rows:
        return False
    status = str(tc.get("status") or "").lower()
    # Legacy v1 profiles (no status) treated as active after migration
    if status in ("", "active") or (status is None):
        if int(tc.get("schema_version") or 0) < 2 and has_rows:
            return True
        return status in ("", "active")
    return False


def get_profile() -> dict[str, Any]:
    """Active profile, or an empty unconfigured draft (no silent Chalk fallback)."""
    cfg = load_config()
    tc = cfg.get("tag_config")
    models = _models_from_config(cfg)
    has_rows = isinstance(tc, dict) and bool(
        tc.get("signals") or tc.get("trend") or tc.get("motors") or tc.get("feedback")
    )
    # Blank vanilla template: v2 with an explicit (possibly empty) signals list
    blank_template = (
        isinstance(tc, dict)
        and int(tc.get("schema_version") or 0) >= 2
        and isinstance(tc.get("signals"), list)
    )
    if has_rows or blank_template:
        if int(tc.get("schema_version") or 0) >= 2 and isinstance(tc.get("signals"), list):
            prof = profile_v2.normalize_v2(tc, models=models)
        else:
            prof = profile_v2.migrate_v1_to_v2(tc, models=models)
        prof["builtin"] = False
        # Persist one-time v1→v2 migration onto disk
        if int(tc.get("schema_version") or 0) < 2:
            try:
                save_config(
                    {"tag_config": {k: v for k, v in prof.items() if k != "builtin"}}
                )
            except Exception:
                pass
        return prof
    empty = profile_v2.empty_profile()
    empty["configured"] = False
    empty["builtin"] = False
    return empty


def get_draft_profile() -> dict[str, Any] | None:
    """Pending Setup draft sidecar, if any (does not affect reports)."""
    cfg = load_config()
    raw = cfg.get("tag_config_draft")
    if not isinstance(raw, dict):
        return None
    if not (raw.get("signals") or raw.get("trend") or raw.get("motors") or raw.get("feedback")):
        return None
    models = _models_from_config(cfg)
    if int(raw.get("schema_version") or 0) >= 2 and isinstance(raw.get("signals"), list):
        prof = profile_v2.normalize_v2(raw, models=models)
    else:
        prof = profile_v2.migrate_v1_to_v2(raw, models=models)
    prof["builtin"] = False
    prof["status"] = "draft"
    prof["configured"] = False
    return prof


def clear_draft_profile() -> None:
    """Remove the Setup draft sidecar without touching the live profile."""
    save_config({"tag_config_draft": None})


def save_profile(raw: dict[str, Any], *, activate: bool = True) -> dict[str, Any]:
    """Save profile. activate=True bumps revision; False keeps a draft.

    When the live plant is already configured/active and activate=False, the
    draft is written to ``tag_config_draft`` only — live ``tag_config`` stays
    active so reports keep working. First-time (never activated) plants still
    save a draft into ``tag_config`` (configured=false) until Activate.
    """
    prof = normalize_profile(raw)
    if activate and prof.get("signals"):
        prof = profile_v2.activate(prof)
        to_store = {k: v for k, v in prof.items() if k != "builtin"}
        save_config({"tag_config": to_store, "tag_config_draft": None})
        _bust_runtime_caches()
        return get_profile()

    # Draft path
    prof["status"] = "draft"
    prof["configured"] = False
    prior = load_config().get("tag_config")
    if isinstance(prior, dict) and prior.get("revision"):
        prof["revision"] = int(prior.get("revision") or 0)
        prof["revision_hash"] = prior.get("revision_hash") or ""
        prof["activated_at"] = prior.get("activated_at")
        prof["profile_id"] = prior.get("profile_id") or prof.get("profile_id")
    to_store = {k: v for k, v in prof.items() if k != "builtin"}

    # Active plant: sidecar only — never demote live tag_config
    if is_configured():
        save_config({"tag_config_draft": to_store})
        _bust_runtime_caches()
        return get_profile()

    # First-time / unconfigured: draft is the primary profile on disk
    save_config({"tag_config": to_store, "tag_config_draft": None})
    _bust_runtime_caches()
    return get_profile()


def reset_profile() -> dict[str, Any]:
    """Clear custom profile → unconfigured (reports blocked until Setup)."""
    save_config({"tag_config": {}, "tag_config_draft": None})
    _bust_runtime_caches()
    return get_profile()


def reset_to_example() -> dict[str, Any]:
    """Load and activate the built-in Chalk River example profile."""
    example = _chalk_profile()
    example["builtin"] = False
    return save_profile(example, activate=True)


def _generic_profile() -> dict[str, Any]:
    """Blank vanilla template — empty tag list, starter section titles only."""
    import generic_defaults as _gen

    sections = [
        {"id": sid, "title": title}
        for sid, title in _gen.SECTION_TITLES.items()
        if sid not in BUILTIN_SECTION_IDS
    ]
    if not sections:
        sections = [{"id": "other", "title": "Process Values"}]
    raw = {
        "schema_version": 2,
        "profile_name": "New plant",
        "sections": sections,
        "signals": [],
        "trend": [],
        "motors": [],
        "feedback": [],
        "roles": {},
        "ct": dict(_gen.CT_DEFAULTS),
        "status": "draft",
        "revision": 0,
        "configured": False,
        "builtin": False,
    }
    models = _models_from_config()
    prof = profile_v2.normalize_v2(raw, models=models)
    prof["builtin"] = False
    prof["configured"] = False
    prof["status"] = "draft"
    return prof


def reset_to_generic() -> dict[str, Any]:
    """Reset to a blank vanilla template (CCI logo; no sample tags).

    Clears the live tag mapping, disconnects DLGLOG (path + model roles),
    forgets remembered sites (so prior plants cannot auto-restore), clears
    Insights hide prefs, disables the scheduler, and wipes day cache /
    archive / PDF / Web / Trends / HMI CSV sidecars.
    Reports stay blocked until Connect → Scan → Activate.
    """
    import json

    import branding
    import generic_defaults as _gen
    import plant_wipe
    from plant_settings import CONFIG_PATH

    plant_wipe.wipe_runtime_artifacts()
    branding.reset_logo()
    blank = _generic_profile()
    to_store = {k: v for k, v in blank.items() if k != "builtin"}

    # Full rewrite — save_config merges plant/sites/schedule and would leave
    # Chalk River (or any prior plant) residue in plant.json.
    full = load_config()
    full["plant"] = {
        "id": _gen.PLANT_DEFAULTS["id"],
        "name": _gen.PLANT_DEFAULTS["name"],
        "municipality": "",
    }
    full["dlglog_path"] = ""
    full["dlglog_candidates"] = []
    full["models"] = {"trend": "", "motors": "", "feedback": ""}
    full["sites"] = {}
    full["report_prefs"] = plant_wipe.empty_report_prefs()
    full["schedule"] = plant_wipe.disabled_schedule()
    full["tag_config"] = to_store
    full["tag_config_draft"] = None
    full.pop("outputs", None)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(full, indent=2), encoding="utf-8")

    _bust_runtime_caches()
    return get_profile()


def _scan_include_default(kind: str, confidence: float) -> bool:
    """Match SetupPage Scan Use defaults."""
    if kind in ("motor", "feedback"):
        return confidence >= 0.7
    return confidence >= 0.75


def bootstrap_from_dlglog(*, sample_day: str | None = None) -> dict[str, Any]:
    """Scan connected DLGLOG and Activate a first profile (blank → ready Daily).

    Used after Connect Save so operators are not stuck on 'not configured'.
    """
    import builder_inventory
    from plant_settings import resolve_dlglog_root

    root = resolve_dlglog_root()
    if not root.is_dir():
        raise FileNotFoundError(f"DLGLOG not found: {root}")
    inv = builder_inventory.build_inventory(root, sample_day=sample_day)
    tags = inv.get("tags") or []
    if not tags:
        raise ValueError("No logged tags found in this DLGLOG — check the folder path")

    title_by_id = {sid: title for sid, title in ANALOG_SECTION_CHOICES}
    title_by_id["runtime"] = "Equipment Runtime Summary"
    title_by_id["feedback"] = "Pump & Compressor Feedback"
    sections: list[dict[str, str]] = []
    seen_sec: set[str] = set()
    signals: list[dict[str, Any]] = []

    for i, t in enumerate(tags):
        s = t.get("suggestion") or {}
        kind = str(s.get("kind") or "trend")
        if kind not in ("trend", "motor", "feedback"):
            continue
        conf = float(s.get("confidence") or 0)
        include = _scan_include_default(kind, conf)
        # Tagname-only ghosts (e.g. CMP*_RUNNING with no Float samples) must not
        # land on Daily with blank Starts — operator can still tick Use later.
        if kind == "motor" and str(t.get("activity") or "") == "no_samples":
            include = False
            conf = min(conf, 0.55)
        sec = str(
            s.get("section")
            or ("runtime" if kind == "motor" else "feedback" if kind == "feedback" else "other")
        )
        if kind == "trend" and sec not in ("runtime", "feedback") and sec not in seen_sec:
            seen_sec.add(sec)
            sections.append({"id": sec, "title": title_by_id.get(sec, sec)})
        signals.append(
            {
                "historian": t["historian"],
                "model": t.get("model") or "",
                "class": kind,
                "tag": s.get("tag") or t["historian"],
                "description": s.get("description") or t["historian"],
                "section": sec if kind == "trend" else ("runtime" if kind == "motor" else "feedback"),
                "units": s.get("units") or "",
                "totalize": bool(s.get("totalize")) if kind == "trend" else False,
                "total_units": s.get("total_units") if kind == "trend" else None,
                "include": include,
                "confirmed": True,
                "confidence": conf,
                "order": i,
            }
        )

    if not any(s.get("include") for s in signals):
        # Never leave a plant with zero Use — include clear instruments at least
        for s in signals:
            if s.get("class") == "trend" and s.get("section") in (
                "flows",
                "levels",
                "ph",
                "chlorine",
                "turbidity",
                "temp",
                "pressure",
            ):
                s["include"] = True

    if not sections:
        sections = [{"id": "other", "title": "Other Analog"}]

    plant = load_config().get("plant") or {}
    raw = {
        "profile_name": str(plant.get("name") or "My plant"),
        "sections": sections,
        "signals": signals,
        "roles": {},
        "ct": {"enabled": False, "inputs": {}},
        "status": "draft",
    }
    prof = save_profile(raw, activate=True)
    return {
        "profile": prof,
        "configured": is_configured(),
        "tag_count": len(tags),
        "included": sum(1 for s in signals if s.get("include")),
        "sample_day": inv.get("sample_day"),
        "sections": [s["id"] for s in sections],
    }


def require_configured() -> dict[str, Any]:
    """Return active profile or raise ValueError for API handlers."""
    if not is_configured():
        raise ValueError(
            "Plant profile not configured. Open Setup: Scan DLGLOG (optionally "
            "import Tags.CSV), map tags, and Save / Activate before producing reports."
        )
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


def section_order_map(prof: dict[str, Any]) -> dict[str, int]:
    return {s["id"]: i for i, s in enumerate(prof.get("sections") or []) if s.get("id")}


def signal_sort_key(prof: dict[str, Any]):
    sec_order = section_order_map(prof)

    def key(s: dict[str, Any]) -> tuple[int, int, str]:
        kind = s.get("class") or ""
        sid = s.get("section") or (
            "runtime" if kind == "motor" else "feedback" if kind == "feedback" else "other"
        )
        # Builtin runtime/feedback sort after profile sections unless listed.
        if sid in sec_order:
            sec_i = sec_order[sid]
        elif sid == "runtime":
            sec_i = 900
        elif sid == "feedback":
            sec_i = 901
        else:
            sec_i = 999
        return (sec_i, int(s.get("order") or 0), s.get("historian") or "")

    return key


def ordered_report_sections(
    sections: dict[str, dict[str, Any]],
    prof: dict[str, Any],
) -> list[dict[str, Any]]:
    """Daily/period report section list in profile section order.

    Motors/feedback assigned to a profile section id share that slot when the
    block id matches; collision blocks use ``{id}__runtime`` / ``{id}__feedback``
    and are emitted immediately after the analog section.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sec in prof.get("sections") or []:
        sid = sec.get("id")
        if not sid:
            continue
        for candidate in (sid, f"{sid}__runtime", f"{sid}__feedback"):
            if candidate in sections and candidate not in seen:
                out.append(sections[candidate])
                seen.add(candidate)
    for sid in ("runtime", "feedback", "efficiency"):
        if sid in sections and sid not in seen:
            out.append(sections[sid])
            seen.add(sid)
    for sid, block in sections.items():
        if sid not in seen:
            out.append(block)
    return out


def section_choices_for_editor(prof: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Profile sections first, then template defaults for new plants."""
    choices: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in prof.get("sections") or [] if prof else []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "").strip()
        if not sid or sid in seen:
            continue
        choices.append({"id": sid, "title": str(s.get("title") or sid)})
        seen.add(sid)
    for sid, title in ANALOG_SECTION_CHOICES:
        if sid not in seen:
            choices.append({"id": sid, "title": title})
            seen.add(sid)
    return choices


def trend_rows() -> list[tuple[str, str, str, str, str, str, str | None]]:
    """(section, kind, tag, description, historian, units, total_units) — included only."""
    prof = get_profile()
    signals = sorted(
        [
            s
            for s in (prof.get("signals") or [])
            if s.get("class") == "trend" and profile_v2.signal_included(s)
        ],
        key=signal_sort_key(prof),
    )
    if signals:
        return [
            (
                s.get("section") or "other",
                "minmax_total" if s.get("totalize") else "minmax_avg",
                s["tag"],
                s["description"],
                s["historian"],
                s.get("units") or "",
                s.get("total_units"),
            )
            for s in signals
        ]
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
        if r.get("include") is not False
    ]


def motor_rows() -> list[tuple[str, str, str]]:
    """Included motor rows only."""
    prof = get_profile()
    signals = sorted(
        [
            s
            for s in (prof.get("signals") or [])
            if s.get("class") == "motor" and profile_v2.signal_included(s)
        ],
        key=signal_sort_key(prof),
    )
    if signals:
        return [(s["tag"], s["description"], s["historian"]) for s in signals]
    return [
        (r["tag"], r["description"], r["historian"])
        for r in prof["motors"]
        if r.get("include") is not False
    ]


def feedback_rows() -> list[tuple[str, str, str, str]]:
    """Included feedback rows only."""
    prof = get_profile()
    signals = sorted(
        [
            s
            for s in (prof.get("signals") or [])
            if s.get("class") == "feedback" and profile_v2.signal_included(s)
        ],
        key=signal_sort_key(prof),
    )
    if signals:
        return [
            (s["tag"], s["description"], s["historian"], s.get("units") or "%")
            for s in signals
        ]
    return [
        (r["tag"], r["description"], r["historian"], r.get("units") or "%")
        for r in prof["feedback"]
        if r.get("include") is not False
    ]


def signal_rows(kind: str | None = None) -> list[dict[str, Any]]:
    """Canonical included signal dicts; optional filter by class."""
    prof = get_profile()
    signals = [
        s for s in (prof.get("signals") or []) if profile_v2.signal_included(s)
    ]
    if kind:
        signals = [s for s in signals if s.get("class") == kind]
    return signals


def section_titles() -> dict[str, str]:
    prof = get_profile()
    titles = {
        s["id"]: (str(s.get("title") or "").strip() or s["id"])
        for s in prof["sections"]
        if s.get("id")
    }
    titles.setdefault("runtime", "Equipment Runtime Summary")
    titles.setdefault("feedback", _chalk.SECTION_TITLES["feedback"])
    return titles


def equipment_block_id(
    section_id: str,
    *,
    kind_suffix: str,
    occupied: set[str],
) -> str:
    """Pick a report section id for motor/feedback rows without clobbering analogs."""
    sid = (section_id or "").strip() or (
        "runtime" if kind_suffix == "runtime" else "feedback"
    )
    if sid not in occupied:
        return sid
    alt = f"{sid}__{kind_suffix}"
    return alt


def motor_rows_by_section() -> list[tuple[str, str, str, str, str]]:
    """(section_id, tag, description, historian, units) — included motors only.

    Units default to ``h`` (runtime is integrated as hours). Setup may set
    ``min`` / ``s`` — report builder converts the displayed total.
    """
    prof = get_profile()
    signals = sorted(
        [
            s
            for s in (prof.get("signals") or [])
            if s.get("class") == "motor" and profile_v2.signal_included(s)
        ],
        key=signal_sort_key(prof),
    )
    if signals:
        return [
            (
                s.get("section") or "runtime",
                s["tag"],
                s["description"],
                s["historian"],
                str(s.get("units") or "h").strip() or "h",
            )
            for s in signals
        ]
    return [
        (
            r.get("section") or "runtime",
            r["tag"],
            r["description"],
            r["historian"],
            str(r.get("units") or "h").strip() or "h",
        )
        for r in prof["motors"]
        if r.get("include") is not False
    ]


def feedback_rows_by_section() -> list[tuple[str, str, str, str, str]]:
    """(section_id, tag, description, historian, units) — included feedback only."""
    prof = get_profile()
    signals = sorted(
        [
            s
            for s in (prof.get("signals") or [])
            if s.get("class") == "feedback" and profile_v2.signal_included(s)
        ],
        key=signal_sort_key(prof),
    )
    if signals:
        return [
            (
                s.get("section") or "feedback",
                s["tag"],
                s["description"],
                s["historian"],
                s.get("units") or "%",
            )
            for s in signals
        ]
    return [
        (
            r.get("section") or "feedback",
            r["tag"],
            r["description"],
            r["historian"],
            r.get("units") or "%",
        )
        for r in prof["feedback"]
        if r.get("include") is not False
    ]


def roles() -> dict[str, Any]:
    return get_profile().get("roles") or {}


def ct_config() -> dict[str, Any]:
    return get_profile().get("ct") or {}


def ct_enabled() -> bool:
    """Master switch — CT geometry/inputs are configured for the plant."""
    return bool(ct_config().get("enabled"))


CT_REPORT_KINDS = ("daily", "weekly", "monthly", "yearly", "custom")


def ct_enabled_for(kind: str) -> bool:
    """True when the CT table should appear on this report kind.

    Master ``ct.enabled`` must be on. Per-report flags live in ``ct.reports``.
    Legacy profiles (enabled, no reports map) → daily only.
    """
    cfg = ct_config()
    if not cfg.get("enabled"):
        return False
    k = str(kind or "").strip().lower()
    if k not in CT_REPORT_KINDS:
        return False
    reports = cfg.get("reports")
    if not isinstance(reports, dict) or not reports:
        return k == "daily"
    return bool(reports.get(k))


def normalize_ct_reports(ct: dict[str, Any]) -> dict[str, bool]:
    """Delegate to profile_v2 (single source of truth)."""
    return profile_v2.normalize_ct_reports(ct)


def flow_tag_config() -> tuple[set[str], dict[str, float]]:
    """(historians integrated as flow totals, per-tag total factor)."""
    prof = get_profile()
    flows: set[str] = set()
    factors: dict[str, float] = {}
    for r in prof["trend"]:
        if r.get("include") is False:
            continue
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
        if r.get("include") is False:
            continue
        if "scale_a" in r:
            out[r["historian"]] = (float(r["scale_a"]), float(r.get("scale_b") or 0.0))
    return out


def apply_scaling_overrides() -> None:
    """Push profile scaling/flow config into eu_scale."""
    import eu_scale

    flows, factors = flow_tag_config()
    eu_scale.EU_SCALE.clear()
    eu_scale.EU_SCALE.update(scaling_overrides())

    eu_scale.FLOW_TAGS.clear()
    eu_scale.FLOW_TAGS.update(flows)

    eu_scale.FLOW_TOTAL_FACTOR.clear()
    eu_scale.FLOW_TOTAL_FACTOR.update(factors)


def cache_fingerprint() -> str:
    """Short hash of inputs that change Float.DAT aggregates.

    Intentionally omits ``revision`` / ``revision_hash`` / Use(include) flags.
    Day pickles store full-model aggregates; include filtering happens at report
    build time. Bumping those on every Activate was orphaning warm caches and
    forcing multi-model DAT rescans (~20–60s) on each Daily open.
    """
    import hashlib

    prof = get_profile()
    if not prof.get("configured") and not (prof.get("signals") or prof.get("trend")):
        return "unconfigured"
    payload = json.dumps(
        {
            "scale": sorted(scaling_overrides().items()),
            "flows": sorted(flow_tag_config()[0]),
            "factors": sorted(flow_tag_config()[1].items()),
            # All mapped historians (included or not) — include toggles must not
            # change the cache namespace; report builders filter Use at read time.
            "models": sorted(
                (s.get("historian"), s.get("model"), s.get("class"))
                for s in (prof.get("signals") or [])
                if (s.get("historian") or "").strip()
            ),
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


_SITE_PREFIXES = ("WTP", "LOW", "TOWER", "HIGH", "F1", "F2")


def short_from_historian(hist: str, *, kind: str | None = None) -> str:
    """Operator-facing short id derived from the historian name.

    Trends/motors: WTP_FIT101_VALUE -> FIT101; LOW_LLP1_RUNNING -> LLP1.
    Feedback: strip site prefix only — keep the rest of the logged name so
    ACTUAL/OUT/SC rows stay unique without inventing FB-* labels
    (LOW_LLP1_ACTUAL -> LLP1_ACTUAL; WTP_CMP03_OUT -> CMP03_OUT).
    """
    if kind == "feedback" or (
        kind is None
        and any(p in hist.upper() for p in ("_ACTUAL", "_OUT", "_SC_", "_MAN_OUT"))
        and not hist.upper().endswith(("_VALUE", "_RUNNING"))
    ):
        return feedback_short_from_historian(hist)

    s = hist
    for suffix in ("_VALUE", "_RUNNING", "_RUN", "_STATUS", "_ACTUAL", "_OUT"):
        if s.upper().endswith(suffix):
            s = s[: -len(suffix)]
            break
    parts = s.split("_")
    while len(parts) > 1 and parts[0].upper() in _SITE_PREFIXES:
        parts = parts[1:]
    return parts[-1] if len(parts) > 1 else (parts[0] if parts else s)


def feedback_short_from_historian(hist: str) -> str:
    """Short report tag from the logged historian — no invented FB- prefix.

    Prefer the Tags.CSV / DLGLOG name with only site prefixes removed so
    another plant's scan stays faithful to the dataset.
    """
    name = hist[1:] if hist.startswith("_") else hist
    parts = [p for p in name.split("_") if p]
    while parts and parts[0].upper() in _SITE_PREFIXES:
        parts.pop(0)
    return "_".join(parts) if parts else hist


def suggest_for_tag(
    hist: str,
    *,
    enrichment: dict[str, Any] | None = None,
    model: str = "",
) -> dict[str, Any]:
    """Pattern-based pre-fill with confidence / reasons for Plant Builder."""
    u = hist.upper()
    enr = enrichment or {}
    enr_desc = str(enr.get("description") or "").strip()
    enr_units = str(enr.get("units") or "").strip()
    enr_type = str(enr.get("tag_type") or "").upper()
    # Tags.CSV tag_name when present — prefer over invented shorts
    enr_tag = str(enr.get("tag_name") or enr.get("report_tag") or "").strip()
    if enr_tag.startswith("_"):
        enr_tag = enr_tag[1:]
    model_u = (model or "").upper()

    confidence = 0.45
    reasons: list[str] = ["name pattern"]

    if model_u and any(n in model_u for n in ("MOTOR", "RUNTIME", "PUMP")):
        confidence = max(confidence, 0.7)
        reasons.append(f"model folder suggests runtime ({model})")
    if model_u and any(n in model_u for n in ("FEEDBACK", "FEED", "CMP")):
        confidence = max(confidence, 0.7)
        reasons.append(f"model folder suggests feedback ({model})")
    if model_u and any(n in model_u for n in ("TREND", "ANALOG", "PROCESS")):
        confidence = max(confidence, 0.65)
        reasons.append(f"model folder suggests analog ({model})")
    if enr_desc:
        confidence = max(confidence, 0.85)
        reasons.append("FactoryTalk Tags.CSV description")

    if any(p in u for p in _MOTOR_PATTERNS) and "_ACTUAL" not in u:
        short = short_from_historian(hist, kind="motor")
        desc = enr_desc or f"{short} Run time"
        if enr_desc and not re.search(r"\brun\b", enr_desc, re.I):
            desc = f"{enr_desc} Run time"
        return {
            "kind": "motor",
            "tag": short,
            "description": desc,
            "section": "runtime",
            "model": model,
            "confidence": min(0.95, confidence + 0.15),
            "reasons": reasons + ["*_RUNNING digital pattern"],
            "from_hmi_export": bool(enr_desc),
            "needs_review": confidence < 0.8 and not enr_desc,
        }
    if any(p in u for p in _FEEDBACK_PATTERNS) or (
        enr_type == "A" and any(p in u for p in ("_ACTUAL", "_OUT", "_SPEED", "_CMD"))
    ):
        # Prefer shortened historian (dataset). If CSV tag_name differs from the
        # historian, use the CSV name; if it matches, still shorten site prefixes.
        if enr_tag and enr_tag.upper() != hist.upper() and enr_tag.upper() != u:
            short = enr_tag
        else:
            short = short_from_historian(hist, kind="feedback")
        return {
            "kind": "feedback",
            "tag": short,
            "description": enr_desc or hist,
            "section": "feedback",
            "units": enr_units or "%",
            "model": model,
            "confidence": min(0.95, confidence + 0.1),
            "reasons": reasons + ["feedback/speed/output pattern"],
            "from_hmi_export": bool(enr_desc),
            "needs_review": False if enr_desc else confidence < 0.75,
        }
    section = "other"
    for sec, needles in _SECTION_PATTERNS:
        if any(n in u for n in needles):
            section = sec
            break
    units = enr_units or _UNIT_BY_SECTION.get(section, "")
    # Flow-like section → offer daily total; operator can untick in Setup.
    # Do not require ISA "FIT" in the tag name.
    totalize = section == "flows"
    # needs_review is advisory — do not block Use.
    needs_review = False
    if section == "flows":
        reasons.append("flow-like name — confirm units and totalization")
        if enr_desc or any(n in u for n in ("FIT", "FLOW", "FT_")):
            confidence = max(confidence, 0.88)
        else:
            needs_review = True
            confidence = min(confidence, 0.7)
    elif not enr_desc and section == "other":
        needs_review = True
    return {
        "kind": "trend",
        "tag": (
            enr_tag
            if enr_tag and enr_tag.upper() != hist.upper() and enr_tag.upper() != u
            else short_from_historian(hist, kind="trend")
        ),
        "description": enr_desc or hist,
        "section": section,
        "units": units,
        "totalize": totalize,
        "total_units": "m3" if section == "flows" else None,
        "model": model,
        "confidence": confidence,
        "reasons": reasons,
        "from_hmi_export": bool(enr_desc),
        "needs_review": needs_review,
    }
