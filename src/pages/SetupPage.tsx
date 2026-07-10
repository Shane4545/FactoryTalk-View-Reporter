import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { API } from "../api";
import "./ConnectDistribute.css";
import "./SetupPage.css";

type RowKind = "trend" | "motor" | "feedback" | "skip";

type EditRow = {
  historian: string;
  model: string;
  include: boolean;
  kind: RowKind;
  tag: string;
  description: string;
  section: string;
  units: string;
  totalize: boolean;
};

type SectionChoice = { id: string; title: string };
type CtRole = { role: string; label: string; which: string };
type InsightRole = { role: string; label: string; kind: "single" | "multi" };

type Profile = {
  profile_name: string;
  builtin?: boolean;
  sections: SectionChoice[];
  trend: {
    tag: string;
    description: string;
    historian: string;
    section: string;
    units: string;
    totalize?: boolean;
    total_units?: string | null;
  }[];
  motors: { tag: string; description: string; historian: string }[];
  feedback: { tag: string; description: string; historian: string; units?: string }[];
  roles: Record<string, string | string[]>;
  ct: Record<string, unknown> & {
    enabled?: boolean;
    inputs?: Record<string, [string, string]>;
  };
};

type SetupState = {
  ok: boolean;
  error?: string | null;
  dlglog?: string;
  models_on_disk?: string[];
  configured: boolean;
  match?: { found: number; total: number; pct: number | null };
  profile: Profile;
  section_choices: SectionChoice[];
  ct_roles: CtRole[];
  insight_roles: InsightRole[];
};

type DiscoverTag = {
  historian: string;
  model: string;
  mapped: boolean;
  suggestion: {
    kind: RowKind;
    tag: string;
    description: string;
    section?: string;
    units?: string;
    totalize?: boolean;
  };
};

const CT_GEOMETRY_FIELDS: [string, string][] = [
  ["clearwell_volume_m3", "Clearwell volume (m³)"],
  ["pipe_volume_m3", "Pipe contact volume (m³)"],
  ["tower_volume_m3", "Tower / reservoir volume (m³)"],
  ["tower_volume_offset_m3", "Tower fixed volume offset (m³)"],
  ["baffle_clearwell", "Baffling factor — clearwell"],
  ["baffle_tower", "Baffling factor — tower"],
  ["baffle_pipe", "Baffling factor — pipe"],
  ["target_giardia_log", "Target Giardia log inactivation"],
  ["target_virus_log", "Target virus log inactivation"],
];

