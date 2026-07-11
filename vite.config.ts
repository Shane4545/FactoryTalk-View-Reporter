import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  // Lasting free URL: https://shane4545.github.io/FactoryTalk-View-Reporter/
  base: mode === "pages" ? "/FactoryTalk-View-Reporter/" : "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8787",
        changeOrigin: true,
        // Trends/Explore/Monthly can take minutes on cold DLGLOG reads
        timeout: 600_000,
        proxyTimeout: 600_000,
      },
    },
  },
}));
