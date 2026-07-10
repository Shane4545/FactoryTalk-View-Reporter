"""
Operator plant insights — traffic-light health scoring from DLGLOG day aggregates.

Heuristics are engineering rules of thumb for WTP transmitters / motors (not
regulatory setpoints). Operators should treat yellow/red as investigate prompts.
"""
from __future__ import annotations

from typing import Any

from dlglog_reader import Aggregate, DigitalRuntime
from tag_config import motor_rows, roles as site_roles, section_titles, trend_rows

Severity = str  # ok | watch | alert | unknown


def _sev_rank(s: Severity) -> int:
    return {"ok": 0, "watch": 1, "alert": 2, "unknown": 1}.get(s, 1)


def _worst(*sevs: Severity) -> Severity:
    return max(sevs, key=_sev_rank)


def _agg_stats(a: Aggregate | None) -> dict[str, Any]:
    if a is None or a.count <= 0:
        return {
            "min": None,
            "max": None,
            "avg": None,
            "total": None,
            "count": 0,
            "range": None,
            "timeOfMin": None,
            "timeOfMax": None,
        }
    mn, mx, avg = a.min, a.max, a.avg
    rng = None
    if mn is not None and mx is not None:
        rng = mx - mn
    return {
        "min": mn,
        "max": mx,
        "avg": avg,
        "total": a.total,
        "count": a.count,
        "range": rng,
        "timeOfMin": a.time_of_min,
        "timeOfMax": a.time_of_max,
    }


