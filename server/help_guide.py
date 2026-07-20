"""In-app operator help for Plant Reporter (any FactoryTalk View plant)."""

from __future__ import annotations

from typing import Any


def help_payload() -> dict[str, Any]:
    return {
        "title": "Plant Reporter — operator guide",
        "lede": (
            "Browser reports from your FactoryTalk View SE DLGLOG. "
            "Works for any plant: Connect the folder, map tags once, then "
            "Activate. Daily edits always need Activate before reports change."
        ),
        "sections": [
            {
                "id": "overview",
                "title": "What this app does",
                "intro": (
                    "Plant Reporter reads historian day files under a DLGLOG "
                    "folder and builds Daily / Weekly / Monthly / Yearly / "
                    "Custom ops reports, Trends charts, and Insights health "
                    "scores — in the browser. No XLReporter license is required "
                    "for this app."
                ),
                "steps": [
                    "Left menu: Home, Insights, Reports, Explore, Connect, Setup, Archive, Log, Help.",
                    "Click the ? button (bottom-right) any time to open this guide.",
                    "Hide the left menu with « Hide menu for a wider Trends/Reports view; click Menu on the slim rail to show it again.",
                ],
                "tips": [
                    "One active DLGLOG per install. To switch plants, Connect → Browse a different folder → Save & connect.",
                    "Reports stay blocked until a profile is Activated in Setup.",
                ],
            },
            {
                "id": "quick-start",
                "title": "Quick start — new plant",
                "intro": "Typical first-time path (about 10–20 minutes once DLGLOG is on disk).",
                "steps": [
                    "Connect → Browse… to this plant’s DLGLOG folder → enter Plant name and Township → optional logo → Test DLGLOG → Save & connect.",
                    "Setup → Scan DLGLOG tags. Tick Use on instruments/motors that belong on reports.",
                    "Edit Description, Type, Section, Units, and Total (flows) as needed. Scan only guesses — you own the final mapping.",
                    "Optional: Insight roles (flows, Cl₂, pH, levels) and Advanced multi-selects (filter turbidity / pump group).",
                    "Optional: enable CT disinfection, enter tank volumes, map CT inputs, choose which report kinds show the CT table.",
                    "Click Activate profile (confirm). Then open Reports → Daily for a known good day.",
                    "Optional: Insights → Manage items to Hide tags that should not appear on reports.",
                    "Archive (Distribute) → set PDF/Web folders and schedule if you want automatic produce.",
                ],
            },
            {
                "id": "connect",
                "title": "Connect",
                "intro": (
                    "Points the app at this PC’s plant data and sets the report header name, township, and crest."
                ),
                "steps": [
                    "Path: Browse… to the main DLGLOG folder (the parent that contains model subfolders with day files).",
                    "Test DLGLOG: confirms models on disk (trend / motors / feedback names vary by plant).",
                    "Plant name + Township / City: printed on report headers.",
                    "Logo: Choose file… or Open Logo folder and place plant-logo.jpg / .png (copied into the app Logo folder).",
                    "Save & connect: stores the path and branding. Status shows Live when the folder is valid.",
                ],
                "tips": [
                    "Models are detected from folder names — you do not hard-code WTP_* or any plant prefix.",
                    "On another computer, install the same app and Connect to that plant’s DLGLOG the same way.",
                ],
            },
            {
                "id": "setup",
                "title": "Setup — map tags",
                "intro": (
                    "Setup builds the plant profile: which historian tags appear on "
                    "reports, under which section titles, with which units. "
                    "Nothing applies to live reports until you Activate profile."
                ),
                "steps": [
                    "Scan DLGLOG tags: lists every logged tag across models. Run again after SCADA adds tags.",
                    "Optional FactoryTalk Tags.CSV: Import from View Studio (Tools → Tag Import and Export), then Apply descriptions for HMI text/units.",
                    "Use checkbox: on = tag is on Daily/Weekly/Monthly/Yearly/Custom (and Insights lists). Off = stays in Setup but omitted from reports after Activate.",
                    "Type: instrument (analogs), motor (runtime), or feedback (%). Changing type may move the row to another section.",
                    "Description / Section / Units: edit freely — any naming style is fine (ISA or not).",
                    "Total: for flow-like instruments, tick to show period totals (e.g. m³) on reports.",
                    "Motors: set units to h, min, or s — runtime converts on reports.",
                    "Report sections: rename, reorder (drag or ↑↓), Add section, Remove (tags remapped).",
                    "Insight roles: pick which of YOUR included tags feed Insights cards (raw flow, Cl₂, etc.). Leave blank to hide that card.",
                    "Advanced (multi): Ctrl/Cmd-click filter-effluent turbidity tags and the high-lift / distribution pump group. Empty = no special Insight grading for those.",
                    "CT disinfection: enable, enter contact volumes (m³), map worst-case inputs, and tick which report kinds show the CT table.",
                    "Activate profile: confirms and stamps a new revision. Open Daily afterward to verify.",
                    "Export / Import profile: copy a finished mapping to another PC. Clear profile blocks reports until Activate. Connect → Default (or Load blank template) wipes tags, DLGLOG path, remembered sites, cache, and archives — full blank start.",
                ],
                "tips": [
                    "Scan may guess section/units from tag names — always review after Scan.",
                    "There is no Save draft button: Activate applies; until then Daily still shows the last activated profile.",
                ],
            },
            {
                "id": "reports",
                "title": "Reports — Daily, Weekly, Monthly, Yearly, Custom",
                "intro": (
                    "Same tag list and sections for every period. Open loads the "
                    "newest matching archive when it matches the live profile; "
                    "Update rebuilds from DLGLOG."
                ),
                "steps": [
                    "Pick the date / week / month / year / custom range.",
                    "Open: fast path from archive when profile/prefs hashes match.",
                    "Update from DLGLOG: rebuilds live from historian files (use after Setup Activate or to refresh).",
                    "Save to archive: stores JSON/HTML (and PDF/Web if enabled under Archive).",
                    "Print PDF: sends the report to print/PDF (avoid mass-printing every day as a test).",
                ],
                "tips": [
                    "After Insights Hide or Setup Use off → Activate, Open must not resurrect hidden tags. If an old archive is stale, Open skips it and you Update.",
                    "Weekly uses Sunday-start weeks (YYYY-Www).",
                ],
            },
            {
                "id": "insights",
                "title": "Insights",
                "intro": (
                    "Traffic-light health for the selected day: instruments, motors, "
                    "optional water-quality index, filter bands, CT margin, and KPIs "
                    "from Setup Insight roles."
                ),
                "steps": [
                    "Pick a Day and Scan day (or wait for auto load).",
                    "Health score and “What to check” list yellow/red items.",
                    "Water quality / filter / metrics cards fill only when Insight roles are mapped in Setup.",
                    "Manage items: Hide motors or tags you do not want on reports → they leave Daily (and other periods) after hide; Restore brings them back.",
                    "Open Trends jumps to multi-tag Trends.",
                ],
                "tips": [
                    "Scores are engineering heuristics (not regulatory setpoints).",
                    "Hide is separate from Setup Use: Hide is operator preference; Use is plant mapping.",
                ],
            },
            {
                "id": "trends",
                "title": "Trends (Reports → Trends)",
                "intro": "Overlay up to six tags from any DLGLOG model over 1 / 7 / 30 / 90 days or a custom range.",
                "steps": [
                    "Open the Tags panel; tick up to 6 tags (from this plant’s catalog).",
                    "Choose Window (1d–90d) or Custom range.",
                    "Refresh to reload. Click the chart to enable scroll-zoom; drag to zoom.",
                    "Save PDF / Print / Export to Excel write under the Trends output folder.",
                ],
                "tips": [
                    "First open picks the first few catalog tags — change selection anytime.",
                    "Long ranges with many tags take longer the first time (day cache warms up).",
                ],
            },
            {
                "id": "explore",
                "title": "Explore",
                "intro": "Single-tag deep dive — useful when Trends overlay is too busy.",
                "steps": [
                    "Pick a tag from the list (filled after Connect).",
                    "Choose preset or custom range → Show trend.",
                    "Read min / max / avg and the chart for that tag only.",
                ],
            },
            {
                "id": "archive",
                "title": "Archive (Distribute) — folders, schedule, backfill",
                "intro": (
                    "Menu label Archive. Sets where PDFs/HTML land, automatic produce "
                    "times, and history backfill."
                ),
                "steps": [
                    "Output folders: Logo, Archive, PDF, Web, Trends, optional network copy-to. Leave blank for defaults next to the app.",
                    "Tick Save PDF / Save Web HTML / year-month subfolders → Save output folders.",
                    "Scheduler: Enable scheduler, set Daily/Weekly/Monthly/Yearly/Trends times and auto-print → Save schedule. Keep Plant Reporter running (or Windows autostart/service).",
                    "Run … now: fires one job immediately.",
                    "Backfill: choose kind + From/To, optional Force regenerate, Start backfill; Stop to cancel.",
                    "Archive list: recent saved reports; Print reprints one archived item.",
                ],
                "tips": [
                    "Silent start: tools\\install_autostart.ps1 — optional Windows service: service\\README.md.",
                    "Force regenerate overwrites an existing archived day — use carefully.",
                ],
            },
            {
                "id": "log",
                "title": "Log",
                "intro": "Scheduler activity only (not PDFs or archives).",
                "steps": [
                    "Browse recent produce / backfill events.",
                    "Set retention (max events / days) → Save retention.",
                    "Clear older than 30 days or Clear all logs when needed.",
                ],
            },
            {
                "id": "troubleshooting",
                "title": "Troubleshooting",
                "steps": [
                    "Reports empty / blocked: Connect DLGLOG and Activate a profile in Setup.",
                    "Tag still on Daily after unchecking Use: click Activate profile.",
                    "Tag still on Daily after Insights Hide: use Manage → Hide, then Open/Update Daily (stale archive is skipped when prefs differ).",
                    "Insights cards blank (—): map Insight roles in Setup → Activate.",
                    "CT table empty or nonsense: enable CT, enter real tank volumes, map CT inputs, Activate; tick Show CT on that report kind.",
                    "Trends slow on 30d: first load builds day cache; later loads are faster.",
                    "Wrong plant name on header: fix Connect → Plant name / Township → Save & connect.",
                    "After Setup edits nothing changed: hard-refresh the browser (Ctrl+F5) so dist/ UI is current.",
                ],
            },
        ],
        "xlreporter": False,
    }
