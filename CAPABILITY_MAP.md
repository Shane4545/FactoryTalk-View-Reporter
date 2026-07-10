# Ops Reporter — capability map (replaces XLReporter)

**Status 2026-07-09:** Chalk River can run ops reporting **without XLReporter**.

## Lifecycle

```
Connect → Design → Report → Distribute
```

| XLReporter | Ops Reporter |
|---|---|
| Project Explorer | App shell + Home |
| Connectors + `.grp` | DLGLOG reader (`/connect` live status) |
| Periods | Daily / Monthly / Custom APIs |
| Template Studio + `.xlsx` | React report pages |
| Data Connect + `.xld` | `chalk_report_builder.py` bindings |
| On-Demand `.xml` | Produce panels (dates, Preview, archive) |
| Preview / Produce → Excel/PDF | Preview + Print PDF + `archive/` HTML |
| Scheduler | Yes — daily/monthly + backfill + auto-print (Distribute) |
| Web Portal | This app |

## Done for Chalk River

1. Project shell (plant, nav, reports)
2. DLGLOG connector (WTP_TREND / MOTORS / FEEDBACK)
3. History: min / max / avg / total / time-of / runtime starts+stops+ON hours
4. Periods: Daily, Monthly, Custom (≤93 days)
5. On-demand Produce with date pickers
6. Summary reports: Daily / Monthly / Custom
7. Multi-tag Trends + Tag Explorer
8. CT summary (worst-case)
9. Print PDF + Save archive (JSON/HTML)
10. Live preview from disk historian

## Later (nice, not blockers)

Scheduler service, email/FTP, visual designer, multi-plant, OPC matrix, eSign.
