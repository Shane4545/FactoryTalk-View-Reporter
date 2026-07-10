import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  DailyReportView,
  type DailyReportData,
} from "../reports/DailyReportView";
import { chalkRiverDaily } from "../data/chalkRiverDaily";
import { API } from "../api";
import "./ProducePage.css";

function localYmd(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

type Meta = {
  days_loaded?: number;
  days_missing?: number;
  kind?: string;
  live?: boolean;
  tag_count_trend?: number;
  tag_count_motors?: number;
  tag_count_feedback?: number;
  proof?: {
    FIT101_samples?: number;
    FIT101_min?: number;
    FIT101_max?: number;
  };
};

export function useAvailableDates() {
  const [dates, setDates] = useState<string[]>([]);
  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/dates`);
        if (!res.ok) return;
        const data = await res.json();
        setDates(data.dates ?? []);
      } catch {
        /* offline */
      }
    })();
  }, []);
  return dates;
}

export async function archiveReport(qs: string): Promise<string> {
  const res = await fetch(`${API}/api/archive?${qs}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string" ? err.detail : res.statusText,
    );
  }
  const data = await res.json();
  return `Archived → ${data.dir}`;
}

type ProduceShellProps = {
  crumb: string;
  title: string;
  lede: string;
  panel: ReactNode;
  report: DailyReportData | null;
  status: string | null;
  source: "dlglog" | "archive" | "demo" | "error";
  loading: boolean;
};

export function ProduceShell({
  crumb,
  title,
  lede,
  panel,
  report,
  status,
  source,
  loading,
}: ProduceShellProps) {
  return (
    <div className="page produce">
      <header className="page__head">
        <div>
          <p className="eyebrow">
            <Link to="/reports">Reports</Link> / {crumb}
          </p>
          <h1>{title}</h1>
          <p className="lede">{lede}</p>
        </div>
        <div className="produce-panel produce-panel--wide">{panel}</div>
      </header>
      {loading && (
        <p className="status">
          {source === "archive" ? "Loading archive…" : "Loading…"}
        </p>
      )}
      {status && (
        <p
          className={`status ${source === "dlglog" || source === "archive" ? "ok" : "warn"}`}
        >
          {status}
        </p>
      )}
      {report ? (
        <DailyReportView data={report} />
      ) : (
        !loading && (
          <p className="status warn">
            No report loaded. Pick a date that has DLGLOG data, then Preview.
          </p>
        )
      )}
    </div>
  );
}

function statusFromMeta(
  data: DailyReportData & {
    meta?: Meta & {
      from_archive?: boolean;
      archive_saved_at?: string;
      source?: string;
    };
    live?: boolean;
  },
): string {
  const m = data.meta;
  const live = data.live || m?.live;
  const p = m?.proof;
  const fingerprint =
    p?.FIT101_min != null && p?.FIT101_max != null
      ? ` · FIT101 ${Number(p.FIT101_min).toFixed(2)}→${Number(p.FIT101_max).toFixed(2)} n=${p.FIT101_samples ?? "?"}`
      : "";
  if (m?.from_archive || m?.source === "archive") {
    const when = m.archive_saved_at ? ` · archived ${m.archive_saved_at}` : "";
    return `From archive (fast open)${when} · use Update if data changed · XLReporter=NO`;
  }
  if (m?.days_loaded != null) {
    return `LIVE DLGLOG · ${m.days_loaded} days loaded · ${m.days_missing ?? 0} missing · XLReporter=NO`;
  }
  if (live) {
    return `LIVE today (midnight -> now)${fingerprint} · auto-refresh · XLReporter=NO`;
  }
  return `From DLGLOG (fresh)${fingerprint} · XLReporter=NO`;
}

