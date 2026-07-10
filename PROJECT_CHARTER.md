# Ops Reporter — Project Charter

**Product:** Ops Reporter v1.0  
**Goal:** Replace XLReporter for plant ops reporting (Chalk River first) — no Excel runtime

## v1.0 complete for plant use

- DLGLOG reader (TREND / MOTORS / FEEDBACK)
- Daily / Monthly / Custom + CT + starts/stops
- Tag Explorer + Trends
- Print PDF + archive
- Day disk cache
- One-click `START_OPS_REPORTER.bat`
- Plant config JSON

## Next commercial releases (not blocking plant use)

| Release | Deliverable |
|---------|-------------|
| 1.1 | Email distribute + Windows Task Scheduler job |
| 1.2 | Login / operator roles |
| 2.0 | Multi-plant installer + licensing |

## FactoryTalk

| Item | Value |
|------|--------|
| Live DLGLOG | `C:\@SE\HMI Projects\CHALK_RIVER_WTP\DLGLOG` |
| Strategy | Direct Float.DAT — no Data Agent required for history |
