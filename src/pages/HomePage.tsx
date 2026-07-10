import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API } from "../api";
import "./HomePage.css";

type PlantInfo = {
  ok?: boolean;
  plant?: { name?: string; municipality?: string };
  date_count?: number;
  first_date?: string;
  last_date?: string;
  version?: string;
};

const phases = [
  {
    to: "/insights",
    title: "Insights",
    body: "Traffic-light plant health — stuck transmitters, motor duty, CT margin.",
  },
  {
    to: "/connect",
    title: "Connect",
    body: "FactoryTalk DLGLOG status — models, dates, live path.",
  },
  {
    to: "/setup",
    title: "Setup",
    body: "Map your plant's tags — sections, motors, roles, CT geometry.",
  },
  {
    to: "/reports",
    title: "Reports",
    body: "Daily, Monthly, Custom, Trends — Preview, Print PDF, Archive.",
  },
  {
    to: "/explore",
    title: "Explore",
    body: "Any tag, any window — 1 hour to 1 year.",
  },
  {
    to: "/distribute",
    title: "Archive",
    body: "Saved HTML/JSON reports on disk for operators and auditors.",
  },
];

export function HomePage() {
  const [plant, setPlant] = useState<PlantInfo | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/plant`);
        if (res.ok) setPlant(await res.json());
      } catch {
        /* offline */
      }
    })();
  }, []);

  const name = plant?.plant?.name ?? "Water Treatment Plant";

  return (
    <div className="home">
      <section className="hero">
        <p className="eyebrow">Ops Reporter {plant?.version ? `· v${plant.version}` : ""}</p>
        <h1>
          Plant reporting
          <br />
          without XLReporter
        </h1>
        <p className="lede">
          {name}
          {plant?.ok
            ? ` · ${plant.date_count} days on disk (${plant.first_date} → ${plant.last_date})`
            : " · connect DLGLOG to go live"}
          . CT, motor starts/stops, trends, and archives — browser only.
        </p>
        <div className="hero-actions">
          <Link className="btn btn-primary" to="/reports/daily">
            Daily report
          </Link>
          <Link className="btn btn-secondary" to="/explore">
            Explore tags
          </Link>
          <Link className="btn btn-secondary" to="/reports/trends">
            Trends
          </Link>
        </div>
      </section>

      <section className="phases">
        {phases.map((p) => (
          <Link key={p.to} to={p.to} className="phase-card">
            <h2>{p.title}</h2>
            <p>{p.body}</p>
          </Link>
        ))}
      </section>

      <section className="parity">
        <h2>Ready for plant use</h2>
        <ul>
          <li>
            <strong>Live:</strong> Daily / Monthly / Custom, CT, starts/stops/hours,
            Explore, Trends, Print PDF, Save archive
          </li>
          <li>
            <strong>Start:</strong> double-click{" "}
            <code>START_OPS_REPORTER.bat</code> → open{" "}
            <code>http://127.0.0.1:8787</code>
          </li>
          <li>
            <strong>Any FT View SE plant:</strong> point Connect at the DLGLOG,
            map tags in Setup — no XLReporter required
          </li>
        </ul>
      </section>
    </div>
  );
}