export function ProduceDailyPage() {
  const dates = useAvailableDates();
  const [date, setDate] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<DailyReportData | null>(null);
  const [source, setSource] = useState<"dlglog" | "archive" | "demo" | "error">(
    "demo",
  );
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    if (!dates.length) return;
    setDate((prev) => {
      if (prev && dates.includes(prev)) return prev;
      // Prefer last complete day (not today) when available — full 24h report
      const today = localYmd();
      const complete = [...dates].reverse().find((d) => d < today);
      return complete ?? dates[dates.length - 1];
    });
  }, [dates]);

  const loadLive = useCallback(async (d: string) => {
    const res = await fetch(`${API}/api/reports/daily?date=${d}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        typeof err.detail === "string" ? err.detail : res.statusText,
      );
    }
    return res.json();
  }, []);

  const load = useCallback(
    async (d: string, opts?: { forceLive?: boolean }) => {
      if (!d) return;
      setLoading(true);
      setStatus(null);
      const today = localYmd();
      const forceLive = !!opts?.forceLive || d === today;
      try {
        if (!forceLive) {
          const look = await fetch(
            `${API}/api/archive/lookup?kind=daily&date=${encodeURIComponent(d)}`,
          );
          if (look.ok) {
            const hit = await look.json();
            if (hit.found && hit.report) {
              setReport(hit.report);
              setSource("archive");
              setStatus(statusFromMeta(hit.report));
              return;
            }
          }
        }
        const data = await loadLive(d);
        setReport(data);
        setSource("dlglog");
        setStatus(statusFromMeta(data));
      } catch (e) {
        setReport(null);
        setSource("error");
        setStatus(
          `No report for ${d}: ${e instanceof Error ? e.message : "error"}`,
        );
      } finally {
        setLoading(false);
      }
    },
    [loadLive],
  );

  const updateFromDlglog = useCallback(async () => {
    if (!date) return;
    setUpdating(true);
    setLoading(true);
    setStatus(null);
    try {
      const data = await loadLive(date);
      setReport(data);
      setSource("dlglog");
      const archived = await archiveReport(`kind=daily&date=${date}`);
      setStatus(`${statusFromMeta(data)} · ${archived}`);
    } catch (e) {
      setSource("error");
      setStatus(e instanceof Error ? e.message : "Update failed");
    } finally {
      setUpdating(false);
      setLoading(false);
    }
  }, [date, loadLive]);

  useEffect(() => {
    if (!date) return;
    void load(date);
  }, [date, load]);

  // Live today: refresh every 60s so midnight→now keeps updating
  useEffect(() => {
    if (!date) return;
    const today = localYmd();
    if (date !== today) return;
    const id = window.setInterval(() => void load(date, { forceLive: true }), 60_000);
    return () => window.clearInterval(id);
  }, [date, load]);

  return (
    <ProduceShell
      crumb="Daily"
      title="Daily Operations Report"
      lede={`Opens from archive when available (fast). Use Update to rebuild from DLGLOG if the day changed.${dates.length ? ` ${dates.length} days on disk.` : ""} Hide unused mixers/tags under Insights → Manage items.`}
      report={report}
      status={status}
      source={source}
      loading={loading}
      panel={
        <>
          <label>
            Report date
            <input
              type="date"
              value={date || dates[dates.length - 1] || ""}
              min={dates[0]}
              max={dates[dates.length - 1]}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
          <div className="produce-actions">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading || !date}
              onClick={() => void load(date)}
            >
              {loading ? "Loading…" : "Open"}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={loading || updating || !date || source === "error"}
              onClick={() => void updateFromDlglog()}
              title="Rebuild from DLGLOG and save a fresh archive copy"
            >
              {updating ? "Updating…" : "Update from DLGLOG"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => window.print()}
            >
              Print PDF
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading || source === "error" || !report}
              onClick={() =>
                void archiveReport(`kind=daily&date=${date}`)
                  .then(setStatus)
                  .catch((e) => setStatus(String(e.message ?? e)))
              }
            >
              Save to archive
            </button>
          </div>
        </>
      }
    />
  );
}

export function ProduceMonthlyPage() {
  const [month, setMonth] = useState("2026-06");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<DailyReportData | null>(null);
  const [source, setSource] = useState<"dlglog" | "archive" | "demo" | "error">(
    "demo",
  );
  const [updating, setUpdating] = useState(false);

  const loadLive = useCallback(async (m: string) => {
    const res = await fetch(`${API}/api/reports/monthly?month=${m}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        typeof err.detail === "string" ? err.detail : res.statusText,
      );
    }
    return res.json();
  }, []);

  const load = useCallback(
    async (m: string, opts?: { forceLive?: boolean }) => {
      setLoading(true);
      setStatus(null);
      try {
        if (!opts?.forceLive) {
          const look = await fetch(
            `${API}/api/archive/lookup?kind=monthly&month=${encodeURIComponent(m)}`,
          );
          if (look.ok) {
            const hit = await look.json();
            if (hit.found && hit.report) {
              setReport(hit.report);
              setSource("archive");
              setStatus(statusFromMeta(hit.report));
              return;
            }
          }
        }
        const data = await loadLive(m);
        setReport(data);
        setSource("dlglog");
        setStatus(statusFromMeta(data));
      } catch (e) {
        setReport(null);
        setSource("error");
        setStatus(
          `Failed (${e instanceof Error ? e.message : "error"}) — no report`,
        );
      } finally {
        setLoading(false);
      }
    },
    [loadLive],
  );

  const updateFromDlglog = useCallback(async () => {
    setUpdating(true);
    setLoading(true);
    setStatus(null);
    try {
      const data = await loadLive(month);
      setReport(data);
      setSource("dlglog");
      const archived = await archiveReport(`kind=monthly&month=${month}`);
      setStatus(`${statusFromMeta(data)} · ${archived}`);
    } catch (e) {
      setSource("error");
      setStatus(e instanceof Error ? e.message : "Update failed");
    } finally {
      setUpdating(false);
      setLoading(false);
    }
  }, [month, loadLive]);

  useEffect(() => {
    void load(month);
  }, [month, load]);

  return (
    <ProduceShell
      crumb="Monthly"
      title="Monthly Operations Report"
      lede="Opens from archive when available (fast). Use Update if the month was incomplete when first archived. Hide unused mixers/tags under Insights → Manage items."
      report={report}
      status={status}
      source={source}
      loading={loading}
      panel={
        <>
          <label>
            Month
            <input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
          </label>
          <div className="produce-actions">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading}
              onClick={() => void load(month)}
            >
              Open
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={loading || updating || source === "error"}
              onClick={() => void updateFromDlglog()}
              title="Rebuild from DLGLOG and save a fresh archive copy"
            >
              {updating ? "Updating…" : "Update from DLGLOG"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => window.print()}
            >
              Print PDF
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading || source === "error" || !report}
              onClick={() =>
                void archiveReport(`kind=monthly&month=${month}`)
                  .then(setStatus)
                  .catch((e) => setStatus(String(e.message ?? e)))
              }
            >
              Save to archive
            </button>
          </div>
        </>
      }
    />
  );
}

