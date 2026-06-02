"""ACBS/IMP-style section builders for client and analyst PDF reports."""
from __future__ import annotations

from html import escape
from typing import Any

from backend.reporting.client_report_view_model import (
    ClientReportViewModel,
    TableData,
)


def _e(value: Any) -> str:
    return escape(str(value))


def _fmt_money(value: Any) -> str:
    if value is None or value == "�":
        return "�"
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return _e(value)


def _fmt_metric(label: str, value: Any) -> str:
    if value is None or value == "�":
        return "�"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _e(value)
    lower = label.lower()
    if any(token in lower for token in ["tang tru?ng", "revenue growth", "gross margin", "sga", "sg&a", "depreciation", "kh?u hao /", "capex /", "effective tax rate", "cash conversion", "terminal growth", "t? su?t", "thu? su?t", "bi�n", "roe", "roa", "roic", "wacc", "eva", "yield", "su?t sinh l?i", "n? r�ng / vcsh", "upside/downside", "stress"]):
        return f"{number * 100:.1f}%"
    if any(token in lower for token in ["p/e", "p/b", "p/s", "ev/", "peg", "n? r�ng / ebitda"]):
        return f"{number:.1f}x"
    if "eps" in lower or "gi� tr? s? s�ch" in lower:
        return f"{number:,.0f}"
    if "target price" in lower or "gi� m?c ti�u" in lower:
        return f"{number:,.0f}"
    return f"{number:,.0f}"


def _format_price(money: Any) -> str:
    if money is None:
        return "�"
    return f"{money.amount:,.0f}"


def _format_percent(percent: Any) -> str:
    if percent is None:
        return "�"
    return f"{percent.value * 100:+.1f}%"


def _render_table(table: TableData, class_name: str = "financial-model-table") -> str:
    header = "".join(f"<th>{_e(period)}</th>" for period in table.periods)
    body = []
    for label, values in table.rows:
        cells = "".join(
            f'<td class="numeric">{_fmt_metric(label, v)}</td>'
            for v in values
        )
        body.append(f"<tr><td>{_e(label)}</td>{cells}</tr>")
    unit = f'<div class="table-unit">{_e(table.unit)}</div>' if table.unit else ""
    return f"""
<div class="model-table-block">
  <h2>{_e(table.title)}</h2>
  {unit}
  <table class="{class_name}">
    <thead><tr><th>Ch? ti�u</th>{header}</tr></thead>
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
    stats = list(vm.market_statistics.items())
    sidebar_rows = [
        ("Gi� m?c ti�u (VND)", _format_price(vm.target_price)),
        ("Gi� hi?n t?i (VND)", _format_price(vm.current_price)),
        ("T? l? tang/gi?m", _format_percent(vm.upside_downside)),
        ("Su?t sinh l?i c? t?c", _format_percent(vm.dividend_yield)),
        ("T?ng t? su?t l?i nhu?n", _format_percent(vm.total_return)),
    ]
    stats_rows = [
        ("M� giao d?ch", vm.market_statistics.get("M� giao d?ch", "�")),
        ("S�n", vm.exchange),
        ("Ng�nh", vm.sector),
        ("V?n h�a", vm.market_statistics.get("V?n h�a")),
        ("S? lu?ng c? phi?u", vm.market_statistics.get("S? lu?ng c? phi?u")),
        ("K? ho?ch doanh thu 2026", vm.market_statistics.get("K? ho?ch doanh thu 2026", "�")),
        ("K? ho?ch LNTT 2026", vm.market_statistics.get("K? ho?ch LNTT 2026", "�")),
        ("T�i s?n Q1/2026", vm.market_statistics.get("T�i s?n Q1/2026", "�")),
        ("V?n ch? s? h?u Q1/2026", vm.market_statistics.get("V?n ch? s? h?u Q1/2026", "�")),
    ]
    return f"""
<div class="client-report-page snapshot-page">
  <div class="acbs-titlebar">
    <div>
      <div class="acbs-report-kicker">{_e(vm.report_title)} - {_e(vm.recommendation)}</div>
      <div class="acbs-date">Ng�y {_e(vm.report_date)}</div>
    </div>
    <div class="acbs-brand">Vietnam Pharma Equity Research</div>
  </div>
  <div class="acbs-layout">
    <aside class="acbs-sidebar">
      <div class="analyst-card">
        <div class="analyst-name">Nh�m ph�n t�ch</div>
        <div>B�o c�o c?p nh?t</div>
      </div>
      <div class="recommendation-card {_rec_css(vm.recommendation)}">
        <div class="rec-label">Khuy?n ngh?</div>
        <div class="rec-value">{_e(vm.recommendation)}</div>
        <div class="rec-sub">{_e(vm.exchange)}: {_e(vm.ticker)}</div>
        <div class="rec-sector">{_e(vm.sector)}</div>
      </div>
      {_render_key_value_table(sidebar_rows)}
      <div class="side-section-title">{_e(vm.trading_performance_table.title)}</div>
      {_render_table(vm.trading_performance_table, "broker-side-table compact")}
      {_chart(vm, "C1")}
      <div class="side-section-title">Th?ng k� th? tru?ng</div>
      {_render_key_value_table(stats_rows, "broker-side-table compact")}
    </aside>
    <main class="acbs-main">
      <h1>{_e(vm.company_name)} ({_e(vm.ticker)} VN)</h1>
      <div class="lead-thesis">{_e(vm.investment_thesis)}</div>
      <h2>Lu?n di?m c?p nh?t</h2>
      <p>{_e(vm.latest_business_update)}</p>
      <h2>B?i c?nh hi?n t?i</h2>
      <p>{_e(vm.current_context)}</p>
      <h2>�?ng l?c tang tru?ng</h2>
      <p>{_e(vm.key_growth_drivers)}</p>
      {_render_table(vm.financial_summary_table)}
    </main>
  </div>
</div>
"""


def _narrative_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>C?p nh?t ho?t d?ng kinh doanh</h1>
  <div class="two-chart-grid">
    {_chart(vm, "C2")}
    {_chart(vm, "C4")}
  </div>
  <h2>Tri?n v?ng d?u tu</h2>
  <p>{_e(vm.key_growth_drivers)}</p>
  <h2>�?ng l?c bi�n l?i nhu?n</h2>
  <p>{_e(vm.key_margin_drivers)}</p>
  <h2>S? ki?n tr?ng y?u</h2>
  <p>{_e(vm.material_events)}</p>
  {_render_table(vm.key_forecast_drivers_table)}
</div>
"""


def _forecast_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>D? ph�ng v� d?nh gi�</h1>
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
  <h1>R?i ro d?u tu v� khuy?n c�o</h1>
  <table class="financial-model-table">
    <thead><tr><th>R?i ro</th>{''.join(f'<th>{_e(p)}</th>' for p in vm.risk_table.periods)}</tr></thead>
    <tbody>{risk_body}</tbody>
  </table>
  <h2>Khuy?n c�o</h2>
  <p>{_e(vm.disclaimer)}</p>
  <h2>Ngu?n tham kh?o ch�nh</h2>
  <p>{_e(vm.source_captions.get("current_context", ""))}</p>
</div>
"""


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
