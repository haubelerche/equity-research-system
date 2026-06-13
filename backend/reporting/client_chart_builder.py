"""Build FPTS-aligned client charts from the locked client report view model."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.reporting.client_report_view_model import ChartArtifact, ClientReportViewModel, TableData


def _numeric(values: list[Any], indexes: list[int]) -> list[float]:
    result: list[float] = []
    for index in indexes:
        value = values[index] if index < len(values) else None
        try:
            result.append(float(value) if value is not None else 0.0)
        except (TypeError, ValueError):
            result.append(0.0)
    return result


def _row(table: TableData, label: str) -> list[Any]:
    for row_label, values in table.rows:
        if row_label == label:
            return values
    return []


def _period_indexes(periods: list[str], *, forecast: bool) -> list[int]:
    return [
        index
        for index, period in enumerate(periods)
        if str(period).endswith("F") is forecast
    ]


def _as_pct(values: list[float]) -> list[float]:
    return [value * 100.0 if abs(value) <= 1.5 else value for value in values]


def _market_series(market_data) -> tuple[list[float], list[float], list[float], list[str]]:
    """Return stock and benchmark series aligned by trade date when possible."""
    if market_data is None:
        return [], [], [], []
    stock = {
        row.get("trade_date"): row.get("adjusted_close") or row.get("close")
        for row in market_data.price_history
    }
    primary = {
        row.get("trade_date"): row.get("adjusted_close") or row.get("close")
        for row in market_data.primary_benchmark_history
    }
    secondary = {
        row.get("trade_date"): row.get("adjusted_close") or row.get("close")
        for row in market_data.secondary_benchmark_history
    }
    dates = sorted(
        date for date, value in stock.items()
        if date and value and (not primary or primary.get(date))
    )
    return (
        [float(stock[date]) for date in dates],
        [float(primary[date]) for date in dates] if primary else [],
        [float(secondary[date]) for date in dates] if secondary and all(secondary.get(date) for date in dates) else [],
        dates,
    )


def build_client_report_charts(
    vm: ClientReportViewModel,
    output_dir: Path | str,
    *,
    run_id: str = "",
    generator_cls=None,
) -> dict[str, ChartArtifact]:
    """Render FPTS-permitted charts from canonical market data and locked tables."""
    if generator_cls is None:
        from backend.reporting.chart_generator import ChartGenerator, ChartSpec

        generator_cls = ChartGenerator
    else:
        from types import SimpleNamespace as ChartSpec

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generator = generator_cls(output)
    charts: dict[str, ChartArtifact] = {}

    price, benchmark, secondary, dates = _market_series(getattr(vm, "market_data", None))
    if generator._has_nonzero(price, min_count=2):
        spec = ChartSpec(
            chart_id="C1",
            ticker=vm.ticker,
            run_id=run_id,
            price_series=price,
            benchmark_series=benchmark,
            secondary_benchmark_series=secondary,
            benchmark_label=getattr(vm.market_data, "primary_benchmark", "VNINDEX"),
            secondary_benchmark_label=getattr(vm.market_data, "secondary_benchmark", ""),
            date_labels=dates,
        )
        path = generator.render_c1_price_vs_vnindex(spec)
        charts["C1"] = ChartArtifact(
            chart_id="C1",
            title="Diễn biến giá cổ phiếu"
            + (f" so với {spec.benchmark_label}" if benchmark else ""),
            path=str(path),
            caption="Nguồn nhóm phân tích thu thập",
            required=True,
        )

    model = vm.valuation_model_table
    historical_indexes = _period_indexes(model.periods, forecast=False)
    forecast_indexes = _period_indexes(model.periods, forecast=True)

    if historical_indexes:
        spec = ChartSpec(
            chart_id="C2",
            ticker=vm.ticker,
            run_id=run_id,
            periods=[model.periods[index] for index in historical_indexes],
            revenue_bn=_numeric(_row(model, "Doanh thu thuần"), historical_indexes),
            ebitda_margin_pct=_as_pct(
                _numeric(_row(model, "Tỷ suất EBITDA"), historical_indexes)
            ),
            ebit_margin_pct=_as_pct(
                _numeric(_row(model, "Biên lợi nhuận HĐKD / EBIT margin"), historical_indexes)
            ),
        )
        if generator._has_nonzero(spec.revenue_bn, min_count=2):
            path = generator.render_c2_revenue_ebitda(spec)
            charts["C2"] = ChartArtifact(
                chart_id="C2",
                title="Doanh thu và biên lợi nhuận",
                path=str(path),
                caption="Nguồn: Báo cáo tài chính công ty; tính toán của nhóm phân tích.",
                required=True,
            )

    if model.periods:
        indexes = list(range(len(model.periods)))
        spec = ChartSpec(
            chart_id="C4",
            ticker=vm.ticker,
            run_id=run_id,
            periods=list(model.periods),
            gross_margin_pct=_as_pct(
                _numeric(_row(model, "Biên lợi nhuận gộp"), indexes)
            ),
            net_margin_pct=_as_pct(_numeric(_row(model, "Biên lợi nhuận ròng"), indexes)),
            roe_pct=_as_pct(_numeric(_row(vm.financial_summary_table, "ROE"), indexes)),
        )
        if any(
            generator._has_nonzero(series, min_count=2)
            for series in (spec.gross_margin_pct, spec.net_margin_pct, spec.roe_pct)
        ):
            path = generator.render_c4_margin_roe(spec)
            charts["C4"] = ChartArtifact(
                chart_id="C4",
                title="Biên lợi nhuận và ROE",
                path=str(path),
                caption="Nguồn: Báo cáo tài chính công ty; tính toán của nhóm phân tích.",
                required=False,
            )

    if forecast_indexes:
        spec = ChartSpec(
            chart_id="C5",
            ticker=vm.ticker,
            run_id=run_id,
            forecast_periods=[model.periods[index] for index in forecast_indexes],
            forecast_revenue_bn=_numeric(
                _row(model, "Doanh thu thuần"), forecast_indexes
            ),
            forecast_profit_bn=_numeric(
                _row(model, "LNST sau CĐKKS / LNST CĐ mẹ"), forecast_indexes
            ),
        )
        if generator._has_nonzero(spec.forecast_revenue_bn, min_count=2):
            path = generator.render_c5_forecast(spec)
            charts["C5"] = ChartArtifact(
                chart_id="C5",
                title="Dự phóng doanh thu và lợi nhuận",
                path=str(path),
                caption="Nguồn: Dự phóng của nhóm phân tích dựa trên giả định đã phê duyệt.",
                required=True,
            )

    return charts
