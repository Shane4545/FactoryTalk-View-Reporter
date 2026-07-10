/**
 * API base URL.
 * - Production (built UI on :8787): same origin ("").
 * - Vite dev (:5173): call API directly so long series loads don't 502 via proxy.
 * Override with VITE_API_BASE if needed.
 */
const envBase = (import.meta as { env?: { VITE_API_BASE?: string; DEV?: boolean } })
  .env;

export const API =
  envBase?.VITE_API_BASE ??
  (envBase?.DEV ? "http://127.0.0.1:8787" : "");
