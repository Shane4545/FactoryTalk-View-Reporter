# Ops Reporter v1.0 — Product

## What you have

A complete **plant ops reporting app** that replaces XLReporter for Chalk River daily work.

| Capability | Done |
|------------|------|
| Daily / Monthly / Custom reports from FactoryTalk DLGLOG | Yes |
| CT calculator | Yes |
| Motor starts / stops / run hours | Yes |
| Tag Explorer + multi-tag Trends | Yes |
| Print PDF + Save archive | Yes |
| Day cache (monthly fast after first load) | Yes |
| 2-worker API (no lockup) | Yes |
| Plant config (`config/plant.json`) | Yes |
| One-click start | Yes — `START_OPS_REPORTER.bat` |
| Built UI served from API | Yes — http://127.0.0.1:8787 |

## How to run

1. Double-click **`apps/ops-reporter/START_OPS_REPORTER.bat`**
2. Browser opens Daily at **http://127.0.0.1:8787**
3. Close the console window to stop

Dev mode (hot reload): `start_all.bat` → UI on :5173

## Not in v1 (commercial follow-ons)

Email, cloud multi-tenant billing, SSO — tracked as 1.1 / 2.0 in `PROJECT_CHARTER.md`.  
**Plant use does not require those.**

## Zero XLReporter

No Excel templates, no `.grp` / `.xld`, no Project Explorer for these reports.
