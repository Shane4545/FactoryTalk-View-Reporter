import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { API } from "../api";
import "./InsightsPage.css";

type Severity = "ok" | "watch" | "alert" | "unknown";

type Instrument = {
  tag: string;
  description: string;
  sectionTitle: string;
  units: string;
  severity: Severity;
  reasons: string[];
  stats: {
    min?: number | null;
    max?: number | null;
    avg?: number | null;
    count?: number;
    range?: number | null;
  };
  sparkline?: (number | null)[];
  trendsHref?: string;
  baseline?: {
    avg_7d: number;
    today_avg: number;
    delta_pct: number;
  };
};

type Motor = {
  tag: string;
  description: string;
  severity: Severity;
  duty_pct?: number | null;
  hours?: number | null;
  starts?: number | null;
  stops?: number | null;
  reasons: string[];
  suggestion?: string | null;
};

type CatalogItem = {
  kind: string;
  tag: string;
  description: string;
  sectionTitle?: string;
  hidden: boolean;
};

type Insights = {
  date: string;
  live?: boolean;
  overall: {
    severity: Severity;
    score: number;
    counts: Record<string, number>;
    label: string;
  };
  metrics: Record<string, number | null | undefined>;
  water_quality?: {
    severity: Severity;
    grade: number;
    label: string;
    parts: { name: string; severity: Severity; value: number | null; note: string }[];
  };
  filters?: {
    severity: Severity;
    note?: string;
    rows: {
      tag: string;
      label: string;
      severity: Severity;
      avg?: number | null;
      max?: number | null;
      reasons: string[];
    }[];
  };
  ct: {
    severity: Severity;
    margin_giardia?: number | null;
    margin_viruses?: number | null;
    reasons: string[];
  };
  instruments: Instrument[];
  motors: Motor[];
  suggestions: string[];
  disclaimer?: string;
  available_dates?: { first?: string; last?: string };
  catalog?: {
    instruments: CatalogItem[];
    motors: CatalogItem[];
    feedback: CatalogItem[];
    sections: CatalogItem[];
  };
  baseline_days?: string[];
};

function fmt(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}

