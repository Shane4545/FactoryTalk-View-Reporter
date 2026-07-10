"""FastAPI backend — FactoryTalk DLGLOG → Ops Reporter."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import tag_config  # noqa: E402
from archive import find_archived_report, list_archive, save_report  # noqa: E402
from chalk_report_builder import build_daily  # noqa: E402
from day_cache import (  # noqa: E402
    load_model_day_cached,
    load_motors_day_cached,
    load_series_cached,
)
from dlglog_reader import (  # noqa: E402
    list_model_tags,
    preset_window,
)
from period_rollup import build_period_report, month_bounds  # noqa: E402
from plant_settings import (  # noqa: E402
    auto_assign_models,
    discover_models,
    load_config,
    model_name,
    resolve_dlglog_root,
    save_config,
    validate_dlglog,
)

FLOAT_RE = re.compile(r"^(\d{4}) (\d{2}) (\d{2}) 0000 \(Float\)\.DAT$")


def tag_labels() -> dict[str, tuple[str, str, str, str]]:
    """historian -> (short, description, units, model-role) from the active
    Setup profile (Chalk River defaults until a custom profile is saved)."""
    out: dict[str, tuple[str, str, str, str]] = {}
    for _sec, _kind, short, desc, hist, units, _tot in tag_config.trend_rows():
        out[hist] = (short, desc, units, "WTP_TREND")
    for short, desc, hist in tag_config.motor_rows():
        out.setdefault(hist, (short, desc, "", "WTP_MOTORS"))
    for short, desc, hist, units in tag_config.feedback_rows():
        out.setdefault(hist, (short, desc, units, "WTP_FEEDBACK"))
    return out


# Ensure custom-profile EU scaling / flow tags are active before any read
tag_config.apply_scaling_overrides()


def resolve_dlglog() -> Path:
    return resolve_dlglog_root(load_config())


def trend_model() -> str:
    return model_name(load_config(), "trend")


def motors_model() -> str:
    return model_name(load_config(), "motors")


def feedback_model() -> str:
    return model_name(load_config(), "feedback")


def clear_data_caches() -> None:
    _cached_model.cache_clear()
    _cached_motors.cache_clear()
    try:
        _disk_tag_index.cache_clear()
    except NameError:
        pass


def list_float_dates(model_dir: Path) -> list[str]:
    dates: list[str] = []
    if not model_dir.is_dir():
        return dates
    for f in model_dir.glob("* (Float).DAT"):
        m = FLOAT_RE.match(f.name)
        if m:
            dates.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    return sorted(set(dates))


def last_sample_anchor(model_dir: Path, tag: str | None = None) -> datetime | None:
    """
    Timestamp of the newest (good-quality) sample in a model folder.

    Short presets (1m/1h/today) must anchor here, not at 23:59:59 of the last
    day — the last Float.DAT often ends mid-day (e.g. log stopped at 15:07),
    and anchoring past the final sample returns an empty window.
    With `tag`, anchors to that tag's own last sample (a tag can stop logging
    hours before the rest of the model, e.g. quality goes bad after a restart).
    Uses the per-day series cache (one scan, then cached).
    """
    dates = list_float_dates(model_dir)
    if not dates:
        return None
    end_of_day = None
    try:
        from day_cache import ensure_day_series_cache

        # Walk back a few days in case the tag has no samples on the last day
        for date_s in reversed(dates[-7:]):
            day = datetime.strptime(date_s, "%Y-%m-%d")
            end_of_day = day.replace(hour=23, minute=59, second=59)
            payload = ensure_day_series_cache(model_dir, day)
            tag_infos = payload.get("tags", {})
            if tag is not None:
                infos = [tag_infos.get(tag)] if tag in tag_infos else []
            else:
                infos = list(tag_infos.values())
            last_ts: datetime | None = None
            for info in infos:
                pts = (info or {}).get("points") or []
                if not pts:
                    continue
                ts = datetime.strptime(pts[-1][0], "%Y-%m-%d %H:%M:%S")
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            if last_ts is not None:
                return min(last_ts, end_of_day)
    except (OSError, ValueError, FileNotFoundError):
        pass
    last_day = datetime.strptime(dates[-1], "%Y-%m-%d")
    return last_day.replace(hour=23, minute=59, second=59)


@lru_cache(maxsize=32)
def _cached_model(model: str, date: str) -> dict:
    root = resolve_dlglog()
    day = datetime.strptime(date, "%Y-%m-%d")
    return load_model_day_cached(root / model, day)


@lru_cache(maxsize=32)
def _cached_motors(date: str) -> tuple:
    """Return (aggregates_dict, runtime_dict) — one Float.DAT pass (disk-cached)."""
    root = resolve_dlglog()
    day = datetime.strptime(date, "%Y-%m-%d")
    want = {hist for _, _, hist in tag_config.motor_rows()}
    return load_motors_day_cached(root / motors_model(), day, want_tags=want)


app = FastAPI(title="Ops Reporter", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_series_caches() -> None:
    """
    Pre-build per-day series caches in the background (newest days first)
    so 30d/90d trend presets are instant instead of minutes on first use.
    """
    import threading

    def worker() -> None:
        from day_cache import ensure_day_series_cache

        try:
            root = resolve_dlglog()
        except FileNotFoundError:
            return
        for model_name in discover_models(root):
            model_dir = root / model_name
            for date_s in reversed(list_float_dates(model_dir)):
                try:
                    ensure_day_series_cache(
                        model_dir, datetime.strptime(date_s, "%Y-%m-%d")
                    )
                except (OSError, ValueError, FileNotFoundError):
                    continue

    threading.Thread(target=worker, name="cache-warmer", daemon=True).start()

    try:
        from scheduler import start_scheduler

        start_scheduler()
    except Exception:
        pass


@app.get("/api/health")
def health():
    cfg = load_config()
    try:
        root = resolve_dlglog()
        tm, mm, fm = trend_model(), motors_model(), feedback_model()
        dates = list_float_dates(root / tm)
        found = discover_models(root)
        return {
            "ok": True,
            "dlglog": str(root),
            "xlreporter": False,
            "plant": cfg.get("plant"),
            "models": {
                tm: (root / tm).is_dir(),
                mm: (root / mm).is_dir(),
                fm: (root / fm).is_dir(),
            },
            "models_on_disk": found,
            "date_count": len(dates),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
        }
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "xlreporter": False, "plant": cfg.get("plant")}


@app.get("/api/dates")
def available_dates():
    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    dates = list_float_dates(root / trend_model())
    return {"dlglog": str(root), "dates": dates, "count": len(dates)}


@app.post("/api/config/test")
def config_test(body: dict = Body(...)):
    """Validate a DLGLOG folder without saving."""
    path = body.get("dlglog_path") or body.get("path") or ""
    return validate_dlglog(path)


@app.post("/api/config/browse")
def config_browse():
    """
    Open a native Windows folder picker so the operator can point at the main
    DLGLOG folder without typing the path.
    """
    import subprocess

    chosen = ""
    err = ""
    try:
        if getattr(sys, "frozen", False):
            # Frozen exe: re-invoke self with a browse-only flag (tk in subprocess)
            proc = subprocess.run(
                [sys.executable, "--browse-folder"],
                capture_output=True,
                text=True,
                timeout=300,
            )
        else:
            script = (
                "import tkinter as tk\n"
                "from tkinter import filedialog\n"
                "root = tk.Tk()\n"
                "root.withdraw()\n"
                "try:\n"
                "    root.attributes('-topmost', True)\n"
                "except Exception:\n"
                "    pass\n"
                "path = filedialog.askdirectory(title='Select FactoryTalk DLGLOG folder')\n"
                "root.destroy()\n"
                "print(path or '')\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=300,
            )
        lines = (proc.stdout or "").strip().splitlines()
        chosen = lines[-1].strip() if lines else ""
        err = (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "path": None,
            "error": "Folder picker timed out",
            "cancelled": True,
            "models": [],
            "assigned": {},
        }
    except OSError as e:
        return {
            "ok": False,
            "path": None,
            "error": str(e),
            "cancelled": True,
            "models": [],
            "assigned": {},
        }

    if not chosen:
        return {
            "ok": False,
            "path": None,
            "error": err or "Cancelled — no folder selected",
            "cancelled": True,
            "models": [],
            "assigned": {},
        }
    check = validate_dlglog(chosen)
    return {**check, "cancelled": False}


@app.get("/api/config")
def get_config():
    cfg = load_config()
    try:
        root = str(resolve_dlglog())
        models = discover_models(Path(root))
        ok = True
        err = None
    except FileNotFoundError as e:
        root = cfg.get("dlglog_path") or ""
        models = []
        ok = False
        err = str(e)
    return {**cfg, "resolved_dlglog": root, "ok": ok, "error": err, "models_on_disk": models}


@app.put("/api/config")
def put_config(body: dict = Body(...)):
    """
    Save plant settings. Point dlglog_path at the main DLGLOG folder;
    model subfolders are auto-detected (TREND / MOTORS / FEEDBACK by name).
    Optional: plant{name,municipality}, models{...} override.
    """
    path = (body.get("dlglog_path") or "").strip()
    if path:
        check = validate_dlglog(path)
        if not check["ok"]:
            raise HTTPException(400, check["error"])
        body = {**body, "dlglog_path": check["path"]}
        # Auto-assign unless caller explicitly sent models
        if not body.get("models"):
            body["models"] = check.get("assigned") or {}
        cands = list(
            body.get("dlglog_candidates")
            or load_config().get("dlglog_candidates")
            or []
        )
        if check["path"] not in cands:
            cands = [check["path"], *cands]
        body["dlglog_candidates"] = cands

    saved = save_config(body)
    clear_data_caches()
    try:
        root = resolve_dlglog()
        models = discover_models(root)
        assigned = auto_assign_models(models) if models else saved.get("models")
        ok = True
        err = None
    except FileNotFoundError as e:
        root = None
        models = []
        assigned = saved.get("models")
        ok = False
        err = str(e)
    return {
        "ok": ok,
        "saved": True,
        "error": err,
        "config": saved,
        "resolved_dlglog": str(root) if root else None,
        "models_on_disk": models,
        "assigned": assigned,
        "xlreporter": False,
    }


@app.get("/api/setup")
def setup_state():
    """Everything the Setup page needs: active profile, DLGLOG status,
    role catalogs, and section choices."""
    cfg = load_config()
    try:
        root = str(resolve_dlglog())
        models = discover_models(Path(root))
        ok = True
        err = None
    except FileNotFoundError as e:
        root = cfg.get("dlglog_path") or ""
        models = []
        ok = False
        err = str(e)

    prof = tag_config.get_profile()
    # How much of the active profile exists in this DLGLOG? Low match on a
    # fresh site = the built-in Chalk mapping doesn't fit → run Setup.
    match = {"found": 0, "total": 0, "pct": None}
    if ok:
        disk: set[str] = set()
        for m in models:
            try:
                disk |= set(list_model_tags(Path(root) / m).values())
            except FileNotFoundError:
                continue
        hists = (
            [r["historian"] for r in prof["trend"]]
            + [r["historian"] for r in prof["motors"]]
            + [r["historian"] for r in prof["feedback"]]
        )
        found = sum(1 for h in hists if h in disk)
        match = {
            "found": found,
            "total": len(hists),
            "pct": round(100.0 * found / len(hists), 1) if hists else None,
        }

    return {
        "ok": ok,
        "error": err,
        "dlglog": root,
        "models_on_disk": models,
        "models": cfg.get("models") or {},
        "plant": cfg.get("plant") or {},
        "configured": tag_config.is_configured(),
        "match": match,
        "profile": prof,
        "section_choices": [
            {"id": sid, "title": t} for sid, t in tag_config.ANALOG_SECTION_CHOICES
        ],
        "ct_roles": [
            {"role": role, "label": label, "which": which}
            for role, label, which in tag_config.CT_INPUT_ROLES
        ],
        "insight_roles": [
            {"role": role, "label": label, "kind": kind}
            for role, label, kind in tag_config.INSIGHT_ROLES
        ],
        "xlreporter": False,
    }


@app.get("/api/setup/discover")
def setup_discover():
    """Scan every datalog model's Tagname file and suggest a mapping for
    each historian tag (pattern-based; the operator reviews in Setup)."""
    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    prof = tag_config.get_profile()
    mapped = (
        {r["historian"] for r in prof["trend"]}
        | {r["historian"] for r in prof["motors"]}
        | {r["historian"] for r in prof["feedback"]}
    )

    out: list[dict] = []
    for model in discover_models(root):
        try:
            idx = list_model_tags(root / model)
        except FileNotFoundError:
            continue
        for _i, hist in sorted(idx.items(), key=lambda x: x[1]):
            if hist.startswith("_"):
                continue
            out.append(
                {
                    "historian": hist,
                    "model": model,
                    "mapped": hist in mapped,
                    "suggestion": tag_config.suggest_for_tag(hist),
                }
            )
    return {"tags": out, "count": len(out), "xlreporter": False}


def _warm_day_aggregates(days: int = 45) -> None:
    """Rebuild recent day-aggregate caches in the background after a profile
    change (new scaling fingerprint = cold caches; first report would
    otherwise take minutes)."""
    import threading

    def worker() -> None:
        try:
            root = resolve_dlglog()
        except FileNotFoundError:
            return
        tm, mm = trend_model(), motors_model()
        want_m = {h for _, _, h in tag_config.motor_rows()}
        for date_s in reversed(list_float_dates(root / tm)[-days:]):
            day = datetime.strptime(date_s, "%Y-%m-%d")
            try:
                load_model_day_cached(root / tm, day)
            except (OSError, ValueError, FileNotFoundError):
                pass
            try:
                load_motors_day_cached(root / mm, day, want_tags=want_m)
            except (OSError, ValueError, FileNotFoundError):
                pass

    threading.Thread(target=worker, name="day-agg-warmer", daemon=True).start()


@app.put("/api/setup/profile")
def setup_save_profile(body: dict = Body(...)):
    """Save the site tag profile (normalized). Clears data caches so new
    scaling / flow settings take effect immediately."""
    prof = tag_config.save_profile(body or {})
    _warm_day_aggregates()
    return {"ok": True, "profile": prof, "configured": tag_config.is_configured()}


@app.post("/api/setup/reset")
def setup_reset_profile():
    """Drop the custom profile — back to built-in Chalk River defaults."""
    prof = tag_config.reset_profile()
    _warm_day_aggregates()
    return {"ok": True, "profile": prof, "configured": tag_config.is_configured()}


@app.get("/api/setup/export")
def setup_export_profile():
    """Portable profile JSON (tag map + plant info) for backup / another PC."""
    cfg = load_config()
    return {
        "ops_reporter_profile": 1,
        "plant": cfg.get("plant") or {},
        "tag_config": tag_config.get_profile(),
    }


@app.post("/api/setup/import")
def setup_import_profile(body: dict = Body(...)):
    """Import a profile exported from another Ops Reporter install."""
    data = body or {}
    tc = data.get("tag_config") if isinstance(data.get("tag_config"), dict) else data
    if not isinstance(tc, dict) or not (tc.get("trend") or tc.get("motors")):
        raise HTTPException(400, "Not a valid Ops Reporter profile (no trend/motor rows)")
    if isinstance(data.get("plant"), dict):
        save_config({"plant": data["plant"]})
    prof = tag_config.save_profile(tc)
    _warm_day_aggregates()
    return {"ok": True, "profile": prof, "configured": tag_config.is_configured()}


def _short_id(hist: str) -> str:
    """Operator-facing id; keep uniqueness for motors/feedback."""
    if hist.endswith("_VALUE"):
        base = hist[: -len("_VALUE")]
        last = base.split("_")[-1]
        # FIT101 / PH01 / TUR01 style
        if any(c.isdigit() for c in last) and last[:1].isalpha():
            return last
        return base
    if hist.endswith("_RUNNING"):
        return hist[: -len("_RUNNING")] + "_RUN"
    if hist.endswith("_ACTUAL"):
        return hist[: -len("_ACTUAL")] + "_ACT"
    if hist.endswith("_OUT"):
        return hist[: -len("_OUT")] + "_OUT"
    return hist


@app.get("/api/tags")
def list_tags():
    """Every tag from every datalog model folder under the connected DLGLOG."""
    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    labels = tag_labels()
    # Remap label model folder names to configured plant folders
    role_map = {
        "WTP_TREND": trend_model(),
        "WTP_MOTORS": motors_model(),
        "WTP_FEEDBACK": feedback_model(),
    }

    tags: list[dict] = []
    seen_hist: set[str] = set()
    seen_id: set[str] = set()

    # Labeled trend tags first (stable operator names)
    for hist, (short, desc, units, model) in labels.items():
        model = role_map.get(model, model)
        tags.append(
            {
                "id": short,
                "historianTag": hist,
                "description": desc,
                "units": units,
                "model": model,
            }
        )
        seen_hist.add(hist)
        seen_id.add(short.upper())

    for model_name in discover_models(root):
        try:
            idx = list_model_tags(root / model_name)
        except FileNotFoundError:
            continue
        for _i, name in sorted(idx.items(), key=lambda x: x[1]):
            if name in seen_hist or name.startswith("_"):
                continue
            if name in labels:
                continue
            short = _short_id(name)
            # Avoid colliding with FIT101-style ids
            if short.upper() in seen_id:
                short = name.replace("_VALUE", "").replace("_RUNNING", "")
            tags.append(
                {
                    "id": short,
                    "historianTag": name,
                    "description": name,
                    "units": "",
                    "model": model_name,
                }
            )
            seen_hist.add(name)
            seen_id.add(short.upper())

    return {"tags": tags, "count": len(tags)}


@lru_cache(maxsize=4)
def _disk_tag_index(dlglog: str) -> dict[str, tuple[str, str]]:
    """Map short/historian → (historian, model) from all model Tagname.DAT files."""
    root = Path(dlglog)
    out: dict[str, tuple[str, str]] = {}
    for model_name in discover_models(root):
        try:
            idx = list_model_tags(root / model_name)
        except FileNotFoundError:
            continue
        for _i, name in idx.items():
            if name.startswith("_"):
                continue
            out[name] = (name, model_name)
            out[name.upper()] = (name, model_name)
            short = _short_id(name)
            out.setdefault(short.upper(), (name, model_name))
            bare = name.replace("_VALUE", "").replace("_RUNNING", "")
            out.setdefault(bare.upper(), (name, model_name))
    return out


def _resolve_tag(tag: str) -> tuple[str, str, str, str]:
    """Return historian, short, desc, model."""
    t = tag.strip()
    labels = tag_labels()
    for hist, (short, desc, units, model) in labels.items():
        if t.upper() == short.upper() or t == hist:
            if model == "WTP_TREND":
                model = trend_model()
            elif model == "WTP_MOTORS":
                model = motors_model()
            elif model == "WTP_FEEDBACK":
                model = feedback_model()
            return hist, short, desc, model

    try:
        root = resolve_dlglog()
        disk = _disk_tag_index(str(root))
        hit = disk.get(t) or disk.get(t.upper())
        if hit:
            hist, model = hit
            label = labels.get(hist)
            if label:
                return hist, label[0], label[1], model
            return hist, _short_id(hist), hist, model
    except FileNotFoundError:
        pass

    if t.endswith("_VALUE") or t.endswith("_RUNNING") or "_ACTUAL" in t or t.endswith("_OUT"):
        model = (
            motors_model()
            if "RUNNING" in t
            else (
                feedback_model()
                if ("ACTUAL" in t or t.endswith("_OUT"))
                else trend_model()
            )
        )
        return t, _short_id(t), t, model
    raise HTTPException(404, f"Unknown tag {tag}")


@app.get("/api/tags/{tag}/series")
def tag_series(
    tag: str,
    preset: str | None = Query(None, description="1m,1h,1d,7d,30d,1y,today"),
    start: str | None = Query(None, description="YYYY-MM-DD or YYYY-MM-DDTHH:MM"),
    end: str | None = Query(None),
    max_points: Annotated[int, Query(ge=50, le=5000)] = 1500,
):
    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    hist, short, desc, model = _resolve_tag(tag)
    dates = list_float_dates(root / model)
    if not dates:
        raise HTTPException(404, f"No data files for {model}")

    last_data = last_sample_anchor(root / model, tag=hist)
    assert last_data is not None

    if preset:
        # Anchor presets to last available sample (not wall clock) so offline works
        try:
            s, e = preset_window(preset, now=last_data)
        except ValueError as ex:
            raise HTTPException(400, str(ex)) from ex
    else:
        if not start or not end:
            raise HTTPException(400, "Provide preset= or start=&end=")
        def parse_dt(s: str) -> datetime:
            s = s.replace("T", " ")
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
            raise ValueError(s)
        try:
            s, e = parse_dt(start), parse_dt(end)
        except ValueError as ex:
            raise HTTPException(400, f"bad datetime: {ex}") from ex
        if e.hour == 0 and e.minute == 0 and len(end) <= 10:
            e = e.replace(hour=23, minute=59, second=59)

    if e < s:
        raise HTTPException(400, "end before start")

    series = load_series_cached(root / model, hist, s, e, max_points=max_points)
    series["id"] = short
    series["description"] = desc
    series["model"] = model
    series["units"] = tag_labels().get(hist, ("", "", "", ""))[2]
    series["preset"] = preset
    series["xlreporter"] = False
    return series


@app.get("/api/reports/daily")
def daily_report(date: str = Query(..., description="YYYY-MM-DD")):
    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(400, f"bad date: {e}") from e

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    today = datetime.now().strftime("%Y-%m-%d")
    live = date == today

    # Today must re-read as Float.DAT grows — clear LRU for this date
    if live:
        _cached_model.cache_clear()
        _cached_motors.cache_clear()

    try:
        trend = _cached_model(trend_model(), date)
    except FileNotFoundError as e:
        raise HTTPException(404, f"No trend data for {date}: {e}") from e

    motors: dict = {}
    feedback: dict = {}
    motor_runtime: dict = {}
    try:
        motors, motor_runtime = _cached_motors(date)
    except FileNotFoundError:
        motors = {}
        motor_runtime = {}
    try:
        feedback = _cached_model(feedback_model(), date)
    except FileNotFoundError:
        feedback = {}

    as_of = datetime.now() if live else None
    from report_prefs import hidden_sets

    hide = hidden_sets()
    report = build_daily(
        day,
        trend,
        motors,
        feedback,
        motor_runtime=motor_runtime,
        live=live,
        as_of=as_of,
        hidden_trend=hide["trend"],
        hidden_motor=hide["motor"],
        hidden_feedback=hide["feedback"],
        hidden_sections=hide["section"],
    )
    # Proof tag: configured raw-flow role, else first trend row
    proof_hist = tag_config.roles().get("raw_flow")
    trows = tag_config.trend_rows()
    if not proof_hist and trows:
        proof_hist = trows[0][4]
    proof_short = next((t for _s, _k, t, _d, h, _u, _t in trows if h == proof_hist), proof_hist)
    fit = trend.get(proof_hist) if proof_hist else None
    ct0 = report["ct"][0] if report.get("ct") else {}
    report["meta"] = {
        "source": "dlglog",
        "dlglog": str(root),
        "xlreporter": False,
        "kind": "daily",
        "live": live,
        "tag_count_trend": len(trend),
        "tag_count_motors": len(motors),
        "tag_count_feedback": len(feedback),
        "proof": {
            "tag": proof_short,
            "FIT101_samples": fit.count if fit else 0,
            "FIT101_min": fit.min if fit else None,
            "FIT101_max": fit.max if fit else None,
            "CT_Achieved": ct0.get("giardia"),
        },
    }
    return report


def _parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


@app.get("/api/reports/monthly")
def monthly_report(month: str = Query(..., description="YYYY-MM")):
    try:
        y, m = month.split("-")
        start, end = month_bounds(int(y), int(m))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"bad month (use YYYY-MM): {e}") from e

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    try:
        report = build_period_report(
            root,
            start,
            end,
            subtitle="Monthly Operations Report",
            period_label=f"Calendar month {month} (days with DLGLOG data)",
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e

    report["meta"] = {
        "source": "dlglog",
        "dlglog": str(root),
        "xlreporter": False,
        "kind": "monthly",
        "month": month,
        **(report.pop("meta_period", {})),
    }
    return report


@app.get("/api/insights")
def plant_insights_api(
    date: str | None = Query(None, description="YYYY-MM-DD (default: last complete day)"),
):
    """
    Operator troubleshooting dashboard: traffic-light instrument/motor health,
    CT margin, plant metrics, and suggestions for the selected day.
    """
    from plant_insights import build_insights
    from report_prefs import catalog, hidden_sets

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    dates = list_float_dates(root / trend_model())
    if not dates:
        raise HTTPException(404, "No trend days available")

    today = datetime.now().strftime("%Y-%m-%d")
    if not date:
        complete = [d for d in dates if d < today]
        date = complete[-1] if complete else dates[-1]

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(400, f"bad date: {e}") from e

    live = date == today
    if live:
        _cached_model.cache_clear()
        _cached_motors.cache_clear()

    try:
        trend = _cached_model(trend_model(), date)
    except FileNotFoundError as e:
        raise HTTPException(404, f"No trend data for {date}: {e}") from e

    motor_runtime: dict = {}
    try:
        _motors, motor_runtime = _cached_motors(date)
    except FileNotFoundError:
        motor_runtime = {}

    feedback: dict = {}
    try:
        feedback = _cached_model(feedback_model(), date)
    except FileNotFoundError:
        feedback = {}

    hide = hidden_sets()
    day = datetime.strptime(date, "%Y-%m-%d")
    as_of = datetime.now() if live else None
    report = build_daily(
        day,
        trend,
        {},
        feedback,
        motor_runtime=motor_runtime,
        live=live,
        as_of=as_of,
        hidden_trend=hide["trend"],
        hidden_motor=hide["motor"],
        hidden_feedback=hide["feedback"],
        hidden_sections=hide["section"],
    )

    # 7-day baseline (prior days with data, excluding today)
    baseline_avgs: dict[str, float] = {}
    prior = [d for d in dates if d < date][-7:]
    if prior:
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        hist_by_short = {
            short: hist for _s, _k, short, _d, hist, _u, _t in tag_config.trend_rows()
        }
        for d in prior:
            try:
                day_aggs = _cached_model(trend_model(), d)
            except FileNotFoundError:
                continue
            for short, hist in hist_by_short.items():
                a = day_aggs.get(hist)
                if a and a.count and a.avg is not None:
                    sums[short] = sums.get(short, 0.0) + float(a.avg)
                    counts[short] = counts.get(short, 0) + 1
        for short, n in counts.items():
            if n >= 2:
                baseline_avgs[short] = sums[short] / n

    sparklines: dict[str, list[float | None]] = {}
    day_start = day.replace(hour=0, minute=0, second=0)
    day_end = (
        as_of if live and as_of else day.replace(hour=23, minute=59, second=59)
    )
    # Live today: duty % over hours elapsed so far, not a full 24 h
    period_hours = 24.0
    if live and as_of:
        period_hours = max(0.25, (as_of - day_start).total_seconds() / 3600.0)
    prelim = build_insights(
        date=date,
        trend=trend,
        motor_runtime=motor_runtime,
        ct_rows=report.get("ct"),
        live=live,
        hidden_trend=hide["trend"],
        hidden_motor=hide["motor"],
        hidden_sections=hide["section"],
        baseline_avgs=baseline_avgs,
        period_hours=period_hours,
    )
    spark_tags = [
        inst
        for inst in prelim["instruments"]
        if inst["severity"] in ("watch", "alert")
    ][:8]
    if len(spark_tags) < 4:
        # Key process tags from Setup roles (falls back to first trend rows)
        r = tag_config.roles()
        hist_to_short = {
            hist: short for _s, _k, short, _d, hist, _u, _t in tag_config.trend_rows()
        }
        want: set[str] = set()
        for role in (
            "raw_flow",
            "treated_flow",
            "clearwell_level",
            "tower_level",
            "treated_cl2",
        ):
            h = r.get(role)
            if h and h in hist_to_short:
                want.add(hist_to_short[h])
        for h in (r.get("filter_turbidity") or [])[:1]:
            if h in hist_to_short:
                want.add(hist_to_short[h])
        if not want:
            want = {i["tag"] for i in prelim["instruments"][:6]}
        have = {i["tag"] for i in spark_tags}
        for inst in prelim["instruments"]:
            if inst["tag"] in want and inst["tag"] not in have:
                spark_tags.append(inst)
                have.add(inst["tag"])
            if len(spark_tags) >= 6:
                break

    for inst in spark_tags:
        hist = inst["historian"]
        try:
            ser = load_series_cached(
                root / trend_model(), hist, day_start, day_end, max_points=36
            )
            pts = ser.get("points") or []
            sparklines[inst["tag"]] = [
                (p.get("v") if isinstance(p, dict) else None) for p in pts
            ]
        except Exception:
            continue

    insights = build_insights(
        date=date,
        trend=trend,
        motor_runtime=motor_runtime,
        ct_rows=report.get("ct"),
        live=live,
        sparklines=sparklines,
        hidden_trend=hide["trend"],
        hidden_motor=hide["motor"],
        hidden_sections=hide["section"],
        baseline_avgs=baseline_avgs,
        period_hours=period_hours,
    )
    insights["dlglog"] = str(root)
    insights["baseline_days"] = prior
    insights["available_dates"] = {
        "first": dates[0],
        "last": dates[-1],
        "count": len(dates),
    }
    insights["catalog"] = catalog()
    return insights


@app.get("/api/report-prefs")
def report_prefs_get():
    from report_prefs import catalog

    return {**catalog(), "xlreporter": False}


@app.put("/api/report-prefs")
def report_prefs_put(body: dict = Body(...)):
    from report_prefs import catalog, save_prefs

    save_prefs(body or {})
    return {**catalog(), "ok": True, "xlreporter": False}


@app.post("/api/report-prefs/hide")
def report_prefs_hide(body: dict = Body(...)):
    from report_prefs import catalog, hide_tag

    kind = body.get("kind") or ""
    tag = body.get("tag") or ""
    try:
        hide_tag(kind, tag)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {**catalog(), "ok": True, "xlreporter": False}


@app.post("/api/report-prefs/show")
def report_prefs_show(body: dict = Body(...)):
    from report_prefs import catalog, show_tag

    kind = body.get("kind") or ""
    tag = body.get("tag") or ""
    try:
        show_tag(kind, tag)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {**catalog(), "ok": True, "xlreporter": False}


@app.get("/api/reports/custom")
def custom_report(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
):
    try:
        s, e = _parse_ymd(start), _parse_ymd(end)
    except ValueError as ex:
        raise HTTPException(400, f"bad date: {ex}") from ex
    if e < s:
        raise HTTPException(400, "end before start")
    if (e - s).days > 92:
        raise HTTPException(400, "custom range max 93 days (use monthly for longer)")

    try:
        root = resolve_dlglog()
    except FileNotFoundError as ex:
        raise HTTPException(503, str(ex)) from ex

    try:
        report = build_period_report(
            root,
            s,
            e,
            subtitle="Custom Operations Report",
            period_label=f"Custom range {start} → {end}",
        )
    except FileNotFoundError as ex:
        raise HTTPException(404, str(ex)) from ex

    report["meta"] = {
        "source": "dlglog",
        "dlglog": str(root),
        "xlreporter": False,
        "kind": "custom",
        **(report.pop("meta_period", {})),
    }
    return report


@app.get("/api/trends")
def multi_trend(
    tags: str = Query(..., description="Comma-separated short or historian tags"),
    preset: str | None = None,
    start: str | None = None,
    end: str | None = None,
    max_points: Annotated[int, Query(ge=50, le=3000)] = 800,
):
    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    names = [t.strip() for t in tags.split(",") if t.strip()]
    if not names or len(names) > 6:
        raise HTTPException(400, "Provide 1–6 tags")

    hist0, _, _, model0 = _resolve_tag(names[0])
    dates = list_float_dates(root / model0)
    if not dates:
        raise HTTPException(404, f"No data for {model0}")
    last_data = last_sample_anchor(root / model0, tag=hist0)
    assert last_data is not None

    use_preset = (preset or "7d") if not start or not end else None
    if use_preset:
        try:
            s, e = preset_window(use_preset, now=last_data)
        except ValueError as ex:
            raise HTTPException(400, str(ex)) from ex
    else:
        assert start is not None and end is not None

        def parse_dt(raw: str) -> datetime:
            raw = raw.replace("T", " ")
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
            raise ValueError(raw)

        try:
            s, e = parse_dt(start), parse_dt(end)
        except ValueError as ex:
            raise HTTPException(400, f"bad datetime: {ex}") from ex
        if e.hour == 0 and e.minute == 0 and len(end) <= 10:
            e = e.replace(hour=23, minute=59, second=59)

    # Warm day caches once per model (shared across tags), then assemble series
    models_needed = {_resolve_tag(n)[3] for n in names}
    from datetime import timedelta as _td
    from day_cache import ensure_day_series_cache

    day = datetime(s.year, s.month, s.day)
    last_day = datetime(e.year, e.month, e.day)
    while day <= last_day:
        for mname in models_needed:
            try:
                ensure_day_series_cache(root / mname, day)
            except FileNotFoundError:
                pass
        day = day + _td(days=1)

    series_out = []
    for name in names:
        hist, short, desc, model = _resolve_tag(name)
        ser = load_series_cached(root / model, hist, s, e, max_points=max_points)
        ser["id"] = short
        ser["description"] = desc
        ser["model"] = model
        ser["units"] = TAG_LABELS.get(hist, ("", "", "", ""))[2]
        series_out.append(ser)

    return {
        "start": s.isoformat(sep=" "),
        "end": e.isoformat(sep=" "),
        "preset": use_preset or preset,
        "xlreporter": False,
        "series": series_out,
    }


@app.post("/api/archive")
def archive_produce(
    kind: str = "daily",
    date: str | None = None,
    month: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Produce report and save under archive/ (+ PDF/Web per output settings)."""
    if kind == "daily":
        if not date:
            raise HTTPException(400, "date=YYYY-MM-DD required")
        report = daily_report(date)
    elif kind == "monthly":
        if not month:
            raise HTTPException(400, "month=YYYY-MM required")
        report = monthly_report(month)
    elif kind == "custom":
        if not start or not end:
            raise HTTPException(400, "start=&end= required")
        report = custom_report(start, end)
    else:
        raise HTTPException(400, "kind must be daily|monthly|custom")

    paths = save_report(report, kind)
    return {"ok": True, "xlreporter": False, **paths}


