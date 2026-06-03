"""ACBS/IMP-style section builders for client and analyst PDF reports."""
from __future__ import annotations

from html import escape
from typing import Any

from backend.reporting.client_report_view_model import (
    ClientReportViewModel,
    TableData,
)


DASH = "—"


def _e(value: Any) -> str:
    return escape(str(value))


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == DASH


def _fmt_money(value: Any) -> str:
    if _is_missing(value):
        return DASH
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return _e(value)


def _fmt_metric(label: str, value: Any) -> str:
    if _is_missing(value):
        return DASH
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _e(value)

    lower = label.lower()
    percent_tokens = [
        "tăng trưởng",
        "revenue growth",
        "gross margin",
        "biên",
        "sga",
        "sg&a",
        "khấu hao /",
        "capex /",
        "effective tax rate",
        "cash conversion",
        "terminal growth",
        "tỷ suất",
        "thuế suất",
        "roe",
        "roa",
        "roic",
        "wacc",
        "eva",
        "yield",
        "suất sinh lời",
        "nợ ròng / vcsh",
        "upside/downside",
        "stress",
    ]
    multiple_tokens = ["p/e", "p/b", "p/s", "ev/", "peg", "nợ ròng / ebitda"]
    if any(token in lower for token in percent_tokens):
        return f"{number * 100:.1f}%"
    if any(token in lower for token in multiple_tokens):
        return f"{number:.1f}x"
    if "eps" in lower or "giá trị sổ sách" in lower:
        return f"{number:,.0f}"
    if "target price" in lower or "giá mục tiêu" in lower:
        return f"{number:,.0f}"
    return f"{number:,.0f}"


def _format_price(money: Any) -> str:
    if money is None:
        return DASH
    return f"{money.amount:,.0f}"


def _format_percent(percent: Any) -> str:
    if percent is None:
        return DASH
    return f"{percent.value * 100:+.1f}%"


def _render_table(table: TableData, class_name: str = "financial-model-table") -> str:
    header = "".join(f"<th>{_e(period)}</th>" for period in table.periods)
    body = []
    for label, values in table.rows:
        cells = "".join(
            f'<td class="numeric">{_fmt_metric(label, value)}</td>'
            for value in values
        )
        body.append(f"<tr><td>{_e(label)}</td>{cells}</tr>")
    unit = f'<div class="table-unit">{_e(table.unit)}</div>' if table.unit else ""
    return f"""
<div class="model-table-block">
  <h2>{_e(table.title)}</h2>
  {unit}
  <table class="{class_name}">
    <thead><tr><th>Chỉ tiêu</th>{header}</tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table>
</div>
"""


def _render_key_value_table(rows: list[tuple[str, Any]], class_name: str = "broker-side-table") -> str:
    body = "".join(
        f"<tr><td>{_e(label)}</td><td>{_fmt_metric(label, value)}</td></tr>"
        for label, value in rows
    )
    return f'<table class="{class_name}"><tbody>{body}</tbody></table>'


def _chart(vm: ClientReportViewModel, chart_id: str) -> str:
    chart = vm.charts.get(chart_id)
    if not chart:
        return ""
    return f"""
<figure class="report-chart">
  <img src="{_e(chart.path)}" alt="{_e(chart.title)}" />
  <figcaption>{_e(chart.caption)}</figcaption>
</figure>
"""


_REC_CSS: dict[str, str] = {
    "MUA": "buy",
    "KHẢ QUAN": "outperform",
    "TRUNG LẬP": "neutral",
    "KÉM KHẢ QUAN": "underperform",
    "BÁN": "sell",
}


def _rec_css(recommendation: str) -> str:
    return _REC_CSS.get((recommendation or "").upper().strip(), "review")


