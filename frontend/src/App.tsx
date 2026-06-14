import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/common/Layout";
import { ReportsPage } from "./pages/ReportsPage";
import { EvalDashboardPage } from "./pages/EvalDashboardPage";
import "./styles/global.css";

// Page routes must NOT collide with backend API paths (/reports, /research),
// which the dev server proxies to FastAPI. Reports lives at "/", eval at "/eval".
export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ReportsPage />} />
        <Route path="/eval" element={<EvalDashboardPage />} />
      </Routes>
    </Layout>
  );
}