@app.get("/api/outputs")
def outputs_get():
    from output_settings import archive_root, get_outputs, pdf_root, web_root

    out = get_outputs()
    return {
        "outputs": out,
        "resolved": {
            "archive": str(archive_root()),
            "pdf": str(pdf_root()),
            "web": str(web_root()),
        },
        "xlreporter": False,
    }


@app.put("/api/outputs")
def outputs_put(body: dict = Body(...)):
    from output_settings import archive_root, get_outputs, pdf_root, save_outputs, web_root

    saved = save_outputs(body or {})
    return {
        "ok": True,
        "outputs": saved,
        "resolved": {
            "archive": str(archive_root()),
            "pdf": str(pdf_root()),
            "web": str(web_root()),
        },
        "xlreporter": False,
    }


@app.post("/api/outputs/browse")
def outputs_browse():
    """Native folder picker for PDF / Web / archive / copy-to paths (no DLGLOG check)."""
    import subprocess

    chosen = ""
    err = ""
    try:
        if getattr(sys, "frozen", False):
            proc = subprocess.run(
                [sys.executable, "--browse-folder"],
                capture_output=True,
                text=True,
                timeout=300,
            )
        else:
            script = (
                "import tkinter as tk\n"
                "from tkinter import filedialog\n"
                "root = tk.Tk()\n"
                "root.withdraw()\n"
                "try:\n"
                "    root.attributes('-topmost', True)\n"
                "except Exception:\n"
                "    pass\n"
                "path = filedialog.askdirectory(title='Select output folder')\n"
                "root.destroy()\n"
                "print(path or '')\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=300,
            )
        lines = (proc.stdout or "").strip().splitlines()
        chosen = lines[-1].strip() if lines else ""
        err = (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return {"ok": False, "path": None, "error": "Folder picker timed out", "cancelled": True}
    except OSError as e:
        return {"ok": False, "path": None, "error": str(e), "cancelled": True}

    if not chosen:
        return {
            "ok": False,
            "path": None,
            "error": err or "Cancelled — no folder selected",
            "cancelled": True,
        }
    return {"ok": True, "path": chosen, "cancelled": False}


@app.get("/api/outputs/files")
def outputs_files(
    kind: Annotated[str, Query()] = "pdf",
    limit: Annotated[int, Query(ge=1, le=200)] = 80,
):
    from output_settings import list_output_files

    if kind not in ("pdf", "web", "archive"):
        raise HTTPException(400, "kind must be pdf|web|archive")
    return {"kind": kind, "items": list_output_files(kind, limit), "xlreporter": False}


@app.post("/api/outputs/open")
def outputs_open(body: dict | None = Body(default=None)):
    from output_settings import open_folder

    body = body or {}
    result = open_folder(body.get("path"), kind=str(body.get("kind") or "pdf"))
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "Could not open folder")
    return result


