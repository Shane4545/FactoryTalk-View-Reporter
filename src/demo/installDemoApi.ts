/**
 * Static demo API for GitHub Pages — lasting free URL, no backend.
 * Maps /api/* fetches to JSON fixtures under public/demo-api/.
 */
const DEMO =
  (import.meta as { env?: { VITE_STATIC_DEMO?: string } }).env?.VITE_STATIC_DEMO ===
    "1" ||
  (typeof location !== "undefined" &&
    /\.github\.io$/i.test(location.hostname));

function baseUrl(): string {
  const b = (import.meta as { env?: { BASE_URL?: string } }).env?.BASE_URL || "/";
  return b.endsWith("/") ? b : `${b}/`;
}

function fixture(name: string): string {
  return `${baseUrl()}demo-api/${name}`;
}

function pickDate(url: string, fallback: string): string {
  const m = /[?&]date=(\d{4}-\d{2}-\d{2})/.exec(url);
  return m?.[1] || fallback;
}

function mapApi(url: string, method: string): string | null {
  const u = url.replace(/^https?:\/\/[^/]+/i, "");
  const path = u.split("?")[0] || "";
  const m = method.toUpperCase();

  // Mutations are no-ops in the static demo
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
  if (path.includes("/api/archive/lookup"))
    return fixture("archive-lookup-daily-2026-06-14.json");
  if (path.includes("/api/report-prefs")) return fixture("report-prefs.json");

  if (path.includes("/api/reports/daily")) {
    const d = pickDate(u, "2026-06-14");
    const known = ["2026-06-13", "2026-06-14", "2026-06-15"];
    const use = known.includes(d) ? d : "2026-06-14";
    return fixture(`reports-daily-${use}.json`);
  }
  if (path.includes("/api/reports/monthly"))
    return fixture("reports-monthly-2026-06.json");
  if (path.includes("/api/insights")) {
    const d = pickDate(u, "2026-06-14");
    const use = d === "2026-06-13" ? "2026-06-13" : "2026-06-14";
    return fixture(`insights-${use}.json`);
  }
  if (path.includes("/api/tags/") && path.includes("/series")) {
    // One real series baked in; others get an empty shell
    if (/FIT101/i.test(path)) return fixture("series-FIT101-1d.json");
    return null; // handled as synthetic empty below
  }
  if (path.includes("/api/setup/discover")) return fixture("tags.json");
  if (path.includes("/api/schedule")) return fixture("health.json");
  if (path.includes("/api/printers")) return fixture("health.json");

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
      // For POST/PUT, still return the GET fixture body (read-only demo)
      return res;
    }

    // Empty series for tags we didn't bake
    if (url.includes("/series")) {
      return new Response(
        JSON.stringify({
          tag: "demo",
          count: 0,
          points: [],
          demo: true,
          note: "Static GitHub Pages demo — only FIT101 1d series is bundled",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    return new Response(
      JSON.stringify({
        ok: false,
        demo: true,
        error:
          "This control needs the live app. Static demo covers Home, Insights, Daily/Monthly, Explore tags, and FIT101 trends.",
      }),
      { status: 501, headers: { "Content-Type": "application/json" } },
    );
  };

  return true;
}

export function isStaticDemo(): boolean {
  return DEMO;
}