export function ProduceCustomPage() {
  const [start, setStart] = useState("2026-06-01");
  const [end, setEnd] = useState("2026-06-13");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<DailyReportData | null>(null);
  const [source, setSource] = useState<"dlglog" | "archive" | "demo" | "error">(
    "demo",
  );

  const load = useCallback(async (s: string, e: string) => {
    setLoading(true);
    setStatus(null);
    try {
      const res = await fetch(
        `${API}/api/reports/custom?start=${s}&end=${e}`,
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          typeof err.detail === "string" ? err.detail : res.statusText,
        );
      }
      const data = await res.json();
      setReport(data);
      setSource("dlglog");
      setStatus(statusFromMeta(data));
    } catch (err) {
      setReport({
        ...chalkRiverDaily,
        subtitle: "Custom Operations Report",
        startDate: s,
        endDate: e,
      });
      setSource("error");
      setStatus(
        `Failed (${err instanceof Error ? err.message : "error"}) — demo shell`,
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(start, end);
  }, [start, end, load]);

  return (
    <ProduceShell
      crumb="Custom"
      title="Custom Operations Report"
      lede="Operator-chosen range (max 93 days). Same sections as Daily, rolled across the window."
      report={report}
      status={status}
      source={source}
      loading={loading}
      panel={
        <>
          <label>
            Start
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label>
            End
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
          <div className="produce-actions">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading}
              onClick={() => void load(start, end)}
            >
              Preview
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => window.print()}
            >
              Print PDF
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={loading || source !== "dlglog"}
              onClick={() =>
                void archiveReport(
                  `kind=custom&start=${start}&end=${end}`,
                )
                  .then(setStatus)
                  .catch((e) => setStatus(String(e.message ?? e)))
              }
            >
              Save to archive
            </button>
          </div>
        </>
      }
    />
  );
}

const reports = [
  {
    id: "daily",
    name: "Daily Operations Report",
    blurb: "Calendar day · live DLGLOG",
  },
  {
    id: "monthly",
    name: "Monthly Operations Report",
    blurb: "Full month rollup from disk",
  },
  {
    id: "custom",
    name: "Custom Operations Report",
    blurb: "Any start → end (≤93 days)",
  },
  {
    id: "trends",
    name: "Multi-tag Trends",
    blurb: "Overlay flows, levels, Cl₂…",
  },
];

export function ReportsPage() {
  return (
    <div className="page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Report · On-Demand</p>
          <h1>Produce reports</h1>
          <p className="lede">
            FactoryTalk View DLGLOG → browser. No XLReporter. No Excel templates.
          </p>
        </div>
      </header>
      <div className="report-grid">
        {reports.map((r) => (
          <Link key={r.id} to={`/reports/${r.id}`} className="report-card">
            <h2>{r.name}</h2>
            <p>{r.blurb}</p>
            <span>Open →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
