import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { API } from "../api";
import { TrendChart } from "../components/TrendChart";
import "./ExplorePage.css";

type TagInfo = {
  id: string;
  historianTag: string;
  description: string;
  units: string;
  model: string;
};

type Series = {
  id: string;
  tag: string;
  description: string;
  units: string;
  count: number;
  min: number | null;
  max: number | null;
  avg: number | null;
  timeOfMin?: string;
  timeOfMax?: string;
  start: string;
  end: string;
  preset?: string;
  points: { t: string; v: number }[];
};

const PRESETS = [
  { id: "1h", label: "1 hour" },
  { id: "6h", label: "6 hours" },
  { id: "1d", label: "1 day" },
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
  { id: "1y", label: "1 year" },
];

export function ExplorePage() {
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [tag, setTag] = useState("FIT101");
  const [preset, setPreset] = useState("1d");
  const [custom, setCustom] = useState(false);
  const [start, setStart] = useState("2026-06-13T00:00");
  const [end, setEnd] = useState("2026-06-13T23:59");
  const [series, setSeries] = useState<Series | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/tags`);
        const data = await res.json();
        setTags(data.tags ?? []);
      } catch {
        setStatus("API offline — start server on :8787");
      }
    })();
  }, []);

  const loadSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setStatus(null);
    try {
      const qs = custom
        ? `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
        : `preset=${preset}`;
      const res = await fetch(
        `${API}/api/tags/${encodeURIComponent(tag)}/series?${qs}&max_points=1500`,
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const data = (await res.json()) as Series;
      if (seq !== loadSeq.current) return; // a newer request superseded this one
      setSeries(data);
      setStatus(
        `LIVE · ${data.count.toLocaleString()} samples · ${data.start} → ${data.end} · XLReporter=NO`,
      );
    } catch (e) {
      if (seq !== loadSeq.current) return;
      setSeries(null);
      setStatus(e instanceof Error ? e.message : "error");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [tag, preset, custom, start, end]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = tags.find((t) => t.id === tag);

  return (
    <div className="page explore">
      <header className="page__head">
        <div>
          <p className="eyebrow">
            <Link to="/">Home</Link> / Explore
          </p>
          <h1>Tag explorer</h1>
          <p className="lede">
            Ask what any tag did — last hour, day, month, year, or any custom
            range. Built for operators, not Excel.
          </p>
        </div>
      </header>

      <div className="explore-panel">
        <label>
          Tag
          <select value={tag} onChange={(e) => setTag(e.target.value)}>
            {tags.map((t) => (
              <option key={t.historianTag} value={t.id}>
                {t.id} — {t.description}
              </option>
            ))}
          </select>
        </label>

        <div className="preset-row">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={
                !custom && preset === p.id ? "chip is-active" : "chip"
              }
              onClick={() => {
                setCustom(false);
                setPreset(p.id);
              }}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            className={custom ? "chip is-active" : "chip"}
            onClick={() => setCustom(true)}
          >
            Custom
          </button>
        </div>

        {custom && (
          <div className="custom-row">
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
          </div>
        )}

        <button
          type="button"
          className="btn btn-primary"
          disabled={loading}
          onClick={() => void load()}
        >
          {loading ? "Loading…" : "Show trend"}
        </button>
        {status && <p className="status ok">{status}</p>}
      </div>

      {series && (
        <section className="explore-result">
          <div className="kpi-row">
            <div className="kpi">
              <span>Tag</span>
              <strong>
                {series.id}
                <small>{selected?.units || series.units}</small>
              </strong>
            </div>
            <div className="kpi">
              <span>Min</span>
              <strong>
                {series.min?.toFixed(3) ?? "—"}
                <small>{series.timeOfMin}</small>
              </strong>
            </div>
            <div className="kpi">
              <span>Max</span>
              <strong>
                {series.max?.toFixed(3) ?? "—"}
                <small>{series.timeOfMax}</small>
              </strong>
            </div>
            <div className="kpi">
              <span>Average</span>
              <strong>{series.avg?.toFixed(3) ?? "—"}</strong>
            </div>
            <div className="kpi">
              <span>Samples</span>
              <strong>{series.count.toLocaleString()}</strong>
            </div>
          </div>
          <h2>{series.description}</h2>
          <TrendChart
            series={[
              {
                id: series.id,
                description: series.description,
                units: selected?.units || series.units,
                color: "#0e7490",
                points: series.points,
              },
            ]}
          />
          <p className="window">
            Window: {series.start} → {series.end}
          </p>
        </section>
      )}
    </div>
  );
}
