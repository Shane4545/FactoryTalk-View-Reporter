"""
FactoryTalk View SE DLGLOG Float.DAT reader.

Record layout verified 2026-07-09 against:
  C:\\XLRprojects\\CHALK RIVER WTP REV25 SIMULATE\\Data\\SCADA\\DLGLOG\\WTP_TREND\\2026 06 13 0000 (Float).DAT

After a dBASE-like schema header, each sample is a fixed 39-byte record:
  Date(8) Time(8) Millitm(3) TagIndex(5 ASCII) pad(4) Value(float32 LE) Status(1) Marker(1) Internal(4)
Leading byte before Date is a space separator included in the 39-byte stride from Date-to-Date.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


RECORD_SIZE = 39
# Offsets relative to start of Date (YYYYMMDD) within each record
OFF_DATE = 0
OFF_TIME = 8
OFF_MILLI = 16
OFF_TAGIDX = 19  # 5 ASCII chars
OFF_VALUE = 28  # after "    N\x00\x00\x00 " pattern — verified
OFF_STATUS = 32
OFF_MARKER = 33
OFF_INTERNAL = 34


@dataclass
class Sample:
    ts: datetime
    tag_index: int
    value: float
    status: str


@dataclass
class Aggregate:
    min: float | None
    max: float | None
    avg: float | None
    total: float | None
    time_of_min: str | None
    time_of_max: str | None
    count: int


@dataclass
class DigitalRuntime:
    """Edge counts + ON duration for a digital RUNNING tag."""

    starts: int
    stops: int
    on_hours: float
    count: int
    on_threshold: float = 0.5


def _find_data_start(data: bytes) -> int:
    """First YYYYMMDD after schema header (Date field name at offset 32)."""
    pos = data.find(b"Date")
    search_from = pos if pos >= 0 else 0
    # Find first digit run that looks like YYYYMMDD
    i = search_from
    while i < len(data) - 8:
        chunk = data[i : i + 8]
        if chunk.isdigit() and chunk[:2] in (b"20", b"19"):
            # Prefer records that also have HH:MM:SS right after
            if i + 16 <= len(data) and data[i + 10 : i + 11] == b":":
                return i
        i += 1
    raise ValueError("no data records found in Float.DAT")


def parse_tagname_csv(path: Path) -> dict[int, str]:
    """Parse Tagname.csv → {index: tag}."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[int, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.lower().startswith("tagname"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        try:
            idx = int(parts[1])
        except ValueError:
            continue
        if name:
            out[idx] = name
    return out


def parse_tagname_dat(path: Path) -> dict[int, str]:
    """Parse Tagname.DAT for the day. Prefer same-day .csv only if present.

    Do not fall back to an older Tagname.csv — indices can change over time.
    """
    import re

    if path.suffix.lower() == ".csv":
        return parse_tagname_csv(path)

    same_day_csv = path.with_name(path.name.replace("(Tagname).DAT", "(Tagname).csv"))
    if same_day_csv.is_file():
        return parse_tagname_csv(same_day_csv)

    raw = path.read_bytes()
    text = raw.decode("latin-1", errors="replace")
    out: dict[int, str] = {}
    # Rows look like: NAME + spaces + "{index}{TagType} {TagDataType}"
    # e.g. index 0 type 2 → "02 1"; index 10 type 2 → "102 1"
    for m in re.finditer(
        r"([A-Za-z_][A-Za-z0-9_]{2,})\s+(\d+)(\d)\s*(-?\d+)",
        text,
    ):
        name, idx_s, _typ, _dt = m.groups()
        if name in ("Tagname", "TTagIndex", "TagType", "TagDataTyp"):
            continue
        out[int(idx_s)] = name
    if not out:
        raise ValueError(f"could not parse tag index: {path}")
    return out


