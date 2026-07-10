"""
Build a SCADA-ready Ops Reporter kit:
  releases/OpsReporter_SCADA/OpsReporter.exe  (+ deps)
  releases/OpsReporter_SCADA.zip

Run from apps/ops-reporter:
  python package_scada_kit.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "releases"
KIT_NAME = "OpsReporter_SCADA"
KIT_DIR = RELEASES / KIT_NAME
DIST_UI = ROOT / "dist"
SERVER = ROOT / "server"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd or ROOT)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def build_ui() -> None:
    if not (DIST_UI / "index.html").is_file():
        run(["npm.cmd", "run", "build"])
    else:
        # Always rebuild so kit matches latest UI
        run(["npm.cmd", "run", "build"])


def build_exe() -> Path:
    py = sys.executable
    run([py, "-m", "pip", "install", "-q", "pyinstaller", "fastapi", "uvicorn[standard]"])

    work = RELEASES / "_pyi_work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    # Windows PyInstaller uses ; as path separator in --add-data
    sep = ";"
    add_dist = f"{DIST_UI}{sep}dist"
    add_server = f"{SERVER}{sep}server"
    add_ct = f"{SERVER / 'ct_tables.json'}{sep}server"

    cmd = [
        py,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed" if False else "--console",  # keep console so operators see URL
        "--name",
        "OpsReporter",
        "--distpath",
        str(work / "dist"),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        f"--add-data={add_dist}",
        f"--add-data={add_server}",
        f"--add-data={add_ct}",
        "--paths",
        str(SERVER),
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=uvicorn.lifespan.off",
        "--hidden-import=fastapi",
        "--hidden-import=starlette",
        "--hidden-import=anyio",
        "--hidden-import=app_paths",
        "--hidden-import=main",
        "--hidden-import=plant_settings",
        "--hidden-import=dlglog_reader",
        "--hidden-import=day_cache",
        "--hidden-import=archive",
        "--hidden-import=scheduler",
        "--hidden-import=report_jobs",
        "--hidden-import=print_util",
        "--hidden-import=pdf_export",
        "--hidden-import=output_settings",
        "--hidden-import=chalk_report_builder",
        "--hidden-import=period_rollup",
        "--hidden-import=ct_calculator",
        "--hidden-import=plant_insights",
        "--hidden-import=report_prefs",
        "--hidden-import=tag_config",
        "--hidden-import=chalk_defaults",
        "--hidden-import=eu_scale",
        "--collect-all",
        "uvicorn",
        "--collect-all",
        "fastapi",
        "--collect-all",
        "starlette",
        str(ROOT / "scada_launcher.py"),
    ]
    run(cmd)

    built = work / "dist" / "OpsReporter"
    if not (built / "OpsReporter.exe").is_file():
        raise SystemExit(f"PyInstaller did not produce exe at {built}")
    return built


def stage_kit(built: Path) -> Path:
    if KIT_DIR.exists():
        shutil.rmtree(KIT_DIR, ignore_errors=True)
    KIT_DIR.mkdir(parents=True, exist_ok=True)

    # Copy onedir output
    for item in built.iterdir():
        dest = KIT_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Writable runtime folders + blank plant config
    for name in ("config", "cache", "archive", "PDF", "Web", "profiles"):
        (KIT_DIR / name).mkdir(exist_ok=True)

    # Importable example profile (Setup → Import profile…)
    example = ROOT / "profiles" / "chalk_river_example.json"
    if example.is_file():
        shutil.copy2(example, KIT_DIR / "profiles" / example.name)

    (KIT_DIR / "config" / "plant.json").write_text(
        """{
  "product": "Ops Reporter",
  "version": "1.0.0",
  "plant": {
    "id": "plant-1",
    "name": "Water Treatment Plant",
    "municipality": ""
  },
  "dlglog_path": "",
  "dlglog_candidates": [],
  "models": {
    "trend": "WTP_TREND",
    "motors": "WTP_MOTORS",
    "feedback": "WTP_FEEDBACK"
  },
  "api_port": 8787
}
""",
        encoding="utf-8",
    )

    (KIT_DIR / "README_SCADA.txt").write_text(
        """Ops Reporter — SCADA plant kit
================================

1. Copy this WHOLE folder to the SCADA / HMI PC
   (example: C:\\OpsReporter\\)

2. Double-click OpsReporter.exe

3. Browser opens to Connect.
   Click Browse… → select the main FactoryTalk DLGLOG folder
   (the folder that contains your datalog model folders)
   → Save & connect

4. Open Setup → "Scan DLGLOG tags".
   Tick the tags you want on reports, name them, pick sections,
   set Insight roles, and (optionally) enter your CT geometry
   (clearwell / pipe / tower volumes + baffling factors).
   → Save plant profile

   Working at Chalk River? Skip Setup — its mapping is built in.
   profiles\\chalk_river_example.json is an importable example.

5. Use Explore / Reports / Trends / Insights as usual.

Notes
-----
- Keep this window open while using the app. Close it to stop.
- First trend load for a day may take a few seconds (builds cache).
- Config is saved in config\\plant.json next to the .exe
- PDFs go to PDF\\ (or a folder you set under Distribute → Output folders)
- Web HTML copies go to Web\\
- No XLReporter / Excel required.
- Port: http://127.0.0.1:8787

If Windows SmartScreen warns: More info → Run anyway
(unsigned local build).
""",
        encoding="utf-8",
    )

    # Convenience shortcut bat (same folder)
    (KIT_DIR / "START.bat").write_text(
        "@echo off\r\ncd /d \"%~dp0\"\r\nstart \"\" OpsReporter.exe\r\n",
        encoding="utf-8",
    )
    return KIT_DIR


def zip_kit(kit: Path) -> Path:
    zip_path = RELEASES / f"{KIT_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in kit.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(kit.parent).as_posix())
    return zip_path


def main() -> int:
    RELEASES.mkdir(parents=True, exist_ok=True)
    print("Building UI…")
    build_ui()
    print("Building OpsReporter.exe…")
    built = build_exe()
    print("Staging kit…")
    kit = stage_kit(built)
    print("Zipping…")
    z = zip_kit(kit)
    print()
    print("DONE")
    print(f"  Folder: {kit}")
    print(f"  Zip:    {z}")
    print("  Copy the zip to the SCADA PC, extract, run OpsReporter.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
