/**
 * Static demo API for GitHub Pages — lasting free URL, no backend.
 *
 * Default = blank (unloaded) plant so co-workers see Connect / Setup empty.
 * Click “Load Chalk River sample” → fixtures under demo-api/chalk/.
 * “Reset to blank” → back to unloaded.
 */
const DEMO =
  (import.meta as { env?: { VITE_STATIC_DEMO?: string } }).env?.VITE_STATIC_DEMO ===
    "1" ||
  (typeof location !== "undefined" &&
    /\.github\.io$/i.test(location.hostname));

const MODE_KEY = "plant-reporter-demo-mode";

export type DemoMode = "blank" | "chalk";

export function getDemoMode(): DemoMode {
  if (typeof localStorage === "undefined") return "blank";
  return localStorage.getItem(MODE_KEY) === "chalk" ? "chalk" : "blank";
}

export function setDemoMode(mode: DemoMode): void {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(MODE_KEY, mode);
}

function baseUrl(): string {
  const b = (import.meta as { env?: { BASE_URL?: string } }).env?.BASE_URL || "/";
  return b.endsWith("/") ? b : `${b}/`;
}

function fixture(name: string): string {
  const mode = getDemoMode();
  const folder = mode === "chalk" ? "chalk/" : "blank/";
  return `${baseUrl()}demo-api/${folder}${name}`;
}

function pickDate(url: string, fallback: string): string {
  const m = /[?&]date=(\d{4}-\d{2}-\d{2})/.exec(url);
  return m?.[1] || fallback;
}

function mapApi(url: string, method: string): string | null {
  const u = url.replace(/^https?:\/\/[^/]+/i, "");
  const path = u.split("?")[0] || "";
  const m = method.toUpperCase();
  const chalk = getDemoMode() === "chalk";

  // Mutations: in blank mode, Load sample is client-side only (Connect UI).
  // Other POSTs return current fixtures (read-only demo).
  if (m !== "GET" && m !== "HEAD") {
    if (path.includes("/api/report-prefs")) return fixture("report-prefs.json");
    if (path.includes("/api/archive")) return fixture("archive.json");
    if (path.includes("/api/setup")) return fixture("setup.json");
    if (path.includes("/api/config")) return fixture("config.json");
    if (path.includes("/api/outputs")) return fixture("outputs.json");
    if (path.includes("/api/schedule")) return fixture("health.json");
    return fixture("health.json");
  }

  if (path.endsWith("/api/health")) return fixture("health.json");
  if (path.endsWith("/api/plant")) return fixture("plant.json");
  if (path.endsWith("/api/dates")) return fixture("dates.json");
  if (path.endsWith("/api/tags")) return fixture("tags.json");
  if (path.endsWith("/api/config")) return fixture("config.json");
  if (path.endsWith("/api/setup")) return fixture("setup.json");
  if (path.endsWith("/api/outputs")) return fixture("outputs.json");
  if (path.includes("/api/outputs/files")) return fixture("archive.json");
  if (path.endsWith("/api/archive") || path.includes("/api/archive?"))
    return fixture("archive.json");
  if (path.includes("/api/archive/lookup")) {
    if (!chalk) return fixture("archive-lookup.json");
    return fixture("archive-lookup-daily-2026-06-14.json");
  }
  if (path.includes("/api/report-prefs")) return fixture("report-prefs.json");

  if (path.includes("/api/reports/daily")) {
    if (!chalk) return fixture("reports-blocked.json");
    const d = pickDate(u, "2026-06-14");
    const known = ["2026-06-13", "2026-06-14", "2026-06-15"];
    const use = known.includes(d) ? d : "2026-06-14";
    return fixture(`reports-daily-${use}.json`);
  }
  if (path.includes("/api/reports/monthly")) {
    if (!chalk) return fixture("reports-blocked.json");
    return fixture("reports-monthly-2026-06.json");
  }
  if (path.includes("/api/insights")) {
    if (!chalk) return fixture("insights-empty.json");
    const d = pickDate(u, "2026-06-14");
    const use = d === "2026-06-13" ? "2026-06-13" : "2026-06-14";
    return fixture(`insights-${use}.json`);
  }
  if (path.includes("/api/tags/") && path.includes("/series")) {
    if (!chalk) return null;
    if (/FIT101/i.test(path)) return fixture("series-FIT101-1d.json");
    return null;
  }
  if (path.includes("/api/setup/discover")) return fixture("tags.json");
  if (path.includes("/api/schedule")) return fixture("health.json");
  if (path.includes("/api/printers")) return fixture("health.json");
  if (path.includes("/api/help")) return null; // fall through — no fixture

  return null;
}

export function installDemoApi(): boolean {
  if (!DEMO || typeof window === "undefined") return false;
  const orig = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    if (!url.includes("/api/")) return orig(input, init);

    const method = (init?.method || "GET").toUpperCase();
    const mapped = mapApi(url, method);

    if (mapped) {
      const res = await orig(mapped, { method: "GET", cache: "no-store" });
      if (!res.ok) {
        return new Response(
          JSON.stringify({
            ok: false,
            demo: true,
            error: "Demo fixture missing",
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }
      return res;
    }

    if (url.includes("/series")) {
      return new Response(
        JSON.stringify({
          tag: "demo",
          count: 0,
          points: [],
          demo: true,
          note:
            getDemoMode() === "blank"
              ? "Blank demo — Load Chalk River sample on Connect to see trends"
              : "Static demo — only FIT101 1d series is bundled",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    return new Response(
      JSON.stringify({
        ok: false,
        demo: true,
        error:
          getDemoMode() === "blank"
            ? "Blank demo — open Connect and Load Chalk River sample, or download the SCADA kit for a real plant."
            : "This control needs the live / SCADA app. Static chalk sample covers Home, Insights, Daily/Monthly, and FIT101 trends.",
      }),
      { status: 501, headers: { "Content-Type": "application/json" } },
    );
  };

  return true;
}

export function isStaticDemo(): boolean {
  return DEMO;
}
