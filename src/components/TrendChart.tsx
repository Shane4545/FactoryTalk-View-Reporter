import { useEffect, useId, useMemo, useRef, useState } from "react";
import "./TrendChart.css";

export type ChartPoint = { t: string; v: number };
export type ChartSeries = {
  id: string;
  description?: string;
  units?: string;
  color: string;
  points: ChartPoint[];
};

const W = 900;
const H = 340;
const PAD_L = 56;
const PAD_R = 16;
const PAD_T = 16;
const PAD_B = 30;
const INNER_W = W - PAD_L - PAD_R;
const INNER_H = H - PAD_T - PAD_B;
const MIN_SPAN_MS = 5_000;

type Pt = { e: number; t: string; v: number };

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function fmtEpoch(e: number, withSeconds = true): string {
  const d = new Date(e);
  const base = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  return withSeconds ? `${base}:${pad2(d.getSeconds())}` : base;
}

function fmtValue(v: number): string {
  const a = Math.abs(v);
  if (a >= 1000) return v.toFixed(0);
  if (a >= 100) return v.toFixed(1);
  return v.toFixed(2);
}

function nearestPt(pts: Pt[], target: number): Pt | null {
  if (!pts.length) return null;
  let lo = 0;
  let hi = pts.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (pts[mid].e < target) lo = mid;
    else hi = mid;
  }
  return target - pts[lo].e <= pts[hi].e - target ? pts[lo] : pts[hi];
}

