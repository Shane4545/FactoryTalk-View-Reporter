"""Produce + archive + backfill helpers (shared by API and scheduler)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app_paths import app_home
from archive import ensure_archive, save_report
from output_settings import archive_root
from print_util import print_html

BACKFILL_STATE = app_home() / "config" / "backfill_state.json"

_backfill_lock = threading.Lock()
_backfill_thread: threading.Thread | None = None


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except (OSError, ValueError):
        return dict(default)


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def archived_keys(kind: str | None = None) -> set[str]:
    """
    Set of 'kind|startDate|endDate' already in the archive.
    Used to skip duplicates during backfill / scheduled runs.
    """
    root = ensure_archive()
    keys: set[str] = set()
    if not root.is_dir():
        return keys
    for d in root.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "report.json"
        if not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        arch = data.get("archive") or {}
        k = arch.get("kind") or data.get("meta", {}).get("kind") or ""
        if kind and k != kind:
            continue
        start = data.get("startDate") or arch.get("startDate") or ""
        end = data.get("endDate") or arch.get("endDate") or start
        if start:
            keys.add(f"{k}|{start}|{end}")
    return keys


def already_archived(kind: str, start: str, end: str | None = None) -> bool:
    end = end or start
    return f"{kind}|{start}|{end}" in archived_keys(kind)


def produce_and_archive(
    kind: str,
    *,
    date: str | None = None,
    month: str | None = None,
    start: str | None = None,
    end: str | None = None,
    skip_existing: bool = False,
    do_print: bool = False,
    printer: str | None = None,
) -> dict[str, Any]:
    """
    Build a report and save under archive/ (+ PDF/Web per output settings).
    Lazy-imports FastAPI route handlers from main (same builders).
    """
    # Import inside to avoid circular import at module load
    from main import custom_report, daily_report, monthly_report

    if kind == "daily":
        if not date:
            raise ValueError("date=YYYY-MM-DD required")
        start_s = end_s = date
        if skip_existing and already_archived("daily", start_s, end_s):
            return {
                "ok": True,
                "skipped": True,
                "kind": kind,
                "startDate": start_s,
                "endDate": end_s,
                "reason": "already archived",
            }
        report = daily_report(date=date)
    elif kind == "monthly":
        if not month:
            raise ValueError("month=YYYY-MM required")
        if skip_existing:
            for key in archived_keys("monthly"):
                # key = monthly|startDate|endDate — match any report in this month
                parts = key.split("|")
                if len(parts) >= 2 and str(parts[1]).startswith(month):
                    return {
                        "ok": True,
                        "skipped": True,
                        "kind": kind,
                        "month": month,
                        "startDate": parts[1],
                        "endDate": parts[2] if len(parts) > 2 else parts[1],
                        "reason": "already archived",
                    }
        report = monthly_report(month=month)
    elif kind == "custom":
        if not start or not end:
            raise ValueError("start=&end= required")
        start_s, end_s = start, end
        if skip_existing and already_archived("custom", start_s, end_s):
            return {
                "ok": True,
                "skipped": True,
                "kind": kind,
                "startDate": start_s,
                "endDate": end_s,
                "reason": "already archived",
            }
        report = custom_report(start=start, end=end)
    else:
        raise ValueError("kind must be daily|monthly|custom")

    paths = save_report(report, kind)
    result: dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "kind": kind,
        "startDate": report.get("startDate"),
        "endDate": report.get("endDate"),
        **paths,
    }
    if do_print:
        printed = print_html(paths["html"], printer=printer)
        result["print"] = printed
    return result


def print_archived(archive_id: str, printer: str | None = None) -> dict[str, Any]:
    html = archive_root() / archive_id / "report.html"
    return print_html(html, printer=printer)


def backfill_status() -> dict[str, Any]:
    return _load_json(
        BACKFILL_STATE,
        {
            "running": False,
            "kind": None,
            "from": None,
            "to": None,
            "done": 0,
            "total": 0,
            "skipped": 0,
            "failed": 0,
            "current": None,
            "errors": [],
            "started_at": None,
            "finished_at": None,
            "message": None,
        },
    )


def _set_backfill(updates: dict[str, Any]) -> dict[str, Any]:
    with _backfill_lock:
        state = backfill_status()
        state.update(updates)
        _save_json(BACKFILL_STATE, state)
        return state


def _month_span(first: str, last: str) -> list[str]:
    y0, m0, _ = first.split("-")
    y1, m1, _ = last.split("-")
    cur = datetime(int(y0), int(m0), 1)
    end = datetime(int(y1), int(m1), 1)
    out: list[str] = []
    while cur <= end:
        out.append(f"{cur.year:04d}-{cur.month:02d}")
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)
    return out


def _day_span(first: str, last: str) -> list[str]:
    cur = datetime.strptime(first, "%Y-%m-%d")
    end = datetime.strptime(last, "%Y-%m-%d")
    out: list[str] = []
    while cur <= end:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def start_backfill(
    kind: str = "daily",
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    print_each: bool = False,
    printer: str | None = None,
) -> dict[str, Any]:
    """
    Kick off a background backfill of daily or monthly reports.
    Defaults to the full DLGLOG date range.
    """
    global _backfill_thread

    if kind not in ("daily", "monthly"):
        raise ValueError("backfill kind must be daily or monthly")

    state = backfill_status()
    if state.get("running"):
        return {"ok": False, "error": "Backfill already running", **state}

    # Resolve date range from DLGLOG if not provided
    from main import list_float_dates, resolve_dlglog, trend_model

    root = resolve_dlglog()
    dates = list_float_dates(root / trend_model())
    if not dates:
        raise FileNotFoundError("No DLGLOG dates found")

    first = date_from or dates[0]
    last = date_to or dates[-1]
    if first > last:
        raise ValueError("from date must be on or before to date")

    if kind == "daily":
        # Only days that actually have Float.DAT
        available = set(dates)
        items = [d for d in _day_span(first, last) if d in available]
    else:
        items = _month_span(first, last)

    _set_backfill(
        {
            "running": True,
            "kind": kind,
            "from": first,
            "to": last,
            "done": 0,
            "total": len(items),
            "skipped": 0,
            "failed": 0,
            "current": None,
            "errors": [],
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "message": f"Starting {kind} backfill ({len(items)} items)…",
        }
    )

    def worker() -> None:
        skipped = failed = done = 0
        errors: list[str] = []
        for i, item in enumerate(items):
            _set_backfill(
                {
                    "current": item,
                    "done": done,
                    "skipped": skipped,
                    "failed": failed,
                    "message": f"Producing {kind} {item} ({i + 1}/{len(items)})",
                }
            )
            try:
                if kind == "daily":
                    result = produce_and_archive(
                        "daily",
                        date=item,
                        skip_existing=True,
                        do_print=print_each,
                        printer=printer,
                    )
                else:
                    result = produce_and_archive(
                        "monthly",
                        month=item,
                        skip_existing=True,
                        do_print=print_each,
                        printer=printer,
                    )
                if result.get("skipped"):
                    skipped += 1
                else:
                    done += 1
            except Exception as e:  # noqa: BLE001 — keep backfill going
                failed += 1
                errors.append(f"{item}: {e}")
                if len(errors) > 40:
                    errors = errors[-40:]
        _set_backfill(
            {
                "running": False,
                "current": None,
                "done": done,
                "skipped": skipped,
                "failed": failed,
                "errors": errors,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "message": (
                    f"Done — produced {done}, skipped {skipped}, failed {failed}"
                ),
            }
        )

    _backfill_thread = threading.Thread(
        target=worker, name="report-backfill", daemon=True
    )
    _backfill_thread.start()
    return {"ok": True, **backfill_status()}