function Sparkline({
  values,
  severity,
}: {
  values?: (number | null)[];
  severity: Severity;
}) {
  const pts = useMemo(() => {
    if (!values?.length) return "";
    const nums = values.filter((v): v is number => v != null && !Number.isNaN(v));
    if (nums.length < 2) return "";
    const min = Math.min(...nums);
    const max = Math.max(...nums);
    const span = max - min || 1;
    const w = 120;
    const h = 36;
    return values
      .map((v, i) => {
        if (v == null) return null;
        const x = (i / Math.max(1, values.length - 1)) * w;
        const y = h - ((v - min) / span) * (h - 4) - 2;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .filter(Boolean)
      .join(" ");
  }, [values]);

  if (!pts) return <div className="spark spark--empty" />;
  return (
    <svg className={`spark sev-${severity}`} viewBox="0 0 120 36" aria-hidden>
      <polyline fill="none" strokeWidth="2" points={pts} />
    </svg>
  );
}

function RangeBar({
  min,
  max,
  avg,
  severity,
}: {
  min?: number | null;
  max?: number | null;
  avg?: number | null;
  severity: Severity;
}) {
  if (min == null || max == null) return null;
  const span = max - min || 1;
  const avgPct =
    avg != null ? Math.min(100, Math.max(0, ((avg - min) / span) * 100)) : 50;
  return (
    <div className={`range-bar sev-${severity}`}>
      <span className="range-bar__track" />
      <span className="range-bar__avg" style={{ left: `${avgPct}%` }} />
    </div>
  );
}

function ScoreRing({ score, severity }: { score: number; severity: Severity }) {
  const r = 54;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - Math.min(100, Math.max(0, score)) / 100);
  return (
    <div className={`score-ring sev-${severity}`}>
      <svg viewBox="0 0 140 140" aria-hidden>
        <circle className="score-ring__track" cx="70" cy="70" r={r} />
        <circle
          className="score-ring__value"
          cx="70"
          cy="70"
          r={r}
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="score-ring__label">
        <strong>{score}</strong>
        <span>health</span>
      </div>
    </div>
  );
}

export function InsightsPage() {
  const [date, setDate] = useState("");
  const [data, setData] = useState<Insights | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<"all" | Severity>("all");
  const [manageOpen, setManageOpen] = useState(false);
  const [busyTag, setBusyTag] = useState<string | null>(null);

  const load = useCallback(async (d?: string) => {
    setLoading(true);
    setStatus(null);
    try {
      const qs = d ? `?date=${encodeURIComponent(d)}` : "";
      const res = await fetch(`${API}/api/insights${qs}`, { cache: "no-store" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          typeof err.detail === "string" ? err.detail : res.statusText,
        );
      }
      const json = (await res.json()) as Insights;
      setData(json);
      setDate(json.date);
      setStatus(
        `${json.overall.label} · ${json.overall.counts.alert || 0} red · ${json.overall.counts.watch || 0} yellow`,
      );
    } catch (e) {
      setData(null);
      setStatus(e instanceof Error ? e.message : "Failed to load insights");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hideItem = async (kind: string, tag: string) => {
    setBusyTag(`${kind}:${tag}`);
    try {
      const res = await fetch(`${API}/api/report-prefs/hide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, tag }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Hide failed");
      setStatus(`Hidden ${tag} from reports & Insights`);
      await load(date);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Hide failed");
    } finally {
      setBusyTag(null);
    }
  };

  const showItem = async (kind: string, tag: string) => {
    setBusyTag(`${kind}:${tag}`);
    try {
      const res = await fetch(`${API}/api/report-prefs/show`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, tag }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Show failed");
      setStatus(`Restored ${tag}`);
      await load(date);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Show failed");
    } finally {
      setBusyTag(null);
    }
  };

  const instruments = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.instruments;
    return data.instruments.filter((i) => i.severity === filter);
  }, [data, filter]);

  const motors = data?.motors ?? [];
  const m = data?.metrics;
  const hiddenItems = useMemo(() => {
    if (!data?.catalog) return [];
    return [
      ...data.catalog.instruments,
      ...data.catalog.motors,
      ...data.catalog.feedback,
      ...data.catalog.sections,
    ].filter((x) => x.hidden);
  }, [data]);

  return (
    <div className="page insights">
      <header className="page__head insights__head">
        <div>
          <p className="eyebrow">Operator tools</p>
          <h1>Plant Insights</h1>
          <p className="lede">
            Traffic-light health, water-quality index, filter bands, and 7-day
            baselines. Hide mixers or tags you do not use — Daily/Monthly
            reports follow the same list.
          </p>
        </div>
        <div className="insights__controls">
          <label>
            Day
            <input
              type="date"
              value={date}
              min={data?.available_dates?.first}
              max={data?.available_dates?.last}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="btn btn-primary"
            disabled={loading || !date}
            onClick={() => void load(date)}
          >
            {loading ? "Scanning…" : "Scan day"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setManageOpen((v) => !v)}
          >
            {manageOpen ? "Close manage" : "Manage items"}
          </button>
          <Link className="btn btn-secondary" to="/reports/trends">
            Open Trends
          </Link>
        </div>
      </header>

      {status && (
        <p className={`status ${data ? "ok" : "warn"}`}>{status}</p>
      )}

      {manageOpen && data?.catalog && (
        <section className="manage-card">
          <h2>Show / hide report items</h2>
          <p className="cfg-hint">
            Hidden items leave Daily, Monthly, Custom, and Insights. Example:
            hide mixers you only run in manual.
          </p>
          {!!hiddenItems.length && (
            <div className="manage-block">
              <h3>Currently hidden — click Restore</h3>
              <div className="manage-chips">
                {hiddenItems.map((it) => (
                  <button
                    key={`${it.kind}-${it.tag}`}
                    type="button"
                    className="manage-chip is-hidden"
                    disabled={busyTag === `${it.kind}:${it.tag}`}
                    onClick={() => void showItem(it.kind, it.tag)}
                  >
                    Restore {it.tag}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="manage-block">
            <h3>Motors — hide unused</h3>
            <div className="manage-chips">
              {data.catalog.motors
                .filter((x) => !x.hidden)
                .map((it) => (
                  <button
                    key={it.tag}
                    type="button"
                    className="manage-chip"
                    title={it.description}
                    disabled={busyTag === `motor:${it.tag}`}
                    onClick={() => void hideItem("motor", it.tag)}
                  >
                    Hide {it.tag}
                  </button>
                ))}
            </div>
          </div>
          <div className="manage-block">
            <h3>Instruments — hide unused</h3>
            <div className="manage-chips">
              {data.catalog.instruments
                .filter((x) => !x.hidden)
                .map((it) => (
                  <button
                    key={it.tag}
                    type="button"
                    className="manage-chip"
                    title={it.description}
                    disabled={busyTag === `trend:${it.tag}`}
                    onClick={() => void hideItem("trend", it.tag)}
                  >
                    Hide {it.tag}
                  </button>
                ))}
            </div>
          </div>
        </section>
      )}

      {data && (
        <>
          <section className="insights-hero">
            <ScoreRing
              score={data.overall.score}
              severity={data.overall.severity}
            />
            <div className="insights-hero__copy">
              <p className={`pill sev-${data.overall.severity}`}>
                {data.overall.label}
              </p>
              <h2>
                {data.date}
                {data.live ? " · live today" : ""}
              </h2>
              <div className="count-chips">
                <span className="sev-ok">{data.overall.counts.ok || 0} green</span>
                <span className="sev-watch">
                  {data.overall.counts.watch || 0} yellow
                </span>
                <span className="sev-alert">
                  {data.overall.counts.alert || 0} red
                </span>
              </div>
              {!!data.baseline_days?.length && (
                <p className="disclaimer">
                  Baseline: {data.baseline_days[0]} →{" "}
                  {data.baseline_days[data.baseline_days.length - 1]} (
                  {data.baseline_days.length} days)
                </p>
              )}
              <p className="disclaimer">{data.disclaimer}</p>
            </div>
            <div className={`ct-card sev-${data.ct.severity}`}>
              <h3>Disinfection CT</h3>
              <div className="ct-card__grid">
                <div>
                  <small>Giardia margin</small>
                  <strong>{fmt(data.ct.margin_giardia, 2)}</strong>
                </div>
                <div>
                  <small>Viruses margin</small>
                  <strong>{fmt(data.ct.margin_viruses, 2)}</strong>
                </div>
              </div>
              <ul>
                {data.ct.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          </section>

          {data.water_quality && (
            <section className={`wqi-card sev-${data.water_quality.severity}`}>
              <div className="wqi-card__head">
                <div>
                  <h2>Water Quality Index</h2>
                  <p>{data.water_quality.label}</p>
                </div>
                <strong className="wqi-grade">{data.water_quality.grade}</strong>
              </div>
              <div className="wqi-parts">
                {data.water_quality.parts.map((p) => (
                  <article key={p.name} className={`sev-${p.severity}`}>
                    <span className={`dot sev-${p.severity}`} />
                    <div>
                      <strong>{p.name}</strong>
                      <small>{p.note}</small>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}

          {!!data.filters?.rows?.length && (
            <section className="filter-strip">
              <div className="insights-section__head">
                <h2>Filter performance</h2>
                <small>{data.filters.note}</small>
              </div>
              <div className="filter-strip__grid">
                {data.filters.rows.map((r) => (
                  <article key={r.tag} className={`sev-${r.severity}`}>
                    <header>
                      <span className={`dot sev-${r.severity}`} />
                      <strong>{r.label}</strong>
                      <Link to={`/reports/trends?tags=${r.tag}&preset=1d`}>
                        Trend
                      </Link>
                    </header>
                    <p>
                      avg {fmt(r.avg, 3)} · max {fmt(r.max, 3)} NTU
                    </p>
                    <small>{r.reasons[0]}</small>
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className="metric-strip">
            <article>
              <small>Raw flow</small>
              <strong>
                {fmt(m?.raw_flow_ls, 1)} <em>L/s</em>
              </strong>
            </article>
            <article>
              <small>Treated flow</small>
              <strong>
                {fmt(m?.treated_flow_ls, 1)} <em>L/s</em>
              </strong>
            </article>
            <article>
              <small>Plant recovery</small>
              <strong>
                {fmt(m?.plant_recovery_pct, 1)} <em>%</em>
              </strong>
            </article>
            <article>
              <small>Clearwell</small>
              <strong>
                {fmt(m?.clearwell_level_pct, 1)} <em>%</em>
              </strong>
            </article>
            <article>
              <small>Tower level</small>
              <strong>
                {fmt(m?.tower_level_pct, 1)} <em>%</em>
              </strong>
            </article>
            <article>
              <small>Treated Cl₂</small>
              <strong>
                {fmt(m?.treated_cl2_mgl, 3)} <em>mg/L</em>
              </strong>
            </article>
            <article>
              <small>High-lift hours</small>
              <strong>
                {fmt(m?.high_lift_hours, 1)} <em>h</em>
              </strong>
            </article>
            <article>
              <small>Treated volume</small>
              <strong>
                {fmt(m?.treated_volume_m3, 0)} <em>m³</em>
              </strong>
            </article>
          </section>

          {!!data.suggestions.length && (
            <section className="suggest-card">
              <h2>What to check</h2>
              <ol>
                {data.suggestions.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            </section>
          )}

          <section className="insights-section">
            <div className="insights-section__head">
              <h2>Instruments &amp; analyzers</h2>
              <div className="filter-row">
                {(["all", "alert", "watch", "ok"] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={filter === f ? "is-on" : ""}
                    onClick={() => setFilter(f)}
                  >
                    {f === "all" ? "All" : f}
                  </button>
                ))}
              </div>
            </div>
            <div className="inst-grid">
              {instruments.map((inst) => (
                <article
                  key={inst.tag}
                  className={`inst-card sev-${inst.severity}`}
                >
                  <header>
                    <span className={`dot sev-${inst.severity}`} />
                    <div>
                      <strong>{inst.tag}</strong>
                      <small>{inst.sectionTitle}</small>
                    </div>
                    <Sparkline
                      values={inst.sparkline}
                      severity={inst.severity}
                    />
                  </header>
                  <p className="inst-card__desc">{inst.description}</p>
                  <div className="inst-card__stats">
                    <span>min {fmt(inst.stats.min)}</span>
                    <span>avg {fmt(inst.stats.avg)}</span>
                    <span>max {fmt(inst.stats.max)}</span>
                    <span>{inst.units}</span>
                  </div>
                  <RangeBar
                    min={inst.stats.min}
                    max={inst.stats.max}
                    avg={inst.stats.avg}
                    severity={inst.severity}
                  />
                  {inst.baseline && (
                    <p className="baseline-line">
                      vs 7d: {inst.baseline.delta_pct >= 0 ? "+" : ""}
                      {inst.baseline.delta_pct}% (base{" "}
                      {fmt(inst.baseline.avg_7d)})
                    </p>
                  )}
                  <p className="inst-card__why">{inst.reasons[0]}</p>
                  <div className="inst-card__actions">
                    <Link
                      className="btn btn-secondary"
                      style={{ padding: "0.2rem 0.55rem", fontSize: "0.78rem" }}
                      to={
                        inst.trendsHref ||
                        `/reports/trends?tags=${inst.tag}&preset=1d`
                      }
                    >
                      Trends
                    </Link>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ padding: "0.2rem 0.55rem", fontSize: "0.78rem" }}
                      disabled={busyTag === `trend:${inst.tag}`}
                      onClick={() => void hideItem("trend", inst.tag)}
                    >
                      Hide
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="insights-section">
            <div className="insights-section__head">
              <h2>Motor duty &amp; cycling</h2>
              <Link to="/reports/daily" className="ok">
                Full runtime report →
              </Link>
            </div>
            <div className="motor-grid">
              {motors.map((mot) => (
                <article
                  key={mot.tag}
                  className={`motor-card sev-${mot.severity}`}
                >
                  <header>
                    <span className={`dot sev-${mot.severity}`} />
                    <strong>{mot.tag}</strong>
                    <span className="duty">{fmt(mot.duty_pct, 0)}%</span>
                  </header>
                  <p>{mot.description.replace(/ Run time$/i, "")}</p>
                  <div className="duty-bar">
                    <span
                      style={{ width: `${Math.min(100, mot.duty_pct ?? 0)}%` }}
                    />
                  </div>
                  <div className="motor-meta">
                    <span>{fmt(mot.hours, 1)} h</span>
                    <span>{mot.starts ?? "—"} starts</span>
                    <span>{mot.stops ?? "—"} stops</span>
                  </div>
                  {mot.suggestion && (
                    <p className="motor-tip">{mot.suggestion}</p>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{
                      marginTop: "0.45rem",
                      padding: "0.2rem 0.55rem",
                      fontSize: "0.78rem",
                    }}
                    disabled={busyTag === `motor:${mot.tag}`}
                    onClick={() => void hideItem("motor", mot.tag)}
                  >
                    Hide from reports
                  </button>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
