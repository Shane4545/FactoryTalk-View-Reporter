"""FastAPI backend — FactoryTalk DLGLOG → Plant Reporter."""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
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
from eu_scale import EU_CACHE_VERSION  # noqa: E402
from period_rollup import (  # noqa: E402
    build_period_report,
    month_bounds,
    parse_iso_week,
    week_bounds,
    year_bounds,
)
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

# Trends remounts hit /api/tags + /api/dates every visit — TTL cache avoids
# re-walking large DLGLOG trees on a warm server (cold disk can be tens of seconds).
_META_TTL_S = 120.0
_tags_meta_cache: dict[str, tuple[float, dict]] = {}
_dates_meta_cache: dict[str, tuple[float, dict]] = {}
_meta_cache_lock = threading.Lock()

# Day-or-longer presets: end of last Float day is a fine chart anchor and skips
# building the full day series cache solely to learn the last sample clock.
_CHEAP_ANCHOR_PRESETS = frozenset({"1d", "7d", "30d", "90d", "1y", "1M"})


def tag_labels() -> dict[str, tuple[str, str, str, str]]:
    """historian -> (short, description, units, source-model) from included profile signals."""
    import profile_v2

    out: dict[str, tuple[str, str, str, str]] = {}
    prof = tag_config.get_profile()
    for s in prof.get("signals") or []:
        if not profile_v2.signal_included(s):
            continue
        hist = s.get("historian") or ""
        if not hist:
            continue
        out[hist] = (
            s.get("tag") or hist,
            s.get("description") or hist,
            s.get("units") or "",
            s.get("model") or "",
        )
    if out:
        return out
    # Projected v1 views (during migration / empty signals)
    for _sec, _kind, short, desc, hist, units, _tot in tag_config.trend_rows():
        out[hist] = (short, desc, units, trend_model())
    for short, desc, hist in tag_config.motor_rows():
        out.setdefault(hist, (short, desc, "", motors_model()))
    for short, desc, hist, units in tag_config.feedback_rows():
        out.setdefault(hist, (short, desc, units, feedback_model()))
    return out


def _require_plant_profile():
    """Raise HTTP 409 when no activated plant profile is configured."""
    try:
        return tag_config.require_configured()
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


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
    with _meta_cache_lock:
        _tags_meta_cache.clear()
        _dates_meta_cache.clear()
    try:
        _disk_tag_index.cache_clear()
    except NameError:
        pass
    try:
        from day_cache import clear_series_mem

        clear_series_mem()
    except Exception:
        pass
    try:
        _last_sample_anchor_cached.cache_clear()
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


@lru_cache(maxsize=64)
def _last_sample_anchor_cached(
    model_key: str, tag: str | None, last_date: str
) -> datetime | None:
    """Cached anchor — invalidated when the newest Float.DAT date changes."""
    root = resolve_dlglog()
    model_dir = root / model_key
    dates = list_float_dates(model_dir)
    if not dates:
        return None
    try:
        from day_cache import ensure_day_series_cache

        # Only need the newest day that has points (walk back a few if empty).
        for date_s in reversed(dates[-3:]):
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
                # points are chronological; last entry ≈ newest sample that day
                ts = datetime.strptime(pts[-1][0], "%Y-%m-%d %H:%M:%S")
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            if last_ts is not None:
                return min(last_ts, end_of_day)
    except (OSError, ValueError, FileNotFoundError):
        pass
    last_day = datetime.strptime(dates[-1], "%Y-%m-%d")
    return last_day.replace(hour=23, minute=59, second=59)


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
    return _last_sample_anchor_cached(model_dir.name, tag, dates[-1])


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


app = FastAPI(title="Plant Reporter", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_api_exception(request, exc: Exception):
    """JSON body for unexpected /api errors (never text/plain 500).

    HTTPException keeps FastAPI's own handler. Setup Activate previously failed
    with plain-text 500 when plant.json replace raced; the UI then showed a
    cryptic JSON parse error.
    """
    from fastapi.responses import JSONResponse

    # Do not swallow HTTPException / validation errors (more-specific handlers).
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if not str(getattr(request.url, "path", "")).startswith("/api"):
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "message": "Server error — see detail",
        },
    )


def _warm_trends_default_day() -> None:
    """Background: build last-day series cache for the trend model (Trends default)."""
    try:
        from day_cache import ensure_day_series_cache

        root = resolve_dlglog()
        model = trend_model()
        dates = list_float_dates(root / model)
        if not dates:
            return
        day = datetime.strptime(dates[-1], "%Y-%m-%d")
        ensure_day_series_cache(root / model, day)
    except Exception as e:  # noqa: BLE001 — never break API
        print(f"[Plant Reporter] trends day warm skipped: {e}", file=sys.stderr)


@app.on_event("startup")
def _warm_series_caches() -> None:
    """Start scheduler + warm last trend day (not full history).

    Full-history series warm on startup saturates disk and makes monthly
    reports 5–6× slower. One day is enough for the Trends default window.
    """
    try:
        from scheduler import start_scheduler

        start_scheduler()
    except Exception as e:  # noqa: BLE001 — never block API boot
        print(f"[Plant Reporter] scheduler failed to start: {e}", file=sys.stderr)
    threading.Thread(
        target=_warm_trends_default_day, name="warm-trends-1d", daemon=True
    ).start()


@app.get("/api/health")
def health():
    cfg = load_config()
    from plant_settings import config_load_warning

    warn = config_load_warning()
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
            "configured": tag_config.is_configured(),
            "profile": (
                __import__("profile_v2").stamp_meta(tag_config.get_profile())
                if tag_config.is_configured()
                else None
            ),
            "models": {
                tm: (root / tm).is_dir(),
                mm: (root / mm).is_dir(),
                fm: (root / fm).is_dir(),
            },
            "models_on_disk": found,
            "date_count": len(dates),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "config_warning": warn,
            "bind": "127.0.0.1:8787",
            "auth": "none — localhost only; do not expose past the plant PC",
        }
    except FileNotFoundError as e:
        return {
            "ok": False,
            "error": str(e),
            "xlreporter": False,
            "plant": cfg.get("plant"),
            "config_warning": warn,
            "bind": "127.0.0.1:8787",
            "auth": "none — localhost only; do not expose past the plant PC",
        }