def _parse_ts_fast(date_s: bytes, time_s: bytes, milli_s: bytes) -> datetime | None:
    """Faster than datetime.strptime for YYYYMMDD + HH:MM:SS records."""
    try:
        y = (date_s[0] - 48) * 1000 + (date_s[1] - 48) * 100 + (date_s[2] - 48) * 10 + (
            date_s[3] - 48
        )
        mo = (date_s[4] - 48) * 10 + (date_s[5] - 48)
        d = (date_s[6] - 48) * 10 + (date_s[7] - 48)
        hh = (time_s[0] - 48) * 10 + (time_s[1] - 48)
        mm = (time_s[3] - 48) * 10 + (time_s[4] - 48)
        ss = (time_s[6] - 48) * 10 + (time_s[7] - 48)
        milli = 0
        for b in milli_s:
            if 48 <= b <= 57:
                milli = milli * 10 + (b - 48)
        return datetime(y, mo, d, hh, mm, ss, milli * 1000)
    except (ValueError, IndexError):
        return None


def iter_float_samples(path: Path):
    data = path.read_bytes()
    start = _find_data_start(data)
    # Records are 39 bytes; Date sits at offset 0 of each record window.
    # Observed: Date positions advance by 39; byte before first Date is space.
    # Align so each record begins one byte before Date (the space), OR at Date
    # with size 39 including trailing fields.
    # Using Date-aligned 39-byte windows:
    end = start + ((len(data) - start) // RECORD_SIZE) * RECORD_SIZE
    for off in range(start, end, RECORD_SIZE):
        rec = data[off : off + RECORD_SIZE]
        if len(rec) < RECORD_SIZE:
            break
        date_b = rec[OFF_DATE : OFF_DATE + 8]
        if not (date_b[0] == 50 or date_b[0] == 49):  # '2' or '1'
            continue
        try:
            idx_s = rec[OFF_TAGIDX : OFF_TAGIDX + 5].decode("ascii").strip()
            tag_index = int(idx_s)
            value = struct.unpack_from("<f", rec, OFF_VALUE)[0]
            status = chr(rec[OFF_STATUS]) if rec[OFF_STATUS] >= 32 else "?"
        except (UnicodeDecodeError, ValueError, struct.error):
            continue
        ts = _parse_ts_fast(
            date_b,
            rec[OFF_TIME : OFF_TIME + 8],
            rec[OFF_MILLI : OFF_MILLI + 3],
        )
        if ts is None:
            continue
        yield Sample(ts=ts, tag_index=tag_index, value=value, status=status)


def aggregate_day(
    float_path: Path,
    tag_index: dict[int, str],
    *,
    want_tags: set[str] | None = None,
) -> dict[str, Aggregate]:
    buckets: dict[str, list[tuple[datetime, float]]] = {}
    for sample in iter_float_samples(float_path):
        name = tag_index.get(sample.tag_index)
        if not name:
            continue
        if want_tags is not None and name not in want_tags:
            continue
        # Skip obvious bad quality if status is E (error) — keep S/U/blank for now
        if sample.status == "E":
            continue
        if sample.value != sample.value:  # NaN
            continue
        buckets.setdefault(name, []).append((sample.ts, sample.value))

    return _aggregates_from_buckets(buckets)


def resolve_day_files(model_dir: Path, day: datetime) -> tuple[Path, Path]:
    """Return (tagname_path, float_path) for YYYY MM DD 0000 naming."""
    stem = day.strftime("%Y %m %d 0000")
    tag = model_dir / f"{stem} (Tagname).DAT"
    fl = model_dir / f"{stem} (Float).DAT"
    if not fl.is_file():
        raise FileNotFoundError(fl)
    if not tag.is_file():
        # some days only have csv
        csv = model_dir / f"{stem} (Tagname).csv"
        if csv.is_file():
            return csv, fl
        raise FileNotFoundError(tag)
    return tag, fl


def load_model_day(model_dir: Path, day: datetime, want_tags: set[str] | None = None):
    tag_path, float_path = resolve_day_files(model_dir, day)
    if tag_path.suffix.lower() == ".csv":
        index = parse_tagname_csv(tag_path)
    else:
        index = parse_tagname_dat(tag_path)
    return aggregate_day(float_path, index, want_tags=want_tags)


def _collect_day_buckets(
    model_dir: Path,
    day: datetime,
    want_tags: set[str] | None = None,
) -> dict[str, list[tuple[datetime, float]]]:
    tag_path, float_path = resolve_day_files(model_dir, day)
    if tag_path.suffix.lower() == ".csv":
        index = parse_tagname_csv(tag_path)
    else:
        index = parse_tagname_dat(tag_path)
    buckets: dict[str, list[tuple[datetime, float]]] = {}
    for sample in iter_float_samples(float_path):
        name = index.get(sample.tag_index)
        if not name:
            continue
        if want_tags is not None and name not in want_tags:
            continue
        if sample.status == "E" or sample.value != sample.value:
            continue
        buckets.setdefault(name, []).append((sample.ts, sample.value))
    return buckets


def _aggregates_from_buckets(
    buckets: dict[str, list[tuple[datetime, float]]],
) -> dict[str, Aggregate]:
    """Build aggregates; apply EU scaling for known WTP_TREND analog tags."""
    from eu_scale import FLOW_TAGS, FLOW_TOTAL_FACTOR, to_eu

    out: dict[str, Aggregate] = {}
    for name, pts in buckets.items():
        if not pts:
            continue
        # Scale raw → engineering units before min/max/avg (CT + Daily parity).
        eu_pts = [(ts, to_eu(name, v)) for ts, v in pts]
        vals = [v for _, v in eu_pts]
        tmin = min(eu_pts, key=lambda p: p[1])
        tmax = max(eu_pts, key=lambda p: p[1])
        total = sum(vals)
        if name in FLOW_TAGS and len(eu_pts) >= 2:
            # Integral L/s · s → m³, then PLC Daily TOTAL factor (eu_scale.py).
            ordered = sorted(eu_pts, key=lambda p: p[0])
            integ = 0.0
            for i in range(len(ordered) - 1):
                e = max(0.0, ordered[i][1])
                dt = (ordered[i + 1][0] - ordered[i][0]).total_seconds()
                if dt > 0:
                    integ += e * dt
            total = (integ / 1000.0) * FLOW_TOTAL_FACTOR.get(name, 1.0)
        out[name] = Aggregate(
            min=max(0.0, min(vals)) if name in FLOW_TAGS else min(vals),
            max=max(vals),
            avg=sum(vals) / len(vals),
            total=total,
            time_of_min=tmin[0].strftime("%H:%M"),
            time_of_max=tmax[0].strftime("%H:%M"),
            count=len(vals),
        )
    return out


def load_motors_day(
    model_dir: Path,
    day: datetime,
    want_tags: set[str] | None = None,
    *,
    on_threshold: float = 0.5,
) -> tuple[dict[str, Aggregate], dict[str, DigitalRuntime]]:
    """One Float.DAT pass → analog aggregates + digital start/stop/ON hours."""
    from datetime import timedelta

    buckets = _collect_day_buckets(model_dir, day, want_tags=want_tags)
    aggs = _aggregates_from_buckets(buckets)
    day_end = datetime(day.year, day.month, day.day) + timedelta(days=1)
    runtime = {
        name: digital_runtime_from_points(
            pts, on_threshold=on_threshold, day_end=day_end
        )
        for name, pts in buckets.items()
    }
    return aggs, runtime


def digital_runtime_from_points(
    pts: list[tuple[datetime, float]],
    *,
    on_threshold: float = 0.5,
    day_end: datetime | None = None,
) -> DigitalRuntime:
    """
    Count starts/stops and ON hours from a sorted digital series.

    ON rule matches XLReporter Performance Analysis docs for Chalk River:
    value < 0.5 = off, >= 0.5 = on (history_data_binding.md).
    Start = rising edge off→on; stop = falling edge on→off.
    ON hours = sum of intervals where the *previous* sample was ON
    (state held until next sample), plus hold to day_end if still ON.
    """
    if not pts:
        return DigitalRuntime(starts=0, stops=0, on_hours=0.0, count=0, on_threshold=on_threshold)

    ordered = sorted(pts, key=lambda p: p[0])
    starts = stops = 0
    on_seconds = 0.0
    prev_on: bool | None = None
    prev_ts: datetime | None = None

    for ts, val in ordered:
        on = val >= on_threshold
        if prev_on is not None and prev_ts is not None:
            if prev_on:
                on_seconds += (ts - prev_ts).total_seconds()
            if on and not prev_on:
                starts += 1
            elif (not on) and prev_on:
                stops += 1
        prev_on = on
        prev_ts = ts

    if day_end is not None and prev_on and prev_ts is not None and day_end > prev_ts:
        on_seconds += (day_end - prev_ts).total_seconds()

    return DigitalRuntime(
        starts=starts,
        stops=stops,
        on_hours=on_seconds / 3600.0,
        count=len(ordered),
        on_threshold=on_threshold,
    )


def load_digital_runtime_day(
    model_dir: Path,
    day: datetime,
    want_tags: set[str] | None = None,
    *,
    on_threshold: float = 0.5,
) -> dict[str, DigitalRuntime]:
    """Per-tag start/stop counts and ON hours for one calendar day."""
    _, runtime = load_motors_day(
        model_dir, day, want_tags=want_tags, on_threshold=on_threshold
    )
    return runtime


def list_model_tags(model_dir: Path) -> dict[int, str]:
    """Latest Tagname.DAT in folder."""
    tags = sorted(model_dir.glob("* (Tagname).DAT"), reverse=True)
    if not tags:
        raise FileNotFoundError(f"no Tagname.DAT in {model_dir}")
    return parse_tagname_dat(tags[0])


def load_series(
    model_dir: Path,
    tag: str,
    start: datetime,
    end: datetime,
    *,
    max_points: int = 2000,
) -> dict:
    """Time series for one tag over [start, end], downsampled for charts."""
    from datetime import timedelta

    points: list[tuple[datetime, float]] = []
    d = datetime(start.year, start.month, start.day)
    last = datetime(end.year, end.month, end.day)
    while d <= last:
        try:
            tag_path, float_path = resolve_day_files(model_dir, d)
        except FileNotFoundError:
            d += timedelta(days=1)
            continue
        index = (
            parse_tagname_csv(tag_path)
            if tag_path.suffix.lower() == ".csv"
            else parse_tagname_dat(tag_path)
        )
        want_idx = {i for i, n in index.items() if n == tag}
        if not want_idx:
            d += timedelta(days=1)
            continue
        for sample in iter_float_samples(float_path):
            if sample.tag_index not in want_idx:
                continue
            if sample.status == "E" or sample.value != sample.value:
                continue
            if start <= sample.ts <= end:
                points.append((sample.ts, sample.value))
        d += timedelta(days=1)

    points.sort(key=lambda p: p[0])
    if not points:
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

    vals = [v for _, v in points]
    # downsample evenly
    if len(points) > max_points:
        step = len(points) / max_points
        sampled = [points[int(i * step)] for i in range(max_points)]
    else:
        sampled = points

    return {
        "tag": tag,
        "start": start.isoformat(sep=" "),
        "end": end.isoformat(sep=" "),
        "count": len(points),
        "min": min(vals),
        "max": max(vals),
        "avg": sum(vals) / len(vals),
        "timeOfMin": min(points, key=lambda p: p[1])[0].strftime("%Y-%m-%d %H:%M:%S"),
        "timeOfMax": max(points, key=lambda p: p[1])[0].strftime("%Y-%m-%d %H:%M:%S"),
        "points": [
            {"t": ts.strftime("%Y-%m-%d %H:%M:%S"), "v": round(v, 6)} for ts, v in sampled
        ],
    }


def preset_window(preset: str, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Operator presets: 1m, 1h, 1d, 7d, 1M, 1y, today."""
    from datetime import timedelta

    now = now or datetime.now()
    presets = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "1M": timedelta(days=30),
        "90d": timedelta(days=90),
        "1y": timedelta(days=365),
    }
    if preset == "today":
        start = datetime(now.year, now.month, now.day)
        return start, now
    if preset not in presets:
        raise ValueError(f"unknown preset {preset}")
    return now - presets[preset], now


if __name__ == "__main__":
    import sys

    root = Path(
        r"C:\XLRprojects\CHALK RIVER WTP REV25 SIMULATE\Data\SCADA\DLGLOG\WTP_TREND"
    )
    day = datetime(2026, 6, 13)
    want = {
        "WTP_FIT101_VALUE",
        "WTP_FIT102_VALUE",
        "TOWER_FRC01_VALUE",
        "TOWER_FL01_VALUE",
        "WTP_PH01_VALUE",
    }
    aggs = load_model_day(root, day, want)
    for k, a in sorted(aggs.items()):
        print(
            f"{k}: n={a.count} min={a.min:.4f}@{a.time_of_min} "
            f"max={a.max:.4f}@{a.time_of_max} avg={a.avg:.4f}"
        )
    if not aggs:
        print("NO DATA", file=sys.stderr)
        raise SystemExit(1)
