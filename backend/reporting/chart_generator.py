"""Chart generator — deterministic matplotlib charts per GOAL_OUTPUT.md registry.

Chart IDs
---------
C1 — Stock vs VNINDEX (line, base-100 normalised)         — if data available
C2 — Revenue & EBITDA/EBIT Trend (bar + line, dual Y)     — required
C3 — EPS & P/E Trend (bar + line, dual Y)                 — required
C4 — Margin & ROE Trend (multi-line)                       — required
C5 — Forecast Revenue/Profit (bar + line, dual Y)          — required
C6 — DCF Value Bridge (waterfall bar)                      — recommended
C7 — Sensitivity Heatmap (seaborn)                         — required
C8 — Peer Comparison (horizontal grouped bar)              — required
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be before pyplot import

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import seaborn as sns
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Palette — muted, professional
# ---------------------------------------------------------------------------
_BLUE = "#2563EB"
_TEAL = "#0D9488"
_AMBER = "#D97706"
_RED = "#DC2626"
_GREY = "#6B7280"
_LIGHT_BLUE = "#93C5FD"

_DPI = 150
_FIG_W = 10
_FIG_H = 5.5


# ---------------------------------------------------------------------------
# ChartSpec dataclass
# ---------------------------------------------------------------------------
@dataclass
class ChartSpec:
    """All data needed to render any single chart."""

    chart_id: str
    ticker: str
    run_id: str = ""

    # Historical periods (x-axis labels for C2–C4)
    periods: list[str] = field(default_factory=list)

    # C2 — Revenue & EBITDA/EBIT
    revenue_bn: list[float] = field(default_factory=list)
    ebitda_margin_pct: list[float] = field(default_factory=list)
    ebit_margin_pct: list[float] = field(default_factory=list)

    # C3 — EPS & P/E
    eps_vnd: list[float] = field(default_factory=list)
    pe_x: list[float] = field(default_factory=list)

    # C4 — Margins & ROE
    gross_margin_pct: list[float] = field(default_factory=list)
    net_margin_pct: list[float] = field(default_factory=list)
    roe_pct: list[float] = field(default_factory=list)

    # C5 — Forecast
    forecast_revenue_bn: list[float] = field(default_factory=list)
    forecast_profit_bn: list[float] = field(default_factory=list)
    forecast_periods: list[str] = field(default_factory=list)

    # C1 — Price vs VNINDEX
    price_series: list[float] = field(default_factory=list)
    benchmark_series: list[float] = field(default_factory=list)
    secondary_benchmark_series: list[float] = field(default_factory=list)
    benchmark_label: str = "VNINDEX"
    secondary_benchmark_label: str = ""
    date_labels: list[str] = field(default_factory=list)

    # C6 — DCF Bridge: list of (label, value_billion_vnd) tuples
    bridge_items: list[tuple[str, float]] = field(default_factory=list)

    # C8 — Peer Comparison: list of dicts with keys ticker, pe, ev_ebitda
    peer_data: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ChartGenerator
# ---------------------------------------------------------------------------
class ChartGenerator:
    """Generates deterministic PNG charts from ChartSpec instances."""

    def __init__(self, output_dir: "Path | str"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _out_path(self, spec: ChartSpec) -> Path:
        """Return output file path based on run_id presence."""
        if spec.run_id:
            name = f"{spec.run_id}_{spec.ticker}_{spec.chart_id}.png"
        else:
            name = f"{spec.ticker}_{spec.chart_id}.png"
        return self.output_dir / name

    @staticmethod
    def _safe(lst: list[float], n: int = 1) -> list[float]:
        """Return lst padded/truncated to n elements; replace None/NaN with 0.

        Zero-fill is used for display only on historical charts where the
        absence of a value is visually obvious.  C5/C6/C7 must validate
        data BEFORE calling this so they never render all-zero charts.
        """
        out = [v if (v is not None and not (isinstance(v, float) and np.isnan(v))) else 0.0
               for v in lst]
        while len(out) < n:
            out.append(0.0)
        return out

    @staticmethod
    def _has_nonzero(lst: list[float], min_count: int = 1) -> bool:
        """Return True if lst contains at least min_count non-zero, non-NaN values."""
        count = sum(
            1 for v in lst
            if v is not None and v != 0.0 and not (isinstance(v, float) and np.isnan(v))
        )
        return count >= min_count

    @staticmethod
    def _source_caption(ax: plt.Axes, ticker: str) -> None:
        ax.annotate(
            f"Source: canonical facts — {ticker}",
            xy=(0, 0), xycoords="axes fraction",
            xytext=(0, -0.10), textcoords="axes fraction",
            fontsize=7, color=_GREY,
        )

    @staticmethod
    def _style_ax(ax: plt.Axes, title: str = "", xlabel: str = "", ylabel: str = "") -> None:
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=9)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="both", labelsize=8)

    @staticmethod
    def _save_close(fig: plt.Figure, path: Path) -> Path:
        fig.savefig(path, dpi=_DPI, bbox_inches="tight")
        plt.close(fig)
        return path

    # ------------------------------------------------------------------
    # C1 — Stock vs VNINDEX
    # ------------------------------------------------------------------

    def render_c1_price_vs_vnindex(self, spec: ChartSpec) -> Path:
        """Line chart, base-100 normalised."""
        spec.chart_id = "C1"
        path = self._out_path(spec)

        n = max(
            len(spec.price_series),
            len(spec.benchmark_series),
            len(spec.secondary_benchmark_series),
            1,
        )
        prices = self._safe(spec.price_series, n)
        bench = self._safe(spec.benchmark_series, n)
        secondary = self._safe(spec.secondary_benchmark_series, n)
        labels = spec.date_labels if spec.date_labels else [str(i) for i in range(n)]

        # Normalise to 100
        def _base100(series: list[float]) -> list[float]:
            base = series[0] if series[0] != 0 else 1.0
            return [v / base * 100 for v in series]

        prices_norm = _base100(prices)
        bench_norm = _base100(bench)

        fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
        ax.plot(labels, prices_norm, color=_BLUE, linewidth=2, marker="o", markersize=3,
                label=spec.ticker)
        ax.plot(labels, bench_norm, color=_GREY, linewidth=1.5, linestyle="--",
                label=spec.benchmark_label or "Benchmark")
        if spec.secondary_benchmark_series:
            secondary_norm = _base100(secondary)
            ax.plot(labels, secondary_norm, color=_TEAL, linewidth=1.2, linestyle=":",
                    label=spec.secondary_benchmark_label or "VNINDEX")
        ax.axhline(100, color=_GREY, linewidth=0.8, linestyle=":")
        ax.legend(fontsize=9)
        self._style_ax(
            ax,
            title=f"Biến động giá {spec.ticker} và chỉ số tham chiếu",
            ylabel="Chỉ số hóa (điểm đầu = 100)",
        )
        plt.xticks(rotation=45, ha="right")
        self._source_caption(ax, spec.ticker)
        return self._save_close(fig, path)

    # ------------------------------------------------------------------
    # C2 — Revenue & EBITDA/EBIT Trend
    # ------------------------------------------------------------------

    def render_c2_revenue_ebitda(self, spec: ChartSpec) -> Path:
        """Bar (revenue) + line (EBITDA margin) on dual Y-axis."""
        spec.chart_id = "C2"
        path = self._out_path(spec)

        periods = spec.periods or ["—"]
        n = len(periods)
        rev = self._safe(spec.revenue_bn, n)
        ebitda_m = self._safe(spec.ebitda_margin_pct, n)
        ebit_m = self._safe(spec.ebit_margin_pct, n)
        x = np.arange(n)

        fig, ax1 = plt.subplots(figsize=(_FIG_W, _FIG_H))
        ax2 = ax1.twinx()

        bars = ax1.bar(x, rev, color=_BLUE, alpha=0.75, label="Revenue (bn VND)", width=0.5)
        ax2.plot(x, ebitda_m, color=_TEAL, linewidth=2, marker="o", markersize=5,
                 label="EBITDA Margin %")
        ax2.plot(x, ebit_m, color=_AMBER, linewidth=2, marker="s", markersize=5,
                 linestyle="--", label="EBIT Margin %")

        ax1.set_xticks(x)
        ax1.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)
        self._style_ax(ax1,
                       title=f"{spec.ticker} — Revenue & EBITDA/EBIT Trend",
                       ylabel="Revenue (bn VND)")
        ax2.set_ylabel("Margin (%)", fontsize=9)
        ax2.spines[["top"]].set_visible(False)
        ax2.tick_params(axis="y", labelsize=8)

        # Combined legend
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")

        self._source_caption(ax1, spec.ticker)
        return self._save_close(fig, path)

    # ------------------------------------------------------------------
    # C3 — EPS & P/E Trend
    # ------------------------------------------------------------------

    def render_c3_eps_pe(self, spec: ChartSpec) -> Path:
        """Bar (EPS in VND) + line (P/E) on dual Y-axis."""
        spec.chart_id = "C3"
        path = self._out_path(spec)

        periods = spec.periods or ["—"]
        n = len(periods)
        eps = self._safe(spec.eps_vnd, n)
        pe = self._safe(spec.pe_x, n)
        x = np.arange(n)

        fig, ax1 = plt.subplots(figsize=(_FIG_W, _FIG_H))
        ax2 = ax1.twinx()

        ax1.bar(x, eps, color=_TEAL, alpha=0.75, label="EPS (VND)", width=0.5)
        ax2.plot(x, pe, color=_RED, linewidth=2, marker="D", markersize=5, label="P/E (x)")

        ax1.set_xticks(x)
        ax1.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)
        self._style_ax(ax1,
                       title=f"{spec.ticker} — EPS & P/E Trend",
                       ylabel="EPS (VND)")
        ax2.set_ylabel("P/E (x)", fontsize=9)
        ax2.spines[["top"]].set_visible(False)
        ax2.tick_params(axis="y", labelsize=8)

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")

        self._source_caption(ax1, spec.ticker)
        return self._save_close(fig, path)

    # ------------------------------------------------------------------
    # C4 — Margin & ROE Trend
    # ------------------------------------------------------------------

    def render_c4_margin_roe(self, spec: ChartSpec) -> Path:
        """Multi-line: gross margin, net margin, ROE."""
        spec.chart_id = "C4"
        path = self._out_path(spec)

        periods = spec.periods or ["—"]
        n = len(periods)
        gm = self._safe(spec.gross_margin_pct, n)
        nm = self._safe(spec.net_margin_pct, n)
        roe = self._safe(spec.roe_pct, n)
        x = np.arange(n)

        fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
        ax.plot(x, gm, color=_BLUE, linewidth=2, marker="o", markersize=5, label="Gross Margin %")
        ax.plot(x, nm, color=_TEAL, linewidth=2, marker="s", markersize=5, label="Net Margin %")
        ax.plot(x, roe, color=_AMBER, linewidth=2, marker="D", markersize=5, label="ROE %")

        ax.set_xticks(x)
        ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("%", fontsize=9)
        self._style_ax(ax, title=f"{spec.ticker} — Margin & ROE Trend")
        ax.legend(fontsize=9)
        self._source_caption(ax, spec.ticker)
        return self._save_close(fig, path)

    # ------------------------------------------------------------------
    # C5 — Forecast Revenue / Profit
    # ------------------------------------------------------------------

    def render_c5_forecast(self, spec: ChartSpec) -> Path:
        """Bar (forecast revenue) + line (forecast profit) dual-axis.

        Renders a placeholder if the forecast data contains no non-zero values —
        prevents publishing all-zero forecast charts when assumptions are pending.
        """
        spec.chart_id = "C5"
        path = self._out_path(spec)

        periods = spec.forecast_periods or ["—"]
        n = len(periods)

        # Validate before rendering — require at least 2 non-zero revenue values
        if not self._has_nonzero(spec.forecast_revenue_bn, min_count=2):
            fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
            ax.text(0.5, 0.5,
                    "Forecast chart blocked\nAssumptions pending analyst review",
                    ha="center", va="center", fontsize=11, color=_GREY,
                    transform=ax.transAxes)
            self._style_ax(ax, title=f"{spec.ticker} — Revenue & Profit Forecast (BLOCKED)")
            self._source_caption(ax, spec.ticker)
            return self._save_close(fig, path)

        rev = self._safe(spec.forecast_revenue_bn, n)
        profit = self._safe(spec.forecast_profit_bn, n)
        x = np.arange(n)

        fig, ax1 = plt.subplots(figsize=(_FIG_W, _FIG_H))
        ax2 = ax1.twinx()

        ax1.bar(x, rev, color=_LIGHT_BLUE, alpha=0.85, label="Forecast Revenue (bn VND)",
                width=0.5, edgecolor=_BLUE, linewidth=0.8)
        ax2.plot(x, profit, color=_AMBER, linewidth=2.5, marker="o", markersize=6,
                 label="Forecast Net Profit (bn VND)")

        ax1.set_xticks(x)
        ax1.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)
        self._style_ax(ax1,
                       title=f"{spec.ticker} — Revenue & Profit Forecast",
                       ylabel="Revenue (bn VND)")
        ax2.set_ylabel("Net Profit (bn VND)", fontsize=9)
        ax2.spines[["top"]].set_visible(False)
        ax2.tick_params(axis="y", labelsize=8)

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")

        self._source_caption(ax1, spec.ticker)
        return self._save_close(fig, path)

    # ------------------------------------------------------------------
    # C6 — DCF Value Bridge (waterfall)
    # ------------------------------------------------------------------

    def render_c6_dcf_bridge(self, spec: ChartSpec) -> Path:
        """Waterfall bar chart from bridge_items list."""
        spec.chart_id = "C6"
        path = self._out_path(spec)

        items = spec.bridge_items
        if not items:
            # Render placeholder
            fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
            ax.text(0.5, 0.5, "No DCF bridge data available",
                    ha="center", va="center", fontsize=12, color=_GREY,
                    transform=ax.transAxes)
            self._style_ax(ax, title=f"{spec.ticker} — DCF Value Bridge")
            self._source_caption(ax, spec.ticker)
            return self._save_close(fig, path)

        labels = [item[0] for item in items]
        values = [item[1] for item in items]
        n = len(labels)

        # Build waterfall: running total is the base for each bar
        running = 0.0
        bottoms: list[float] = []
        bar_values: list[float] = []
        colors: list[str] = []

        for i, val in enumerate(values):
            if i == 0:
                # First bar starts at 0 and goes up (positive)
                bottoms.append(0.0)
                bar_values.append(abs(val))
                colors.append(_BLUE)
                running = val
            elif i == n - 1:
                # Last bar: final total — draw from 0 to running
                bottoms.append(0.0)
                bar_values.append(running)
                colors.append(_TEAL)
            else:
                if val >= 0:
                    bottoms.append(running)
                    bar_values.append(val)
                    colors.append(_BLUE)
                else:
                    bottoms.append(running + val)
                    bar_values.append(-val)
                    colors.append(_RED)
                running += val

        x = np.arange(n)
        fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
        ax.bar(x, bar_values, bottom=bottoms, color=colors, alpha=0.82, width=0.5)

        # Value labels above bars
        for i, (bot, val) in enumerate(zip(bottoms, bar_values)):
            ax.text(i, bot + val + max(bar_values) * 0.01,
                    f"{bot + val:,.0f}",
                    ha="center", va="bottom", fontsize=7.5)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        self._style_ax(ax,
                       title=f"{spec.ticker} — DCF Equity Value Bridge",
                       ylabel="Value (bn VND)")
        self._source_caption(ax, spec.ticker)
        return self._save_close(fig, path)

    # ------------------------------------------------------------------
    # C7 — Sensitivity Heatmap
    # ------------------------------------------------------------------

    def render_c7_sensitivity_heatmap(
        self,
        spec: ChartSpec,
        wacc_range: list[float],
        tg_range: list[float],
        matrix: list[list[float]],
    ) -> Path:
        """Seaborn heatmap: rows = terminal growth, cols = WACC.

        Requires a non-empty matrix with no all-zero rows.
        Missing cells are rendered as NaN (grey) not zero, to avoid
        misleading the reader with a false target-price of zero.
        """
        spec.chart_id = "C7"
        path = self._out_path(spec)

        # Validate: matrix must exist and have at least one non-zero value
        all_values = []
        if matrix:
            if isinstance(matrix, list):
                for row in matrix:
                    if isinstance(row, (list, tuple)):
                        all_values.extend(row)
                    elif isinstance(row, (int, float)):
                        all_values.append(row)
            elif isinstance(matrix, dict):
                for row_d in matrix.values():
                    if isinstance(row_d, dict):
                        all_values.extend(row_d.values())
                    elif isinstance(row_d, (int, float)):
                        all_values.append(row_d)

        has_valid_data = any(
            v is not None and v != 0.0 and not (isinstance(v, float) and np.isnan(v))
            for v in all_values
        )

        if not matrix or not wacc_range or not tg_range or not has_valid_data:
            # Placeholder
            fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
            ax.text(0.5, 0.5, "No sensitivity data available",
                    ha="center", va="center", fontsize=12, color=_GREY,
                    transform=ax.transAxes)
            self._style_ax(ax, title=f"{spec.ticker} — DCF Sensitivity")
            self._source_caption(ax, spec.ticker)
            return self._save_close(fig, path)

        import pandas as pd
        df = pd.DataFrame(
            matrix,
            index=[f"{g:.1f}%" for g in tg_range],
            columns=[f"{w:.1f}%" for w in wacc_range],
        )

        fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
        sns.heatmap(
            df,
            annot=True,
            fmt=",.0f",
            cmap="RdYlGn",
            ax=ax,
            linewidths=0.4,
            linecolor="white",
            annot_kws={"size": 8},
        )
        ax.set_title(
            f"{spec.ticker} — DCF Target Price Sensitivity\n"
            "Rows: Terminal Growth (%), Cols: WACC (%)",
            fontsize=10, fontweight="bold", pad=12,
        )
        ax.set_xlabel("WACC (%)", fontsize=9)
        ax.set_ylabel("Terminal Growth (%)", fontsize=9)
        ax.tick_params(axis="both", labelsize=8)
        self._source_caption(ax, spec.ticker)

        return self._save_close(fig, path)

    # ------------------------------------------------------------------
    # C8 — Peer Comparison (horizontal grouped bar)
    # ------------------------------------------------------------------

    def render_c8_peer_comparison(self, spec: ChartSpec) -> Path:
        """Horizontal grouped bar chart comparing ticker vs peers on P/E and EV/EBITDA.

        Uses spec.peer_data for peer metrics. Expected format:
            spec.peer_data = [
                {"ticker": "DHG", "pe": 15.2, "ev_ebitda": 11.0},
                {"ticker": "IMP", "pe": 12.8, "ev_ebitda": 9.5},
                {"ticker": "TRA", "pe": 14.1, "ev_ebitda": 10.2},
                {"ticker": spec.ticker, "pe": 16.5, "ev_ebitda": 12.0},
            ]

        If spec.peer_data is empty or missing: renders a placeholder chart with note.
        Subject ticker bar is highlighted in a distinct color.
        """
        spec.chart_id = "C8"
        path = self._out_path(spec)

        _HIGHLIGHT = "#1a73e8"
        _PEER_GREY = "#9e9e9e"
        _MEDIAN_LINE = "#D97706"

        peer_data = spec.peer_data if spec.peer_data else []

        if not peer_data:
            fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
            ax.text(
                0.5, 0.5,
                "Chưa có dữ liệu peer group",
                ha="center", va="center", fontsize=12, color=_GREY,
                transform=ax.transAxes,
            )
            self._style_ax(ax, title=f"So sánh đồng ngành — {spec.ticker}")
            self._source_caption(ax, spec.ticker)
            return self._save_close(fig, path)

        tickers = [d.get("ticker", "") for d in peer_data]
        pe_vals = [d.get("pe") or 0.0 for d in peer_data]
        ev_vals = [d.get("ev_ebitda") or 0.0 for d in peer_data]

        subject = spec.ticker

        def _bar_colors(vals_tickers: list[str]) -> list[str]:
            return [_HIGHLIGHT if t == subject else _PEER_GREY for t in vals_tickers]

        def _median_nonzero(vals: list[float]) -> float | None:
            non_zero = [v for v in vals if v and v != 0.0]
            if not non_zero:
                return None
            sorted_vals = sorted(non_zero)
            mid = len(sorted_vals) // 2
            if len(sorted_vals) % 2 == 0:
                return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
            return sorted_vals[mid]

        y = np.arange(len(tickers))
        bar_height = 0.55

        fig, (ax_pe, ax_ev) = plt.subplots(1, 2, figsize=(_FIG_W * 1.2, max(_FIG_H, len(tickers) * 0.8 + 1.5)))

        # --- P/E subplot ---
        pe_colors = _bar_colors(tickers)
        ax_pe.barh(y, pe_vals, height=bar_height, color=pe_colors, alpha=0.88)
        ax_pe.set_yticks(y)
        ax_pe.set_yticklabels(tickers, fontsize=9)
        ax_pe.set_xlabel("P/E (x)", fontsize=9)
        self._style_ax(ax_pe, title="P/E")
        # Value labels
        for i, val in enumerate(pe_vals):
            if val:
                ax_pe.text(val + max(pe_vals) * 0.01, i, f"{val:.1f}x",
                           va="center", fontsize=8)
        # Median line
        pe_median = _median_nonzero(pe_vals)
        if pe_median is not None:
            ax_pe.axvline(pe_median, color=_MEDIAN_LINE, linewidth=1.2,
                          linestyle="--", label=f"Median {pe_median:.1f}x")
            ax_pe.legend(fontsize=8)

        # --- EV/EBITDA subplot ---
        ev_colors = _bar_colors(tickers)
        ax_ev.barh(y, ev_vals, height=bar_height, color=ev_colors, alpha=0.88)
        ax_ev.set_yticks(y)
        ax_ev.set_yticklabels(tickers, fontsize=9)
        ax_ev.set_xlabel("EV/EBITDA (x)", fontsize=9)
        self._style_ax(ax_ev, title="EV/EBITDA")
        # Value labels
        for i, val in enumerate(ev_vals):
            if val:
                ax_ev.text(val + max(ev_vals) * 0.01, i, f"{val:.1f}x",
                           va="center", fontsize=8)
        # Median line
        ev_median = _median_nonzero(ev_vals)
        if ev_median is not None:
            ax_ev.axvline(ev_median, color=_MEDIAN_LINE, linewidth=1.2,
                          linestyle="--", label=f"Median {ev_median:.1f}x")
            ax_ev.legend(fontsize=8)

        fig.suptitle(f"So sánh đồng ngành — {spec.ticker}", fontsize=12, fontweight="bold")
        fig.tight_layout(rect=[0, 0.04, 1, 0.95])

        # Source caption on left subplot (conventional)
        self._source_caption(ax_pe, spec.ticker)

        return self._save_close(fig, path)
