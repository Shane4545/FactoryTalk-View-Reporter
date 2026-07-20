import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { API } from "../api";
import { BusyOverlay } from "../components/BusyOverlay";
import "./ConnectDistribute.css";

type Health = {
  ok: boolean;
  dlglog?: string;
  date_count?: number;
  first_date?: string;
  last_date?: string;
  models_on_disk?: string[];
  plant?: { name?: string; municipality?: string };
  error?: string;
};

type Assigned = { trend?: string; motors?: string; feedback?: string };

export function ConnectPage() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<Health | null>(null);
  const [path, setPath] = useState("");
  const [plantName, setPlantName] = useState("");
  const [municipality, setMunicipality] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [diskModels, setDiskModels] = useState<string[]>([]);
  const [assigned, setAssigned] = useState<Assigned>({});
  const [logoKey, setLogoKey] = useState(0);
  const [hasCustomLogo, setHasCustomLogo] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/config`);
      const data = await res.json();
      setPath(data.dlglog_path || data.resolved_dlglog || "");
      setPlantName(data.plant?.name || "");
      setMunicipality(data.plant?.municipality || "");
      setDiskModels(data.models_on_disk || []);
      setAssigned(data.models || data.assigned || {});
      setHasCustomLogo(!!data.plant?.logo_file);
      try {
        const h = await fetch(`${API}/api/health`);
        const hj = (await h.json()) as Health;
        setHealth(
          hj?.ok
            ? hj
            : {
                ok: Boolean(data.ok && data.resolved_dlglog),
                dlglog: data.resolved_dlglog || data.dlglog_path,
                plant: data.plant,
                error: hj?.error || data.error,
              },
        );
      } catch {
        setHealth({
          ok: Boolean(data.ok && (data.resolved_dlglog || data.dlglog_path)),
          dlglog: data.resolved_dlglog || data.dlglog_path,
          plant: data.plant,
          error: data.error,
        });
      }
      try {
        const p = await fetch(`${API}/api/plant`);
        if (p.ok) {
          const pj = await p.json();
          setHasCustomLogo(!!pj.has_custom_logo);
        }
      } catch {
        /* branding probe optional */
      }
      setLogoKey((k) => k + 1);
    } catch {
      setHealth({
        ok: false,
        error: "API unreachable — start Plant Reporter",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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
        `Selected · ${data.models?.length ?? 0} datalog model(s) — set name/logo, then Save & connect`,
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
        setStatus("Saved · scanning DLGLOG and activating profile…");
        await load();
        window.dispatchEvent(new Event("plant-branding-changed"));
        // First-time / blank plant: Scan + Activate so Daily works immediately
        const bootRes = await fetch(`${API}/api/setup/bootstrap-from-dlglog`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        const boot = await bootRes.json();
        if (!bootRes.ok) {
          setStatus(
            typeof boot.detail === "string"
              ? boot.detail
              : "Connected — open Setup and Activate before Daily",
          );
          navigate("/setup?autoscan=1");
          return;
        }
        const day = boot.sample_day || "";
        setStatus(
          `OK · ${boot.included ?? "?"} tags on reports (${boot.tag_count ?? "?"} scanned) — opening Daily`,
        );
        navigate(day ? `/reports/daily?date=${day}` : "/reports/daily");
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const uploadLogo = async (file: File) => {
    setBusy(true);
    setStatus(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API}/api/branding/logo`, {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(
          typeof data.detail === "string" ? data.detail : "Logo upload failed",
        );
        return;
      }
      setHasCustomLogo(true);
      setLogoKey((k) => k + 1);
      setStatus("Logo saved — used in sidebar and reports/PDF");
      window.dispatchEvent(new Event("plant-branding-changed"));
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Logo upload failed");
    } finally {
      setBusy(false);
    }
  };

  const resetLogo = async () => {
    setBusy(true);
    try {
      await fetch(`${API}/api/branding/logo/reset`, { method: "POST" });
      setHasCustomLogo(false);
      setLogoKey((k) => k + 1);
      setStatus("Logo reset to default");
      window.dispatchEvent(new Event("plant-branding-changed"));
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Connect</p>
          <h1>Connect this PC to the plant DLGLOG</h1>
          <p className="lede">
            Point at this plant’s FactoryTalk View <strong>DLGLOG</strong>{" "}
            folder, set the plant name, township, and logo, then Save. One
            active dataset per install — on another computer, Connect to that
            plant’s DLGLOG the same way.{" "}
            <Link to="/help" className="ok">
              Full guide →
            </Link>
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
            <span className="warn">
              {health?.error || "Not connected — choose a DLGLOG folder below"}
            </span>
          )}
        </p>
      </section>

      <section className="cfg-card">
        <h2>Plant identity</h2>
        <p className="cfg-hint">
          Crest goes in the project <strong>Logo</strong> folder (created next to
          the app). Use <em>Open Logo folder</em> to drop a JPEG/PNG named{" "}
          <code>plant-logo.jpg</code>, or <em>Choose file…</em> to pick from
          anywhere — it is copied into Logo automatically.
        </p>
        <div className="brand-row">
          <div className="brand-logo-box">
            <img
              key={logoKey}
              src={`${API}/api/branding/logo?t=${logoKey}`}
              alt={municipality || plantName || "Plant logo"}
            />
            <small>{hasCustomLogo ? "Custom logo" : "Default logo"}</small>
          </div>
          <div className="brand-logo-actions">
            <input
              ref={fileRef}
              type="file"
              accept=".png,.jpg,.jpeg,.gif,.webp,image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void uploadLogo(f);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              Choose file…
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await fetch(`${API}/api/branding/logo/open`, {
                    method: "POST",
                  });
                  setStatus(
                    "Opened Logo folder — drop plant-logo.jpg then Refresh or re-open Connect",
                  );
                  setTimeout(() => void load(), 1500);
                } catch (e) {
                  setStatus(
                    e instanceof Error ? e.message : "Could not open Logo folder",
                  );
                } finally {
                  setBusy(false);
                }
              }}
            >
              Open Logo folder
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy || !hasCustomLogo}
              onClick={() => void resetLogo()}
            >
              Reset default
            </button>
          </div>
        </div>
        <div className="cfg-row">
          <label className="cfg-label">
            Plant name
            <input
              className="cfg-input"
              value={plantName}
              onChange={(e) => setPlantName(e.target.value)}
              placeholder="My Water Treatment Plant"
            />
          </label>
          <label className="cfg-label">
            Township / City
            <input
              className="cfg-input"
              value={municipality}
              onChange={(e) => setMunicipality(e.target.value)}
              placeholder="Town of …"
            />
          </label>
        </div>
      </section>

      <section className="cfg-card">
        <h2>DLGLOG folder</h2>
        <label className="cfg-label">
          Path
          <div className="cfg-path-row">
            <input
              className="cfg-input"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="C:\…\DLGLOG"
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
            className="btn btn-primary"
            disabled={busy || !path.trim()}
            onClick={() => void save()}
          >
            {busy ? "Working…" : "Save & connect"}
          </button>
        </div>
        <BusyOverlay
          active={busy}
          label="Working…"
          detail="Validating the DLGLOG folder / saving settings…"
          taskKey="connect"
          expectSeconds={8}
        />
        {status && !busy && (
          <p
            className={`status ${status.startsWith("OK") || status.startsWith("Saved") || status.startsWith("Logo") ? "ok" : "warn"}`}
          >
            {status}
          </p>
        )}
      </section>
    </div>
  );
}