def score_analog(
    *,
    short: str,
    section: str,
    units: str,
    stats: dict[str, Any],
) -> tuple[Severity, list[str]]:
    """Return (severity, reasons) for a transmitter / analyzer."""
    reasons: list[str] = []
    count = int(stats.get("count") or 0)
    if count <= 0:
        return "alert", ["No samples — check historian / instrument"]

    mn = stats.get("min")
    mx = stats.get("max")
    avg = stats.get("avg")
    rng = stats.get("range")
    sev: Severity = "ok"

    if count < 20:
        sev = _worst(sev, "watch")
        reasons.append(f"Low sample count ({count})")

    # Physical / sanity bounds
    if section == "levels" and mn is not None and mx is not None:
        if mn < -2 or mx > 105:
            sev = _worst(sev, "alert")
            reasons.append(f"Level outside 0–100% ({mn:.1f}→{mx:.1f})")
        elif mn < 0 or mx > 100:
            sev = _worst(sev, "watch")
            reasons.append(f"Level near/over span ({mn:.1f}→{mx:.1f})")

    if section == "ph" and (mn is not None or mx is not None):
        lo = mn if mn is not None else avg
        hi = mx if mx is not None else avg
        if lo is not None and (lo < 0 or (hi is not None and hi > 14)):
            sev = _worst(sev, "alert")
            reasons.append("pH outside 0–14 — sensor fault likely")
        elif lo is not None and hi is not None and (lo < 5.5 or hi > 9.5):
            sev = _worst(sev, "watch")
            reasons.append(f"pH unusual band ({lo:.2f}→{hi:.2f})")

    if section in ("chlorine", "fluoride") and mn is not None:
        if mn < -0.05:
            sev = _worst(sev, "alert")
            reasons.append("Negative residual — analyzer fault")
        if mx is not None and mx > 5.0 and section == "chlorine":
            sev = _worst(sev, "watch")
            reasons.append(f"High Cl₂ max ({mx:.2f} mg/L)")
        # Entry-point style residual band (industry ops KPI heuristic ~0.2–2.0 mg/L)
        if section == "chlorine" and avg is not None:
            if avg < 0.2:
                sev = _worst(sev, "alert" if avg < 0.1 else "watch")
                reasons.append(
                    f"Cl₂ avg {avg:.2f} mg/L below ~0.2 band — check CT / dosing"
                )
            elif avg > 2.0:
                sev = _worst(sev, "watch")
                reasons.append(f"Cl₂ avg {avg:.2f} mg/L above ~2.0 band")

    if section == "turbidity" and mx is not None:
        # Filter optimization bands (common ops goals — not a substitute for your permit)
        if short in ("TUR01", "TUR02"):
            if mx >= 0.3:
                sev = _worst(sev, "alert")
                reasons.append(f"Filter turbidity max {mx:.3f} NTU (≥0.3)")
            elif mx >= 0.1:
                sev = _worst(sev, "watch")
                reasons.append(f"Filter turbidity max {mx:.3f} NTU (≥0.1 opt. goal)")
        if short == "TUR03" and mx > 50:
            sev = _worst(sev, "watch")
            reasons.append(f"Raw turbidity spike (max {mx:.1f} NTU)")

    if section == "flows" and mn is not None and mn < -0.5:
        sev = _worst(sev, "alert")
        reasons.append("Negative flow — transmitter / wiring check")

    if section == "temp" and (mn is not None or mx is not None):
        lo = mn if mn is not None else avg
        hi = mx if mx is not None else avg
        if lo is not None and (lo < -5 or (hi is not None and hi > 45)):
            sev = _worst(sev, "alert")
            reasons.append("Temperature out of plausible range")

    # Stuck / flatline — little movement with plenty of samples
    if rng is not None and count >= 40 and avg is not None:
        abs_avg = abs(avg) if avg else 0.0
        # Absolute flatline thresholds by section
        flat_abs = {
            "flows": 0.05,
            "levels": 0.15,
            "ph": 0.02,
            "chlorine": 0.005,
            "fluoride": 0.005,
            "turbidity": 0.005,
            "temp": 0.05,
        }.get(section, 0.05)
        flat_rel = abs_avg * 0.002  # 0.2% of avg
        if rng <= max(flat_abs, flat_rel):
            # Stable low filter turbidity / controlled residuals are GOOD, not faults
            if section == "turbidity" and short in ("TUR01", "TUR02") and abs_avg < 0.5:
                reasons.append("Filter turbidity stable/low (good)")
            elif section in ("chlorine", "fluoride") and abs_avg > 0.05:
                reasons.append("Residual stable (tight control)")
            elif section == "flows" and abs_avg < 0.2:
                sev = _worst(sev, "watch")
                reasons.append("Flow near zero all day (idle or stuck at 0)")
            elif section in ("chlorine", "fluoride", "ph", "turbidity") and abs_avg < 0.02:
                sev = _worst(sev, "alert")
                reasons.append(
                    f"Stuck near zero (range {rng:.3f} {units}) — check analyzer"
                )
            elif section in ("flows", "levels", "temp"):
                sev = _worst(sev, "alert")
                reasons.append(
                    f"Flatline / stuck signal (range {rng:.3f} {units} over {count} samples)"
                )
            else:
                # Mild note only — analyzers can be very stable
                reasons.append(f"Very flat signal (range {rng:.3f} {units})")

    # Wild swing relative to average
    if rng is not None and avg is not None and abs(avg) > 1e-6 and count >= 40:
        rel = rng / abs(avg)
        if section == "levels" and rel > 1.5 and rng > 40:
            sev = _worst(sev, "watch")
            reasons.append(f"Large level swing ({rng:.1f}%)")
        if section == "flows" and rel > 3.0 and rng > 20:
            sev = _worst(sev, "watch")
            reasons.append(f"Large flow swing ({rng:.1f} {units})")
        if section in ("chlorine", "ph") and rel > 2.0:
            sev = _worst(sev, "watch")
            reasons.append(f"Unstable analyzer (range/avg = {rel:.1f})")

    if not reasons and sev == "ok":
        reasons.append("Looks normal for this day")

    return sev, reasons


def score_motor(
    short: str,
    desc: str,
    rt: DigitalRuntime | None,
    *,
    period_hours: float = 24.0,
) -> dict[str, Any]:
    if rt is None or rt.count <= 0:
        return {
            "tag": short,
            "description": desc,
            "severity": "unknown",
            "duty_pct": None,
            "hours": None,
            "starts": None,
            "stops": None,
            "reasons": ["No runtime samples"],
            "suggestion": None,
        }
    duty = (rt.on_hours / period_hours) * 100.0 if period_hours > 0 else 0.0
    sev: Severity = "ok"
    reasons: list[str] = []
    suggestion: str | None = None

    if rt.starts >= 96:
        sev = _worst(sev, "alert")
        reasons.append(f"Excessive cycling ({rt.starts} starts)")
        suggestion = "Check for hunting / control loop / low-level cut-in"
    elif rt.starts >= 48:
        sev = _worst(sev, "watch")
        reasons.append(f"High start count ({rt.starts})")
        suggestion = "Review start/stop setpoints and deadband"

    if duty >= 98 and rt.starts <= 2:
        # Continuous run is often fine for mixers
        if short.startswith("M") or short in ("RD1", "TD1"):
            reasons.append(f"Near-continuous duty ({duty:.0f}%) — expected for mixer/drive")
        else:
            sev = _worst(sev, "watch")
            reasons.append(f"Near-continuous duty ({duty:.0f}%)")
            suggestion = suggestion or "Confirm lead/lag rotation is working"

    if duty < 1 and rt.starts == 0:
        reasons.append("Idle all day")

    if not reasons:
        reasons.append(f"Duty {duty:.0f}% · {rt.starts} starts")

    return {
        "tag": short,
        "description": desc,
        "severity": sev,
        "duty_pct": round(duty, 1),
        "hours": round(rt.on_hours, 2),
        "starts": rt.starts,
        "stops": rt.stops,
        "reasons": reasons,
        "suggestion": suggestion,
    }


