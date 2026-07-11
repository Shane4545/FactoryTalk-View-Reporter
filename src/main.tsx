import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { installDemoApi } from "./demo/installDemoApi";
import "./index.css";
import App from "./App.tsx";

installDemoApi();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
