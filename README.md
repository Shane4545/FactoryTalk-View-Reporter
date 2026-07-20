# Plant Reporter (FactoryTalk View Reporter)

**Plant operations reporting without XLReporter.**  
Reads FactoryTalk View SE **DLGLOG** files directly. Browser UI + local API.

Works on any FT View SE plant: Connect → point at DLGLOG → Setup → map your tags → Activate.

---

## For co-workers — download the blank kit

**Release:** [Plant Reporter v1.1.0 — blank SCADA kit](https://github.com/Shane4545/FactoryTalk-View-Reporter/releases/tag/v1.1.0)

1. Download **`PlantReporter_SCADA.zip`**
2. Extract the whole folder (keep `PlantReporter.exe` next to `_internal` and `config`)
3. Run **`PlantReporter.exe`** (or `START.bat`)
4. Browser opens → **Connect** → Browse your plant’s DLGLOG → Plant name → Save & connect
5. **Setup** → Scan DLGLOG tags → map instruments/motors → **Activate profile**
6. **Reports → Daily** → Update from DLGLOG

This kit starts **blank** (no plant name, no tags, no Chalk River config).  
**Connect → Default** wipes tags, path, cache, and archives anytime.

### Optional sample DLGLOG (practice data)

Already published: [demo-v1 — Chalk River 3 days](https://github.com/Shane4545/FactoryTalk-View-Reporter/releases/tag/demo-v1)

- Download `demo_dlglog_chalk_river_3days.zip`
- Unzip → Connect → Browse that folder → Save
- Dates: **2026-06-13 … 2026-06-15** (WTP_TREND / WTP_MOTORS / WTP_FEEDBACK)

---

## Live / static demos

| Link | What |
|------|------|
| [GitHub Pages sample](https://shane4545.github.io/FactoryTalk-View-Reporter/) | Static sample days only |
| [Live bookmark](https://shane4545.github.io/FactoryTalk-View-Reporter/live.html) | Redirects to live tunnel when host PC is online |

---

## From source (this repo)

**Needs:** Python 3.11+ and Node.js LTS on PATH.

```bat
START_OPS_REPORTER.bat
```

Open http://127.0.0.1:8787

## Build the SCADA zip

```bat
python package_scada_kit.py
```

Output: `releases\PlantReporter_SCADA\` and `releases\PlantReporter_SCADA.zip`.

## What you get

| Feature | Status |
|---------|--------|
| Daily / Weekly / Monthly / Yearly / Custom | Live |
| Archive-first load + Update from DLGLOG | Live |
| CT disinfection (optional, Setup-mapped) | Live |
| Plant Insights + Trends | Live |
| Scheduler / Archive PDF+Web | Live |
| Blank Default wipe (sites + cache + archives) | Live |

**Zero XLReporter / Excel dependency for this app.**

## License / sales

Internal Capital Controls product. Contact sales for deployment terms.