def _pump_groups(motors: list[dict[str, Any]]) -> list[tuple[list[str], str]]:
    """Groups to check for duty imbalance.

    The configured high-lift group (Setup roles) is always a group; other
    groups are auto-derived from short tags sharing an alpha prefix
    (LLP1+LLP2, SP1+SP2, HLP3+HLP4+HLP5, ...).
    """
    import re

    groups: dict[str, list[str]] = {}
    for m in motors:
        tag = str(m["tag"])
        stem = re.sub(r"\d+$", "", tag)
        # Single-letter stems (M1..M6 mixers) are unrelated units — skip
        if len(stem) >= 2 and stem != tag:
            groups.setdefault(stem, []).append(tag)

    out: list[tuple[list[str], str]] = []
    hlp = [str(t) for t in (site_roles().get("high_lift_pumps") or [])]
    if len(hlp) >= 2:
        out.append((hlp, "High-lift pumps"))
    covered = set(hlp)
    for stem, tags in groups.items():
        if len(tags) >= 2 and not (set(tags) & covered):
            out.append((tags, f"{stem} group"))
    return out


def _balance_suggestions(motors: list[dict[str, Any]]) -> list[str]:
    """Flag uneven duty within pump groups."""
    by_tag = {m["tag"]: m for m in motors}
    out: list[str] = []

    def group(tags: list[str], label: str) -> None:
        rows = [by_tag[t] for t in tags if t in by_tag and by_tag[t].get("duty_pct") is not None]
        if len(rows) < 2:
            return
        duties = [float(r["duty_pct"]) for r in rows]
        if max(duties) < 5:
            return  # all idle
        spread = max(duties) - min(duties)
        if spread >= 40:
            detail = ", ".join(f"{r['tag']} {r['duty_pct']:.0f}%" for r in rows)
            out.append(
                f"{label} duty imbalance ({spread:.0f} pt spread): {detail}. "
                "Check alternation / lead-lag."
            )

    for tags, label in _pump_groups(motors):
        group(tags, label)
    return out


