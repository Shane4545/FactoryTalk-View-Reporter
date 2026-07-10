import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API } from "../api";
import "./ConnectDistribute.css";

type Health = {
  ok: boolean;
  dlglog?: string;
  xlreporter?: boolean;
  date_count?: number;
  first_date?: string;
  last_date?: string;
  models?: Record<string, boolean>;
  models_on_disk?: string[];
  plant?: { name?: string; municipality?: string };
  error?: string;
};

type Assigned = { trend?: string; motors?: string; feedback?: string };

type ArchiveItem = {
  id: string;
  kind: string;
  saved_at?: string;
  startDate?: string;
  endDate?: string;
  subtitle?: string;
  html?: string;
  pdf?: string | null;
  web?: string | null;
};

type OutputFile = {
  name: string;
  path: string;
  rel?: string;
  modified?: string;
  size?: number;
};

type OutputsConfig = {
  archive_folder: string;
  pdf_folder: string;
  web_folder: string;
  subfolders: boolean;
  save_pdf: boolean;
  save_html: boolean;
  save_json: boolean;
  copy_to: string;
};

export function ConnectPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [path, setPath] = useState("");
  const [plantName, setPlantName] = useState("");
  const [municipality, setMunicipality] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [diskModels, setDiskModels] = useState<string[]>([]);
  const [assigned, setAssigned] = useState<Assigned>({});

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/config`);
      const data = await res.json();
      setPath(data.dlglog_path || data.resolved_dlglog || "");
      setPlantName(data.plant?.name || "");
      setMunicipality(data.plant?.municipality || "");
      setDiskModels(data.models_on_disk || []);
      setAssigned(data.models || data.assigned || {});
      const h = await fetch(`${API}/api/health`);
      setHealth(await h.json());
    } catch {
      setHealth({
        ok: false,
        error: "API unreachable — start Ops Reporter",
        xlreporter: false,
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const testPath = async () => {
    setBusy(true);
    setStatus(null);
    try {
      const res = await fetch(`${API}/api/config/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dlglog_path: path }),
      });
      const data = await res.json();
      if (!data.ok) {
        setStatus(`Test failed: ${data.error}`);
        setDiskModels([]);
        setAssigned({});
      } else {
        setDiskModels(data.models || []);
        setAssigned(data.assigned || {});
        setPath(data.path || path);
        setStatus(
          `OK — ${data.models?.length ?? 0} datalog model(s) found inside this folder`,
        );
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Test failed");
    } finally {
      setBusy(false);
    }
  };

  const browseFolder = async () => {
    setBusy(true);
    setStatus("Opening folder picker…");
    try {
      const res = await fetch(`${API}/api/config/browse`, { method: "POST" });
      const data = await res.json();
      if (data.cancelled || !data.path) {
        setStatus(data.error || "Cancelled");
        return;
      }
      if (!data.ok) {
        setStatus(`Folder not valid: ${data.error}`);
        setPath(data.path || path);
        setDiskModels([]);
        setAssigned({});
        return;
      }
      setPath(data.path);
      setDiskModels(data.models || []);
      setAssigned(data.assigned || {});
      setStatus(
        `Selected · ${data.models?.length ?? 0} datalog model(s) found — click Save & connect`,
      );
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Browse failed");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    setStatus(null);
    try {
      // Only send the main DLGLOG path — server auto-detects model subfolders
      const res = await fetch(`${API}/api/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dlglog_path: path,
          plant: { name: plantName, municipality },
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(
          `Save failed: ${typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)}`,
        );
      } else if (!data.ok) {
        setStatus(`Saved but not live: ${data.error}`);
      } else {
        setDiskModels(data.models_on_disk || []);
        setAssigned(data.assigned || data.config?.models || {});
        setStatus(`Saved · connected to ${data.resolved_dlglog}`);
        await load();
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Connect</p>
          <h1>Point at your DLGLOG folder</h1>
          <p className="lede">
            Choose the main FactoryTalk View <strong>DLGLOG</strong> folder (the
            one that contains your datalog model folders). We detect every model
            inside automatically — you do not pick each one.
          </p>
        </div>
      </header>

      <section className="cfg-card">
        <h2>Active connection</h2>
        <p className="cfg-live">
          {health?.ok ? (
            <>
              <span className="ok">Live</span> · {health.dlglog}
              <br />
              {health.date_count} days · {health.first_date} → {health.last_date}
              {health.plant?.name ? ` · ${health.plant.name}` : ""}
            </>
          ) : (
            <span className="warn">{health?.error || "Not connected"}</span>
          )}
        </p>
      </section>

      <section className="cfg-card">
        <h2>Main DLGLOG path</h2>
        <p className="cfg-hint">
          Example:{" "}
          <code>C:\@SE\HMI Projects\CHALK_RIVER_WTP\DLGLOG</code>
          <br />
          Inside it you may have <code>WTP_TREND</code>, <code>WTP_MOTORS</code>,{" "}
          <code>WTP_FEEDBACK</code>, <code>WTP_REPORTS</code>, or any other
          models you created in FactoryTalk SE.
        </p>
        <label className="cfg-label">
          Folder
          <div className="cfg-path-row">
            <input
              className="cfg-input"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="C:\path\to\DLGLOG"
              spellCheck={false}
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => void browseFolder()}
              title="Open Windows folder picker"
            >
              Browse…
            </button>
          </div>
        </label>
        <div className="cfg-row">
          <label className="cfg-label">
            Plant name (optional)
            <input
              className="cfg-input"
              value={plantName}
              onChange={(e) => setPlantName(e.target.value)}
              placeholder="My Water Treatment Plant"
            />
          </label>
          <label className="cfg-label">
            Municipality (optional)
            <input
              className="cfg-input"
              value={municipality}
              onChange={(e) => setMunicipality(e.target.value)}
            />
          </label>
        </div>

        {diskModels.length > 0 && (
          <div className="model-box">
            <p className="cfg-hint" style={{ marginBottom: "0.5rem" }}>
              Datalog models found in this folder:
            </p>
            <div className="model-chips">
              {diskModels.map((m) => {
                const role =
                  m === assigned.trend
                    ? "trend"
                    : m === assigned.motors
                      ? "motors"
                      : m === assigned.feedback
                        ? "feedback"
                        : null;
                return (
                  <span
                    key={m}
                    className={role ? `model-chip is-${role}` : "model-chip"}
                    title={role ? `Used as ${role}` : "Available model"}
                  >
                    {m}
                    {role ? ` · ${role}` : ""}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || !path.trim()}
            onClick={() => void testPath()}
          >
            Test folder
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !path.trim()}
            onClick={() => void save()}
          >
            {busy ? "Working…" : "Save & connect"}
          </button>
        </div>
        {status && (
          <p
            className={`status ${status.startsWith("OK") || status.startsWith("Saved") ? "ok" : "warn"}`}
          >
            {status}
          </p>
        )}
      </section>

      <div className="stub-grid">
        <article className="stub-card">
          <h2>Tag Explorer</h2>
          <p>Browse tags from every model in the connected DLGLOG.</p>
          <Link to="/explore" className="ok">
            Open Explore →
          </Link>
        </article>
        <article className="stub-card">
          <h2>Reports</h2>
          <p>Daily / Monthly / Custom use this DLGLOG automatically.</p>
          <Link to="/reports" className="ok">
            Open Reports →
          </Link>
        </article>
      </div>
    </div>
  );
}

export function DesignPage() {
  return (
    <div className="page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Design</p>
          <h1>Report definitions</h1>
          <p className="lede">
            Sections are React components bound to DLGLOG tags. Connect only
            needs the main DLGLOG folder — model subfolders are detected for you.
          </p>
        </div>
      </header>
      <div className="stub-grid">
        <article className="stub-card">
          <h2>Daily / Monthly / Custom</h2>
          <p>Flows, analyzers, runtime, feedback, CT.</p>
          <Link to="/reports/daily" className="ok">
            Open Daily →
          </Link>
        </article>
        <article className="stub-card">
          <h2>Trends</h2>
          <p>Multi-tag overlay from the connected historian.</p>
          <Link to="/reports/trends" className="ok">
            Open Trends →
          </Link>
        </article>
      </div>
    </div>
  );
}

export function DistributePage() {
  const [items, setItems] = useState<ArchiveItem[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [dailyEnabled, setDailyEnabled] = useState(true);
  const [dailyTime, setDailyTime] = useState("06:00");
  const [dailyPrint, setDailyPrint] = useState(true);
  const [monthlyEnabled, setMonthlyEnabled] = useState(true);
  const [monthlyDay, setMonthlyDay] = useState(1);
  const [monthlyTime, setMonthlyTime] = useState("06:30");
  const [monthlyPrint, setMonthlyPrint] = useState(false);
  const [printer, setPrinter] = useState("");
  const [printers, setPrinters] = useState<
    { name: string; default?: boolean; offline?: boolean }[]
  >([]);
  const [schedLog, setSchedLog] = useState<Record<string, unknown>[]>([]);
  const [schedState, setSchedState] = useState<Record<string, unknown>>({});
  const [bfKind, setBfKind] = useState<"daily" | "monthly">("daily");
  const [bfFrom, setBfFrom] = useState("");
  const [bfTo, setBfTo] = useState("");
  const [bfPrint, setBfPrint] = useState(false);
  const [bfStatus, setBfStatus] = useState<Record<string, unknown> | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [outCfg, setOutCfg] = useState<OutputsConfig>({
    archive_folder: "",
    pdf_folder: "",
    web_folder: "",
    subfolders: true,
    save_pdf: true,
    save_html: true,
    save_json: true,
    copy_to: "",
  });
  const [outResolved, setOutResolved] = useState<{
    archive?: string;
    pdf?: string;
    web?: string;
  }>({});
  const [pdfFiles, setPdfFiles] = useState<OutputFile[]>([]);
  const [fileKind, setFileKind] = useState<"pdf" | "web">("pdf");

  const refreshArchive = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/archive?limit=80`);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      const list: ArchiveItem[] = data.items ?? [];
      setItems(list);
      setStatus(
        `Archive · ${list.length} report${list.length === 1 ? "" : "s"} · ${new Date().toLocaleTimeString()}`,
      );
    } catch {
      setStatus("API offline — cannot list archive. Is Ops Reporter running?");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshOutputs = useCallback(async () => {
    try {
      const [oRes, fRes] = await Promise.all([
        fetch(`${API}/api/outputs`),
        fetch(`${API}/api/outputs/files?kind=${fileKind}&limit=60`),
      ]);
      if (oRes.ok) {
        const data = await oRes.json();
        const o = data.outputs || {};
        setOutCfg({
          archive_folder: o.archive_folder || "",
          pdf_folder: o.pdf_folder || "",
          web_folder: o.web_folder || "",
          subfolders: o.subfolders !== false,
          save_pdf: o.save_pdf !== false,
          save_html: o.save_html !== false,
          save_json: o.save_json !== false,
          copy_to: o.copy_to || "",
        });
        setOutResolved(data.resolved || {});
      }
      if (fRes.ok) {
        const data = await fRes.json();
        setPdfFiles(data.items || []);
      }
    } catch {
      /* keep prior */
    }
  }, [fileKind]);

  const refreshSchedule = useCallback(async () => {
    try {
      const [sRes, pRes, hRes, bRes] = await Promise.all([
        fetch(`${API}/api/schedule`),
        fetch(`${API}/api/printers`),
        fetch(`${API}/api/health`),
        fetch(`${API}/api/archive/backfill`),
      ]);
      if (sRes.ok) {
        const data = await sRes.json();
        const sch = data.schedule || {};
        setSchedEnabled(!!sch.enabled);
        setDailyEnabled(sch.daily?.enabled !== false);
        setDailyTime(sch.daily?.time || "06:00");
        setDailyPrint(!!sch.daily?.print);
        setMonthlyEnabled(sch.monthly?.enabled !== false);
        setMonthlyDay(Number(sch.monthly?.day || 1));
        setMonthlyTime(sch.monthly?.time || "06:30");
        setMonthlyPrint(!!sch.monthly?.print);
        setPrinter(sch.printer || "");
        setSchedLog(data.log || []);
        setSchedState(data.state || {});
      }
      if (pRes.ok) {
        const data = await pRes.json();
        setPrinters(data.printers || []);
      }
      if (hRes.ok) {
        const h = await hRes.json();
        setBfFrom((prev) => prev || h.first_date || "");
        setBfTo((prev) => prev || h.last_date || "");
      }
      if (bRes.ok) setBfStatus(await bRes.json());
    } catch {
      /* keep prior */
    }
  }, []);

  useEffect(() => {
    void refreshArchive();
    void refreshSchedule();
    void refreshOutputs();
  }, [refreshArchive, refreshSchedule, refreshOutputs]);

  useEffect(() => {
    if (!bfStatus?.running) return;
    const id = window.setInterval(() => {
      void (async () => {
        try {
          const res = await fetch(`${API}/api/archive/backfill`);
          if (res.ok) {
            const data = await res.json();
            setBfStatus(data);
            if (!data.running) {
              void refreshArchive();
              void refreshOutputs();
            }
          }
        } catch {
          /* ignore */
        }
      })();
    }, 2000);
    return () => window.clearInterval(id);
  }, [bfStatus?.running, refreshArchive, refreshOutputs]);

  const browseOutput = async (
    field: "archive_folder" | "pdf_folder" | "web_folder" | "copy_to",
  ) => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/outputs/browse`, { method: "POST" });
      const data = await res.json();
      if (data.cancelled) {
        setStatus("Browse cancelled");
        return;
      }
      if (!data.ok || !data.path) throw new Error(data.error || "Browse failed");
      setOutCfg((prev) => ({ ...prev, [field]: data.path }));
      setStatus(`Selected ${data.path}`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Browse failed");
    } finally {
      setBusy(false);
    }
  };

  const saveOutputs = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/outputs`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(outCfg),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      const o = data.outputs || outCfg;
      setOutCfg({
        archive_folder: o.archive_folder || "",
        pdf_folder: o.pdf_folder || "",
        web_folder: o.web_folder || "",
        subfolders: o.subfolders !== false,
        save_pdf: o.save_pdf !== false,
        save_html: o.save_html !== false,
        save_json: o.save_json !== false,
        copy_to: o.copy_to || "",
      });
      setOutResolved(data.resolved || {});
      setStatus("Output folders saved");
      await refreshOutputs();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const openOutFolder = async (kind: "pdf" | "web" | "archive") => {
    try {
      const res = await fetch(`${API}/api/outputs/open`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Open failed");
      setStatus(`Opened ${data.path}`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Open failed");
    }
  };

  const saveSchedule = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/schedule`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: schedEnabled,
          printer,
          daily: {
            enabled: dailyEnabled,
            time: dailyTime,
            print: dailyPrint,
            offset_days: 1,
          },
          monthly: {
            enabled: monthlyEnabled,
            day: monthlyDay,
            time: monthlyTime,
            print: monthlyPrint,
          },
        }),
      });
      if (!res.ok) throw new Error(res.statusText);
      await refreshSchedule();
      setStatus("Schedule saved");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const runJob = async (job: "daily" | "monthly") => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/schedule/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job, force: true }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      setStatus(
        data.skipped
          ? `${job} skipped (${data.reason || "already done"})`
          : data.ok
            ? `${job} produced → ${data.pdf || data.id || "archive"}`
            : `${job} failed: ${data.error}`,
      );
      await refreshArchive();
      await refreshOutputs();
      await refreshSchedule();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Run failed");
    } finally {
      setBusy(false);
    }
  };

  const startBackfill = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/archive/backfill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: bfKind,
          from: bfFrom || undefined,
          to: bfTo || undefined,
          print: bfPrint,
          printer: printer || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      setBfStatus(data);
      setStatus(data.message || "Backfill started");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Backfill failed");
    } finally {
      setBusy(false);
    }
  };

  const printItem = async (id: string) => {
    setBusy(true);
    try {
      const res = await fetch(
        `${API}/api/archive/${encodeURIComponent(id)}/print`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ printer: printer || undefined }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
      setStatus(`Sent to printer: ${data.printer || "default"}`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Print failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Distribute</p>
          <h1>Outputs, schedule &amp; backfill</h1>
          <p className="lede">
            Choose PDF / Web / archive folders (XLReporter-style), schedule
            automatic produce, and backfill history. PDFs use Edge/Chrome
            print-to-PDF when a report is archived.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={loading}
          onClick={() => {
            void refreshArchive();
            void refreshSchedule();
            void refreshOutputs();
          }}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>
      {status && (
        <p
          className={`status ${status.includes("offline") || status.includes("fail") ? "warn" : "ok"}`}
        >
          {status}
        </p>
      )}

      <section className="cfg-card">
        <h2>Output folders</h2>
        <p className="cfg-hint">
          Like XLReporter Project Settings: blank paths use folders next to the
          app (<code>archive</code>, <code>PDF</code>, <code>Web</code>). If you
          pick a parent folder, <code>PDF</code> / <code>Web</code> is appended
          automatically. Subfolders are <code>kind/YYYY/MM</code>.
        </p>

        <label className="cfg-label">
          Archive folder (JSON + working HTML)
          <div className="cfg-path-row">
            <input
              className="cfg-input"
              value={outCfg.archive_folder}
              placeholder={outResolved.archive || "…/archive"}
              onChange={(e) =>
                setOutCfg((p) => ({ ...p, archive_folder: e.target.value }))
              }
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => void browseOutput("archive_folder")}
            >
              Browse…
            </button>
          </div>
        </label>

        <label className="cfg-label">
          PDF folder
          <div className="cfg-path-row">
            <input
              className="cfg-input"
              value={outCfg.pdf_folder}
              placeholder={outResolved.pdf || "…/PDF"}
              onChange={(e) =>
                setOutCfg((p) => ({ ...p, pdf_folder: e.target.value }))
              }
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => void browseOutput("pdf_folder")}
            >
              Browse…
            </button>
          </div>
        </label>

        <label className="cfg-label">
          Web folder (HTML copies)
          <div className="cfg-path-row">
            <input
              className="cfg-input"
              value={outCfg.web_folder}
              placeholder={outResolved.web || "…/Web"}
              onChange={(e) =>
                setOutCfg((p) => ({ ...p, web_folder: e.target.value }))
              }
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => void browseOutput("web_folder")}
            >
              Browse…
            </button>
          </div>
        </label>

        <label className="cfg-label">
          Also copy to (optional network share)
          <div className="cfg-path-row">
            <input
              className="cfg-input"
              value={outCfg.copy_to}
              placeholder="\\\\server\\share\\Reports"
              onChange={(e) =>
                setOutCfg((p) => ({ ...p, copy_to: e.target.value }))
              }
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => void browseOutput("copy_to")}
            >
              Browse…
            </button>
          </div>
        </label>

        <div className="cfg-checks">
          <label className="cfg-check">
            <input
              type="checkbox"
              checked={outCfg.save_pdf}
              onChange={(e) =>
                setOutCfg((p) => ({ ...p, save_pdf: e.target.checked }))
              }
            />
            Save PDF
          </label>
          <label className="cfg-check">
            <input
              type="checkbox"
              checked={outCfg.save_html}
              onChange={(e) =>
                setOutCfg((p) => ({ ...p, save_html: e.target.checked }))
              }
            />
            Save Web HTML
          </label>
          <label className="cfg-check">
            <input
              type="checkbox"
              checked={outCfg.subfolders}
              onChange={(e) =>
                setOutCfg((p) => ({ ...p, subfolders: e.target.checked }))
              }
            />
            Year/month subfolders
          </label>
        </div>

        <p className="cfg-hint">
          Resolved: PDF <code>{outResolved.pdf || "—"}</code>
          {" · "}Web <code>{outResolved.web || "—"}</code>
          {" · "}Archive <code>{outResolved.archive || "—"}</code>
        </p>

        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void saveOutputs()}
          >
            Save output folders
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void openOutFolder("pdf")}
          >
            Open PDF folder
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void openOutFolder("web")}
          >
            Open Web folder
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void openOutFolder("archive")}
          >
            Open archive
          </button>
        </div>
      </section>

      <section className="cfg-card">
        <h2>Stored files</h2>
        <div className="cfg-row cfg-row--3" style={{ marginBottom: "0.75rem" }}>
          <label className="cfg-label">
            Show
            <select
              className="cfg-input"
              value={fileKind}
              onChange={(e) =>
                setFileKind(e.target.value === "web" ? "web" : "pdf")
              }
            >
              <option value="pdf">PDF files</option>
              <option value="web">Web HTML files</option>
            </select>
          </label>
        </div>
        {!pdfFiles.length ? (
          <p className="cfg-hint">
            No {fileKind === "pdf" ? "PDFs" : "HTML files"} yet. Archive a report
            (or run schedule/backfill) with Save{" "}
            {fileKind === "pdf" ? "PDF" : "Web HTML"} enabled.
          </p>
        ) : (
          <table className="arch-table">
            <thead>
              <tr>
                <th>Modified</th>
                <th>Name</th>
                <th>Path</th>
              </tr>
            </thead>
            <tbody>
              {pdfFiles.map((f) => (
                <tr key={f.path}>
                  <td>{f.modified ?? "—"}</td>
                  <td>{f.name}</td>
                  <td className="path-cell" title={f.path}>
                    {f.rel || f.path}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="cfg-card">
        <h2>Scheduler</h2>
        <p className="cfg-hint">
          Keep Ops Reporter running (or the SCADA kit exe open) so jobs fire.
          Daily job produces <strong>yesterday</strong>; monthly runs on the
          chosen day and produces the <strong>previous calendar month</strong>.
        </p>
        <label className="cfg-check">
          <input
            type="checkbox"
            checked={schedEnabled}
            onChange={(e) => setSchedEnabled(e.target.checked)}
          />
          Enable scheduler
        </label>

        <div className="cfg-row cfg-row--3" style={{ marginTop: "0.75rem" }}>
          <label className="cfg-label">
            Daily time
            <input
              className="cfg-input"
              type="time"
              value={dailyTime}
              onChange={(e) => setDailyTime(e.target.value)}
            />
          </label>
          <label className="cfg-label">
            Monthly day
            <input
              className="cfg-input"
              type="number"
              min={1}
              max={28}
              value={monthlyDay}
              onChange={(e) => setMonthlyDay(Number(e.target.value) || 1)}
            />
          </label>
          <label className="cfg-label">
            Monthly time
            <input
              className="cfg-input"
              type="time"
              value={monthlyTime}
              onChange={(e) => setMonthlyTime(e.target.value)}
            />
          </label>
        </div>

        <div className="cfg-checks">
          <label className="cfg-check">
            <input
              type="checkbox"
              checked={dailyEnabled}
              onChange={(e) => setDailyEnabled(e.target.checked)}
            />
            Daily produce
          </label>
          <label className="cfg-check">
            <input
              type="checkbox"
              checked={dailyPrint}
              onChange={(e) => setDailyPrint(e.target.checked)}
            />
            Auto-print daily
          </label>
          <label className="cfg-check">
            <input
              type="checkbox"
              checked={monthlyEnabled}
              onChange={(e) => setMonthlyEnabled(e.target.checked)}
            />
            Monthly produce
          </label>
          <label className="cfg-check">
            <input
              type="checkbox"
              checked={monthlyPrint}
              onChange={(e) => setMonthlyPrint(e.target.checked)}
            />
            Auto-print monthly
          </label>
        </div>

        <label className="cfg-label">
          Printer (blank = Windows default)
          <select
            className="cfg-input"
            value={printer}
            onChange={(e) => setPrinter(e.target.value)}
          >
            <option value="">Windows default printer</option>
            {printers.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
                {p.default ? " (default)" : ""}
                {p.offline ? " — offline" : ""}
              </option>
            ))}
          </select>
        </label>
        <p className="cfg-hint">
          Auto-print uses Windows “Print” on the archived HTML. For a named
          queue, set that printer as the Windows default if the association
          ignores the name.
        </p>

        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void saveSchedule()}
          >
            Save schedule
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void runJob("daily")}
          >
            Run daily now
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void runJob("monthly")}
          >
            Run monthly now
          </button>
        </div>
        {Boolean(schedState.last_daily_date || schedState.last_monthly_month) && (
          <p className="cfg-hint" style={{ marginTop: "0.75rem" }}>
            Last daily: {String(schedState.last_daily_date || "—")}
            {schedState.last_daily_at
              ? ` @ ${String(schedState.last_daily_at)}`
              : ""}
            {" · "}
            Last monthly: {String(schedState.last_monthly_month || "—")}
          </p>
        )}
      </section>

      <section className="cfg-card">
        <h2>Backfill history</h2>
        <p className="cfg-hint">
          Produce and archive every daily (or monthly) report from the first
          trend day through the last available day. Already-archived periods are
          skipped. PDFs/Web copies follow Output folders. First run can take a
          while — leave the app open.
        </p>
        <div className="cfg-row cfg-row--3">
          <label className="cfg-label">
            Kind
            <select
              className="cfg-input"
              value={bfKind}
              onChange={(e) =>
                setBfKind(e.target.value === "monthly" ? "monthly" : "daily")
              }
            >
              <option value="daily">Daily reports</option>
              <option value="monthly">Monthly reports</option>
            </select>
          </label>
          <label className="cfg-label">
            From
            <input
              className="cfg-input"
              type="date"
              value={bfFrom}
              onChange={(e) => setBfFrom(e.target.value)}
            />
          </label>
          <label className="cfg-label">
            To
            <input
              className="cfg-input"
              type="date"
              value={bfTo}
              onChange={(e) => setBfTo(e.target.value)}
            />
          </label>
        </div>
        <label className="cfg-check">
          <input
            type="checkbox"
            checked={bfPrint}
            onChange={(e) => setBfPrint(e.target.checked)}
          />
          Print each report as it is produced (slow — usually leave off)
        </label>
        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || Boolean(bfStatus?.running)}
            onClick={() => void startBackfill()}
          >
            {bfStatus?.running ? "Backfill running…" : "Start backfill"}
          </button>
        </div>
        {bfStatus && (
          <p className="cfg-hint" style={{ marginTop: "0.75rem" }}>
            {String(bfStatus.message || "")}
            {bfStatus.total
              ? ` · done ${String(bfStatus.done)} / skip ${String(bfStatus.skipped)} / fail ${String(bfStatus.failed)} / total ${String(bfStatus.total)}`
              : ""}
            {bfStatus.current ? ` · current ${String(bfStatus.current)}` : ""}
          </p>
        )}
      </section>

      <section className="cfg-card">
        <h2>Recent schedule log</h2>
        {!schedLog.length ? (
          <p className="cfg-hint">No scheduler events yet.</p>
        ) : (
          <table className="arch-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Job</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {schedLog.slice(0, 12).map((row, i) => (
                <tr key={i}>
                  <td>{String(row.at || "—")}</td>
                  <td>{String(row.job || "—")}</td>
                  <td className="path-cell">
                    {row.error
                      ? String(row.error)
                      : row.skipped
                        ? "skipped"
                        : row.id
                          ? String(row.id)
                          : row.message
                            ? String(row.message)
                            : row.ok
                              ? "ok"
                              : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="cfg-card">
        <h2>Archive</h2>
        {!items.length && !loading ? (
          <p className="cfg-hint">
            No archived reports yet. Use Daily / Monthly / Custom{" "}
            <strong>Save to archive</strong>, run a scheduled job, or start a
            backfill.
          </p>
        ) : (
          <table className="arch-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Kind</th>
                <th>Period</th>
                <th>Title</th>
                <th>PDF</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id}>
                  <td>{it.saved_at ?? "—"}</td>
                  <td>{it.kind}</td>
                  <td>
                    {it.startDate}
                    {it.endDate && it.endDate !== it.startDate
                      ? ` → ${it.endDate}`
                      : ""}
                  </td>
                  <td>{it.subtitle}</td>
                  <td className="path-cell" title={it.pdf || it.html || ""}>
                    {it.pdf ? it.pdf.split(/[/\\]/).slice(-1)[0] : "—"}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ padding: "0.25rem 0.55rem", fontSize: "0.8rem" }}
                      disabled={busy}
                      onClick={() => void printItem(it.id)}
                    >
                      Print
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