@app.get("/api/archive")
def archive_list(limit: Annotated[int, Query(ge=1, le=200)] = 40):
    return {"items": list_archive(limit), "xlreporter": False}


@app.get("/api/archive/lookup")
def archive_lookup(
    kind: Annotated[str, Query()] = "daily",
    date: str | None = None,
    month: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """
    Fast open: return newest archived report for a period (if any).
    Daily/Monthly UI loads this first; use Update to rebuild from DLGLOG.
    """
    if kind not in ("daily", "monthly", "custom"):
        raise HTTPException(400, "kind must be daily|monthly|custom")
    if kind == "daily" and not date:
        raise HTTPException(400, "date=YYYY-MM-DD required")
    if kind == "monthly" and not month:
        raise HTTPException(400, "month=YYYY-MM required")
    if kind == "custom" and (not start or not end):
        raise HTTPException(400, "start=&end= required")

    hit = find_archived_report(
        kind, date=date, month=month, start=start, end=end
    )
    if not hit:
        return {"found": False, "kind": kind, "xlreporter": False}

    report = dict(hit["report"])
    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    report["meta"] = {
        **meta,
        "source": "archive",
        "from_archive": True,
        "archive_id": hit["id"],
        "archive_saved_at": hit.get("saved_at"),
        "xlreporter": False,
    }
    return {
        "found": True,
        "kind": kind,
        "id": hit["id"],
        "saved_at": hit.get("saved_at"),
        "pdf": hit.get("pdf"),
        "web": hit.get("web"),
        "report": report,
        "xlreporter": False,
    }



@app.get("/api/printers")
def printers():
    from print_util import list_printers

    return {"printers": list_printers(), "xlreporter": False}


@app.post("/api/archive/{archive_id}/print")
def archive_print(archive_id: str, body: dict | None = Body(default=None)):
    from report_jobs import print_archived
    from scheduler import get_schedule

    body = body or {}
    printer = body.get("printer")
    if printer is None:
        printer = get_schedule().get("printer") or None
    result = print_archived(archive_id, printer=printer or None)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "Print failed")
    return result


