"""Save produced reports to a local archive (no XLReporter)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from output_settings import archive_root, publish_outputs


def ensure_archive() -> Path:
    root = archive_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def archive_path(kind: str, start: str, end: str) -> Path:
    root = ensure_archive()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_s = (start or "unknown")[:19].replace(":", "")
    end_s = (end or start_s)[:19].replace(":", "")
    safe = f"{kind}_{start_s}_to_{end_s}_{stamp}"
    return root / safe


def save_report(report: dict[str, Any], kind: str) -> dict[str, str | Any]:
    """Write JSON + print-ready HTML, then publish PDF/Web per output settings."""
    start = report.get("startDate", "unknown")
    end = report.get("endDate", start)
    base = archive_path(kind, start, end)
    base.mkdir(parents=True, exist_ok=True)
    json_path = base / "report.json"
    html_path = base / "report.html"
    meta = {
        "kind": kind,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "xlreporter": False,
        "startDate": start,
        "endDate": end,
        "plant": report.get("plant"),
        "subtitle": report.get("subtitle"),
    }
    payload = {**report, "archive": meta}
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    html_path.write_text(_html_report(payload), encoding="utf-8")

    published = publish_outputs(
        kind=kind,
        start=str(start),
        end=str(end),
        html_path=html_path,
        json_path=json_path,
    )
    if published.get("pdf") and isinstance(published["pdf"], dict):
        meta["pdf"] = published["pdf"].get("path")
        meta["web"] = published.get("web")
        payload["archive"] = meta
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "id": base.name,
        "dir": str(base),
        "json": str(json_path),
        "html": str(html_path),
        "pdf": (published.get("pdf") or {}).get("path")
        if isinstance(published.get("pdf"), dict)
        else None,
        "web": published.get("web"),
        "publish": published,
    }


def list_archive(limit: int = 50) -> list[dict[str, Any]]:
    root = ensure_archive()
    items: list[dict[str, Any]] = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta_path = d / "report.json"
        if not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        arch = data.get("archive") or {}
        items.append(
            {
                "id": d.name,
                "kind": arch.get("kind") or "report",
                "saved_at": arch.get("saved_at"),
                "startDate": data.get("startDate"),
                "endDate": data.get("endDate"),
                "subtitle": data.get("subtitle"),
                "html": str(d / "report.html"),
                "json": str(meta_path),
                "pdf": arch.get("pdf"),
                "web": arch.get("web"),
            }
        )
        if len(items) >= limit:
            break
    return items


def find_archived_report(
    kind: str,
    *,
    date: str | None = None,
    month: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any] | None:
    """
    Return the newest archived report matching kind + period, or None.
    Used so Daily/Monthly can open instantly from archive, then Update from DLGLOG.
    """
    root = ensure_archive()
    if not root.is_dir():
        return None

    matches: list[tuple[str, Path, dict[str, Any]]] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "report.json"
        if not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        arch = data.get("archive") if isinstance(data.get("archive"), dict) else {}
        k = str(arch.get("kind") or (data.get("meta") or {}).get("kind") or "")
        if k != kind:
            continue

        start_d = str(data.get("startDate") or arch.get("startDate") or "")[:10]
        end_d = str(data.get("endDate") or arch.get("endDate") or start_d)[:10]
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}

        if kind == "daily":
            if not date or start_d != date:
                continue
        elif kind == "monthly":
            if not month:
                continue
            meta_month = str(meta.get("month") or "")
            if meta_month != month and start_d[:7] != month:
                continue
        elif kind == "custom":
            if not start or not end:
                continue
            if start_d != start[:10] or end_d != end[:10]:
                continue
        else:
            continue

        saved = str(arch.get("saved_at") or "")
        matches.append((saved, d, data))

    if not matches:
        return None

    # Newest first: saved_at ISO string, then folder name
    matches.sort(key=lambda t: (t[0], t[1].name), reverse=True)
    saved_at, folder, data = matches[0]
    arch = data.get("archive") if isinstance(data.get("archive"), dict) else {}
    return {
        "found": True,
        "id": folder.name,
        "dir": str(folder),
        "saved_at": arch.get("saved_at") or saved_at,
        "pdf": arch.get("pdf"),
        "web": arch.get("web"),
        "report": data,
    }


def _fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        if digits == 0:
            return str(int(round(v)))
        return f"{v:.{digits}f}"
    return str(v)


def _html_report(report: dict[str, Any]) -> str:
    sections_html = []
    for sec in report.get("sections") or []:
        rows = []
        kind = sec.get("kind")
        if kind == "runtime":
            head = "<tr><th>Tag</th><th>Description</th><th>Starts</th><th>Stops</th><th>Hours</th></tr>"
            for r in sec.get("rows") or []:
                a = r.get("aggregate") or {}
                rows.append(
                    f"<tr><td>{r.get('tag')}</td><td>{r.get('description')}</td>"
                    f"<td class='n'>{_fmt(a.get('starts'), 0)}</td>"
                    f"<td class='n'>{_fmt(a.get('stops'), 0)}</td>"
                    f"<td class='n'>{_fmt(a.get('total'), 1)}</td></tr>"
                )
        elif kind == "ct":
            continue
        else:
            head = "<tr><th>Tag</th><th>Description</th><th>Min</th><th>Max</th><th>Avg/Total</th></tr>"
            for r in sec.get("rows") or []:
                a = r.get("aggregate") or {}
                mid = a.get("total") if a.get("total") is not None else a.get("avg")
                rows.append(
                    f"<tr><td>{r.get('tag')}</td><td>{r.get('description')}</td>"
                    f"<td class='n'>{_fmt(a.get('min'))}</td>"
                    f"<td class='n'>{_fmt(a.get('max'))}</td>"
                    f"<td class='n'>{_fmt(mid)}</td></tr>"
                )
        sections_html.append(
            f"<h2>{sec.get('title')}</h2><table>{head}{''.join(rows)}</table>"
        )

    ct_rows = []
    for m in report.get("ct") or []:
        ct_rows.append(
            f"<tr><td>{m.get('label')}</td>"
            f"<td class='n'>{m.get('giardiaDisplay') or _fmt(m.get('giardia'))}</td>"
            f"<td class='n'>{m.get('virusesDisplay') or _fmt(m.get('viruses'))}</td></tr>"
        )
    ct_html = (
        "<h2>CT Summary</h2>"
        "<table><tr><th>Metric</th><th>Giardia</th><th>Viruses</th></tr>"
        + "".join(ct_rows)
        + "</table>"
        + f"<p class='note'>{report.get('ctNote') or ''}</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>{report.get('subtitle')} — {report.get('startDate')}</title>
<style>
body {{ font-family: Segoe UI, system-ui, sans-serif; color:#0f172a; margin:2rem; }}
h1 {{ font-size:1.35rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.05rem; margin:1.5rem 0 .5rem; border-bottom:1px solid #cbd5e1; padding-bottom:.25rem; }}
.meta {{ color:#64748b; font-size:.9rem; }}
table {{ border-collapse:collapse; width:100%; font-size:.88rem; margin-bottom:1rem; }}
th,td {{ border:1px solid #e2e8f0; padding:.35rem .5rem; text-align:left; }}
th {{ background:#f1f5f9; }}
.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
.note {{ color:#64748b; font-size:.85rem; }}
@media print {{ body {{ margin:0.5in; }} }}
</style></head><body>
<h1>{report.get('plant')}</h1>
<p class="meta">{report.get('subtitle')} · {report.get('municipality')}<br/>
{report.get('periodLabel')} · {report.get('startDate')} → {report.get('endDate')}<br/>
Ops Reporter · XLReporter=NO</p>
{''.join(sections_html)}
{ct_html}
</body></html>"""
