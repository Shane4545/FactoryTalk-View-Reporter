"""Background report scheduler (daily / monthly produce + optional print)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app_paths import app_home
from plant_settings import load_config, save_config

STATE_PATH = app_home() / "config" / "schedule_state.json"
LOG_PATH = app_home() / "config" / "schedule_log.jsonl"

DEFAULT_SCHEDULE: dict[str, Any] = {
    "enabled": False,
    "daily": {
        "enabled": True,
        "time": "06:00",
        "print": True,
        "offset_days": 1,  # produce yesterday
    },
    "monthly": {
        "enabled": True,
        "day": 1,  # calendar day of month to run
        "time": "06:30",
        "print": False,
    },
    "printer": "",
}

_lock = threading.Lock()
_started = False
_thread: threading.Thread | None = None


def default_schedule() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_SCHEDULE))


def get_schedule() -> dict[str, Any]:
    cfg = load_config()
    sched = default_schedule()
    raw = cfg.get("schedule")
    if isinstance(raw, dict):
        sched["enabled"] = bool(raw.get("enabled", sched["enabled"]))
        sched["printer"] = str(raw.get("printer") or "")
        if isinstance(raw.get("daily"), dict):
            sched["daily"] = {**sched["daily"], **raw["daily"]}
        if isinstance(raw.get("monthly"), dict):
            sched["monthly"] = {**sched["monthly"], **raw["monthly"]}
    return sched


def save_schedule(updates: dict[str, Any]) -> dict[str, Any]:
    current = get_schedule()
    if "enabled" in updates:
        current["enabled"] = bool(updates["enabled"])
    if "printer" in updates:
        current["printer"] = str(updates["printer"] or "")
    if isinstance(updates.get("daily"), dict):
        current["daily"] = {**current["daily"], **updates["daily"]}
    if isinstance(updates.get("monthly"), dict):
        current["monthly"] = {**current["monthly"], **updates["monthly"]}
    save_config({"schedule": current})
    return current


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def append_log(entry: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"at": datetime.now().isoformat(timespec="seconds"), **entry},
        ensure_ascii=False,
    )
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def recent_log(limit: int = 40) -> list[dict[str, Any]]:
    if not LOG_PATH.is_file():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return list(reversed(out))


def _parse_hhmm(s: str) -> tuple[int, int]:
    parts = (s or "06:00").strip().split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return h, m


def run_daily_job(*, force: bool = False) -> dict[str, Any]:
    """Produce yesterday's (or configured offset) daily report."""
    from report_jobs import produce_and_archive

    sched = get_schedule()
    daily = sched.get("daily") or {}
    offset = int(daily.get("offset_days", 1) or 1)
    target = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")

    # If that calendar day has no Float.DAT yet (or archive ends earlier),
    # fall back to the newest available DLGLOG day on or before the target.
    try:
        from main import list_float_dates, resolve_dlglog, trend_model

        dates = list_float_dates(resolve_dlglog() / trend_model())
        if dates and target not in dates:
            earlier = [d for d in dates if d <= target]
            if earlier:
                target = earlier[-1]
            else:
                return {
                    "ok": False,
                    "error": f"No DLGLOG days on or before {target}",
                    "date": target,
                }
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "date": target}

    state = _load_state()
    if not force and state.get("last_daily_date") == target:
        return {"ok": True, "skipped": True, "reason": "already ran for this day", "date": target}

    printer = sched.get("printer") or None
    do_print = bool(daily.get("print"))
    try:
        result = produce_and_archive(
            "daily",
            date=target,
            skip_existing=not force,
            do_print=do_print,
            printer=printer,
        )
        state["last_daily_date"] = target
        state["last_daily_at"] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)
        append_log({"job": "daily", "date": target, **{k: result.get(k) for k in ("ok", "skipped", "id", "html", "print")}})
        return result
    except Exception as e:  # noqa: BLE001
        append_log({"job": "daily", "date": target, "ok": False, "error": str(e)})
        return {"ok": False, "error": str(e), "date": target}


def run_monthly_job(*, force: bool = False) -> dict[str, Any]:
    """Produce the previous calendar month's report (or latest month with data)."""
    from report_jobs import produce_and_archive

    sched = get_schedule()
    now = datetime.now()
    first_this = datetime(now.year, now.month, 1)
    last_prev = first_this - timedelta(days=1)
    month = f"{last_prev.year:04d}-{last_prev.month:02d}"

    try:
        from main import list_float_dates, resolve_dlglog, trend_model

        dates = list_float_dates(resolve_dlglog() / trend_model())
        if dates:
            months = sorted({d[:7] for d in dates if d[:7] <= month})
            if months:
                month = months[-1]
            else:
                return {"ok": False, "error": "No DLGLOG months available", "month": month}
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "month": month}

    state = _load_state()
    if not force and state.get("last_monthly_month") == month:
        return {"ok": True, "skipped": True, "reason": "already ran for month", "month": month}

    printer = sched.get("printer") or None
    do_print = bool((sched.get("monthly") or {}).get("print"))
    try:
        result = produce_and_archive(
            "monthly",
            month=month,
            skip_existing=not force,
            do_print=do_print,
            printer=printer,
        )
        state["last_monthly_month"] = month
        state["last_monthly_at"] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)
        append_log({"job": "monthly", "month": month, **{k: result.get(k) for k in ("ok", "skipped", "id", "html", "print")}})
        return result
    except Exception as e:  # noqa: BLE001
        append_log({"job": "monthly", "month": month, "ok": False, "error": str(e)})
        return {"ok": False, "error": str(e), "month": month}


def status() -> dict[str, Any]:
    sched = get_schedule()
    state = _load_state()
    return {
        "schedule": sched,
        "state": state,
        "log": recent_log(25),
        "thread_alive": bool(_thread and _thread.is_alive()),
    }


def _due(now: datetime, hhmm: str, last_key: str, state: dict[str, Any]) -> bool:
    """True once per calendar day after the scheduled clock time."""
    h, m = _parse_hhmm(hhmm)
    if (now.hour, now.minute) < (h, m):
        return False
    stamp = now.strftime("%Y-%m-%d")
    return state.get(last_key) != stamp


def _tick() -> None:
    sched = get_schedule()
    if not sched.get("enabled"):
        return
    now = datetime.now()
    state = _load_state()

    daily = sched.get("daily") or {}
    if daily.get("enabled") and _due(now, str(daily.get("time") or "06:00"), "daily_fired_on", state):
        run_daily_job(force=False)
        state = _load_state()
        state["daily_fired_on"] = now.strftime("%Y-%m-%d")
        _save_state(state)

    monthly = sched.get("monthly") or {}
    if monthly.get("enabled"):
        day = int(monthly.get("day") or 1)
        if now.day == day and _due(
            now, str(monthly.get("time") or "06:30"), "monthly_fired_on", state
        ):
            run_monthly_job(force=False)
            state = _load_state()
            state["monthly_fired_on"] = now.strftime("%Y-%m-%d")
            _save_state(state)


def _loop() -> None:
    # Stagger first tick so startup cache warmer gets priority
    time.sleep(15)
    while True:
        try:
            _tick()
        except Exception as e:  # noqa: BLE001
            append_log({"job": "tick", "ok": False, "error": str(e)})
        time.sleep(30)


def start_scheduler() -> None:
    global _started, _thread
    with _lock:
        if _started:
            return
        _started = True
        _thread = threading.Thread(target=_loop, name="report-scheduler", daemon=True)
        _thread.start()
        append_log({"job": "scheduler", "ok": True, "message": "started"})
