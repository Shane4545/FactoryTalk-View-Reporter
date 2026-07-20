import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API } from "../api";
import "./ConnectDistribute.css";
import "./HelpPage.css";

type HelpSection = {
  id: string;
  title: string;
  intro?: string;
  steps: string[];
  tips?: string[];
};

type HelpPayload = {
  title?: string;
  lede?: string;
  sections?: HelpSection[];
};

export function HelpPage() {
  const [title, setTitle] = useState("Plant Reporter — operator guide");
  const [lede, setLede] = useState(
    "Connect DLGLOG, map tags, Activate, then produce reports.",
  );
  const [sections, setSections] = useState<HelpSection[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/help`);
        if (!res.ok) {
          setStatus("Help guide could not load from the server.");
          return;
        }
        const data = (await res.json()) as HelpPayload;
        setTitle(data.title || "Plant Reporter — operator guide");
        if (data.lede) setLede(data.lede);
        setSections(data.sections || []);
        setStatus(null);
      } catch {
        setStatus("API offline — start Plant Reporter server on :8787");
      }
    })();
  }, []);

  return (
    <div className="page help-page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Help</p>
          <h1>{title}</h1>
          <p className="lede">{lede}</p>
        </div>
      </header>

      {status && <p className="status warn">{status}</p>}

      {sections.length > 0 && (
        <nav className="help-toc cfg-card" aria-label="Help topics">
          <h2>On this page</h2>
          <ul>
            {sections.map((s) => (
              <li key={s.id}>
                <a href={`#help-${s.id}`}>{s.title}</a>
              </li>
            ))}
          </ul>
        </nav>
      )}

      {sections.map((s) => (
        <section key={s.id} id={`help-${s.id}`} className="cfg-card help-section">
          <h2>{s.title}</h2>
          {s.intro ? <p className="help-intro">{s.intro}</p> : null}
          {s.steps?.length ? (
            <ol className="help-steps">
              {s.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          ) : null}
          {s.tips?.length ? (
            <div className="help-tips">
              <h3>Tips</h3>
              <ul>
                {s.tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ))}

      <p className="help-footer">
        Need a page?{" "}
        <Link to="/connect">Connect</Link>
        {" · "}
        <Link to="/setup">Setup</Link>
        {" · "}
        <Link to="/reports/daily">Daily</Link>
        {" · "}
        <Link to="/insights">Insights</Link>
        {" · "}
        <Link to="/reports/trends">Trends</Link>
        {" · "}
        <Link to="/distribute">Archive</Link>
      </p>
    </div>
  );
}
