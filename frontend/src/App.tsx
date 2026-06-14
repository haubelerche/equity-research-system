import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/common/Layout";
import { ReportsPage } from "./pages/ReportsPage";
import { EvalDashboardPage } from "./pages/EvalDashboardPage";
import "./styles/global.css";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/reports" replace />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/eval" element={<EvalDashboardPage />} />
      </Routes>
    </Layout>
  );
}