def score_ct(ct_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not ct_rows:
        return {
            "severity": "unknown",
            "giardia_achieved": None,
            "giardia_required": None,
            "viruses_achieved": None,
            "viruses_required": None,
            "margin_giardia": None,
            "margin_viruses": None,
            "reasons": ["CT not available"],
        }
    by_label = {str(r.get("label") or ""): r for r in ct_rows}
    ach = by_label.get("CT Achieved") or {}
    req = by_label.get("CT Required") or {}
    g_a = ach.get("giardia")
    g_r = req.get("giardia")
    v_a = ach.get("viruses")
    v_r = req.get("viruses")

    reasons: list[str] = []
    sev: Severity = "ok"
    mg = (g_a - g_r) if isinstance(g_a, (int, float)) and isinstance(g_r, (int, float)) else None
    mv = (v_a - v_r) if isinstance(v_a, (int, float)) and isinstance(v_r, (int, float)) else None

    for name, margin, req_v in (("Giardia", mg, g_r), ("Viruses", mv, v_r)):
        if margin is None or req_v is None:
            continue
        if margin < 0:
            sev = _worst(sev, "alert")
            reasons.append(f"{name} CT below required (margin {margin:.2f})")
        elif req_v and margin < 0.15 * abs(float(req_v)):
            sev = _worst(sev, "watch")
            reasons.append(f"{name} CT thin margin ({margin:.2f})")
        else:
            reasons.append(f"{name} CT OK (margin {margin:.2f})")

    if not reasons:
        reasons.append("CT rows present but incomplete")

    return {
        "severity": sev,
        "giardia_achieved": g_a,
        "giardia_required": g_r,
        "viruses_achieved": v_a,
        "viruses_required": v_r,
        "margin_giardia": round(mg, 3) if isinstance(mg, (int, float)) else None,
        "margin_viruses": round(mv, 3) if isinstance(mv, (int, float)) else None,
        "reasons": reasons,
    }


def plant_metrics(
    trend: dict[str, Aggregate],
    motors: list[dict[str, Any]],
) -> dict[str, Any]:
    r = site_roles()

    def avg(tag: str | None) -> float | None:
        a = trend.get(tag) if tag else None
        return a.avg if a and a.count else None

    def total(tag: str | None) -> float | None:
        a = trend.get(tag) if tag else None
        return a.total if a and a.count else None

    raw_tag = r.get("raw_flow")
    treated_tag = r.get("treated_flow")
    raw = avg(raw_tag)
    treated = avg(treated_tag)
    dist = avg(r.get("distribution_flow"))
    clearwell = avg(r.get("clearwell_level"))
    tower = avg(r.get("tower_level"))
    cl2 = avg(r.get("treated_cl2"))

    recovery = None
    if raw and treated and raw > 0.1:
        recovery = round(100.0 * treated / raw, 1)

    hlp_tags = {str(t) for t in (r.get("high_lift_pumps") or [])}
    hlp_hours = sum(
        float(m["hours"] or 0)
        for m in motors
        if m["tag"] in hlp_tags and m.get("hours") is not None
    )

    raw_vol = total(raw_tag)
    treated_vol = total(treated_tag)
    return {
        "raw_flow_ls": round(raw, 2) if raw is not None else None,
        "treated_flow_ls": round(treated, 2) if treated is not None else None,
        "distribution_flow_ls": round(dist, 2) if dist is not None else None,
        "raw_volume_m3": round(raw_vol, 1) if raw_vol is not None else None,
        "treated_volume_m3": round(treated_vol, 1) if treated_vol is not None else None,
        "plant_recovery_pct": recovery,
        "clearwell_level_pct": round(clearwell, 1) if clearwell is not None else None,
        "tower_level_pct": round(tower, 1) if tower is not None else None,
        "treated_cl2_mgl": round(cl2, 3) if cl2 is not None else None,
        "high_lift_hours": round(hlp_hours, 2) if hlp_tags else None,
    }


def water_quality_index(trend: dict[str, Aggregate]) -> dict[str, Any]:
    """
    Combined drinking-water quality grade from treated Cl₂, filter turbidity, treated pH.
    Industry dashboards often roll these into one health index.
    """
    parts: list[dict[str, Any]] = []
    sev: Severity = "ok"

    def add(name: str, hist: str, score_fn) -> None:
        nonlocal sev
        a = trend.get(hist)
        if not a or not a.count:
            parts.append(
                {"name": name, "severity": "unknown", "value": None, "note": "No data"}
            )
            sev = _worst(sev, "unknown")
            return
        s, note, val = score_fn(a)
        parts.append({"name": name, "severity": s, "value": val, "note": note})
        sev = _worst(sev, s)

    def cl2(a: Aggregate):
        v = a.avg
        assert v is not None
        if v < 0.1:
            return "alert", f"avg {v:.2f} mg/L", round(v, 3)
        if v < 0.2 or v > 2.0:
            return "watch", f"avg {v:.2f} mg/L (band ~0.2–2.0)", round(v, 3)
        return "ok", f"avg {v:.2f} mg/L", round(v, 3)

    def filt(a: Aggregate):
        v = a.max if a.max is not None else a.avg
        assert v is not None
        if v >= 0.3:
            return "alert", f"max {v:.3f} NTU", round(v, 3)
        if v >= 0.1:
            return "watch", f"max {v:.3f} NTU", round(v, 3)
        return "ok", f"max {v:.3f} NTU", round(v, 3)

    def ph(a: Aggregate):
        v = a.avg
        assert v is not None
        if v < 6.5 or v > 8.5:
            return "watch", f"avg {v:.2f}", round(v, 2)
        return "ok", f"avg {v:.2f}", round(v, 2)

    r = site_roles()
    hist_to_short = {hist: tag for _s, _k, tag, _d, hist, _u, _t in trend_rows()}

    def label(prefix: str, hist: str) -> str:
        short = hist_to_short.get(hist, hist)
        return f"{prefix} ({short})"

    if r.get("treated_cl2"):
        add(label("Treated Cl₂", r["treated_cl2"]), r["treated_cl2"], cl2)
    for i, turb in enumerate(r.get("filter_turbidity") or [], start=1):
        add(label(f"Filter {i} turb", turb), turb, filt)
    if r.get("treated_ph"):
        add(label("Treated pH", r["treated_ph"]), r["treated_ph"], ph)

    if not parts:
        return {
            "severity": "unknown",
            "grade": None,
            "label": "Water quality roles not mapped — set them in Setup",
            "parts": [],
        }

    rank = {"ok": 100, "watch": 65, "alert": 25, "unknown": 50}
    scores = [rank.get(p["severity"], 50) for p in parts]
    grade = int(round(sum(scores) / max(1, len(scores))))
    return {
        "severity": sev,
        "grade": grade,
        "label": {
            "ok": "Water quality looks good",
            "watch": "Water quality — check yellow items",
            "alert": "Water quality — investigate",
            "unknown": "Water quality incomplete",
        }.get(sev, "Water quality"),
        "parts": parts,
    }


def filter_performance(trend: dict[str, Aggregate]) -> dict[str, Any]:
    """IFE-style strip for the configured filter turbidity tags."""
    hist_to_short = {hist: tag for _s, _k, tag, _d, hist, _u, _t in trend_rows()}
    filters = [
        (hist_to_short.get(hist, hist), hist, f"Filter {i}")
        for i, hist in enumerate(site_roles().get("filter_turbidity") or [], start=1)
    ]
    rows = []
    overall: Severity = "ok"
    for short, hist, label in filters:
        stats = _agg_stats(trend.get(hist))
        sev, reasons = score_analog(
            short=short, section="turbidity", units="NTU", stats=stats
        )
        overall = _worst(overall, sev)
        rows.append(
            {
                "tag": short,
                "label": label,
                "severity": sev,
                "avg": stats.get("avg"),
                "max": stats.get("max"),
                "min": stats.get("min"),
                "reasons": reasons,
            }
        )
    return {
        "severity": overall,
        "rows": rows,
        "note": "Optimization bands: watch ≥0.1 NTU max, alert ≥0.3 NTU max (ops heuristic).",
    }


def apply_baseline(
    instruments: list[dict[str, Any]],
    baseline_avgs: dict[str, float],
) -> None:
    """
    Mutate instruments with 7-day baseline comparison.
    baseline_avgs: short_tag -> mean of daily avgs over prior days.
    """
    for inst in instruments:
        tag = inst["tag"]
        base = baseline_avgs.get(tag)
        today = (inst.get("stats") or {}).get("avg")
        if base is None or today is None or abs(base) < 1e-9:
            continue
        delta_pct = 100.0 * (today - base) / abs(base)
        inst["baseline"] = {
            "avg_7d": round(base, 4),
            "today_avg": round(today, 4),
            "delta_pct": round(delta_pct, 1),
        }
        # Large drift vs recent normal
        if abs(delta_pct) >= 40 and inst["section"] in (
            "flows",
            "levels",
            "chlorine",
            "ph",
            "turbidity",
        ):
            inst["severity"] = _worst(inst["severity"], "watch")
            inst["reasons"] = [
                f"Today avg {delta_pct:+.0f}% vs 7-day baseline ({base:.3g})",
                *inst["reasons"],
            ]


def build_insights(
    *,
    date: str,
    trend: dict[str, Aggregate],
    motor_runtime: dict[str, DigitalRuntime],
    ct_rows: list[dict[str, Any]] | None,
    live: bool = False,
    sparklines: dict[str, list[float | None]] | None = None,
    hidden_trend: set[str] | None = None,
    hidden_motor: set[str] | None = None,
    hidden_sections: set[str] | None = None,
    baseline_avgs: dict[str, float] | None = None,
    period_hours: float = 24.0,
) -> dict[str, Any]:
    hidden_trend = hidden_trend or set()
    hidden_motor = hidden_motor or set()
    hidden_sections = hidden_sections or set()

    titles = section_titles()
    instruments: list[dict[str, Any]] = []
    for section, _kind, short, desc, hist, units, _tot in trend_rows():
        if section in hidden_sections or short in hidden_trend:
            continue
        stats = _agg_stats(trend.get(hist))
        sev, reasons = score_analog(short=short, section=section, units=units, stats=stats)
        instruments.append(
            {
                "tag": short,
                "historian": hist,
                "description": desc,
                "section": section,
                "sectionTitle": titles.get(section, section),
                "units": units,
                "severity": sev,
                "reasons": reasons,
                "stats": stats,
                "sparkline": (sparklines or {}).get(short) or (sparklines or {}).get(hist),
                "trendsHref": f"/reports/trends?tags={short}&preset=1d",
            }
        )

    if baseline_avgs:
        apply_baseline(instruments, baseline_avgs)

    motors = [
        score_motor(short, desc, motor_runtime.get(hist), period_hours=period_hours)
        for short, desc, hist in motor_rows()
        if short not in hidden_motor and "runtime" not in hidden_sections
    ]
    suggestions = _balance_suggestions(motors)
    for m in motors:
        if m.get("suggestion"):
            suggestions.append(f"{m['tag']}: {m['suggestion']}")
        m["trendsHref"] = None  # motors not on trend overlay by default

    for inst in instruments:
        if inst["severity"] in ("watch", "alert"):
            suggestions.append(
                f"{inst['tag']} ({inst['description']}): {inst['reasons'][0]}"
            )

    from tag_config import ct_enabled as _ct_enabled

    ct_on = _ct_enabled()
    if ct_on:
        ct = score_ct(ct_rows)
        if ct["severity"] in ("watch", "alert"):
            suggestions.insert(0, "Disinfection CT: " + "; ".join(ct["reasons"]))
    else:
        ct = {**score_ct(None), "reasons": ["CT disabled in Setup"], "disabled": True}

    wqi = water_quality_index(trend)
    if wqi["severity"] in ("watch", "alert"):
        suggestions.insert(0, f"Water quality index: {wqi['label']}")

    filt = filter_performance(trend)
    # Respect hidden turbidity tags in filter strip
    filt["rows"] = [
        r
        for r in filt["rows"]
        if r["tag"] not in hidden_trend and "turbidity" not in hidden_sections
    ]

    counts = {"ok": 0, "watch": 0, "alert": 0, "unknown": 0}
    for row in instruments + motors:
        counts[row["severity"]] = counts.get(row["severity"], 0) + 1
    if ct_on:
        counts[ct["severity"]] = counts.get(ct["severity"], 0) + 1
    if wqi.get("parts"):
        counts[wqi["severity"]] = counts.get(wqi["severity"], 0) + 1

    n = max(1, sum(counts.values()))
    score = int(
        round(
            100
            * (
                counts["ok"] * 1.0
                + counts["watch"] * 0.55
                + counts["unknown"] * 0.4
                + counts["alert"] * 0.1
            )
            / n
        )
    )
    overall: Severity = "ok"
    if counts["alert"] > 0:
        overall = "alert"
    elif counts["watch"] > 0:
        overall = "watch"

    instruments.sort(key=lambda r: (-_sev_rank(r["severity"]), r["tag"]))
    motors.sort(key=lambda r: (-_sev_rank(r["severity"]), -(r.get("starts") or 0), r["tag"]))

    return {
        "date": date,
        "live": live,
        "xlreporter": False,
        "overall": {
            "severity": overall,
            "score": score,
            "counts": counts,
            "label": {
                "ok": "Plant looks healthy",
                "watch": "Check yellow items",
                "alert": "Investigate red items",
                "unknown": "Incomplete data",
            }.get(overall, "Status"),
        },
        "metrics": plant_metrics(trend, motors),
        "water_quality": wqi,
        "filters": filt,
        "ct": ct,
        "instruments": instruments,
        "motors": motors,
        "suggestions": suggestions[:20],
        "legend": {
            "ok": "Green — trend/behavior looks normal for this day",
            "watch": "Yellow — unusual; worth a look",
            "alert": "Red — likely fault, stuck signal, or CT shortfall",
            "unknown": "Grey — not enough data",
        },
        "disclaimer": (
            "Scores are operator decision-support heuristics from DLGLOG "
            "min/max/avg/runtime — not calibrated plant setpoints or alarms. "
            "Hide unused equipment under Manage items."
        ),
    }