@app.get("/api/dates")
def available_dates():
    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    key = f"{root}|{trend_model()}"
    now = time.monotonic()
    with _meta_cache_lock:
        hit = _dates_meta_cache.get(key)
        if hit and now - hit[0] < _META_TTL_S:
            return hit[1]
    dates = list_float_dates(root / trend_model())
    payload = {"dlglog": str(root), "dates": dates, "count": len(dates)}
    with _meta_cache_lock:
        _dates_meta_cache[key] = (now, payload)
    return payload


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
        from site_memory import remember_current_site

        remember_current_site()
    except Exception:
        pass
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
    import ftview_tags_csv

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

    draft = tag_config.get_draft_profile()
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
        # Sidecar draft for Setup editor — live profile stays active for reports
        "draft_profile": draft,
        "draft_pending": draft is not None,
        "hmi_tag_export": ftview_tags_csv.summary(),
        "section_choices": tag_config.section_choices_for_editor(
            draft or prof,
        ),
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
    each historian tag (pattern-based; the operator reviews in Setup).

    When an optional FactoryTalk Tags.CSV has been imported, suggestions use
    its descriptions / units instead of raw historian names.
    """
    import ftview_tags_csv

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
    hmi_export = ftview_tags_csv.load_export()

    out: list[dict] = []
    for model in discover_models(root):
        try:
            idx = list_model_tags(root / model)
        except FileNotFoundError:
            continue
        for _i, hist in sorted(idx.items(), key=lambda x: x[1]):
            if hist.startswith("_"):
                continue
            enr = ftview_tags_csv.enrichment_for(hist, hmi_export)
            out.append(
                {
                    "historian": hist,
                    "model": model,
                    "mapped": hist in mapped,
                    "suggestion": tag_config.suggest_for_tag(
                        hist, enrichment=enr, model=model
                    ),
                    "hmi_export": enr,
                }
            )
    return {
        "tags": out,
        "count": len(out),
        "hmi_tag_export": ftview_tags_csv.summary(hmi_export),
        "xlreporter": False,
    }


@app.get("/api/setup/hmi-tags")
def setup_hmi_tags_status():
    """Status of the optional FactoryTalk Tags.CSV enrichment store."""
    import ftview_tags_csv

    summary = ftview_tags_csv.summary()
    dlglog_match = None
    try:
        root = resolve_dlglog()
        names: list[str] = []
        for model in discover_models(root):
            try:
                names.extend(list_model_tags(root / model).values())
            except FileNotFoundError:
                continue
        dlglog_match = ftview_tags_csv.match_against(names)
    except FileNotFoundError:
        dlglog_match = None
    return {**summary, "dlglog_match": dlglog_match, "xlreporter": False}


@app.post("/api/setup/hmi-tags")
async def setup_hmi_tags_import(file: UploadFile = File(...)):
    """Import an optional FactoryTalk View Tag Import/Export CSV.

    File → Tools → Tag Import and Export Wizard → Export. Not required —
    DLGLOG alone works — but when present it fills authoritative descriptions.
    """
    import ftview_tags_csv

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > 20_000_000:
        raise HTTPException(400, "Tags CSV too large (max 20 MB)")
    name = file.filename or "Tags.CSV"
    if not name.lower().endswith((".csv", ".txt")):
        raise HTTPException(400, "Expected a .CSV export from FactoryTalk View")
    try:
        payload = ftview_tags_csv.parse_tags_csv_bytes(data, source_filename=name)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    summary = ftview_tags_csv.save_export(payload)

    dlglog_match = None
    try:
        root = resolve_dlglog()
        names: list[str] = []
        for model in discover_models(root):
            try:
                names.extend(list_model_tags(root / model).values())
            except FileNotFoundError:
                continue
        dlglog_match = ftview_tags_csv.match_against(names, payload)
    except FileNotFoundError:
        dlglog_match = None

    return {
        "ok": True,
        **summary,
        "dlglog_match": dlglog_match,
        "xlreporter": False,
    }


@app.delete("/api/setup/hmi-tags")
def setup_hmi_tags_clear():
    """Remove the optional Tags.CSV enrichment (DLGLOG-only suggestions resume)."""
    import ftview_tags_csv

    ftview_tags_csv.clear_export()
    return {"ok": True, **ftview_tags_csv.summary(), "xlreporter": False}


@app.post("/api/setup/hmi-tags/apply")
def setup_hmi_tags_apply():
    """Return description patches for the active profile from the imported CSV.

    The Setup UI applies these to the in-memory row list so the operator can
    review before Save. Does not write the plant profile by itself.
    """
    import ftview_tags_csv

    export = ftview_tags_csv.load_export()
    if not export:
        raise HTTPException(400, "No FactoryTalk Tags.CSV imported yet")

    patches: list[dict] = []
    for kind, rows in (
        ("trend", tag_config.get_profile()["trend"]),
        ("motor", tag_config.get_profile()["motors"]),
        ("feedback", tag_config.get_profile()["feedback"]),
    ):
        for r in rows:
            hist = r.get("historian") or ""
            enr = ftview_tags_csv.enrichment_for(hist, export)
            if not enr or not enr.get("description"):
                continue
            patch: dict = {
                "historian": hist,
                "kind": kind,
                "description": enr["description"],
            }
            if kind != "motor" and enr.get("units"):
                patch["units"] = enr["units"]
            patches.append(patch)

    # Also suggest patches for any DLGLOG tags not yet in the profile
    discover_patches: list[dict] = []
    try:
        root = resolve_dlglog()
        mapped = {p["historian"] for p in patches}
        mapped |= {r["historian"] for r in tag_config.get_profile()["trend"]}
        mapped |= {r["historian"] for r in tag_config.get_profile()["motors"]}
        mapped |= {r["historian"] for r in tag_config.get_profile()["feedback"]}
        for model in discover_models(root):
            try:
                idx = list_model_tags(root / model)
            except FileNotFoundError:
                continue
            for _i, hist in idx.items():
                if hist.startswith("_") or hist in mapped:
                    continue
                enr = ftview_tags_csv.enrichment_for(hist, export)
                if not enr or not enr.get("description"):
                    continue
                sug = tag_config.suggest_for_tag(hist, enrichment=enr)
                discover_patches.append(
                    {
                        "historian": hist,
                        "model": model,
                        "suggestion": sug,
                        "hmi_export": enr,
                    }
                )
    except FileNotFoundError:
        pass

    return {
        "ok": True,
        "profile_patches": patches,
        "unmapped_with_descriptions": discover_patches[:200],
        "count": len(patches),
        "xlreporter": False,
    }


def _warm_day_aggregates(days: int = 45) -> None:
    """Rebuild recent day-aggregate caches in the background after a profile
    change (new scaling fingerprint = cold caches; first report would
    otherwise take minutes).

    Skips days already warm. Seeds the current fingerprint folder from orphan
    sibling caches first so Activate/include edits do not thrash the disk.
    """
    import os
    import threading
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from day_cache import day_cache_ready, seed_cache_namespace_from_orphans
    from model_reads import profile_model_set
    from period_rollup import _load_one_day_worker

    def worker() -> None:
        try:
            seed_cache_namespace_from_orphans()
            root = resolve_dlglog()
            prof = tag_config.get_profile()
        except (FileNotFoundError, Exception):
            return
        if not prof.get("configured"):
            return
        models = profile_model_set(prof)
        date_set: set[str] = set()
        for m in models:
            date_set |= set(list_float_dates(root / m)[-days:])
        dates = sorted(date_set)[-days:]
        if not dates:
            return
        need: list[str] = []
        for ds in dates:
            day = datetime.strptime(ds, "%Y-%m-%d")
            cold = False
            for m in models:
                md = root / m
                # Analog models need plain cache; motor folders need runtime cache.
                if not day_cache_ready(md, day) and not day_cache_ready(
                    md, day, runtime=True
                ):
                    cold = True
                    break
            if cold:
                need.append(ds)
        if not need:
            return
        root_s = str(root)
        workers = min(2, os.cpu_count() or 2, max(1, len(need)))
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futs = [
                    pool.submit(_load_one_day_worker, root_s, ds, prof)
                    for ds in need
                ]
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except Exception:
                        pass
        except Exception:
            for ds in need:
                try:
                    _load_one_day_worker(root_s, ds, prof)
                except Exception:
                    pass

    threading.Thread(target=worker, name="day-agg-warmer", daemon=True).start()


@app.get("/api/setup/inventory")
def setup_inventory(sample_day: str | None = Query(None)):
    """Full DLGLOG inventory + confidence-scored suggestions for Plant Builder."""
    import builder_inventory

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    return builder_inventory.build_inventory(root, sample_day=sample_day)


@app.post("/api/setup/bootstrap-from-dlglog")
def setup_bootstrap_from_dlglog(body: dict = Body(default=None)):
    """After Connect: scan DLGLOG and Activate so Daily works immediately."""
    raw = body or {}
    sample_day = raw.get("sample_day") if isinstance(raw, dict) else None
    try:
        result = tag_config.bootstrap_from_dlglog(sample_day=sample_day)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    _warm_day_aggregates()
    return {"ok": True, **result}


@app.post("/api/setup/validate")
def setup_validate(body: dict = Body(default=None)):
    """Validate a draft profile (or the saved one) before activation."""
    import profile_validate

    raw = body or {}
    if raw.get("tag_config"):
        raw = raw["tag_config"]
    if not raw or not (
        raw.get("signals") or raw.get("trend") or raw.get("motors") or raw.get("feedback")
    ):
        raw = tag_config.get_profile()
    else:
        raw = tag_config.normalize_profile(raw)
    try:
        dlg = resolve_dlglog()
    except FileNotFoundError:
        dlg = None
    result = profile_validate.validate_profile(raw, dlglog=dlg)
    return {**result, "xlreporter": False}


@app.put("/api/setup/profile")
def setup_save_profile(body: dict = Body(...)):
    """Save the site tag profile. Pass activate=false to keep a draft.

    On an already-active plant, activate=false writes a draft sidecar only and
    does **not** demote live ``tag_config`` (reports stay configured). First-time
    plants still save draft as the primary profile until Activate.
    """
    data = body or {}
    activate = True
    if "activate" in data:
        activate = bool(data.pop("activate"))
        # allow nested tag_config
    if isinstance(data.get("tag_config"), dict) and not (
        data.get("trend") or data.get("signals")
    ):
        data = data["tag_config"]
    if activate:
        import profile_validate

        draft = tag_config.normalize_profile(data)
        try:
            dlg = resolve_dlglog()
        except FileNotFoundError:
            dlg = None
        # Mutates draft: clears CT/Insight refs to Use=false tags (warn, don't block)
        gate = profile_validate.validate_profile(draft, dlglog=dlg)
        if not gate["ok"]:
            raise HTTPException(
                400,
                {
                    "message": "Validation failed — fix errors before activating",
                    **gate,
                },
            )
        # Persist pruned roles/CT from the validated draft
        data = draft
    # Soft-confirm signals that were reviewed (included rows are confirmed)
    if isinstance(data.get("signals"), list):
        for s in data["signals"]:
            if isinstance(s, dict) and s.get("confirmed") is None:
                s["confirmed"] = True
    for key in ("trend", "motors", "feedback"):
        for r in data.get(key) or []:
            if isinstance(r, dict) and "confirmed" not in r:
                r["confirmed"] = True
    was_configured = tag_config.is_configured()
    try:
        prof = tag_config.save_profile(data, activate=activate)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        # Windows file lock on plant.json — return JSON so the UI does not show
        # a cryptic "Unexpected token" / JSON parse error from text/plain 500s.
        raise HTTPException(
            503,
            f"Could not save plant profile (file busy): {e}. Try Activate again.",
        ) from e
    _warm_day_aggregates()
    draft_prof = tag_config.get_draft_profile()
    sidecar = (not activate) and was_configured and draft_prof is not None
    return {
        "ok": True,
        "profile": prof,
        "draft_profile": draft_prof,
        "draft_pending": draft_prof is not None,
        "draft_sidecar": sidecar,
        "configured": tag_config.is_configured(),
        "activated": activate and prof.get("status") == "active",
    }


@app.post("/api/setup/activate")
def setup_activate(body: dict = Body(default=None)):
    """Validate + activate current draft (or body) as a new immutable revision."""
    data = body
    if not data:
        data = tag_config.get_draft_profile() or tag_config.get_profile()
    if isinstance(data.get("tag_config"), dict) and not (
        data.get("trend") or data.get("signals") or data.get("motors")
    ):
        data = data["tag_config"]
    # Accept nested {profile: {...}} the same way export/import clients may send it
    if isinstance(data.get("profile"), dict) and not (
        data.get("trend") or data.get("signals") or data.get("motors")
    ):
        data = data["profile"]
    return setup_save_profile({**data, "activate": True})


def _setup_preview_report(date: str, prof: dict) -> dict:
    """Build a daily report for Setup preview from an in-memory or saved profile.

    Never writes plant.json — callers must not demote an active profile.
    """
    from model_reads import load_day_for_profile
    import profile_v2
    from report_prefs import hidden_sets

    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(400, f"bad date: {e}") from e

    if not (prof.get("signals") or prof.get("trend") or prof.get("motors")):
        raise HTTPException(
            409,
            "No draft mapping yet — scan inventory and include tags, then preview "
            "or Save draft",
        )

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    try:
        trend, motors, feedback, motor_runtime, coverage = load_day_for_profile(
            root, day, prof
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    if not coverage.get("day_ok"):
        raise HTTPException(404, f"No data for profile models on {date}")

    hide = hidden_sets()
    report = build_daily(
        day,
        trend,
        motors,
        feedback,
        motor_runtime=motor_runtime,
        hidden_trend=hide["trend"],
        hidden_motor=hide["motor"],
        hidden_feedback=hide["feedback"],
        hidden_sections=hide["section"],
    )
    report["meta"] = {
        "kind": "preview",
        "preview": True,
        "profile": profile_v2.stamp_meta(prof),
        "coverage": coverage,
    }
    return report


@app.get("/api/setup/preview")
def setup_preview(date: str = Query(..., description="YYYY-MM-DD")):
    """Preview using the saved profile on disk (active or draft). Read-only."""
    return _setup_preview_report(date, tag_config.get_profile())


@app.post("/api/setup/preview")
def setup_preview_post(
    date: str = Query(..., description="YYYY-MM-DD"),
    body: dict = Body(default=None),
):
    """Preview a day from an in-memory draft mapping without writing plant.json.

    Prefer this over PUT for throwaway checks. Save draft on an active plant
    writes a sidecar only (does not demote); Preview never writes plant.json.
    First-time (never activated) plants can still preview before Activate.
    """
    raw = body or {}
    if isinstance(raw.get("tag_config"), dict) and not (
        raw.get("trend") or raw.get("signals")
    ):
        raw = raw["tag_config"]
    if raw and (
        raw.get("signals") or raw.get("trend") or raw.get("motors") or raw.get("feedback")
    ):
        prof = tag_config.normalize_profile(raw)
    else:
        prof = tag_config.get_profile()
    return _setup_preview_report(date, prof)


@app.post("/api/setup/reset")
def setup_reset_profile():
    """Clear the custom profile — plant becomes unconfigured (reports blocked)."""
    prof = tag_config.reset_profile()
    clear_data_caches()
    return {"ok": True, "profile": prof, "configured": False}


@app.post("/api/setup/reset-example")
def setup_reset_example():
    """Load and activate the built-in Chalk River example profile."""
    prof = tag_config.reset_to_example()
    _warm_day_aggregates()
    return {"ok": True, "profile": prof, "configured": tag_config.is_configured()}


@app.post("/api/setup/reset-generic")
def setup_reset_generic():
    """Reset to a blank vanilla plant template (empty tags; disconnect DLGLOG).

    Also wipes day cache, archives, PDF/Web/Trends outputs, site memory,
    schedule (disabled), and HMI Tags.CSV import — so no prior plant data remains.
    """
    from app_paths import app_home

    prof = tag_config.reset_to_generic()
    clear_data_caches()
    cfg = load_config()
    plant = cfg.get("plant") or {}
    chalk_leaks = []
    blob = json.dumps(cfg).lower()
    for needle in ("chalk", "laurentian", "wtp_trend", "fit101"):
        if needle in blob:
            chalk_leaks.append(needle)
    home = app_home()
    cache_days = home / "cache" / "days"
    archive = home / "archive"
    return {
        "ok": True,
        "profile": prof,
        "configured": tag_config.is_configured(),
        "plant": plant,
        "dlglog_path": cfg.get("dlglog_path") or "",
        "sites_count": len(cfg.get("sites") or {}),
        "models_on_disk": [],
        "logo": "capital-controls (CCI) until plant uploads",
        "blank": True,
        "disconnected": True,
        "cache_days_empty": not cache_days.is_dir()
        or not any(cache_days.iterdir()),
        "archive_empty": not archive.is_dir()
        or not any(
            p for p in archive.iterdir() if p.name.lower() not in ("readme.txt", ".gitkeep")
        ),
        "chalk_residue": chalk_leaks,
    }


@app.get("/api/setup/export")
def setup_export_profile():
    """Portable profile JSON (tag map + plant info) for backup / another PC."""
    cfg = load_config()
    return {
        "ops_reporter_profile": 2,
        "plant": cfg.get("plant") or {},
        "tag_config": tag_config.get_profile(),
    }


@app.post("/api/setup/import")
def setup_import_profile(body: dict = Body(...)):
    """Import a profile exported from another Plant Reporter install."""
    data = body or {}
    tc = data.get("tag_config") if isinstance(data.get("tag_config"), dict) else data
    if not isinstance(tc, dict) or not (
        tc.get("signals") or tc.get("trend") or tc.get("motors")
    ):
        raise HTTPException(
            400, "Not a valid Plant Reporter profile (no signals/trend/motor rows)"
        )
    if isinstance(data.get("plant"), dict):
        save_config({"plant": data["plant"]})
    # Import as draft-then-activate through validation
    return setup_save_profile({**tc, "activate": True})


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
    """Tags for Trends: included profile signals first, then unmapped model tags.

    Historians explicitly unchecked (include=false) in the active plant profile
    are never listed — Setup Use must filter Trends the same way as reports.
    """
    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    key = str(root)
    now = time.monotonic()
    with _meta_cache_lock:
        hit = _tags_meta_cache.get(key)
        if hit and now - hit[0] < _META_TTL_S:
            return hit[1]

    import profile_v2

    labels = tag_labels()
    excluded_hist: set[str] = set()
    for s in tag_config.get_profile().get("signals") or []:
        hist = s.get("historian") or ""
        if hist and not profile_v2.signal_included(s):
            excluded_hist.add(hist)

    tags: list[dict] = []
    seen_hist: set[str] = set()
    seen_id: set[str] = set()

    # Labeled profile tags first (stable operator names + source model)
    for hist, (short, desc, units, model) in labels.items():
        tags.append(
            {
                "id": short,
                "historianTag": hist,
                "description": desc,
                "units": units,
                "model": model or trend_model(),
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
            if name in excluded_hist:
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

    payload = {"tags": tags, "count": len(tags)}
    with _meta_cache_lock:
        _tags_meta_cache[key] = (now, payload)
    return payload


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
            return hist, short, desc, model or trend_model()

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
        # Prefer profile signal model when known
        for hist, (short, desc, units, model) in labels.items():
            if hist == t:
                return hist, short, desc, model or trend_model()
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

    series = load_series_cached(
        root / model, hist, s, e, max_points=max_points, want_tags={hist}
    )
    series["id"] = short
    series["description"] = desc
    series["model"] = model
    series["units"] = tag_labels().get(hist, ("", "", "", ""))[2]
    series["preset"] = preset
    series["xlreporter"] = False
    return series


@app.get("/api/reports/daily")
def daily_report(date: str = Query(..., description="YYYY-MM-DD")):
    from model_reads import load_day_for_profile
    import profile_v2

    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(400, f"bad date: {e}") from e

    prof = _require_plant_profile()

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
        trend, motors, feedback, motor_runtime, coverage = load_day_for_profile(
            root, day, prof
        )
    except FileNotFoundError as e:
        raise HTTPException(404, f"No data for {date}: {e}") from e

    if not coverage.get("day_ok"):
        raise HTTPException(
            404,
            f"No Float.DAT for profile models on {date} "
            f"(tried: {', '.join(profile_v2.signals_by_model(prof).keys())})",
        )

    as_of = datetime.now() if live else None
    from report_prefs import hidden_sets
    import time as _time

    hide = hidden_sets()
    _t0 = _time.perf_counter()
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
        report_kind="daily",
    )
    _build_s = _time.perf_counter() - _t0
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
        "data_version": EU_CACHE_VERSION,
        "xlreporter": False,
        "kind": "daily",
        "live": live,
        "tag_count_trend": len(trend),
        "tag_count_motors": len(motors),
        "tag_count_feedback": len(feedback),
        "coverage": coverage,
        "profile": profile_v2.stamp_meta(prof),
        "timing_build_s": round(_build_s, 3),
        "proof": {
            "tag": proof_short,
            "FIT101_samples": fit.count if fit else 0,
            "FIT101_min": fit.min if fit else None,
            "FIT101_max": fit.max if fit else None,
            "CT_Achieved": ct0.get("giardia"),
        },
    }
    # Insights health strip — Daily only (nudges operators to open Insights).
    try:
        from plant_insights import build_insights

        period_hours = 24.0
        if live and as_of is not None:
            day_start = datetime(day.year, day.month, day.day, 0, 0, 0)
            period_hours = max(0.25, (as_of - day_start).total_seconds() / 3600.0)
        insights = build_insights(
            date=date,
            trend=trend,
            motor_runtime=motor_runtime,
            ct_rows=report.get("ct"),
            live=live,
            hidden_trend=hide["trend"],
            hidden_motor=hide["motor"],
            hidden_sections=hide["section"],
            period_hours=period_hours,
        )
        ov = insights.get("overall") or {}
        wqi = insights.get("water_quality") or {}
        ct_i = insights.get("ct") or {}
        report["insights"] = {
            "date": date,
            "score": ov.get("score"),
            "severity": ov.get("severity"),
            "label": ov.get("label"),
            "counts": ov.get("counts") or {},
            "wqi_grade": wqi.get("grade"),
            "wqi_label": wqi.get("label"),
            "ct_severity": ct_i.get("severity"),
            "suggestions": (insights.get("suggestions") or [])[:3],
            "href": f"/insights?date={date}",
        }
    except Exception:
        report["insights"] = None
    try:
        import day_notes

        report["operatorNotes"] = day_notes.get_notes(date)
    except Exception:
        report["operatorNotes"] = {
            "date": date,
            "notes": "",
            "operator": "",
            "reviewed_by": "",
            "updated_at": None,
        }
    return report


@app.get("/api/reports/daily/notes")
def daily_notes_get(date: str = Query(..., description="YYYY-MM-DD")):
    import day_notes

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(400, f"bad date: {e}") from e
    return day_notes.get_notes(date)


@app.put("/api/reports/daily/notes")
def daily_notes_put(body: dict = Body(...)):
    import day_notes

    date = str(body.get("date") or "").strip()[:10]
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(400, f"bad date: {e}") from e
    try:
        return day_notes.save_notes(
            date,
            notes=str(body.get("notes") or ""),
            operator=str(body.get("operator") or ""),
            reviewed_by=str(body.get("reviewed_by") or ""),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _proof_from_report(report: dict) -> dict:
    """Sample fingerprint for status / report header (same shape as Daily).

    Uses the configured raw-flow role when present, else the first flow/totalize
    row, else the first trend row with samples.
    """
    proof_hist = tag_config.roles().get("raw_flow")
    trows = tag_config.trend_rows()
    if not proof_hist and trows:
        proof_hist = next(
            (h for _s, kind, _t, _d, h, _u, _tu in trows if kind == "minmax_total"),
            trows[0][4],
        )
    proof_short = next(
        (t for _s, _k, t, _d, h, _u, _t in trows if h == proof_hist),
        proof_hist,
    )
    agg: dict | None = None
    if proof_short:
        for sec in report.get("sections") or []:
            for row in sec.get("rows") or []:
                if row.get("tag") == proof_short or row.get("historianTag") == proof_hist:
                    agg = row.get("aggregate") or {}
                    break
            if agg is not None:
                break
    samples = int((agg or {}).get("count") or 0)
    return {
        "tag": proof_short,
        "FIT101_samples": samples,
        "FIT101_min": (agg or {}).get("min"),
        "FIT101_max": (agg or {}).get("max"),
        "CT_Achieved": None,
    }


@app.get("/api/reports/monthly")
def monthly_report(month: str = Query(..., description="YYYY-MM")):
    _require_plant_profile()
    try:
        y, m = month.split("-")
        start, end = month_bounds(int(y), int(m))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"bad month (use YYYY-MM): {e}") from e

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    import time as _time

    _t0 = _time.perf_counter()
    try:
        report = build_period_report(
            root,
            start,
            end,
            subtitle="Monthly Operations Report",
            period_label=f"Calendar month {month} (days with DLGLOG data)",
            report_kind="monthly",
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    _build_s = _time.perf_counter() - _t0

    meta_period = report.pop("meta_period", {}) or {}
    report["meta"] = {
        "source": "dlglog",
        "dlglog": str(root),
        "data_version": EU_CACHE_VERSION,
        "xlreporter": False,
        "kind": "monthly",
        "month": month,
        "profile": report.get("profile"),
        "timing_build_s": round(_build_s, 3),
        "proof": _proof_from_report(report),
        **meta_period,
    }
    # Keep for archive HTML / UI helpers that still read meta_period.
    report["meta_period"] = dict(meta_period)
    return report


@app.get("/api/reports/weekly")
def weekly_report(week: str = Query(..., description="Sunday-start week YYYY-Www")):
    _require_plant_profile()
    try:
        y, w = parse_iso_week(week)
        start, end = week_bounds(y, w)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"bad week (use YYYY-Www): {e}") from e

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    import time as _time

    week_key = f"{y:04d}-W{w:02d}"
    _t0 = _time.perf_counter()
    try:
        report = build_period_report(
            root,
            start,
            end,
            subtitle="Weekly Operations Report",
            period_label=(
                f"Week {week_key} (Sun–Sat) "
                f"({start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')})"
            ),
            report_kind="weekly",
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    _build_s = _time.perf_counter() - _t0

    meta_period = report.pop("meta_period", {}) or {}
    report["meta"] = {
        "source": "dlglog",
        "dlglog": str(root),
        "data_version": EU_CACHE_VERSION,
        "xlreporter": False,
        "kind": "weekly",
        "week": week_key,
        "week_start": "sunday",
        "profile": report.get("profile"),
        "timing_build_s": round(_build_s, 3),
        "proof": _proof_from_report(report),
        **meta_period,
    }
    report["meta_period"] = dict(meta_period)
    return report


@app.get("/api/reports/yearly")
def yearly_report(year: int = Query(..., description="Calendar year YYYY", ge=1990, le=2100)):
    _require_plant_profile()
    start, end = year_bounds(int(year))

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    import time as _time

    _t0 = _time.perf_counter()
    try:
        report = build_period_report(
            root,
            start,
            end,
            subtitle="Yearly Operations Report",
            period_label=f"Calendar year {year} (days with DLGLOG data)",
            report_kind="yearly",
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    _build_s = _time.perf_counter() - _t0

    meta_period = report.pop("meta_period", {}) or {}
    report["meta"] = {
        "source": "dlglog",
        "dlglog": str(root),
        "data_version": EU_CACHE_VERSION,
        "xlreporter": False,
        "kind": "yearly",
        "year": int(year),
        "profile": report.get("profile"),
        "timing_build_s": round(_build_s, 3),
        "proof": _proof_from_report(report),
        **meta_period,
    }
    report["meta_period"] = dict(meta_period)
    return report


@app.get("/api/insights")
def plant_insights_api(
    date: str | None = Query(None, description="YYYY-MM-DD (default: last complete day)"),
):
    """
    Operator troubleshooting dashboard: traffic-light instrument/motor health,
    CT margin, plant metrics, and suggestions for the selected day.
    """
    from model_reads import load_day_for_profile, profile_model_set
    from plant_insights import build_insights
    from report_prefs import catalog, hidden_sets

    prof = _require_plant_profile()

    try:
        root = resolve_dlglog()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e

    date_set: set[str] = set()
    for m in profile_model_set(prof):
        date_set |= set(list_float_dates(root / m))
    dates = sorted(date_set)
    if not dates:
        raise HTTPException(404, "No datalog days available for profile models")

    today = datetime.now().strftime("%Y-%m-%d")
    if not date:
        complete = [d for d in dates if d < today]
        date = complete[-1] if complete else dates[-1]

    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(400, f"bad date: {e}") from e

    live = date == today
    if live:
        _cached_model.cache_clear()
        _cached_motors.cache_clear()

    try:
        trend, _motors, feedback, motor_runtime, coverage = load_day_for_profile(
            root, day, prof
        )
    except FileNotFoundError as e:
        raise HTTPException(404, f"No trend data for {date}: {e}") from e
    if not coverage.get("day_ok"):
        raise HTTPException(404, f"No data for profile models on {date}")

    hide = hidden_sets()
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
                day_aggs, _, _, _, cov = load_day_for_profile(
                    root, datetime.strptime(d, "%Y-%m-%d"), prof
                )
            except FileNotFoundError:
                continue
            if not cov.get("day_ok"):
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
            _, _, _, model = _resolve_tag(hist)
            ser = load_series_cached(
                root / model, hist, day_start, day_end, max_points=36
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
    _require_plant_profile()
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
            report_kind="custom",
        )
    except FileNotFoundError as ex:
        raise HTTPException(404, str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(409, str(ex)) from ex

    meta_period = report.pop("meta_period", {}) or {}
    report["meta"] = {
        "source": "dlglog",
        "dlglog": str(root),
        "data_version": EU_CACHE_VERSION,
        "xlreporter": False,
        "kind": "custom",
        "profile": report.get("profile"),
        "proof": _proof_from_report(report),
        **meta_period,
    }
    report["meta_period"] = dict(meta_period)
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

    resolved = [_resolve_tag(n) for n in names]
    hist0, _, _, model0 = resolved[0]
    dates = list_float_dates(root / model0)
    if not dates:
        raise HTTPException(404, f"No data for {model0}")

    use_preset = (preset or "1d") if not start or not end else None
    if use_preset and use_preset in _CHEAP_ANCHOR_PRESETS:
        # Avoid last_sample_anchor → ensure_day_series_cache just for the clock.
        last_data = datetime.strptime(dates[-1], "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    else:
        last_data = last_sample_anchor(root / model0, tag=hist0)
    assert last_data is not None

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

    # Warm day caches once per model/day for selected tags only, then assemble.
    models_needed = {m for _h, _s, _d, m in resolved}
    want_by_model: dict[str, set[str]] = {}
    for hist, _short, _desc, model in resolved:
        want_by_model.setdefault(model, set()).add(hist)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import timedelta as _td
    from day_cache import ensure_day_series_cache

    warm_days: list[datetime] = []
    day = datetime(s.year, s.month, s.day)
    last_day = datetime(e.year, e.month, e.day)
    while day <= last_day:
        warm_days.append(day)
        day = day + _td(days=1)

    def _warm(mname: str, d: datetime) -> None:
        try:
            ensure_day_series_cache(
                root / mname, d, want_tags=want_by_model.get(mname)
            )
        except FileNotFoundError:
            pass

    jobs = [(m, d) for d in warm_days for m in models_needed]
    workers = min(12 if len(jobs) >= 30 else 8, max(1, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_warm, m, d) for m, d in jobs]
        for fut in as_completed(futs):
            fut.result()

    def _one_series(name: str, hist: str, short: str, desc: str, model: str) -> dict:
        ser = load_series_cached(
            root / model,
            hist,
            s,
            e,
            max_points=max_points,
            want_tags=want_by_model.get(model),
        )
        ser["id"] = short
        ser["description"] = desc
        ser["model"] = model
        ser["units"] = tag_labels().get(hist, ("", "", "", ""))[2]
        return ser

    series_out: list[dict] = []
    # After warm, assembly is memory/disk-hit — parallelize tag extract.
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(resolved)))) as pool:
        futs = [
            pool.submit(_one_series, n, h, short, desc, model)
            for n, (h, short, desc, model) in zip(names, resolved)
        ]
        for fut in futs:
            series_out.append(fut.result())

    return {
        "start": s.isoformat(sep=" "),
        "end": e.isoformat(sep=" "),
        "preset": use_preset or preset,
        "xlreporter": False,
        "series": series_out,
    }


@app.post("/api/trends/export")
def trends_export(body: dict = Body(...)):
    """Save current multi-tag Trends view as PDF under Trends/."""
    from trend_export import export_trends_pdf

    tags = body.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not tags or len(tags) > 6:
        raise HTTPException(400, "Provide 1–6 tags")
    preset = body.get("preset")
    start = body.get("start")
    end = body.get("end")
    open_after = bool(body.get("open", False))
    # Reuse GET /api/trends logic
    qs_tags = ",".join(str(t) for t in tags)
    data = multi_trend(
        tags=qs_tags,
        preset=preset if not (start and end) else None,
        start=start,
        end=end,
        max_points=800,
    )
    result = export_trends_pdf(
        data.get("series") or [],
        start=data.get("start") or "",
        end=data.get("end") or "",
        preset=data.get("preset"),
        open_after=open_after,
    )
    if not result.get("ok"):
        raise HTTPException(500, result.get("error") or "Trends PDF export failed")
    return {**result, "xlreporter": False}


@app.get("/api/trends/export.csv")
def trends_export_csv(
    tags: str = Query(..., description="Comma-separated short or historian tags"),
    preset: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Download the current Trends view as CSV (one column per tag)."""
    import csv
    import io

    from fastapi.responses import Response

    data = multi_trend(
        tags=tags,
        preset=preset if not (start and end) else None,
        start=start,
        end=end,
        max_points=3000,
    )
    series = data.get("series") or []

    # Wide format: union of sample times, one value column per tag
    per_tag: list[dict[str, float]] = []
    stamps: set[str] = set()
    for ser in series:
        m = {p["t"]: p["v"] for p in (ser.get("points") or [])}
        per_tag.append(m)
        stamps.update(m)

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    header = ["Timestamp"]
    for ser in series:
        label = ser.get("id") or ser.get("tag") or ""
        desc = ser.get("description") or ""
        units = ser.get("units") or ""
        if desc and desc != label:
            label = f"{label} — {desc}"
        if units:
            label = f"{label} ({units})"
        header.append(label)
    w.writerow(header)
    for t in sorted(stamps):
        w.writerow([t] + [m.get(t, "") for m in per_tag])

    first_day = (data.get("start") or "")[:10]
    short_ids = "_".join(
        str(s.get("id") or s.get("tag") or "tag") for s in series
    )[:60]
    fname = f"trends_{first_day}_{short_ids}.csv" if series else "trends.csv"
    # UTF-8 BOM so Excel detects encoding (units like °C, µg/L)
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/archive")
def archive_produce(
    kind: str = "daily",
    date: str | None = None,
    month: str | None = None,
    week: str | None = None,
    year: int | None = None,
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
    elif kind == "weekly":
        if not week:
            raise HTTPException(400, "week=YYYY-Www required")
        report = weekly_report(week)
    elif kind == "yearly":
        if year is None:
            raise HTTPException(400, "year=YYYY required")
        report = yearly_report(int(year))
    elif kind == "custom":
        if not start or not end:
            raise HTTPException(400, "start=&end= required")
        report = custom_report(start, end)
    else:
        raise HTTPException(400, "kind must be daily|weekly|monthly|yearly|custom")

    paths = save_report(report, kind)
    return {"ok": True, "xlreporter": False, **paths}


@app.get("/api/outputs")
def outputs_get():
    from output_settings import (
        archive_root,
        get_outputs,
        logo_root,
        pdf_root,
        trends_root,
        web_root,
    )

    out = get_outputs()
    return {
        "outputs": out,
        "resolved": {
            "archive": str(archive_root()),
            "pdf": str(pdf_root()),
            "web": str(web_root()),
            "logo": str(logo_root()),
            "trends": str(trends_root()),
        },
        "xlreporter": False,
    }


@app.put("/api/outputs")
def outputs_put(body: dict = Body(...)):
    from output_settings import (
        archive_root,
        get_outputs,
        logo_root,
        pdf_root,
        save_outputs,
        trends_root,
        web_root,
    )

    saved = save_outputs(body or {})
    return {
        "ok": True,
        "outputs": saved,
        "resolved": {
            "archive": str(archive_root()),
            "pdf": str(pdf_root()),
            "web": str(web_root()),
            "logo": str(logo_root()),
            "trends": str(trends_root()),
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

    if kind not in ("pdf", "web", "archive", "trends", "logo"):
        raise HTTPException(400, "kind must be pdf|web|archive|trends|logo")
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
    week: str | None = None,
    year: int | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """
    Fast open: return newest archived report for a period (if any).
    Daily/Monthly UI loads this first; use Update to rebuild from DLGLOG.
    """
    if kind not in ("daily", "weekly", "monthly", "yearly", "custom"):
        raise HTTPException(400, "kind must be daily|weekly|monthly|yearly|custom")
    if kind == "daily" and not date:
        raise HTTPException(400, "date=YYYY-MM-DD required")
    if kind == "monthly" and not month:
        raise HTTPException(400, "month=YYYY-MM required")
    if kind == "weekly" and not week:
        raise HTTPException(400, "week=YYYY-Www required")
    if kind == "yearly" and year is None:
        raise HTTPException(400, "year=YYYY required")
    if kind == "custom" and (not start or not end):
        raise HTTPException(400, "start=&end= required")

    hit = find_archived_report(
        kind,
        date=date,
        month=month,
        week=week,
        year=year,
        start=start,
        end=end,
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
    if kind == "daily" and date:
        try:
            import day_notes

            report["operatorNotes"] = day_notes.get_notes(date)
        except Exception:
            pass
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
def schedule_get(log_limit: int = 50):
    from scheduler import status

    return {**status(log_limit=log_limit), "xlreporter": False}


@app.put("/api/schedule")
def schedule_put(body: dict = Body(...)):
    from scheduler import save_schedule, status

    data = body or {}
    # Accept either flat schedule fields (UI) or nested {schedule: {...}}
    if isinstance(data.get("schedule"), dict) and not any(
        k in data for k in ("enabled", "daily", "weekly", "monthly", "yearly")
    ):
        data = data["schedule"]
    save_schedule(data)
    return {**status(), "ok": True, "xlreporter": False}


@app.delete("/api/schedule/log")
def schedule_log_clear(
    older_than_days: int | None = None,
    body: dict | None = Body(default=None),
):
    """
    Clear schedule activity log (config/schedule_log.jsonl).
    Query or body: older_than_days=null|int
      - omit / null → clear all entries
      - N → keep only events from the last N days
    Does not delete archived reports or PDF/Web output files.
    """
    from scheduler import clear_log, status

    body = body or {}
    older = body.get("older_than_days", older_than_days)
    if older is not None:
        try:
            older = int(older)
        except (TypeError, ValueError) as e:
            raise HTTPException(400, "older_than_days must be an integer or null") from e
        if older < 0:
            raise HTTPException(400, "older_than_days must be >= 0")
    result = clear_log(older_than_days=older)
    return {**result, **status(), "xlreporter": False}


@app.post("/api/schedule/run")
def schedule_run_now(body: dict | None = Body(default=None)):
    """Manually fire daily/weekly/monthly/yearly/trends job (for testing / catch-up)."""
    from scheduler import (
        run_daily_job,
        run_monthly_job,
        run_trends_job,
        run_weekly_job,
        run_yearly_job,
    )

    body = body or {}
    # UI sends {job}; accept legacy {kind} as an alias — never silently default
    # when the client sent an unrecognized key.
    job = body.get("job") or body.get("kind")
    if not job:
        raise HTTPException(400, "job must be daily|weekly|monthly|yearly|trends")
    force = bool(body.get("force", True))
    if job == "daily":
        return run_daily_job(force=force)
    if job == "weekly":
        return run_weekly_job(force=force)
    if job == "monthly":
        return run_monthly_job(force=force)
    if job == "yearly":
        return run_yearly_job(force=force)
    if job == "trends":
        return run_trends_job(force=force)
    raise HTTPException(400, "job must be daily|weekly|monthly|yearly|trends")

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
    force = bool(body.get("force", False))
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
            force=force,
        )
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/archive/backfill/stop")
def backfill_stop():
    from report_jobs import stop_backfill

    return {**stop_backfill(), "xlreporter": False}


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
    plant = cfg.get("plant") or {
        "id": "plant-1",
        "name": "Water Treatment Plant",
        "municipality": "",
    }
    return {
        "product": cfg.get("product", "Plant Reporter"),
        "version": cfg.get("version", "1.0.0"),
        "plant": plant,
        "models": cfg.get("models"),
        "ok": ok,
        "dlglog": dlglog,
        "date_count": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "logo_url": "/api/branding/logo",
        "has_custom_logo": bool((plant or {}).get("logo_file")),
        "xlreporter": False,
    }


@app.get("/api/branding/logo")
def branding_logo():
    """Serve active plant logo (custom upload or Chalk default JPEG/PNG)."""
    from fastapi.responses import FileResponse

    import branding

    path = branding.active_logo_path()
    if not path:
        raise HTTPException(404, "No logo available")
    return FileResponse(
        path,
        media_type=branding.logo_media_type(path),
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/api/branding/logo")
async def branding_logo_upload(file: UploadFile = File(...)):
    import branding

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > 8_000_000:
        raise HTTPException(400, "Logo too large (max 8 MB)")
    return branding.save_uploaded_logo(data, file.filename or "logo.jpg")


@app.post("/api/branding/logo/reset")
def branding_logo_reset():
    import branding

    return branding.reset_logo()


@app.post("/api/branding/logo/open")
def branding_logo_open():
    """Open the project Logo folder in Explorer (drop crest files here)."""
    import branding

    result = branding.open_logo_folder()
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "Could not open Logo folder")
    return result


@app.get("/api/sites")
def sites_list():
    """Remembered / candidate plants — any prior DLGLOG path, no hard-coded sites."""
    from site_memory import list_sites

    return {"sites": list_sites(), "xlreporter": False}


@app.post("/api/sites/switch")
def sites_switch(body: dict = Body(...)):
    """Switch to another DLGLOG path; restore remembered branding/profile if known."""
    from site_memory import switch_site

    path = (body.get("dlglog_path") or body.get("path") or "").strip()
    if not path:
        raise HTTPException(400, "dlglog_path required")
    try:
        return {**switch_site(path), "xlreporter": False}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/sites/remember")
def sites_remember():
    from site_memory import remember_current_site

    return {**remember_current_site(), "xlreporter": False}


@app.get("/api/help")
def help_guide():
    """In-app help for operators / integrators — works for any FT View plant."""
    from help_guide import help_payload

    return help_payload()



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
        # Default Vite base "/" (tunnel / desktop)
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
        # Also accept a Pages-mode build that references /FactoryTalk-View-Reporter/assets/...
        app.mount(
            "/FactoryTalk-View-Reporter/assets",
            StaticFiles(directory=str(assets)),
            name="pages_assets",
        )

    @app.get("/{full_path:path}")
    def spa(full_path: str = ""):
        # Never shadow API — FastAPI should match /api/* first, but guard anyway
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        # Strip GitHub Pages base prefix if present
        rel = full_path
        if rel.startswith("FactoryTalk-View-Reporter/"):
            rel = rel[len("FactoryTalk-View-Reporter/") :]
        candidate = (_DIST / rel).resolve() if rel else (_DIST / "index.html").resolve()
        try:
            candidate.relative_to(_DIST.resolve())
        except ValueError:
            raise HTTPException(404)
        if rel and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8787, workers=1)