export function TrendChart({
  series,
  emptyMessage = "No samples in this window",
}: {
  series: ChartSeries[];
  emptyMessage?: string;
}) {
  const clipId = useId();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);

  const parsed = useMemo(
    () =>
      series.map((s) => ({
        s,
        pts: s.points
          .map((p) => ({
            e: new Date(p.t.replace(" ", "T")).getTime(),
            t: p.t,
            v: p.v,
          }))
          .filter((p) => Number.isFinite(p.e))
          .sort((a, b) => a.e - b.e),
      })),
    [series],
  );

  const full = useMemo<[number, number] | null>(() => {
    let lo = Infinity;
    let hi = -Infinity;
    for (const { pts } of parsed) {
      if (pts.length) {
        lo = Math.min(lo, pts[0].e);
        hi = Math.max(hi, pts[pts.length - 1].e);
      }
    }
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
    return [lo, hi === lo ? lo + 1 : hi];
  }, [parsed]);

  const [zoom, setZoom] = useState<[number, number] | null>(null);
  const [hoverE, setHoverE] = useState<number | null>(null);
  const [pinE, setPinE] = useState<number | null>(null);
  const [dragSel, setDragSel] = useState<[number, number] | null>(null);

  // New data → reset view + pins
  const dataKey = useMemo(
    () =>
      parsed
        .map(({ s, pts }) => `${s.id}:${pts.length}:${pts[0]?.e ?? 0}:${pts[pts.length - 1]?.e ?? 0}`)
        .join("|"),
    [parsed],
  );
  useEffect(() => {
    setZoom(null);
    setPinE(null);
    setHoverE(null);
    setDragSel(null);
  }, [dataKey]);

  const domain: [number, number] = zoom ?? full ?? [0, 1];
  const [d0, d1] = domain;
  const dSpan = d1 - d0 || 1;
  const zoomed = zoom != null;

  const domainRef = useRef(domain);
  domainRef.current = domain;
  const fullRef = useRef(full);
  fullRef.current = full;

  // Visible slice per series (one extra point either side so lines run off-edge)
  const view = useMemo(() => {
    const vis = parsed.map(({ s, pts }) => {
      let i0 = pts.findIndex((p) => p.e >= d0);
      if (i0 < 0) i0 = pts.length;
      let i1 = i0;
      while (i1 < pts.length && pts[i1].e <= d1) i1++;
      const slice = pts.slice(Math.max(0, i0 - 1), Math.min(pts.length, i1 + 1));
      return { s, pts, slice };
    });
    let lo = Infinity;
    let hi = -Infinity;
    for (const { slice } of vis) {
      for (const p of slice) {
        if (p.v < lo) lo = p.v;
        if (p.v > hi) hi = p.v;
      }
    }
    if (!Number.isFinite(lo)) {
      lo = 0;
      hi = 1;
    }
    if (hi === lo) {
      hi = lo + 1;
    }
    const vSpan = hi - lo;
    const x = (e: number) => PAD_L + ((e - d0) / dSpan) * INNER_W;
    const y = (v: number) => PAD_T + (1 - (v - lo) / vSpan) * INNER_H;
    const paths = vis.map(({ s, slice }) => {
      const d =
        slice.length >= 2
          ? slice
              .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.e).toFixed(1)},${y(p.v).toFixed(1)}`)
              .join(" ")
          : "";
      return { s, d, dot: slice.length === 1 ? slice[0] : null };
    });
    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({
      y: PAD_T + f * INNER_H,
      v: lo + vSpan * (1 - f),
    }));
    return { vis, paths, yTicks, x, y };
  }, [parsed, d0, d1, dSpan]);

  // Wheel zoom needs a non-passive native listener (React's is passive)
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (ev: WheelEvent) => {
      ev.preventDefault();
      const f = fullRef.current;
      if (!f) return;
      const [a, b] = domainRef.current;
      const rect = svg.getBoundingClientRect();
      const xSvg = ((ev.clientX - rect.left) / rect.width) * W;
      const frac = Math.min(1, Math.max(0, (xSvg - PAD_L) / INNER_W));
      const at = a + frac * (b - a);
      const factor = ev.deltaY < 0 ? 0.8 : 1.25;
      let na = at - (at - a) * factor;
      let nb = at + (b - at) * factor;
      if (nb - na >= f[1] - f[0]) {
        setZoom(null);
        return;
      }
      if (nb - na < MIN_SPAN_MS) return;
      if (na < f[0]) {
        nb += f[0] - na;
        na = f[0];
      }
      if (nb > f[1]) {
        na -= nb - f[1];
        nb = f[1];
      }
      setZoom([Math.max(f[0], na), Math.min(f[1], nb)]);
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
    // dataKey: the svg only exists once there is data, so re-attach on data change
  }, [dataKey]);

  if (!full || !parsed.some(({ pts }) => pts.length > 0)) {
    return <div className="chart-empty">{emptyMessage}</div>;
  }

  const epochAt = (clientX: number): number => {
    const svg = svgRef.current;
    if (!svg) return d0;
    const rect = svg.getBoundingClientRect();
    const xSvg = ((clientX - rect.left) / rect.width) * W;
    const frac = Math.min(1, Math.max(0, (xSvg - PAD_L) / INNER_W));
    return d0 + frac * dSpan;
  };

  const onPointerDown = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (ev.button !== 0) return;
    try {
      ev.currentTarget.setPointerCapture(ev.pointerId);
    } catch {
      // capture is best-effort (some pointer types don't support it)
    }
    const e = epochAt(ev.clientX);
    setDragSel([e, e]);
  };

  const onPointerMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    const e = epochAt(ev.clientX);
    if (dragSel) setDragSel([dragSel[0], e]);
    setHoverE(e);
  };

  const onPointerUp = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (!dragSel) return;
    const [a, b] = dragSel;
    setDragSel(null);
    const pxPerMs = INNER_W / dSpan;
    if (Math.abs(b - a) * pxPerMs > 6) {
      const lo = Math.min(a, b);
      const hi = Math.max(a, b);
      if (hi - lo >= MIN_SPAN_MS) setZoom([lo, hi]);
    } else {
      // Plain click → pin/unpin the value cursor
      const e = epochAt(ev.clientX);
      setPinE((prev) =>
        prev != null && Math.abs(prev - e) * pxPerMs < 8 ? null : e,
      );
    }
  };

  const zoomBy = (factor: number) => {
    const mid = (d0 + d1) / 2;
    let na = mid - (dSpan / 2) * factor;
    let nb = mid + (dSpan / 2) * factor;
    if (nb - na >= full[1] - full[0]) {
      setZoom(null);
      return;
    }
    if (nb - na < MIN_SPAN_MS) return;
    if (na < full[0]) {
      nb += full[0] - na;
      na = full[0];
    }
    if (nb > full[1]) {
      na -= nb - full[1];
      nb = full[1];
    }
    setZoom([na, nb]);
  };

  const panTo = (startFrac: number) => {
    const fSpan = full[1] - full[0];
    const winFrac = dSpan / fSpan;
    const f = Math.min(1 - winFrac, Math.max(0, startFrac));
    const na = full[0] + f * fSpan;
    setZoom([na, na + dSpan]);
  };

  const onTrackPointerDown = (ev: React.PointerEvent<HTMLDivElement>) => {
    const track = trackRef.current;
    if (!track) return;
    try {
      ev.currentTarget.setPointerCapture(ev.pointerId);
    } catch {
      // capture is best-effort
    }
    const move = (clientX: number) => {
      const rect = track.getBoundingClientRect();
      const winFrac = dSpan / (full[1] - full[0]);
      const frac = (clientX - rect.left) / rect.width - winFrac / 2;
      panTo(frac);
    };
    move(ev.clientX);
    const onMove = (e: PointerEvent) => move(e.clientX);
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  // Crosshair readout (pinned takes priority over hover)
  const cursorE =
    pinE != null && pinE >= d0 && pinE <= d1
      ? pinE
      : hoverE != null && hoverE >= d0 && hoverE <= d1
        ? hoverE
        : null;
  const readout =
    cursorE != null
      ? {
          x: view.x(cursorE),
          rows: view.vis.map(({ s, pts }) => {
            const p = nearestPt(pts, cursorE);
            return { s, p };
          }),
        }
      : null;
  const readoutTime =
    readout && readout.rows.length
      ? (() => {
          const withPts = readout.rows.filter((r) => r.p);
          if (!withPts.length) return fmtEpoch(cursorE!);
          // Show the sample time of the series nearest to the cursor
          const best = withPts.reduce((a, b) =>
            Math.abs(a.p!.e - cursorE!) <= Math.abs(b.p!.e - cursorE!) ? a : b,
          );
          return best.p!.t;
        })()
      : "";

  const fSpan = full[1] - full[0];
  const thumbLeft = ((d0 - full[0]) / fSpan) * 100;
  const thumbW = Math.max(2, (dSpan / fSpan) * 100);

  const selX =
    dragSel && Math.abs(dragSel[1] - dragSel[0]) * (INNER_W / dSpan) > 6
      ? ([view.x(Math.min(...dragSel)), view.x(Math.max(...dragSel))] as const)
      : null;

  return (
    <div className="chart-wrap trend-chart">
      <div className="trend-chart__bar">
        <span className="trend-chart__range">
          {fmtEpoch(d0, false)} → {fmtEpoch(d1, false)}
          {zoomed ? " (zoomed)" : ""}
        </span>
        <span className="trend-chart__hint">
          drag = zoom · wheel = zoom · click = pin values
        </span>
        <span className="trend-chart__btns">
          <button type="button" onClick={() => zoomBy(0.5)} title="Zoom in">
            +
          </button>
          <button type="button" onClick={() => zoomBy(2)} title="Zoom out">
            −
          </button>
          <button
            type="button"
            disabled={!zoomed}
            onClick={() => setZoom(null)}
            title="Show everything"
          >
            Reset
          </button>
        </span>
      </div>

      <div className="trend-chart__plot">
        <svg
          ref={svgRef}
          className="chart chart--tall"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => {
            setHoverE(null);
            setDragSel(null);
          }}
          onDoubleClick={() => setZoom(null)}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={PAD_L} y={PAD_T} width={INNER_W} height={INNER_H} />
            </clipPath>
          </defs>
          <rect x="0" y="0" width={W} height={H} fill="#f8fafc" rx="10" />
          {view.yTicks.map((t) => (
            <g key={t.y}>
              <line
                x1={PAD_L}
                x2={W - PAD_R}
                y1={t.y}
                y2={t.y}
                stroke="#e2e8f0"
                strokeWidth="1"
              />
              <text
                x={PAD_L - 8}
                y={t.y + 4}
                textAnchor="end"
                fontSize="11"
                fill="#64748b"
              >
                {fmtValue(t.v)}
              </text>
            </g>
          ))}
          <g clipPath={`url(#${clipId})`}>
            {view.paths.map(({ s, d }) =>
              d ? (
                <path
                  key={s.id}
                  d={d}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ) : null,
            )}
            {view.paths.map(({ s, dot }) =>
              dot ? (
                <circle
                  key={`dot-${s.id}`}
                  cx={view.x(dot.e)}
                  cy={view.y(dot.v)}
                  r="3.5"
                  fill={s.color}
                />
              ) : null,
            )}
            {selX && (
              <rect
                x={selX[0]}
                y={PAD_T}
                width={selX[1] - selX[0]}
                height={INNER_H}
                fill="#0e7490"
                opacity="0.12"
              />
            )}
            {readout && (
              <g>
                <line
                  x1={readout.x}
                  x2={readout.x}
                  y1={PAD_T}
                  y2={PAD_T + INNER_H}
                  stroke={pinE != null ? "#0f172a" : "#64748b"}
                  strokeWidth="1.2"
                  strokeDasharray={pinE != null ? undefined : "4 3"}
                />
                {readout.rows.map(({ s, p }) =>
                  p ? (
                    <circle
                      key={`c-${s.id}`}
                      cx={view.x(p.e)}
                      cy={view.y(p.v)}
                      r="4"
                      fill={s.color}
                      stroke="#fff"
                      strokeWidth="1.5"
                    />
                  ) : null,
                )}
              </g>
            )}
          </g>
          <text x={PAD_L} y={H - 10} fontSize="11" fill="#64748b">
            {fmtEpoch(d0, false)}
          </text>
          <text
            x={W - PAD_R}
            y={H - 10}
            textAnchor="end"
            fontSize="11"
            fill="#64748b"
          >
            {fmtEpoch(d1, false)}
          </text>
        </svg>

        {readout && (
          <div
            className={`trend-tip${pinE != null ? " is-pinned" : ""}`}
            style={
              readout.x < W / 2
                ? { left: `${((readout.x + 14) / W) * 100}%` }
                : { right: `${((W - readout.x + 14) / W) * 100}%` }
            }
          >
            <div className="trend-tip__time">
              {readoutTime}
              {pinE != null && (
                <button
                  type="button"
                  className="trend-tip__close"
                  onClick={() => setPinE(null)}
                  title="Unpin"
                >
                  ×
                </button>
              )}
            </div>
            {readout.rows.map(({ s, p }) => (
              <div key={s.id} className="trend-tip__row">
                <span className="trend-tip__dot" style={{ background: s.color }} />
                <span className="trend-tip__tag">{s.id}</span>
                <span className="trend-tip__val">
                  {p ? `${fmtValue(p.v)}${s.units ? ` ${s.units}` : ""}` : "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {zoomed && (
        <div
          className="trend-scroll"
          ref={trackRef}
          onPointerDown={onTrackPointerDown}
          title="Drag to scroll through time"
        >
          <div
            className="trend-scroll__thumb"
            style={{ left: `${thumbLeft}%`, width: `${thumbW}%` }}
          />
        </div>
      )}

      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.id} style={{ color: s.color }}>
            ● {s.id}
            {s.description && s.description !== s.id ? ` — ${s.description}` : ""}
            {s.units ? ` (${s.units})` : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
