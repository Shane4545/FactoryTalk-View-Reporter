"""Prove Ops Reporter reads FactoryTalk DLGLOG — not XLReporter, not demo."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chalk_report_builder import build_daily
from dlglog_reader import load_model_day
from main import list_float_dates, resolve_dlglog

OUT = Path(__file__).resolve().parents[1] / "proof"
OUT.mkdir(exist_ok=True)


def main() -> int:
    root = resolve_dlglog()
    dates = list_float_dates(root / "WTP_TREND")
    # Prefer a mid-range full day
    day_s = "2026-06-13" if "2026-06-13" in dates else dates[-2]
    day = datetime.strptime(day_s, "%Y-%m-%d")

    float_path = root / "WTP_TREND" / f"{day.strftime('%Y %m %d 0000')} (Float).DAT"
    tag_path = root / "WTP_TREND" / f"{day.strftime('%Y %m %d 0000')} (Tagname).DAT"

    trend = load_model_day(root / "WTP_TREND", day)
    motors = load_model_day(root / "WTP_MOTORS", day)
    feedback = load_model_day(root / "WTP_FEEDBACK", day)
    report = build_daily(day, trend, motors, feedback)

    fit = trend["WTP_FIT101_VALUE"]
    proof = {
        "ok": True,
        "xlreporter": False,
        "demo_data": False,
        "dlglog_root": str(root),
        "date": day_s,
        "float_file": str(float_path),
        "float_bytes": float_path.stat().st_size,
        "tagname_file": str(tag_path),
        "available_dates": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "tag_counts": {
            "trend": len(trend),
            "motors": len(motors),
            "feedback": len(feedback),
        },
        "FIT101": {
            "historian": "WTP_FIT101_VALUE",
            "samples": fit.count,
            "min": fit.min,
            "max": fit.max,
            "avg": fit.avg,
            "time_of_min": fit.time_of_min,
            "time_of_max": fit.time_of_max,
        },
        "sections": [s["id"] for s in report["sections"]],
        "section_row_counts": {s["id"]: len(s["rows"]) for s in report["sections"]},
    }

    out_json = OUT / f"proof_{day_s}.json"
    out_json.write_text(json.dumps(proof, indent=2), encoding="utf-8")

    # Human-readable summary
    lines = [
        "# Ops Reporter — FactoryTalk proof",
        "",
        f"**Date:** {day_s}",
        f"**DLGLOG:** `{root}`",
        f"**XLReporter used:** NO",
        f"**Demo data:** NO",
        "",
        f"Float file: `{float_path.name}` ({float_path.stat().st_size:,} bytes)",
        f"Available trend days: {len(dates)} ({dates[0]} → {dates[-1]})",
        "",
        "## WTP_FIT101_VALUE (Raw Water Flow)",
        f"- samples: **{fit.count}**",
        f"- min: **{fit.min:.4f}** at {fit.time_of_min}",
        f"- max: **{fit.max:.4f}** at {fit.time_of_max}",
        f"- avg: **{fit.avg:.4f}**",
        "",
        "## Tag coverage",
        f"- trend: {len(trend)}",
        f"- motors: {len(motors)}",
        f"- feedback: {len(feedback)}",
        "",
        "## Report sections",
        ", ".join(s["id"] for s in report["sections"]),
        "",
        f"JSON: `{out_json}`",
    ]
    out_md = OUT / f"proof_{day_s}.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