export function SetupPage() {
  const [state, setState] = useState<SetupState | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [profileName, setProfileName] = useState("");
  const [roles, setRoles] = useState<Record<string, string | string[]>>({});
  const [ctEnabled, setCtEnabled] = useState(false);
  const [ctGeo, setCtGeo] = useState<Record<string, string>>({});
  const [ctInputs, setCtInputs] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [filter, setFilter] = useState("");
  const [onlyIncluded, setOnlyIncluded] = useState(false);
  const importRef = useRef<HTMLInputElement | null>(null);

  const applyProfile = useCallback((s: SetupState) => {
    const prof = s.profile;
    setProfileName(prof.builtin ? "" : prof.profile_name || "");
    const next: EditRow[] = [];
    for (const r of prof.trend) {
      next.push({
        historian: r.historian,
        model: "",
        include: true,
        kind: "trend",
        tag: r.tag,
        description: r.description,
        section: r.section,
        units: r.units || "",
        totalize: !!r.totalize,
      });
    }
    for (const r of prof.motors) {
      next.push({
        historian: r.historian,
        model: "",
        include: true,
        kind: "motor",
        tag: r.tag,
        description: r.description,
        section: "",
        units: "",
        totalize: false,
      });
    }
    for (const r of prof.feedback) {
      next.push({
        historian: r.historian,
        model: "",
        include: true,
        kind: "feedback",
        tag: r.tag,
        description: r.description,
        section: "",
        units: r.units || "%",
        totalize: false,
      });
    }
    setRows(next);
    setRoles(prof.roles || {});
    setCtEnabled(!!prof.ct?.enabled);
    const geo: Record<string, string> = {};
    for (const [key] of CT_GEOMETRY_FIELDS) {
      const v = prof.ct?.[key];
      geo[key] = v == null ? "" : String(v);
    }
    setCtGeo(geo);
    const inputs: Record<string, string> = {};
    for (const [role, spec] of Object.entries(prof.ct?.inputs || {})) {
      if (Array.isArray(spec) && spec[0]) inputs[role] = String(spec[0]);
    }
    setCtInputs(inputs);
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/setup`);
      const data: SetupState = await res.json();
      setState(data);
      applyProfile(data);
    } catch {
      setStatus("API unreachable — start Ops Reporter");
    }
  }, [applyProfile]);

  useEffect(() => {
    void load();
  }, [load]);

  const scan = async () => {
    setScanning(true);
    setStatus(null);
    try {
      const res = await fetch(`${API}/api/setup/discover`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          typeof err.detail === "string" ? err.detail : res.statusText,
        );
      }
      const data: { tags: DiscoverTag[] } = await res.json();
      setRows((prev) => {
        const have = new Set(prev.map((r) => r.historian));
        const added: EditRow[] = [];
        for (const t of data.tags) {
          if (have.has(t.historian)) continue;
          const s = t.suggestion;
          added.push({
            historian: t.historian,
            model: t.model,
            include: false,
            kind: s.kind,
            tag: s.tag,
            description: s.description,
            section: s.section || "other",
            units: s.units || "",
            totalize: !!s.totalize,
          });
        }
        if (added.length) {
          setStatus(
            `Scan found ${data.tags.length} logged tags — ${added.length} new (unchecked below; tick the ones you want on reports)`,
          );
        } else {
          setStatus(
            `Scan found ${data.tags.length} logged tags — all already in the list`,
          );
        }
        return [...prev, ...added];
      });
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const update = (hist: string, patch: Partial<EditRow>) => {
    setRows((prev) =>
      prev.map((r) => (r.historian === hist ? { ...r, ...patch } : r)),
    );
  };

  const trendIncluded = useMemo(
    () => rows.filter((r) => r.include && r.kind === "trend"),
    [rows],
  );
  const motorIncluded = useMemo(
    () => rows.filter((r) => r.include && r.kind === "motor"),
    [rows],
  );

  const buildProfile = () => {
    const sections = state?.section_choices || [];
    const usedSections = new Set(trendIncluded.map((r) => r.section || "other"));
    const cleanRoles: Record<string, string | string[]> = {};
    const trendHists = new Set(trendIncluded.map((r) => r.historian));
    for (const ir of state?.insight_roles || []) {
      const v = roles[ir.role];
      if (ir.kind === "multi") {
        const list = (Array.isArray(v) ? v : []).filter((x) =>
          ir.role === "high_lift_pumps"
            ? motorIncluded.some((m) => m.tag === x)
            : trendHists.has(x),
        );
        if (list.length) cleanRoles[ir.role] = list;
      } else if (typeof v === "string" && trendHists.has(v)) {
        cleanRoles[ir.role] = v;
      }
    }
    const inputs: Record<string, [string, string]> = {};
    for (const cr of state?.ct_roles || []) {
      const hist = ctInputs[cr.role];
      if (hist && trendHists.has(hist)) inputs[cr.role] = [hist, cr.which];
    }
    const geo: Record<string, unknown> = {};
    for (const [key] of CT_GEOMETRY_FIELDS) {
      const raw = (ctGeo[key] || "").trim();
      if (raw !== "" && !Number.isNaN(Number(raw))) geo[key] = Number(raw);
    }
    return {
      profile_name: profileName.trim() || "My plant",
      sections: sections.filter((s) => usedSections.has(s.id)),
      trend: trendIncluded.map((r) => ({
        tag: r.tag,
        description: r.description,
        historian: r.historian,
        section: r.section || "other",
        units: r.units,
        totalize: r.totalize,
        total_units: r.totalize ? "m3" : null,
      })),
      motors: motorIncluded.map((r) => ({
        tag: r.tag,
        description: r.description,
        historian: r.historian,
      })),
      feedback: rows
        .filter((r) => r.include && r.kind === "feedback")
        .map((r) => ({
          tag: r.tag,
          description: r.description,
          historian: r.historian,
          units: r.units || "%",
        })),
      roles: cleanRoles,
      ct: { enabled: ctEnabled, ...geo, inputs },
    };
  };

  const save = async () => {
    if (!trendIncluded.length && !motorIncluded.length) {
      setStatus("Include at least one instrument or motor before saving");
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      const res = await fetch(`${API}/api/setup/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildProfile()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      setStatus(
        `Saved "${data.profile.profile_name}" — reports, Insights and Trends now use this mapping`,
      );
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    setStatus(null);
    try {
      await fetch(`${API}/api/setup/reset`, { method: "POST" });
      setStatus("Reset to the built-in Chalk River example profile");
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  };

  const exportProfile = async () => {
    try {
      const res = await fetch(`${API}/api/setup/export`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const name = (data.tag_config?.profile_name || "plant")
        .replace(/[^\w-]+/g, "_")
        .toLowerCase();
      a.download = `ops_reporter_profile_${name}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Export failed");
    }
  };

  const importProfile = async (file: File) => {
    setBusy(true);
    setStatus(null);
    try {
      const text = await file.text();
      const res = await fetch(`${API}/api/setup/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: text,
      });
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Import failed",
        );
      setStatus(`Imported profile "${data.profile.profile_name}"`);
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleMulti = (role: string, value: string) => {
    setRoles((prev) => {
      const cur = Array.isArray(prev[role]) ? (prev[role] as string[]) : [];
      const next = cur.includes(value)
        ? cur.filter((x) => x !== value)
        : [...cur, value];
      return { ...prev, [role]: next };
    });
  };

  const q = filter.trim().toUpperCase();
  const visible = rows.filter((r) => {
    if (onlyIncluded && !r.include) return false;
    if (!q) return true;
    return (
      r.historian.toUpperCase().includes(q) ||
      r.tag.toUpperCase().includes(q) ||
      r.description.toUpperCase().includes(q)
    );
  });

  const includedCount = rows.filter((r) => r.include).length;

  return (
    <div className="page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Setup</p>
          <h1>Map this plant's tags</h1>
          <p className="lede">
            Works on any FactoryTalk View SE machine that logs to DLGLOG. Scan
            the datalog, tick the tags you want on reports, name them, assign
            sections and roles, and set your CT geometry. Chalk River ships as
            the built-in example — Reset brings it back any time.
          </p>
        </div>
      </header>

      <section className="cfg-card">
        <h2>Status</h2>
        <p className="cfg-live">
          {state?.ok ? (
            <>
              <span className="ok">DLGLOG connected</span> · {state.dlglog}
              <br />
              Active profile:{" "}
              <strong>
                {state.profile.builtin
                  ? "Chalk River (built-in example)"
                  : state.profile.profile_name}
              </strong>
              {state.match?.total ? (
                <>
                  {" "}
                  · {state.match.found}/{state.match.total} mapped tags exist in
                  this DLGLOG ({state.match.pct}%)
                </>
              ) : null}
              {state.match?.pct != null && state.match.pct < 50 && (
                <>
                  <br />
                  <span className="warn">
                    Low match — this DLGLOG doesn't look like the active
                    profile. Scan and save your own mapping below.
                  </span>
                </>
              )}
            </>
          ) : (
            <span className="warn">
              {state?.error || "Not connected"} —{" "}
              <Link to="/connect">open Connect</Link> first
            </span>
          )}
        </p>
        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={scanning || !state?.ok}
            onClick={() => void scan()}
          >
            {scanning ? "Scanning…" : "Scan DLGLOG tags"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void exportProfile()}
          >
            Export profile
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => importRef.current?.click()}
          >
            Import profile…
          </button>
          <input
            ref={importRef}
            type="file"
            accept=".json,application/json"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importProfile(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void reset()}
            title="Back to the built-in Chalk River example"
          >
            Reset to example
          </button>
        </div>
        {status && (
          <p
            className={`status ${/^(Saved|Imported|Reset|Scan)/.test(status) ? "ok" : "warn"}`}
          >
            {status}
          </p>
        )}
      </section>

      <section className="cfg-card">
        <h2>1 · Profile</h2>
        <div className="cfg-row">
          <label className="cfg-label">
            Profile name
            <input
              className="cfg-input"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              placeholder="My Water Treatment Plant"
            />
          </label>
        </div>
        <p className="cfg-hint">
          Plant name and municipality for report headers are on the{" "}
          <Link to="/connect">Connect</Link> page.
        </p>
      </section>

      <section className="cfg-card">
        <h2>
          2 · Tags on reports{" "}
          <small className="setup-count">
            {includedCount} included / {rows.length} listed
          </small>
        </h2>
        <p className="cfg-hint">
          Tick <strong>Use</strong> for every tag you want on the Daily /
          Monthly reports and Insights. Type = analog instrument (min/max/avg),
          motor (runtime, starts/stops from a digital RUN tag), or feedback
          (speed/output %). Suggestions are pre-filled from the tag names —
          adjust anything.
        </p>
        <div className="setup-filter-row">
          <input
            className="cfg-input"
            placeholder="Filter tags…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <label className="setup-check">
            <input
              type="checkbox"
              checked={onlyIncluded}
              onChange={(e) => setOnlyIncluded(e.target.checked)}
            />
            Only included
          </label>
        </div>
        <div className="setup-table-wrap">
          <table className="setup-table">
            <thead>
              <tr>
                <th>Use</th>
                <th>Logged tag (historian)</th>
                <th>Type</th>
                <th>Report tag</th>
                <th>Description</th>
                <th>Section</th>
                <th>Units</th>
                <th title="Integrate flow to a daily volume total">Total</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.historian} className={r.include ? "" : "is-off"}>
                  <td>
                    <input
                      type="checkbox"
                      checked={r.include}
                      onChange={(e) =>
                        update(r.historian, { include: e.target.checked })
                      }
                    />
                  </td>
                  <td className="setup-hist" title={r.model || undefined}>
                    {r.historian}
                    {r.model ? <small> · {r.model}</small> : null}
                  </td>
                  <td>
                    <select
                      value={r.kind}
                      onChange={(e) =>
                        update(r.historian, { kind: e.target.value as RowKind })
                      }
                    >
                      <option value="trend">instrument</option>
                      <option value="motor">motor</option>
                      <option value="feedback">feedback</option>
                    </select>
                  </td>
                  <td>
                    <input
                      className="setup-mini"
                      value={r.tag}
                      onChange={(e) =>
                        update(r.historian, { tag: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <input
                      className="setup-desc"
                      value={r.description}
                      onChange={(e) =>
                        update(r.historian, { description: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    {r.kind === "trend" ? (
                      <select
                        value={r.section}
                        onChange={(e) =>
                          update(r.historian, { section: e.target.value })
                        }
                      >
                        {(state?.section_choices || []).map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.title}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="setup-dash">—</span>
                    )}
                  </td>
                  <td>
                    {r.kind !== "motor" ? (
                      <input
                        className="setup-mini"
                        value={r.units}
                        onChange={(e) =>
                          update(r.historian, { units: e.target.value })
                        }
                      />
                    ) : (
                      <span className="setup-dash">h</span>
                    )}
                  </td>
                  <td>
                    {r.kind === "trend" ? (
                      <input
                        type="checkbox"
                        checked={r.totalize}
                        onChange={(e) =>
                          update(r.historian, { totalize: e.target.checked })
                        }
                      />
                    ) : (
                      <span className="setup-dash">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {!visible.length && (
                <tr>
                  <td colSpan={8} className="setup-empty">
                    {rows.length
                      ? "No tags match the filter."
                      : "Press “Scan DLGLOG tags” to list everything this SCADA logs."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="cfg-card">
        <h2>3 · Insight roles (optional)</h2>
        <p className="cfg-hint">
          Tell Insights which mapped instruments play these roles. Anything you
          leave blank simply hides that metric — nothing breaks.
        </p>
        <div className="setup-roles">
          {(state?.insight_roles || []).map((ir) =>
            ir.kind === "single" ? (
              <label key={ir.role} className="cfg-label">
                {ir.label}
                <select
                  className="cfg-input"
                  value={typeof roles[ir.role] === "string" ? (roles[ir.role] as string) : ""}
                  onChange={(e) =>
                    setRoles((p) => ({ ...p, [ir.role]: e.target.value }))
                  }
                >
                  <option value="">— not used —</option>
                  {trendIncluded.map((r) => (
                    <option key={r.historian} value={r.historian}>
                      {r.tag} — {r.description}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <div key={ir.role} className="cfg-label">
                {ir.label}
                <div className="setup-chiprow">
                  {(ir.role === "high_lift_pumps"
                    ? motorIncluded.map((m) => ({ id: m.tag, label: m.tag }))
                    : trendIncluded.map((t) => ({
                        id: t.historian,
                        label: t.tag,
                      }))
                  ).map((opt) => {
                    const cur = Array.isArray(roles[ir.role])
                      ? (roles[ir.role] as string[])
                      : [];
                    const on = cur.includes(opt.id);
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        className={`setup-chip ${on ? "is-on" : ""}`}
                        onClick={() => toggleMulti(ir.role, opt.id)}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ),
          )}
        </div>
      </section>

      <section className="cfg-card">
        <h2>4 · CT disinfection (optional)</h2>
        <label className="setup-check setup-ct-toggle">
          <input
            type="checkbox"
            checked={ctEnabled}
            onChange={(e) => setCtEnabled(e.target.checked)}
          />
          Include the CT Achieved / Required table on reports
        </label>
        {ctEnabled && (
          <>
            <p className="cfg-hint">
              Same worst-case calculation as the Chalk River CT workbook — only
              the sizes change per plant. Enter your contact volumes and
              baffling factors, then pick which instruments feed each input. If
              your plant has no tower or pipe segment, set that volume to 0.
            </p>
            <div className="setup-geo">
              {CT_GEOMETRY_FIELDS.map(([key, label]) => (
                <label key={key} className="cfg-label">
                  {label}
                  <input
                    className="cfg-input"
                    inputMode="decimal"
                    value={ctGeo[key] ?? ""}
                    onChange={(e) =>
                      setCtGeo((p) => ({ ...p, [key]: e.target.value }))
                    }
                  />
                </label>
              ))}
            </div>
            <h3 className="setup-sub">CT inputs (worst case per day)</h3>
            <div className="setup-roles">
              {(state?.ct_roles || []).map((cr) => (
                <label key={cr.role} className="cfg-label">
                  {cr.label}{" "}
                  <small className="setup-which">daily {cr.which}</small>
                  <select
                    className="cfg-input"
                    value={ctInputs[cr.role] || ""}
                    onChange={(e) =>
                      setCtInputs((p) => ({ ...p, [cr.role]: e.target.value }))
                    }
                  >
                    <option value="">— not used —</option>
                    {trendIncluded.map((r) => (
                      <option key={r.historian} value={r.historian}>
                        {r.tag} — {r.description}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="cfg-card">
        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void save()}
          >
            {busy ? "Saving…" : "Save plant profile"}
          </button>
          <Link to="/reports/daily" className="btn btn-secondary">
            Open Daily report
          </Link>
        </div>
        {status && (
          <p
            className={`status ${/^(Saved|Imported|Reset|Scan)/.test(status) ? "ok" : "warn"}`}
          >
            {status}
          </p>
        )}
      </section>
    </div>
  );
}
