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
  ProduceWeeklyPage,
  ProduceYearlyPage,
  ReportsPage,
} from "./pages/ReportsPages";
import { DistributePage } from "./pages/StubPages";
import { LogPage } from "./pages/LogPage";
import { ConnectPage } from "./pages/ConnectPage";
import { SetupPage } from "./pages/SetupPage";
import { HelpPage } from "./pages/HelpPage";
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
          <Route path="help" element={<HelpPage />} />
          <Route path="design" element={<Navigate to="/reports" replace />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="reports/daily" element={<ProduceDailyPage />} />
          <Route path="reports/weekly" element={<ProduceWeeklyPage />} />
          <Route path="reports/monthly" element={<ProduceMonthlyPage />} />
          <Route path="reports/yearly" element={<ProduceYearlyPage />} />
          <Route path="reports/custom" element={<ProduceCustomPage />} />
          <Route path="reports/trends" element={<TrendsPage />} />
          <Route path="trends" element={<Navigate to="/reports/trends" replace />} />
          <Route path="distribute" element={<DistributePage />} />
          <Route path="log" element={<LogPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
