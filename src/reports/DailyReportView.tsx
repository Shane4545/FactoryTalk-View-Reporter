import type { DailyReport, Section } from "../data/chalkRiverDaily";
import { chalkRiverDaily, fmt } from "../data/chalkRiverDaily";
import "./DailyReport.css";

export type DailyReportData = DailyReport;

type Props = {
  data?: DailyReportData;
  startDate?: string;
  endDate?: string;
};

function SectionTable({ section }: { section: Section }) {
  if (section.kind === "runtime") {
    return (
      <section className="rpt-section">
        <h2>{section.title}</h2>
        <table>
          <thead>
            <tr>
              <th>Tag</th>
              <th>Description</th>
              <th className="num">Starts</th>
              <th className="num">Stops</th>
              <th className="num">Run duration (h)</th>
            </tr>
          </thead>
          <tbody>
            {section.rows.map((row) => (
              <tr key={row.tag}>
                <td className="tag">{row.tag}</td>
                <td>{row.description}</td>
                <td className="num">
                  {fmt(row.aggregate.starts ?? row.aggregate.min, 0)}
                </td>
                <td className="num">
                  {fmt(row.aggregate.stops ?? row.aggregate.max, 0)}
                </td>
                <td className="num">{fmt(row.aggregate.total, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    );
  }

  if (section.kind === "efficiency") {
    return (
      <section className="rpt-section">
        <h2>{section.title}</h2>
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th className="num">Value</th>
              <th>Units</th>
            </tr>
          </thead>
          <tbody>
            {section.rows.map((row) => (
              <tr key={row.tag}>
                <td>{row.description}</td>
                <td className="num strong">{fmt(row.aggregate.avg, 1)}</td>
                <td className="units">{row.aggregate.units}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    );
  }

  const lastCol = section.kind === "minmax_total" ? "Total" : "Average";

  return (
    <section className="rpt-section">
      <h2>{section.title}</h2>
      <table>
        <thead>
          <tr>
            <th>Tag</th>
            <th>Description</th>
            <th className="num">Min</th>
            <th>Units</th>
            <th className="num">Time of min</th>
            <th className="num">Max</th>
            <th>Units</th>
            <th className="num">Time of max</th>
            <th className="num">{lastCol}</th>
            <th>Units</th>
          </tr>
        </thead>
        <tbody>
          {section.rows.map((row) => {
            const a = row.aggregate;
            const last = section.kind === "minmax_total" ? a.total : a.avg;
            const lastUnits =
              section.kind === "minmax_total"
                ? a.totalUnits ?? a.units
                : a.units;
            return (
              <tr key={row.tag} className={row.emphasize ? "emph" : undefined}>
                <td className="tag">{row.tag}</td>
                <td>{row.description}</td>
                <td
                  className={
                    row.ctCell === "min" ? "num ct-input" : "num"
                  }
                >
                  {fmt(a.min, 2)}
                </td>
                <td className="units">{a.units}</td>
                <td className="num muted">{a.timeOfMin ?? "—"}</td>
                <td
                  className={
                    row.ctCell === "max" ? "num ct-input" : "num"
                  }
                >
                  {fmt(a.max, 2)}
                </td>
                <td className="units">{a.units}</td>
                <td className="num muted">{a.timeOfMax ?? "—"}</td>
                <td className="num strong">{fmt(last, 1)}</td>
                <td className="units">{lastUnits}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export function DailyReportView({ data, startDate, endDate }: Props) {
  const report: DailyReportData = {
    ...(data ?? chalkRiverDaily),
    startDate: startDate ?? data?.startDate ?? chalkRiverDaily.startDate,
    endDate: endDate ?? data?.endDate ?? chalkRiverDaily.endDate,
  };

  return (
    <article className="rpt">
      <header className="rpt-header">
        <div className="rpt-logo">
          <img src="/township-crest.png" alt="Town of Laurentian Hills" />
        </div>
        <div className="rpt-titles">
          <p className="rpt-kicker">{report.municipality}</p>
          <h1>{report.plant}</h1>
          <p className="rpt-sub">
            {report.subtitle}
            <span className="dot">·</span>
            {report.periodLabel}
          </p>
        </div>
        <dl className="rpt-period">
          <div>
            <dt>Start</dt>
            <dd>{report.startDate}</dd>
          </div>
          <div>
            <dt>End</dt>
            <dd>{report.endDate}</dd>
          </div>
        </dl>
      </header>

      {report.sections.map((section) => (
        <SectionTable key={section.id} section={section} />
      ))}

      <section className="rpt-section rpt-ct">
        <h2>Disinfection CT Summary</h2>
        <table className="ct-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th className="num">Giardia</th>
              <th className="num">Viruses</th>
            </tr>
          </thead>
          <tbody>
            {report.ct.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td className="num ct-cell">
                  {row.giardiaDisplay ?? fmt(row.giardia, 2)}
                </td>
                <td className="num ct-cell">
                  {row.virusesDisplay ?? fmt(row.viruses, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="ct-note">{report.ctNote}</p>
      </section>

      <footer className="rpt-footer">
        <div className="sig">
          <span>Operator signature</span>
        </div>
        <div className="sig">
          <span>Reviewed by (ORO)</span>
        </div>
        <div className="sig">
          <span>Date</span>
        </div>
        <div className="prepared">
          <small>Prepared with Ops Reporter</small>
          <img
            src="/capital-controls-logo.png"
            alt="Capital Controls — Electrical/Control Panels, PLC/SCADA Programming, Instrumentation Calibrations"
          />
        </div>
      </footer>
    </article>
  );
}
