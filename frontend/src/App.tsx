import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/common/Layout";
import { ReportsPage } from "./pages/ReportsPage";
import { EvalDashboardPage } from "./pages/EvalDashboardPage";
import { GenerationProvider } from "./generation/GenerationContext";
import "./styles/global.css";

// Page routes must NOT collide with backend API paths (/reports, /research),
// which the dev server proxies to FastAPI. Reports lives at "/", eval at "/eval".
// GenerationProvider wraps everything so report generation (progress modal +
// completion toast) survives navigation and modal hiding.
export default function App() {
  return (
    <GenerationProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<ReportsPage />} />
          <Route path="/eval" element={<EvalDashboardPage />} />
        </Routes>
      </Layout>
    </GenerationProvider>
  );
}
