"""Chalk River disinfection CT — parity with Daily Report Calculations sheet.

Formulas from `Chalk River CT Calculator unprotected.xlsx` + `scripts/verify_ct_daily.py`.
Worst-case bridge: min levels/chlorine, max flow/temp/pH.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dlglog_reader import Aggregate

TABLES_PATH = Path(__file__).with_name("ct_tables.json")

I23, I24, I25 = 100.0, 23.56194490192345, 1000.0
BAFFLE_TOWER = 0.1
BAFFLE_CLEARWELL = 0.1
TARGET_GIARDIA = 0.5
TARGET_VIRUS = 2.0

# Historian tags → worst-case User Input
# (tag, which aggregate: min|max)
WORST_CASE = {
    "L7": ("TOWER_LIT03_VALUE", "min"),  # tower level
    "W7": ("WTP_LIT02_VALUE", "min"),  # clearwell level
    "Y7": ("WTP_FIT105_VALUE", "max"),  # pre-chem flow
    "B11": ("TOWER_FRC01_VALUE", "min"),  # tower Cl2
    # Temp: colder water → higher CT required (worst case = MIN).
    # Matches white CT cells on legacy Daily (e.g. 2026-06-08 TEM01 min).
    "E11": ("TOWER_TEM01_VALUE", "min"),
    "M11": ("WTP_FRC02_VALUE", "min"),  # treated Cl2
    "P11": ("WTP_FIT102_VALUE", "max"),  # treated flow
    "M13": ("WTP_PH02_VALUE", "max"),  # treated pH
    "B14": ("TOWER_FIT106_VALUE", "max"),  # distribution flow
    "E14": ("TOWER_PH03_VALUE", "max"),  # tower pH
}

# Setup-page role names → workbook cells (same formula, site-specific tags)
ROLE_TO_CELL = {
    "tower_level": "L7",
    "clearwell_level": "W7",
    "pre_chem_flow": "Y7",
    "tower_cl2": "B11",
    "temperature": "E11",
    "treated_cl2": "M11",
    "treated_flow": "P11",
    "treated_ph": "M13",
    "distribution_flow": "B14",
    "tower_ph": "E14",
}

# Chalk River contact geometry defaults (I23/I24/I25 + 300 m³ tower offset)
DEFAULT_GEOMETRY = {
    "clearwell_volume_m3": I23,
    "pipe_volume_m3": I24,
    "tower_volume_m3": I25,
    "tower_volume_offset_m3": 300.0,
    "baffle_clearwell": BAFFLE_CLEARWELL,
    "baffle_tower": BAFFLE_TOWER,
    "baffle_pipe": 1.0,
    "target_giardia_log": TARGET_GIARDIA,
    "target_virus_log": TARGET_VIRUS,
}


@dataclass
class CtResult:
    ct_achieved_giardia: float
    ct_achieved_viruses: float
    ct_required_giardia: float
    ct_required_viruses: float
    log_giardia: float
    log_viruses: float
    log_giardia_display: str
    log_viruses_display: str
    inputs: dict[str, float | None]
    basis: str


def ceil_to(x: float, step: float) -> float:
    return math.ceil(x / step - 1e-12) * step


def floor_to(x: float, step: float) -> float:
    return math.floor(x / step + 1e-12) * step


def _load_virus_k() -> list[tuple[float, float]]:
    if TABLES_PATH.is_file():
        data = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
        return [(float(r["temp"]), float(r["k"])) for r in data.get("virus", [])]
    # Built from Virus CT sheet C/D averages (log/CT)
    return [
        (0.5, (2 / 6 + 3 / 9 + 4 / 12) / 3),
        (5.0, (2 / 4 + 3 / 6 + 4 / 8) / 3),
        (10.0, (2 / 3 + 3 / 4 + 4 / 6) / 3),
        (15.0, (2 / 2 + 3 / 3 + 4 / 4) / 3),
        (20.0, (2 / 1 + 3 / 2 + 4 / 3) / 3),
        (25.0, (2 / 1 + 3 / 1 + 4 / 2) / 3),
    ]


def _load_giardia_table() -> list[dict[str, Any]]:
    if not TABLES_PATH.is_file():
        return []
    data = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
    return data.get("giardia", [])


def virus_k(temp_floor: float) -> float:
    pairs = _load_virus_k()
    chosen = pairs[0][1]
    for t, k in pairs:
        if temp_floor >= t:
            chosen = k
    return chosen


def giardia_k(co_ceil: float, ph_ceil: float) -> float | None:
    """Table lookup when cached values exist; else None → equation-only."""
    grid = _load_giardia_table()
    if not grid:
        return None
    row = None
    for r in grid:
        if abs(r["co"] - co_ceil) < 0.01:
            row = r
            break
    if not row:
        return None
    kmap = row.get("k") or {}
    # exact or nearest ph key
    best = None
    best_d = 1e9
    for ph_s, kv in kmap.items():
        if kv is None:
            continue
        d = abs(float(ph_s) - ph_ceil)
        if d < best_d:
            best_d = d
            best = float(kv)
    return best


def _agg_pick(a: Aggregate | None, which: str) -> float | None:
    if a is None:
        return None
    return getattr(a, which, None)


def bridge_worst_case(
    trend: dict[str, Aggregate],
    ct_cfg: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    """Worst-case inputs from aggregates. ct_cfg (Setup page) overrides the
    Chalk River tag map and baffling/target constants."""
    mapping: dict[str, tuple[str, str]] = dict(WORST_CASE)
    geo = dict(DEFAULT_GEOMETRY)
    if ct_cfg:
        for k in geo:
            if ct_cfg.get(k) is not None:
                try:
                    geo[k] = float(ct_cfg[k])
                except (TypeError, ValueError):
                    pass
        inputs = ct_cfg.get("inputs")
        if isinstance(inputs, dict) and inputs:
            mapping = {}
            for role, spec in inputs.items():
                cell = ROLE_TO_CELL.get(role)
                if not cell or not spec:
                    continue
                if isinstance(spec, (list, tuple)) and len(spec) >= 2:
                    mapping[cell] = (str(spec[0]), str(spec[1]))
                elif isinstance(spec, str):
                    mapping[cell] = (spec, WORST_CASE[cell][1])

    out: dict[str, float | None] = {}
    for cell, (tag, which) in mapping.items():
        out[cell] = _agg_pick(trend.get(tag), which)
    out["J9"] = geo["baffle_tower"]
    out["W16"] = geo["baffle_clearwell"]
    out["P20"] = geo["target_giardia_log"]
    out["P21"] = geo["target_virus_log"]
    return out


def _temp(e11: float | None) -> float:
    return 0.0 if e11 is None else float(e11)


def _segment(
    *,
    volume: float,
    flow: float,
    baffle: float,
    chlorine: float,
    ph: float,
    temp_c: float,
) -> tuple[float, float, float, float]:
    """Returns G (T10 min), J (Co), Q (giardia log), U (virus log)."""
    d = flow
    e = volume / d * 1000 / 60 if volume > 0 and d > 0 else 0.0
    g = e * baffle
    h = ph
    j = chlorine
    k = 0.0 if j < 0 else max(0.0, ceil_to(j, 0.2))
    l = temp_c
    m = 0.5 if l < 5 else floor_to(l, 5)
    i_ph = ceil_to(h, 0.5)

    n = giardia_k(k, i_ph)
    o = (n or 0.0) * j * g
    # Guard: negative pH / chlorine can make ** yield complex in Python
    try:
        p = (
            0.0
            if j == 0
            else j * g / (0.2828 * (h**2.69) * (j**0.15) * (0.933 ** (l - 5)))
        )
        if isinstance(p, complex):
            p = float(p.real)
        p = float(p)
    except (ZeroDivisionError, ValueError, OverflowError, TypeError):
        p = 0.0
    o = float(o.real if isinstance(o, complex) else o)
    q = max(o, p)

    r = virus_k(m) if k else 0.0
    s = r * j * g
    try:
        t = 0.0 if j == 0 else (j * g * math.exp(0.071 * m) - 0.42) / 2.94
        if isinstance(t, complex):
            t = float(t.real)
        t = float(t)
    except (ValueError, OverflowError, TypeError):
        t = 0.0
    s = float(s.real if isinstance(s, complex) else s)
    u = max(s, t)
    return g, j, q, u


def compute_ct(
    inputs: dict[str, float | None],
    geometry: dict[str, Any] | None = None,
) -> CtResult:
    def req(key: str, default: float = 0.0) -> float:
        v = inputs.get(key)
        return default if v is None else float(v)

    geo = dict(DEFAULT_GEOMETRY)
    for k in geo:
        if geometry and geometry.get(k) is not None:
            try:
                geo[k] = float(geometry[k])
            except (TypeError, ValueError):
                pass

    l7, w7 = req("L7"), req("W7")
    y7, p11, b14 = req("Y7"), req("P11"), req("B14")
    b11, m11 = req("B11"), req("M11")
    m13, e14 = req("M13"), req("E14")
    e11 = inputs.get("E11")
    temp = _temp(e11)
    w16, j9 = req("W16", geo["baffle_clearwell"]), req("J9", geo["baffle_tower"])
    p20, p21 = req("P20", geo["target_giardia_log"]), req("P21", geo["target_virus_log"])

    # Clearwell
    c8 = geo["clearwell_volume_m3"] * w7 / 100
    d8 = max(y7, p11)
    g8, j8, q8, u8 = _segment(
        volume=c8, flow=d8, baffle=w16, chlorine=m11, ph=m13, temp_c=temp
    )
    # Pipe
    d9 = p11
    g9, j9c, q9, u9 = _segment(
        volume=geo["pipe_volume_m3"], flow=d9, baffle=geo["baffle_pipe"],
        chlorine=m11, ph=m13, temp_c=temp
    )
    # Tower
    c10 = geo["tower_volume_m3"] * l7 / 100 + geo["tower_volume_offset_m3"]
    d10 = max(p11, b14)
    g10, j10, q10, u10 = _segment(
        volume=c10, flow=d10, baffle=j9, chlorine=b11, ph=e14, temp_c=temp
    )

    c24 = q8 + q9 + q10
    d24 = u8 + u9 + u10
    c26 = j8 * g8 + j9c * g9 + j10 * g10
    d26 = c26
    c27 = c26 * p20 / c24 if c24 else 0.0
    d27 = d26 * p21 / d24 if d24 else 0.0

    return CtResult(
        ct_achieved_giardia=c26,
        ct_achieved_viruses=d26,
        ct_required_giardia=c27,
        ct_required_viruses=d27,
        log_giardia=c24,
        log_viruses=d24,
        log_giardia_display="> 3" if c24 > 3 else f"{c24:.3f}",
        log_viruses_display="> 4" if d24 > 4 else f"{d24:.3f}",
        inputs=inputs,
        basis="Worst case: min levels/chlorine, max flow/temp/pH",
    )


def ct_from_trend(
    trend: dict[str, Aggregate],
    ct_cfg: dict[str, Any] | None = None,
) -> CtResult:
    return compute_ct(bridge_worst_case(trend, ct_cfg), geometry=ct_cfg)


def ct_to_report(ct: CtResult | None) -> dict[str, Any]:
    if ct is None:
        return {}  # CT disabled in Setup — omit block from report
    return {
        "ct": [
            {
                "label": "CT Achieved",
                "giardia": ct.ct_achieved_giardia,
                "viruses": ct.ct_achieved_viruses,
            },
            {
                "label": "CT Required",
                "giardia": ct.ct_required_giardia,
                "viruses": ct.ct_required_viruses,
            },
            {
                "label": "Log Inactivation",
                "giardia": ct.log_giardia if ct.log_giardia <= 3 else None,
                "viruses": ct.log_viruses if ct.log_viruses <= 4 else None,
                "giardiaDisplay": ct.log_giardia_display,
                "virusesDisplay": ct.log_viruses_display,
            },
        ],
        "ctNote": ct.basis,
        "ctInputs": {k: v for k, v in ct.inputs.items() if k in WORST_CASE},
    }


if __name__ == "__main__":
    # Sanity vs verify_ct_daily reference inputs (average bridge day)
    demo = {
        "L7": 77.47,
        "W7": 71.04,
        "Y7": (0.00 + 11.36) / 2,
        "B11": 0.94,
        "E11": None,
        "M11": 1.88,
        "P11": (0.00 + 18.27) / 2,
        "M13": 7.85,
        "B14": (1.23 + 11.45) / 2,
        "E14": 7.21,
        "J9": 0.1,
        "W16": 0.1,
        "P20": 0.5,
        "P21": 2.0,
    }
    r = compute_ct(demo)
    print(f"C26={r.ct_achieved_giardia:.5f} (ref 289.86)")
    print(f"C27={r.ct_required_giardia:.5f} (ref 44.93)")
    print(f"D27={r.ct_required_viruses:.5f} (ref 5.70)")
    print(f"log G={r.log_giardia_display} V={r.log_viruses_display}")
