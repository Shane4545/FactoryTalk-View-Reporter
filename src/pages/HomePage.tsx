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

const shortcuts = [
  {
    to: "/reports/daily",
    title: "Daily report",
    body: "Produce yesterday or any calendar day from DLGLOG.",
  },
  {
    to: "/insights",
    title: "Insights",
    body: "Traffic-light plant health — transmitters and CT margin.",
  },
  {
    to: "/reports/trends",
    title: "Trends",
    body: "Overlay up to six tags across any time window.",
  },
  {
    to: "/setup",
    title: "Setup",
    body: "Map tags, sections, Insight roles, and CT geometry.",
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
        <p className="eyebrow">
          Plant Reporter{plant?.version ? ` · v${plant.version}` : ""}
        </p>
        <h1>
          Plant reporting
          <br />
          from your DLGLOG
        </h1>
        <p className="lede">
          {name}
          {plant?.ok
            ? ` · ${plant.date_count} days on disk (${plant.first_date} → ${plant.last_date})`
            : " · unloaded — Connect a DLGLOG to go live"}
          . Daily and monthly ops reports, CT, trends, and
          archives — browser only.
        </p>
        <div className="hero-actions">
          <Link className="btn btn-primary" to="/connect">
            Connect DLGLOG
          </Link>
          <Link className="btn btn-secondary" to="/reports/daily">
            Daily report
          </Link>
          <Link className="btn btn-secondary" to="/explore">
            Explore tags
          </Link>
        </div>
      </section>

      <section className="phases">
        {shortcuts.map((p) => (
          <Link key={p.to} to={p.to} className="phase-card">
            <h2>{p.title}</h2>
            <p>{p.body}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
