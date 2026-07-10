"""Multi-day DLGLOG rollups for Monthly / Custom reports."""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any

from chalk_report_builder import build_daily
from tag_config import motor_rows
from day_cache import load_model_day_cached, load_motors_day_cached
from dlglog_reader import Aggregate, DigitalRuntime
from plant_settings import load_config, model_name


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    last = monthrange(year, month)[1]
    return datetime(year, month, 1), datetime(year, month, last)


def iter_days(start: datetime, end: datetime):
    d = datetime(start.year, start.month, start.day)
    last = datetime(end.year, end.month, end.day)
    while d <= last:
        yield d
        d += timedelta(days=1)


def merge_aggregates(parts: list[Aggregate]) -> Aggregate | None:
    if not parts:
        return None
    mins = [p.min for p in parts if p.min is not None]
    maxs = [p.max for p in parts if p.max is not None]
    wsum = 0.0
    w = 0
    total = 0.0
    count = 0
    tmin = None
    tmax = None
    gmin = None
    gmax = None
    for p in parts:
        if p.count:
            count += p.count
        if p.avg is not None and p.count:
            wsum += p.avg * p.count
            w += p.count
        if p.total is not None:
            total += p.total
        if p.min is not None and (gmin is None or p.min < gmin):
            gmin = p.min
            tmin = p.time_of_min
        if p.max is not None and (gmax is None or p.max > gmax):
            gmax = p.max
            tmax = p.time_of_max
    return Aggregate(
        min=min(mins) if mins else None,
        max=max(maxs) if maxs else None,
        avg=(wsum / w) if w else None,
        total=total if count else None,
        time_of_min=tmin,
        time_of_max=tmax,
        count=count,
    )


def merge_runtime(parts: list[DigitalRuntime]) -> DigitalRuntime | None:
    if not parts:
        return None
    return DigitalRuntime(
        starts=sum(p.starts for p in parts),
        stops=sum(p.stops for p in parts),
        on_hours=sum(p.on_hours for p in parts),
        count=sum(p.count for p in parts),
        on_threshold=parts[0].on_threshold,
    )


def load_period(
    root,
    start: datetime,
    end: datetime,
) -> tuple[
    dict[str, Aggregate],
    dict[str, Aggregate],
    dict[str, Aggregate],
    dict[str, DigitalRuntime],
    list[str],
    list[str],
]:
    cfg = load_config()
    trend_name = model_name(cfg, "trend")
    motors_name = model_name(cfg, "motors")
    feedback_name = model_name(cfg, "feedback")

    trend_parts: dict[str, list[Aggregate]] = {}
    motor_parts: dict[str, list[Aggregate]] = {}
    fb_parts: dict[str, list[Aggregate]] = {}
    rt_parts: dict[str, list[DigitalRuntime]] = {}
    days_ok: list[str] = []
    days_miss: list[str] = []
    want_motors = {h for _, _, h in motor_rows()}

    for day in iter_days(start, end):
        ds = day.strftime("%Y-%m-%d")
        try:
            trend = load_model_day_cached(root / trend_name, day)
        except FileNotFoundError:
            days_miss.append(ds)
            continue
        days_ok.append(ds)
        for name, agg in trend.items():
            trend_parts.setdefault(name, []).append(agg)
        try:
            motors, rt = load_motors_day_cached(
                root / motors_name, day, want_tags=want_motors
            )
            for name, agg in motors.items():
                motor_parts.setdefault(name, []).append(agg)
            for name, dig in rt.items():
                rt_parts.setdefault(name, []).append(dig)
        except FileNotFoundError:
            pass
        try:
            fb = load_model_day_cached(root / feedback_name, day)
            for name, agg in fb.items():
                fb_parts.setdefault(name, []).append(agg)
        except FileNotFoundError:
            pass

    trend = {
        k: v
        for k, v in ((k, merge_aggregates(v)) for k, v in trend_parts.items())
        if v
    }
    motors = {
        k: v
        for k, v in ((k, merge_aggregates(v)) for k, v in motor_parts.items())
        if v
    }
    feedback = {
        k: v
        for k, v in ((k, merge_aggregates(v)) for k, v in fb_parts.items())
        if v
    }
    runtime = {
        k: v
        for k, v in ((k, merge_runtime(v)) for k, v in rt_parts.items())
        if v
    }
    return trend, motors, feedback, runtime, days_ok, days_miss


def build_period_report(
    root,
    start: datetime,
    end: datetime,
    *,
    subtitle: str,
    period_label: str,
) -> dict[str, Any]:
    trend, motors, feedback, runtime, days_ok, days_miss = load_period(root, start, end)
    if not days_ok:
        raise FileNotFoundError(
            f"No trend-model days between {start.date()} and {end.date()}"
        )
    from report_prefs import hidden_sets

    hide = hidden_sets()
    report = build_daily(
        start,
        trend,
        motors,
        feedback,
        motor_runtime=runtime,
        hidden_trend=hide["trend"],
        hidden_motor=hide["motor"],
        hidden_feedback=hide["feedback"],
        hidden_sections=hide["section"],
    )
    report["subtitle"] = subtitle
    report["periodLabel"] = period_label
    report["startDate"] = start.strftime("%Y-%m-%d 00:00:00")
    report["endDate"] = end.strftime("%Y-%m-%d 23:59:59")
    report["live"] = False
    report["meta_period"] = {
        "days_loaded": len(days_ok),
        "days_missing": len(days_miss),
        "missing_dates": days_miss[:31],
        "first_loaded": days_ok[0],
        "last_loaded": days_ok[-1],
    }
    return report
