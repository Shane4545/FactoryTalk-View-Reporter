import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { API } from "../api";
import "./AppShell.css";

const nav = [
  { to: "/", label: "Home", end: true },
  { to: "/insights", label: "Insights" },
  { to: "/reports", label: "Reports" },
  { to: "/explore", label: "Explore" },
  { to: "/connect", label: "Connect" },
  { to: "/setup", label: "Setup" },
  { to: "/distribute", label: "Archive" },
  { to: "/log", label: "Log" },
  { to: "/help", label: "Help" },
];

export function AppShell() {
  const [plantName, setPlantName] = useState("Plant");
  const [muni, setMuni] = useState("");
  const [ok, setOk] = useState(false);
  const [logoKey, setLogoKey] = useState(0);
  // Collapsible nav — more horizontal room for trends/reports on SCADA panels
  const [navOpen, setNavOpen] = useState(() => {
    try {
      return localStorage.getItem("shell-nav-open") !== "0";
    } catch {
      return true;
    }
  });
  const toggleNav = () => {
    setNavOpen((prev) => {
      try {
        localStorage.setItem("shell-nav-open", prev ? "0" : "1");
      } catch {
        /* storage unavailable */
      }
      return !prev;
    });
  };

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/plant`);
      const data = await res.json();
      setPlantName(data.plant?.name || "Plant");
      setMuni(data.plant?.municipality || "");
      setOk(!!data.ok);
      setLogoKey((k) => k + 1);
    } catch {
      setOk(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onBrand = () => void refresh();
    window.addEventListener("plant-branding-changed", onBrand);
    window.addEventListener("focus", onBrand);
    return () => {
      window.removeEventListener("plant-branding-changed", onBrand);
      window.removeEventListener("focus", onBrand);
    };
  }, [refresh]);

  return (
    <div className={navOpen ? "shell" : "shell shell--nav-collapsed"}>
      {!navOpen && (
        <button
          type="button"
          className="shell__rail"
          onClick={toggleNav}
          title="Show menu"
          aria-label="Show menu"
        >
          <span className="shell__rail-chevron">»</span>
          <span className="shell__rail-text">Menu</span>
        </button>
      )}
      <aside className="shell__aside" hidden={!navOpen}>
        <button
          type="button"
          className="shell__collapse"
          onClick={toggleNav}
          title="Hide menu — full-width view"
        >
          « Hide menu
        </button>
        <Link to="/" className="shell__brand">
          <img
            className="shell__crest"
            key={logoKey}
            src={`${API}/api/branding/logo?t=${logoKey}`}
            alt={muni || plantName}
          />
          <div>
            <strong>Plant Reporter</strong>
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
      <Link
        to="/help"
        className="shell__help-fab"
        title="Operator help — how to use Plant Reporter"
        aria-label="Open help"
      >
        ?
      </Link>
    </div>
  );
}
