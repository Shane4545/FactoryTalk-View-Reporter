"""Disk cache for per-day DLGLOG aggregates + series — makes monthly/trends fast."""
from __future__ import annotations

import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from dlglog_reader import (
    Aggregate,
    DigitalRuntime,
    _collect_day_buckets,
    load_model_day,
    load_motors_day,
)
from app_paths import app_home

from eu_scale import EU_CACHE_VERSION

SERIES_POINTS_PER_DAY = 1200


def _cache_version() -> str:
    """EU version + site tag-config fingerprint so profile edits re-aggregate."""
    try:
        from tag_config import cache_fingerprint

        fp = cache_fingerprint()
    except Exception:
        fp = "chalk"
    return EU_CACHE_VERSION if fp == "chalk" else f"{EU_CACHE_VERSION}-{fp}"


def _agg_to_dict(a: Aggregate) -> dict:
    return {
        "min": a.min,
        "max": a.max,
        "avg": a.avg,
        "total": a.total,
        "time_of_min": a.time_of_min,
        "time_of_max": a.time_of_max,
        "count": a.count,
    }


def _dict_to_agg(d: dict) -> Aggregate:
    return Aggregate(
        min=d.get("min"),
        max=d.get("max"),
        avg=d.get("avg"),
        total=d.get("total"),
        time_of_min=d.get("time_of_min"),
        time_of_max=d.get("time_of_max"),
        count=int(d.get("count") or 0),
    )


def _rt_to_dict(r: DigitalRuntime) -> dict:
    return {
        "starts": r.starts,
        "stops": r.stops,
        "on_hours": r.on_hours,
        "count": r.count,
        "on_threshold": r.on_threshold,
    }


def _dict_to_rt(d: dict) -> DigitalRuntime:
    return DigitalRuntime(
        starts=int(d.get("starts") or 0),
        stops=int(d.get("stops") or 0),
        on_hours=float(d.get("on_hours") or 0.0),
        count=int(d.get("count") or 0),
        on_threshold=float(d.get("on_threshold") or 0.5),
    )


def _float_mtime(model_dir: Path, day: datetime) -> float | None:
    stem = day.strftime("%Y %m %d 0000")
    fl = model_dir / f"{stem} (Float).DAT"
    if not fl.is_file():
        return None
    return fl.stat().st_mtime


def _cache_path(model: str, day: datetime) -> Path:
    root = app_home() / "cache" / "days" / _cache_version()
    return root / model / f"{day.strftime('%Y-%m-%d')}.json"


def load_model_day_cached(
    model_dir: Path,
    day: datetime,
    want_tags: set[str] | None = None,
) -> dict[str, Aggregate]:
    model = model_dir.name
    mtime = _float_mtime(model_dir, day)
    if mtime is None:
        raise FileNotFoundError(model_dir / day.strftime("%Y %m %d 0000 (Float).DAT"))

    path = _cache_path(model, day)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("mtime") == mtime and "aggregates" in raw:
                return {k: _dict_to_agg(v) for k, v in raw["aggregates"].items()}
        except (json.JSONDecodeError, OSError, TypeError, KeyError):
            pass

    aggs = load_model_day(model_dir, day, want_tags=want_tags)
    # Only cache full-day loads (no tag filter) so monthly reuse is safe
    if want_tags is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mtime": mtime,
            "model": model,
            "date": day.strftime("%Y-%m-%d"),
            "aggregates": {k: _agg_to_dict(v) for k, v in aggs.items()},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    return aggs