@app.get("/api/schedule")
def schedule_get():
    from scheduler import status

    return {**status(), "xlreporter": False}


@app.put("/api/schedule")
def schedule_put(body: dict = Body(...)):
    from scheduler import save_schedule, status

    save_schedule(body or {})
    return {**status(), "ok": True, "xlreporter": False}


@app.post("/api/schedule/run")
def schedule_run_now(body: dict | None = Body(default=None)):
    """Manually fire daily or monthly job (for testing / catch-up)."""
    from scheduler import run_daily_job, run_monthly_job

    body = body or {}
    job = body.get("job") or "daily"
    force = bool(body.get("force", True))
    if job == "daily":
        return run_daily_job(force=force)
    if job == "monthly":
        return run_monthly_job(force=force)
    raise HTTPException(400, "job must be daily|monthly")


@app.get("/api/archive/backfill")
def backfill_get():
    from report_jobs import backfill_status

    return {**backfill_status(), "xlreporter": False}


@app.post("/api/archive/backfill")
def backfill_post(body: dict | None = Body(default=None)):
    from report_jobs import start_backfill
    from scheduler import get_schedule

    body = body or {}
    kind = body.get("kind") or "daily"
    date_from = body.get("from") or body.get("date_from")
    date_to = body.get("to") or body.get("date_to")
    print_each = bool(body.get("print", False))
    printer = body.get("printer")
    if printer is None:
        printer = get_schedule().get("printer") or None
    try:
        return start_backfill(
            kind,
            date_from=date_from,
            date_to=date_to,
            print_each=print_each,
            printer=printer or None,
        )
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/plant")
def plant_info():
    cfg = load_config()
    try:
        root = resolve_dlglog()
        dates = list_float_dates(root / trend_model())
        dlglog = str(root)
        ok = True
    except FileNotFoundError as e:
        dates = []
        dlglog = str(e)
        ok = False
    return {
        "product": cfg.get("product", "Ops Reporter"),
        "version": cfg.get("version", "1.0.0"),
        "plant": cfg.get("plant")
        or {
            "id": "plant-1",
            "name": "Water Treatment Plant",
            "municipality": "",
        },
        "models": cfg.get("models"),
        "ok": ok,
        "dlglog": dlglog,
        "date_count": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "xlreporter": False,
    }


# Production: serve built UI from dist/ (one process for customers)
from app_paths import app_home, ensure_runtime_dirs, resource_root  # noqa: E402

ensure_runtime_dirs()
_DIST = resource_root() / "dist"
if not _DIST.is_dir():
    _DIST = app_home() / "dist"
if _DIST.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    assets = _DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str = ""):
        # Never shadow API — FastAPI should match /api/* first, but guard anyway
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        candidate = (_DIST / full_path).resolve()
        try:
            candidate.relative_to(_DIST.resolve())
        except ValueError:
            raise HTTPException(404)
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8787, workers=1)
