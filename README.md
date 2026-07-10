# Ops Reporter

**Plant operations reporting without XLReporter.**  
Reads FactoryTalk View SE **DLGLOG** files directly. Browser UI + local API.

Works on any FT View SE plant: Connect → point at DLGLOG → Setup → map your tags.

## Quick start (Windows)

### Option A — SCADA kit (easiest for plant PCs)

1. Download the latest **`OpsReporter_SCADA.zip`** from [Releases](../../releases) (or build it — see below).
2. Extract anywhere (e.g. `C:\OpsReporter\`).
3. Run **`OpsReporter.exe`** (or `START.bat`).
4. Browser opens → **Connect** → Browse to your DLGLOG folder → Save.
5. Open **Setup** → Scan tags → map instruments/motors → Save plant profile.

Chalk River ships as the built-in example profile. Other plants configure Setup once.

### Option B — From source (this repo)

**Needs:** Python 3.11+ and Node.js LTS on PATH.

```bat
cd apps\ops-reporter
START_OPS_REPORTER.bat
```

Or manually:

```bat
cd apps\ops-reporter
python -m pip install -r server\requirements.txt
npm install
npm run build
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8787
```

Open http://127.0.0.1:8787

Dev UI (hot reload): `npm run dev` → http://127.0.0.1:5173 (API still on :8787).

## What you get

| Feature | Status |
|---------|--------|
| Daily / Monthly / Custom ops reports | Live |
| Archive-first load + Update from DLGLOG | Live |
| CT disinfection (configurable geometry + opt-out) | Live |
| Motor starts / stops / ON hours + duty Insights | Live |
| Plant Insights (traffic-light health, WQI, filters) | Live |
| Tag Explorer + multi-tag Trends | Live |
| PDF / Web HTML / archive folders (XLReporter-style) | Live |
| Setup page — any plant's tags from Tagname.DAT | Live |
| Hide unused mixers / sections | Live |
| Scheduler | Live |
| Email / cloud multi-tenant billing | Not in v1 |

## Config

- `config/plant.json` — plant name, DLGLOG path, models, tag profile (created on first run).
- **Connect** page — pick the DLGLOG folder (models auto-detected).
- **Setup** page — map tags, Insight roles, CT volumes/baffling.
- Export/import profile JSON to copy a plant setup to another PC.

## Build the SCADA zip

```bat
cd apps\ops-reporter
python package_scada_kit.py
```

Output: `releases\OpsReporter_SCADA\` and `releases\OpsReporter_SCADA.zip`.

## Architecture

```
FactoryTalk DLGLOG (Float.DAT + Tagname)
        ↓
  FastAPI :8787  (+ built UI from dist/)
        ↓
  Browser
```

**Zero XLReporter / Excel dependency.**

## License / sales

Internal Capital Controls product demo. Contact sales for deployment terms.
