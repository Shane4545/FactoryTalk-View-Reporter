import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { HomePage } from "./pages/HomePage";
import { ExplorePage } from "./pages/ExplorePage";
import { TrendsPage } from "./pages/TrendsPage";
import { InsightsPage } from "./pages/InsightsPage";
import {
  ProduceCustomPage,
  ProduceDailyPage,
  ProduceMonthlyPage,
  ReportsPage,
} from "./pages/ReportsPages";
import { ConnectPage, DesignPage, DistributePage } from "./pages/StubPages";
import { SetupPage } from "./pages/SetupPage";
import "./index.css";

const basename =
  (import.meta as { env?: { BASE_URL?: string } }).env?.BASE_URL?.replace(
    /\/$/,
    "",
  ) || undefined;

export default function App() {
  return (
    <BrowserRouter basename={basename || undefined}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="explore" element={<ExplorePage />} />
          <Route path="insights" element={<InsightsPage />} />
          <Route path="connect" element={<ConnectPage />} />
          <Route path="setup" element={<SetupPage />} />
          <Route path="design" element={<DesignPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="reports/daily" element={<ProduceDailyPage />} />
          <Route path="reports/monthly" element={<ProduceMonthlyPage />} />
          <Route path="reports/custom" element={<ProduceCustomPage />} />
          <Route path="reports/trends" element={<TrendsPage />} />
          <Route path="distribute" element={<DistributePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