def _snapshot_page(vm: ClientReportViewModel) -> str:
    sidebar_rows = [
        ("Giá mục tiêu (VND)", _format_price(vm.target_price)),
        ("Giá hiện tại (VND)", _format_price(vm.current_price)),
        ("Tỷ lệ tăng/giảm", _format_percent(vm.upside_downside)),
        ("Suất sinh lời cổ tức", _format_percent(vm.dividend_yield)),
        ("Tổng tỷ suất lợi nhuận", _format_percent(vm.total_return)),
    ]
    stats_rows = [
        ("Mã giao dịch", vm.market_statistics.get("Mã giao dịch", DASH)),
        ("Sàn", vm.exchange),
        ("Ngành", vm.sector),
        ("Vốn hóa", vm.market_statistics.get("Vốn hóa")),
        ("Số lượng cổ phiếu", vm.market_statistics.get("Số lượng cổ phiếu")),
        ("Kế hoạch doanh thu 2026", vm.market_statistics.get("Kế hoạch doanh thu 2026", DASH)),
        ("Kế hoạch LNTT 2026", vm.market_statistics.get("Kế hoạch LNTT 2026", DASH)),
        ("Tài sản Q1/2026", vm.market_statistics.get("Tài sản Q1/2026", DASH)),
        ("Vốn chủ sở hữu Q1/2026", vm.market_statistics.get("Vốn chủ sở hữu Q1/2026", DASH)),
    ]
    return f"""
<div class="client-report-page snapshot-page">
  <div class="acbs-titlebar">
    <div>
      <div class="acbs-report-kicker">{_e(vm.report_title)} - {_e(vm.recommendation)}</div>
      <div class="acbs-date">Ngày {_e(vm.report_date)}</div>
    </div>
    <div class="acbs-brand">Vietnam Pharma Equity Research</div>
  </div>
  <div class="acbs-layout">
    <aside class="acbs-sidebar">
      <div class="analyst-card">
        <div class="analyst-name">Nhóm phân tích</div>
        <div>Báo cáo cập nhật</div>
      </div>
      <div class="recommendation-card {_rec_css(vm.recommendation)}">
        <div class="rec-label">Khuyến nghị</div>
        <div class="rec-value">{_e(vm.recommendation)}</div>
        <div class="rec-sub">{_e(vm.exchange)}: {_e(vm.ticker)}</div>
        <div class="rec-sector">{_e(vm.sector)}</div>
      </div>
      {_render_key_value_table(sidebar_rows)}
      <div class="side-section-title">{_e(vm.trading_performance_table.title)}</div>
      {_render_table(vm.trading_performance_table, "broker-side-table compact")}
      {_chart(vm, "C1")}
      <div class="side-section-title">Thống kê thị trường</div>
      {_render_key_value_table(stats_rows, "broker-side-table compact")}
    </aside>
    <main class="acbs-main">
      <h1>{_e(vm.company_name)} ({_e(vm.ticker)} VN)</h1>
      <div class="lead-thesis">{_e(vm.investment_thesis)}</div>
      <h2>Luận điểm cập nhật</h2>
      <p>{_e(vm.latest_business_update)}</p>
      <h2>Bối cảnh hiện tại</h2>
      <p>{_e(vm.current_context)}</p>
      <h2>Động lực tăng trưởng</h2>
      <p>{_e(vm.key_growth_drivers)}</p>
      {_render_table(vm.financial_summary_table)}
    </main>
  </div>
</div>
"""


def _narrative_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>Cập nhật hoạt động kinh doanh</h1>
  <div class="two-chart-grid">
    {_chart(vm, "C2")}
    {_chart(vm, "C4")}
  </div>
  <h2>Triển vọng đầu tư</h2>
  <p>{_e(vm.key_growth_drivers)}</p>
  <h2>Động lực biên lợi nhuận</h2>
  <p>{_e(vm.key_margin_drivers)}</p>
  <h2>Sự kiện trọng yếu</h2>
  <p>{_e(vm.material_events)}</p>
  {_render_table(vm.key_forecast_drivers_table)}
</div>
"""


def _forecast_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>Dự phóng và định giá</h1>
  <p>{_e(vm.forecast_valuation_narrative)}</p>
  {_render_table(vm.sensitivity_table)}
  {_render_table(vm.valuation_model_table)}
</div>
"""


def _bs_ratios_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  {_render_table(vm.balance_sheet_cashflow_table)}
  {_render_table(vm.profitability_valuation_table)}
</div>
"""


def _risks_disclaimer_page(vm: ClientReportViewModel) -> str:
    risk_body = "".join(
        f"<tr><td>{_e(label)}</td>{''.join(f'<td>{_e(v)}</td>' for v in values)}</tr>"
        for label, values in vm.risk_table.rows
    )
    return f"""
<div class="client-report-page">
  <h1>Rủi ro đầu tư và khuyến cáo</h1>
  <table class="financial-model-table">
    <thead><tr><th>Rủi ro</th>{''.join(f'<th>{_e(p)}</th>' for p in vm.risk_table.periods)}</tr></thead>
    <tbody>{risk_body}</tbody>
  </table>
  <h2>Khuyến cáo</h2>
  <p>{_e(vm.disclaimer)}</p>
  <h2>Nguồn tham khảo chính</h2>
  {_render_key_sources(vm)}
</div>
"""


def _render_key_sources(vm: ClientReportViewModel) -> str:
    if not vm.key_sources:
        return "<p>Nguồn dữ liệu sẽ được bổ sung khi tài liệu công bố chính thức được nạp.</p>"
    items = "".join(f"<li>{_e(s.get('label', ''))}</li>" for s in vm.key_sources)
    return f'<ol class="source-list">{items}</ol>'


def build_client_report_sections(vm: ClientReportViewModel) -> list[dict[str, Any]]:
    pages = [
        ("snapshot", "Investment Snapshot", _snapshot_page(vm), ["C1"]),
        ("business_update", "Operating Update", _narrative_page(vm), ["C2", "C4"]),
        ("valuation_model", "Forecast and Valuation", _forecast_page(vm), []),
        ("bs_cf_ratios", "Balance Sheet, Cash Flow and Ratios", _bs_ratios_page(vm), []),
        ("risks_disclaimer", "Risks and Disclaimer", _risks_disclaimer_page(vm), []),
    ]
    sections: list[dict[str, Any]] = []
    for index, (page, title, html, chart_ids) in enumerate(pages, start=1):
        sections.append(
            {
                "page": page,
                "page_number": index,
                "title": title,
                "markdown": html,
                "chart_ids": chart_ids,
                "word_count": len(html.split()),
            }
        )
    return sections
