import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { API } from "../api";
import "./AppShell.css";

const nav = [
  { to: "/", label: "Home", end: true },
  { to: "/insights", label: "Insights" },
  { to: "/explore", label: "Explore" },
  { to: "/reports", label: "Reports" },
  { to: "/connect", label: "Connect" },
  { to: "/setup", label: "Setup" },
  { to: "/design", label: "Design" },
  { to: "/distribute", label: "Distribute" },
];

export function AppShell() {
  const [plantName, setPlantName] = useState("Plant");
  const [muni, setMuni] = useState("");
  const [ok, setOk] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/plant`);
        const data = await res.json();
        setPlantName(data.plant?.name || "Plant");
        setMuni(data.plant?.municipality || "");
        setOk(!!data.ok);
      } catch {
        setOk(false);
      }
    })();
  }, []);

  return (
    <div className="shell">
      <aside className="shell__aside">
        <Link to="/" className="shell__brand">
          <img
            className="shell__crest"
            src="/township-crest.png"
            alt={muni || plantName}
          />
          <div>
            <strong>Ops Reporter</strong>
            <small>{muni || plantName}</small>
          </div>
        </Link>
        <nav className="shell__nav">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? "shell__link is-active" : "shell__link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="shell__project">
          <span className="shell__pill">{ok ? "Live" : "Setup"}</span>
          <p>{plantName}</p>
          <small>{muni || "Set DLGLOG in Connect"}</small>
        </div>
        <a
          className="shell__vendor"
          href="https://capitalcontrols.ca"
          target="_blank"
          rel="noreferrer"
          title="Electrical/Control Panels · PLC/SCADA Programming · Instrumentation Calibrations"
        >
          <small>Created by</small>
          <img src="/capital-controls-logo.png" alt="Capital Controls" />
          <small>Sales &amp; Service</small>
        </a>
      </aside>
      <main className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}
