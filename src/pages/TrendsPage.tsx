import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API } from "../api";
import { TrendChart } from "../components/TrendChart";
import "./ExplorePage.css";
import "./TrendsPage.css";

type TagInfo = {
  id: string;
  historianTag: string;
  description: string;
  units: string;
  model?: string;
};

type Series = {
  id: string;
  description: string;
  units: string;
  count: number;
  min: number | null;
  max: number | null;
  avg: number | null;
  points: { t: string; v: number }[];
};

const COLORS = [
  "#0e7490",
  "#b45309",
  "#7c3aed",
  "#be123c",
  "#15803d",
  "#0369a1",
];

const PRESETS = [
  { id: "1d", label: "1 day" },
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
];

const DEFAULT_TAGS = ["FIT101", "FIT102", "FIT106"];

export function TrendsPage() {
  const [searchParams] = useSearchParams();
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [filter, setFilter] = useState("");
  const [modelFilter, setModelFilter] = useState("all");
  const [selected, setSelected] = useState<string[]>(() => {
    const q = searchParams.get("tags");
    if (q) {
      const ids = q.split(",").map((s) => s.trim()).filter(Boolean).slice(0, 6);
      if (ids.length) return ids;
    }
    return DEFAULT_TAGS;
  });
  const [preset, setPreset] = useState(() => searchParams.get("preset") || "1d");
  const [custom, setCustom] = useState(false);
  const [start, setStart] = useState("2026-06-08T00:00");
  const [end, setEnd] = useState("2026-06-15T23:59");
  const [series, setSeries] = useState<Series[]>([]);
  const [window, setWindow] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/tags`);
        const data = await res.json();
        const list: TagInfo[] = data.tags ?? [];
        setTags(list);
        if (list.length) {
          setSelected((prev) => {
            const valid = prev.filter((id) => list.some((t) => t.id === id));
            return valid.length ? valid : list.slice(0, 3).map((t) => t.id);
          });
        }
      } catch {
        setStatus("API offline — start server on :8787");
      }
      try {
        const res = await fetch(`${API}/api/dates`);
        const data = await res.json();
        const dates: string[] = data.dates ?? [];
        if (dates.length) {
          // Default the pickers to the last week of available data —
          // the full archive can span many months.
          setStart(`${dates[Math.max(0, dates.length - 7)]}T00:00`);
          setEnd(`${dates[dates.length - 1]}T23:59`);
        }
      } catch {
        // keep fallback defaults
      }
    })();
  }, []);

  const models = useMemo(() => {
    const set = new Set(tags.map((t) => t.model).filter(Boolean) as string[]);
    return Array.from(set).sort();
  }, [tags]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return tags.filter((t) => {
      if (modelFilter !== "all" && t.model !== modelFilter) return false;
      if (!q) return true;
      return (
        t.id.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.historianTag.toLowerCase().includes(q)
      );
    });
  }, [tags, filter, modelFilter]);

  const grouped = useMemo(() => {
    const by = new Map<string, TagInfo[]>();
    for (const t of visible) {
      const key = t.model || "OTHER";
      const arr = by.get(key);
      if (arr) arr.push(t);
      else by.set(key, [t]);
    }
    return Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [visible]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 6) return prev;
      return [...prev, id];
    });
  };

  const loadSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    if (!selected.length) {
      // Nothing selected → clear the chart instead of keeping stale series
      setSeries([]);
      setWindow("");
      setStatus("No tags selected — pick up to 6 from the list");
      setLoading(false);
      return;
    }
    if (custom && (!start || !end || start > end)) {
      setStatus("Pick a valid start/end (start must be before end)");
      return;
    }
    setLoading(true);
    setStatus(null);
    try {
      const range = custom
        ? `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
        : `preset=${preset}`;
      const res = await fetch(
        `${API}/api/trends?tags=${encodeURIComponent(selected.join(","))}&${range}`,
      );
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      if (seq !== loadSeq.current) return; // a newer request superseded this one
      setSeries(data.series ?? []);
      setWindow(`${data.start} → ${data.end}`);
      const n = (data.series ?? []).reduce(
        (a: number, s: Series) => a + (s.count || 0),
        0,
      );
      setStatus(
        `LIVE · ${data.series?.length ?? 0} series · ${n.toLocaleString()} samples · XLReporter=NO`,
      );
    } catch (e) {
      if (seq !== loadSeq.current) return;
      setStatus(e instanceof Error ? e.message : "Failed");
      setSeries([]);
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [selected, preset, custom, start, end]);

  useEffect(() => {
    void load();
  }, [load]);

  const chartSeries = useMemo(
    () =>
      series.map((s, i) => ({
        id: s.id,
        description: s.description,
        units: s.units,
        color: COLORS[i % COLORS.length],
        points: s.points,
      })),
    [series],
  );

  return (
    <div className="page explore">
      <header className="page__head">
        <div>
          <p className="eyebrow">
            <Link to="/reports">Reports</Link> / Trends
          </p>
          <h1>Multi-tag Trends</h1>
          <p className="lede">
            Overlay up to 6 tags from every DLGLOG model. Drag to zoom, click
            the chart to read values at any moment.
          </p>
        </div>
      </header>

      <div className="trends-layout">
        <aside className="trends-tags">
          <div className="trends-selected">
            <p className="trends-label">
              Selected ({selected.length}/6)
              {selected.length > 0 && (
                <button
                  type="button"
                  className="trends-clear"
                  onClick={() => setSelected([])}
                >
                  Clear all
                </button>
              )}
            </p>
            {selected.length === 0 ? (
              <p className="trends-none">None — pick tags below</p>
            ) : (
              <div className="tag-pills">
                {selected.map((id, i) => (
                  <button
                    key={id}
                    type="button"
                    className="tag-pill is-on"
                    style={{
                      borderColor: COLORS[i % COLORS.length],
                      color: COLORS[i % COLORS.length],
                    }}
                    title="Remove from chart"
                    onClick={() => toggle(id)}
                  >
                    {id} ✕
                  </button>
                ))}
              </div>
            )}
          </div>

          <p className="trends-label">
            Tags ({visible.length}/{tags.length})
          </p>
          <input
            className="trends-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter tags…"
          />
          <select
            className="trends-filter"
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
          >
            <option value="all">All models</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <div className="tag-groups">
            {grouped.map(([model, list]) => (
              <div key={model} className="tag-group">
                <p className="tag-group__name">{model}</p>
                <div className="tag-list">
                  {list.map((t) => {
                    const on = selected.includes(t.id);
                    const colorIdx = selected.indexOf(t.id);
                    return (
                      <button
                        key={t.historianTag}
                        type="button"
                        className={on ? "tag-row is-on" : "tag-row"}
                        style={
                          on
                            ? { borderColor: COLORS[colorIdx % COLORS.length] }
                            : undefined
                        }
                        disabled={!on && selected.length >= 6}
                        onClick={() => toggle(t.id)}
                      >
                        <span
                          className="tag-row__mark"
                          style={
                            on
                              ? {
                                  background: COLORS[colorIdx % COLORS.length],
                                  borderColor: COLORS[colorIdx % COLORS.length],
                                }
                              : undefined
                          }
                        />
                        <span className="tag-row__id">{t.id}</span>
                        {t.description && t.description !== t.id && (
                          <span className="tag-row__desc">{t.description}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </aside>

        <div className="trends-main">
          <div className="produce-panel">
            <label>
              Window
              <select
                value={custom ? "custom" : preset}
                onChange={(e) => {
                  if (e.target.value === "custom") {
                    setCustom(true);
                  } else {
                    setCustom(false);
                    setPreset(e.target.value);
                  }
                }}
              >
                {PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
                <option value="custom">Custom range…</option>
              </select>
            </label>
            {custom && (
              <>
                <label>
                  Start
                  <input
                    type="datetime-local"
                    value={start}
                    max={end}
                    onChange={(e) => setStart(e.target.value)}
                  />
                </label>
                <label>
                  End
                  <input
                    type="datetime-local"
                    value={end}
                    min={start}
                    onChange={(e) => setEnd(e.target.value)}
                  />
                </label>
              </>
            )}
            <div className="produce-actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={loading || !selected.length}
                onClick={() => void load()}
              >
                {loading ? "Loading…" : "Refresh"}
              </button>
            </div>
          </div>
          {status && (
            <p className={`status ${status.startsWith("LIVE") ? "ok" : "warn"}`}>
              {status}
            </p>
          )}
          <TrendChart
            series={chartSeries}
            emptyMessage={
              selected.length
                ? "No samples in this window"
                : "No tags selected"
            }
          />
          {window && <p className="window">{window}</p>}
          <div className="kpi-row">
            {series.map((s, i) => (
              <div key={s.id} className="kpi">
                <span style={{ color: COLORS[i % COLORS.length] }}>{s.id}</span>
                {s.description && s.description !== s.id && (
                  <em className="kpi-desc">{s.description}</em>
                )}
                <strong>
                  {s.avg != null ? s.avg.toFixed(2) : "—"} {s.units}
                </strong>
                <small>
                  n={s.count.toLocaleString()} · min {s.min?.toFixed(2) ?? "—"} ·
                  max {s.max?.toFixed(2) ?? "—"}
                </small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