def load_motors_day_cached(
    model_dir: Path,
    day: datetime,
    want_tags: set[str] | None = None,
    *,
    on_threshold: float = 0.5,
) -> tuple[dict[str, Aggregate], dict[str, DigitalRuntime]]:
    model = model_dir.name
    mtime = _float_mtime(model_dir, day)
    if mtime is None:
        raise FileNotFoundError(model_dir / day.strftime("%Y %m %d 0000 (Float).DAT"))

    path = _cache_path(f"{model}__runtime", day)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if (
                raw.get("mtime") == mtime
                and raw.get("on_threshold") == on_threshold
                and "aggregates" in raw
                and "runtime" in raw
            ):
                aggs = {k: _dict_to_agg(v) for k, v in raw["aggregates"].items()}
                runtime = {k: _dict_to_rt(v) for k, v in raw["runtime"].items()}
                if want_tags is not None:
                    aggs = {k: v for k, v in aggs.items() if k in want_tags}
                    runtime = {k: v for k, v in runtime.items() if k in want_tags}
                return aggs, runtime
        except (json.JSONDecodeError, OSError, TypeError, KeyError):
            pass

    aggs, runtime = load_motors_day(
        model_dir, day, want_tags=None, on_threshold=on_threshold
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mtime": mtime,
        "model": model,
        "date": day.strftime("%Y-%m-%d"),
        "on_threshold": on_threshold,
        "aggregates": {k: _agg_to_dict(v) for k, v in aggs.items()},
        "runtime": {k: _rt_to_dict(v) for k, v in runtime.items()},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    if want_tags is not None:
        aggs = {k: v for k, v in aggs.items() if k in want_tags}
        runtime = {k: v for k, v in runtime.items() if k in want_tags}
    return aggs, runtime


def _downsample(
    points: list[tuple[datetime, float]], max_points: int
) -> list[tuple[datetime, float]]:
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    return [points[int(i * step)] for i in range(max_points)]


def _series_cache_path(model: str, day: datetime) -> Path:
    root = app_home() / "cache" / "series" / _cache_version()
    return root / model / f"{day.strftime('%Y-%m-%d')}.pkl"


def ensure_day_series_cache(model_dir: Path, day: datetime) -> dict:
    """
    One Float.DAT pass → all tags' stats + downsampled points for the day.
    First call ~few seconds; later tag/trend requests for that day are instant.
    """
    model = model_dir.name
    mtime = _float_mtime(model_dir, day)
    if mtime is None:
        raise FileNotFoundError(model_dir / day.strftime("%Y %m %d 0000 (Float).DAT"))

    path = _series_cache_path(model, day)
    if path.is_file():
        try:
            raw = pickle.loads(path.read_bytes())
            if raw.get("mtime") == mtime and "tags" in raw:
                return raw
        except (OSError, pickle.PickleError, TypeError, KeyError):
            pass

    buckets = _collect_day_buckets(model_dir, day, want_tags=None)
    from eu_scale import FLOW_TAGS, to_eu

    tags_out: dict = {}
    for name, pts in buckets.items():
        if not pts:
            continue
        eu_pts = [(ts, to_eu(name, v)) for ts, v in pts]
        if name in FLOW_TAGS:
            # Negative EU flow is a scaling artifact — clamp like the Daily does.
            eu_pts = [(ts, max(0.0, v)) for ts, v in eu_pts]
        vals = [v for _, v in eu_pts]
        lo_i = min(range(len(eu_pts)), key=lambda i: eu_pts[i][1])
        hi_i = max(range(len(eu_pts)), key=lambda i: eu_pts[i][1])
        sampled = _downsample(eu_pts, SERIES_POINTS_PER_DAY)
        tags_out[name] = {
            "count": len(eu_pts),
            "min": min(vals),
            "max": max(vals),
            "avg": sum(vals) / len(vals),
            "timeOfMin": eu_pts[lo_i][0].strftime("%Y-%m-%d %H:%M:%S"),
            "timeOfMax": eu_pts[hi_i][0].strftime("%Y-%m-%d %H:%M:%S"),
            "points": [
                (ts.strftime("%Y-%m-%d %H:%M:%S"), round(v, 6)) for ts, v in sampled
            ],
        }

    payload = {
        "mtime": mtime,
        "model": model,
        "date": day.strftime("%Y-%m-%d"),
        "tags": tags_out,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    return payload


def load_series_cached(
    model_dir: Path,
    tag: str,
    start: datetime,
    end: datetime,
    *,
    max_points: int = 2000,
) -> dict:
    """Chart series using per-day all-tag cache (one scan per day, shared)."""
    points: list[tuple[str, float]] = []
    total_count = 0
    mins: list[float] = []
    maxs: list[float] = []
    weighted = 0.0
    weight_n = 0
    tmin: str | None = None
    tmax: str | None = None
    tmin_v = float("inf")
    tmax_v = float("-inf")

    d = datetime(start.year, start.month, start.day)
    last = datetime(end.year, end.month, end.day)
    while d <= last:
        try:
            day_cache = ensure_day_series_cache(model_dir, d)
        except FileNotFoundError:
            d += timedelta(days=1)
            continue
        entry = day_cache.get("tags", {}).get(tag)
        if not entry:
            d += timedelta(days=1)
            continue
        total_count += int(entry.get("count") or 0)
        if entry.get("min") is not None:
            mins.append(float(entry["min"]))
        if entry.get("max") is not None:
            maxs.append(float(entry["max"]))
        c = int(entry.get("count") or 0)
        if c and entry.get("avg") is not None:
            weighted += float(entry["avg"]) * c
            weight_n += c
        if entry.get("min") is not None and entry["min"] < tmin_v:
            tmin_v = float(entry["min"])
            tmin = entry.get("timeOfMin")
        if entry.get("max") is not None and entry["max"] > tmax_v:
            tmax_v = float(entry["max"])
            tmax = entry.get("timeOfMax")
        for t_s, v in entry.get("points") or []:
            try:
                ts = datetime.strptime(t_s, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if start <= ts <= end:
                points.append((t_s, float(v)))
        d += timedelta(days=1)

    if not points and total_count == 0:
        return {
            "tag": tag,
            "start": start.isoformat(sep=" "),
            "end": end.isoformat(sep=" "),
            "count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "points": [],
        }

    if len(points) > max_points:
        step = len(points) / max_points
        points = [points[int(i * step)] for i in range(max_points)]

    return {
        "tag": tag,
        "start": start.isoformat(sep=" "),
        "end": end.isoformat(sep=" "),
        "count": total_count,
        "min": min(mins) if mins else None,
        "max": max(maxs) if maxs else None,
        "avg": (weighted / weight_n) if weight_n else None,
        "timeOfMin": tmin,
        "timeOfMax": tmax,
        "points": [{"t": t, "v": v} for t, v in points],
    }
