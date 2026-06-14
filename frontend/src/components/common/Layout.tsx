import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <nav className="app-nav">
        <span className="app-brand">Pharma Equity Research</span>
        <NavLink to="/" end>Báo cáo</NavLink>
        <NavLink to="/eval">Khung đánh giá</NavLink>
      </nav>
      <main>{children}</main>
    </div>
  );
}
