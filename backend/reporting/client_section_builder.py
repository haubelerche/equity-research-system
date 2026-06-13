"""ACBS/IMP-style section builders for client and analyst PDF reports."""
from __future__ import annotations

from html import escape
from typing import Any

from backend.reporting.client_report_view_model import (
    ClientReportViewModel,
    TableData,
)
from backend.reporting.fpts_chart_policy import is_main_report_chart, main_report_chart_ids


DASH = "—"


def _e(value: Any) -> str:
    return escape(str(value))


def _excerpt(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return shortened + "."


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == DASH


def _fmt_money(value: Any) -> str:
    if _is_missing(value):
        return DASH
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return _e(value)


def _fmt_metric(label: str, value: Any, format_type: str = "auto") -> str:
    if _is_missing(value):
        return DASH
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _e(value)

    def _zeroed(threshold: float) -> float:
        return 0.0 if abs(number) < threshold else number

    if format_type == "currency":
        number = _zeroed(0.5)
        return f"{number:,.0f}"
    if format_type == "percent":
        number = _zeroed(0.0005)
        return f"{number * 100:.1f}%"
    if format_type == "multiple":
        number = _zeroed(0.05)
        return f"{number:.1f}x"
    if format_type == "text":
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
        "chuyển đổi dòng tiền",
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
        "tiềm năng tăng/giảm",
        "stress",
    ]
    multiple_tokens = ["p/e", "p/b", "p/s", "ev/", "peg", "nợ ròng / ebitda"]
    if any(token in lower for token in percent_tokens):
        number = _zeroed(0.0005)
        return f"{number * 100:.1f}%"
    if any(token in lower for token in multiple_tokens):
        number = _zeroed(0.05)
        return f"{number:.1f}x"
    if "eps" in lower or "giá trị sổ sách" in lower:
        number = _zeroed(0.5)
        return f"{number:,.0f}"
    if "target price" in lower or "giá mục tiêu" in lower:
        number = _zeroed(0.5)
        return f"{number:,.0f}"
    number = _zeroed(0.5)
    return f"{number:,.0f}"


def _format_price(money: Any) -> str:
    if money is None:
        return DASH
    return f"{money.amount:,.0f}"


def _format_percent(percent: Any) -> str:
    if percent is None:
        return DASH
    return f"{percent.value * 100:+.1f}%"


def _table_has_data(table: TableData) -> bool:
    """True if at least one cell holds a real value (not None / empty / dash)."""
    for _label, values in table.rows:
        for v in values:
            if v is None:
                continue
            if isinstance(v, str) and v.strip() in ("", DASH):
                continue
            return True
    return False


def _render_table(table: TableData, class_name: str = "financial-model-table") -> str:
    header = "".join(f"<th>{_e(period)}</th>" for period in table.periods)
    body = []
    for label, values in table.rows:
        cells = "".join(
            f'<td class="numeric">{_fmt_metric(label, value, table.format_type)}</td>'
            for value in values
        )
        body.append(f"<tr><td>{_e(label)}</td>{cells}</tr>")
    unit = f'<div class="table-unit">{_e(table.unit)}</div>' if table.unit else ""
    source = f'<div class="table-source-note">{_e(table.source_note)}</div>' if table.source_note else ""
    return f"""
<div class="model-table-block">
  <h2>{_e(table.title)}</h2>
  {unit}
  <table class="{class_name}">
    <thead><tr><th>Chỉ tiêu</th>{header}</tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table>
  {source}
</div>
"""


def _render_variance_table(table: TableData, class_name: str = "financial-model-table") -> str:
    """Render a financial table with automatic positive/negative variance colouring.

    Rows whose labels contain growth or margin keywords get CSS colour classes on
    numeric cells: positive → variance-positive (green), negative → variance-negative (red).
    All other rows are rendered as plain numeric cells.
    """
    _VARIANCE_KEYWORDS = (
        "tăng trưởng", "growth", "biên", "margin", "roe", "roa", "roic",
        "thay đổi", "change", "delta", "variance",
    )

    def _is_variance_row(label: str) -> bool:
        lower = label.lower()
        return any(kw in lower for kw in _VARIANCE_KEYWORDS)

    def _cell(label: str, value: Any) -> str:
        raw = _fmt_metric(label, value, table.format_type)
        if raw == DASH or not _is_variance_row(label):
            return f'<td class="numeric">{raw}</td>'
        try:
            num = float(str(value).replace(",", "")) if value is not None else None
        except (ValueError, TypeError):
            num = None
        if num is None:
            return f'<td class="numeric">{raw}</td>'
        css = "variance-positive" if num >= 0 else "variance-negative"
        return f'<td class="numeric {css}">{raw}</td>'

    header = "".join(f"<th>{_e(period)}</th>" for period in table.periods)
    body = []
    for label, values in table.rows:
        cells = "".join(_cell(label, v) for v in values)
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


def _render_sensitivity_matrix_table(table: TableData) -> str:
    """Render a WACC × growth sensitivity matrix with magnitude-based cell colouring.

    Cells are coloured relative to the median value in the matrix:
      - Top quartile (high upside) → matrix-cell-high (green)
      - Bottom quartile (low/negative) → matrix-cell-low (red)
      - Middle two quartiles → matrix-cell-mid (purple) or matrix-cell-neutral
    """
    # Collect all numeric values to compute median
    all_vals: list[float] = []
    for _label, values in table.rows:
        for v in values:
            try:
                if v is not None:
                    all_vals.append(float(v))
            except (ValueError, TypeError):
                pass

    if all_vals:
        sorted_vals = sorted(all_vals)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[3 * n // 4]
    else:
        q1 = q3 = 0.0

    def _cell_css(value: Any) -> str:
        try:
            num = float(value) if value is not None else None
        except (ValueError, TypeError):
            num = None
        if num is None:
            return "matrix-cell-neutral"
        if num >= q3:
            return "matrix-cell-high"
        if num <= q1:
            return "matrix-cell-low"
        return "matrix-cell-neutral"

    header = "".join(f"<th>{_e(period)}</th>" for period in table.periods)
    body = []
    for label, values in table.rows:
        cells = "".join(
            f'<td class="{_cell_css(v)}">{_fmt_metric(label, v, table.format_type)}</td>'
            for v in values
        )
        body.append(f"<tr><th>{_e(label)}</th>{cells}</tr>")
    unit = f'<div class="table-unit">{_e(table.unit)}</div>' if table.unit else ""
    return f"""
<div class="model-table-block">
  <h2>{_e(table.title)}</h2>
  {unit}
  <table class="matrix-table">
    <thead><tr><th></th>{header}</tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table>
</div>
"""


def _slice_table(table: TableData, max_periods: int = 6) -> TableData:
    """Return a recent-period view for the main report body.

    Detailed multi-year tables stay available in the appendix; the body keeps
    broker-style readability by showing only the most recent columns.
    """
    if len(table.periods) <= max_periods:
        return table
    start = len(table.periods) - max_periods
    return TableData(
        title=table.title,
        periods=table.periods[start:],
        rows=[(label, values[start:]) for label, values in table.rows],
        unit=table.unit,
        format_type=table.format_type,
        source_note=table.source_note,
    )


def _render_main_table(table: TableData, class_name: str = "financial-model-table main-financial-table") -> str:
    return _render_variance_table(_slice_table(table), class_name)


def _render_appendix_table(table: TableData) -> str:
    return _render_variance_table(table, "financial-model-table appendix-financial-table")


def _section_block(title: str, body: str, class_name: str = "") -> str:
    extra = f" {class_name}" if class_name else ""
    return f"""
<section class="fpts-section{extra}">
  <div class="fpts-section-title">{_e(title)}</div>
  {body}
</section>
"""


def _render_key_value_table(rows: list[tuple[str, Any]], class_name: str = "broker-side-table") -> str:
    body = "".join(
        f"<tr><td>{_e(label)}</td><td>{_fmt_metric(label, value)}</td></tr>"
        for label, value in rows
    )
    return f'<table class="{class_name}"><tbody>{body}</tbody></table>'


def _chart(vm: ClientReportViewModel, chart_id: str) -> str:
    if not is_main_report_chart(chart_id):
        return ""
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


def _rec_hero(vm: ClientReportViewModel) -> str:
    """Recommendation hero card embedded in the snapshot cover page.

    Replaces the template-level standalone banner so the cover page is a
    self-contained dashboard without a near-blank preceding page.
    """
    rec_css_class = "recommendation-" + _rec_css(vm.recommendation)
    tp_display = _format_price(vm.target_price)
    upside_display = _format_percent(vm.upside_downside)
    # Cover must agree with the running header and the status page: when the report
    # is not yet publication-ready, mark the recommendation as preliminary instead of
    # presenting unapproved figures as a final published call.
    draft_note = (
        '\n  <div class="rec-draft-note">Dự thảo: khuyến nghị và giá mục tiêu chưa được công bố chính thức</div>'
        if vm.publication_status != "client_exportable"
        else ""
    )
    return f"""
<div class="recommendation-card {_e(rec_css_class)}">
  <span class="rec-label">Khuyến nghị &nbsp;·&nbsp; {_e(vm.exchange)}: {_e(vm.ticker)}</span>
  <div class="rec-value">{_e(vm.recommendation)}</div>
  <div class="rec-sub">
    Giá mục tiêu: <strong>{_e(tp_display)} VND</strong>
    &nbsp;|&nbsp;
    Tiềm năng tăng/giảm: <strong>{_e(upside_display)}</strong>
    &nbsp;|&nbsp;
    {_e(vm.report_date)}
  </div>{draft_note}
</div>
"""


def _snapshot_page(vm: ClientReportViewModel) -> str:
    sidebar_rows = [
        ("Giá mục tiêu (VND)", _format_price(vm.target_price)),
        ("Giá hiện tại (VND)", _format_price(vm.current_price)),
        ("Tỷ lệ tăng/giảm", _format_percent(vm.upside_downside)),
        ("Tổng tỷ suất lợi nhuận", _format_percent(vm.total_return)),
    ]
    stats_rows = [
        ("Mã giao dịch", vm.market_statistics.get("Mã giao dịch", DASH)),
        ("Sàn", vm.exchange),
        ("Ngành", vm.sector),
        ("Giá đóng cửa", vm.market_statistics.get("Giá đóng cửa", "N/A")),
        ("Giá cao/thấp 52 tuần", vm.market_statistics.get("Giá cao/thấp 52 tuần", "N/A")),
        ("Vốn hóa", vm.market_statistics.get("Vốn hóa")),
        ("Số lượng cổ phiếu", vm.market_statistics.get("Số lượng cổ phiếu")),
        ("KLGD bình quân 30 phiên", vm.market_statistics.get("KLGD bình quân 30 phiên", "N/A")),
        ("Tỷ lệ sở hữu nước ngoài", vm.market_statistics.get("Tỷ lệ sở hữu nước ngoài", "N/A")),
    ]
    return f"""
<div class="client-report-page snapshot-page">
  <div class="fpts-cover-topline">
    <div class="fpts-cover-brand">Equity Research</div>
    <div class="fpts-cover-report-type">BÁO CÁO CẬP NHẬT ĐỊNH GIÁ</div>
  </div>
  <div class="fpts-cover-meta">
    <span>NGÀNH {_e(vm.sector).upper()}</span>
    <span>Ngày {_e(vm.report_date)}</span>
  </div>
  <div class="fpts-company-bar">
    <div>{_e(vm.company_name)} ({_e(vm.ticker)} VN)</div>
    <div>{_e(vm.exchange)}: {_e(vm.ticker)}</div>
  </div>
  <div class="acbs-layout">
    <aside class="acbs-sidebar">
      <div class="analyst-card">
        <div class="analyst-name">Nhóm phân tích</div>
        <div>Báo cáo cập nhật</div>
      </div>
      <div class="analyst-meta-card">
        <div class="rec-sub">{_e(vm.exchange)}: {_e(vm.ticker)}</div>
        <div class="rec-sector">{_e(vm.sector)}</div>
      </div>
      {_render_key_value_table(sidebar_rows)}
      {_chart(vm, "C1")}
      {_render_table(vm.trading_performance_table, "broker-side-table compact trading-performance-table")}
      <div class="side-section-title">Thông tin giao dịch</div>
      {_render_key_value_table(stats_rows, "broker-side-table compact")}
    </aside>
    <main class="acbs-main">
      {_rec_hero(vm)}
      <div class="lead-thesis">{_e(_excerpt(vm.investment_thesis, 1050))}</div>
      <h2>Luận điểm cập nhật</h2>
      <p>{_e(_excerpt(vm.latest_business_update, 900))}</p>
      <h2>Động lực tăng trưởng</h2>
      <p>{_e(_excerpt(vm.key_growth_drivers, 700))}</p>
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


def _business_financials_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>Triển vọng kinh doanh và tài chính</h1>
  {_section_block("Cập nhật hoạt động kinh doanh", f"<p>{_e(vm.latest_business_update)}</p>")}
  <div class="two-chart-grid">
    {_chart(vm, "C2")}
    {_chart(vm, "C4")}
  </div>
  {_section_block("Kết quả tài chính chính", f"<p>{_e(vm.current_context)}</p>{_render_main_table(vm.financial_summary_table)}")}
  {_section_block("Động lực dự phóng", f"<p>{_e(vm.key_growth_drivers)}</p><p>{_e(vm.key_margin_drivers)}</p>{_chart(vm, 'C5')}{_render_table(vm.key_forecast_drivers_table, 'financial-model-table driver-table')}", "driver-section")}
</div>
"""


def _valuation_page(vm: ClientReportViewModel) -> str:
    peer = _render_table(vm.peer_table, "financial-model-table peer-table") if vm.peer_table is not None else ""
    return f"""
<div class="client-report-page">
  <h1>Định giá và độ nhạy</h1>
  {_section_block("Luận điểm định giá", f"<p>{_e(vm.forecast_valuation_narrative)}</p>")}
  {_section_block("Mô hình định giá", _render_main_table(vm.valuation_model_table))}
  {_section_block("Độ nhạy giá mục tiêu", _render_sensitivity_matrix_table(vm.sensitivity_table), "sensitivity-section")}
  {peer}
</div>
"""


def _risks_sources_page(vm: ClientReportViewModel) -> str:
    risk_body = "".join(
        f"<tr><td>{_e(label)}</td>{''.join(f'<td>{_e(v)}</td>' for v in values)}</tr>"
        for label, values in vm.risk_table.rows
    )
    return f"""
<div class="client-report-page">
  <h1>Rủi ro, trạng thái và nguồn tham khảo</h1>
  {_section_block("Yếu tố cần theo dõi", f"<p>{_e(vm.material_events)}</p>")}
  <div class="fpts-section">
  <div class="fpts-section-title">Rủi ro đầu tư</div>
  <table class="financial-model-table">
    <thead><tr><th>Rủi ro</th>{''.join(f'<th>{_e(p)}</th>' for p in vm.risk_table.periods)}</tr></thead>
    <tbody>{risk_body}</tbody>
  </table>
  </div>
  {_section_block("Trạng thái báo cáo", f"<p>{_e(_client_status_sentence(vm))}</p>")}
  {_section_block("Nguồn tham khảo chính", _render_key_sources(vm))}
  {_section_block("Tuyên bố miễn trừ trách nhiệm", f"<p>{_e(vm.disclaimer)}</p>")}
</div>
"""


def _client_status_sentence(vm: ClientReportViewModel) -> str:
    """Client-facing status line — no backend tokens (gate keys, artifact names) in the PDF.

    Audit rule: client-facing report must not leak backend jargon such as
    'analyst_review_only; blockers: valuation_gap_gt_25pct'.
    """
    if vm.publication_status == "client_exportable":
        return (
            "Báo cáo đã hoàn tất kiểm định nội bộ và đủ điều kiện công bố."
        )
    return (
        "Báo cáo đang trong quá trình rà soát của chuyên viên phân tích; "
        "khuyến nghị và giá mục tiêu chưa được công bố chính thức cho đến khi "
        "các giả định định giá và dữ liệu nguồn được phê duyệt."
    )


def _appendix_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page appendix-page">
  <h1>Phụ lục bảng tài chính</h1>
  {_render_appendix_table(vm.financial_summary_table)}
  {_render_appendix_table(vm.balance_sheet_cashflow_table)}
  {_render_appendix_table(vm.profitability_valuation_table)}
  {_render_appendix_table(vm.valuation_model_table)}
</div>
"""


# Backend blocker/missing-field codes → client-facing Vietnamese reasons.
# Audit rule: never surface raw gate keys in the client output.
_BLOCKER_REASONS_VI: dict[str, str] = {
    "blend_is_draft_only": "Mô hình định giá hợp nhất (FCFF/FCFE) mới ở trạng thái nháp, chưa được phê duyệt.",
    "valuation_gap_gt_25pct": "Chênh lệch giữa định giá FCFF và FCFE vượt ngưỡng kiểm định (>25%), cần soát lại giả định nợ vay, CAPEX và vốn lưu động.",
    "valuation_result_not_publishable": "Kết quả định giá chưa đủ điều kiện công bố (chưa tái lập được giá mục tiêu từ giả định đã khóa).",
    "current_price": "Thiếu giá thị trường hiện tại đã xác thực.",
    "target_price": "Chưa tính được giá mục tiêu hợp lệ.",
    "upside_downside": "Chưa xác định được tiềm năng tăng/giảm.",
    "forecast_years": "Thiếu bảng dự phóng 5 năm hợp lệ.",
    "fcff_table": "Thiếu bảng dòng tiền FCFF chi tiết.",
    "price_chart": "Thiếu biểu đồ diễn biến giá.",
    "shares_outstanding": "Thiếu số lượng cổ phiếu đang lưu hành đã xác thực (EPS không reconcile được).",
    "approval_status": "Chưa có phê duyệt của chuyên viên phân tích cho các giả định định giá.",
}

_REQUIRED_ACTIONS_VI: list[str] = [
    "Nạp tài liệu công bố chính thức: BCTC kiểm toán, BCTC quý gần nhất, nghị quyết/biên bản ĐHĐCĐ, công bố cổ tức và corporate action.",
    "Reconcile P&L (Doanh thu → EBITDA → EBIT → PBT → Thuế → LNST) và EPS theo số cổ phiếu bình quân/pha loãng.",
    "Hoàn thiện debt schedule, dividend schedule, cash sweep và equity roll-forward trước khi định giá.",
    "Tái lập giá mục tiêu từ valuation_result (FCFF/FCFE bridge, WACC/Re, terminal value, net-debt & share bridge).",
    "Chuyên viên phân tích phê duyệt giả định định giá; chỉ khi đó mới công bố khuyến nghị và giá mục tiêu.",
]


def _is_publishable(vm: ClientReportViewModel) -> bool:
    """Render the full analytical report only when valuation is genuinely usable.

    Signal is the valuation itself: a valid target price. The display gate already
    forces ``target_price`` to None whenever any valuation blocker fires
    (not publishable / draft-only / gap > 25%), so an available target price is the
    single authoritative "valuation is usable" signal. A missing *cosmetic* field
    (e.g. price chart) must NOT demote the whole report to a review dashboard.
    NOTE: ``publication_status`` is client-final specific (always
    'analyst_review_only' in analyst_draft) and is deliberately NOT used here.
    """
    return vm.target_price is not None and not vm.display_blocking_reasons


def _review_reasons(vm: ClientReportViewModel) -> list[str]:
    codes = list(dict.fromkeys(list(vm.display_blocking_reasons) + list(vm.missing_required_fields)))
    reasons = [_BLOCKER_REASONS_VI.get(c) for c in codes]
    reasons = [r for r in reasons if r]
    if not reasons:
        reasons = ["Mô hình định giá chưa đủ điều kiện công bố; cần chuyên viên rà soát."]
    return reasons


def _review_dashboard_pages(vm: ClientReportViewModel) -> list[tuple[str, str, str, list[str]]]:
    """Render an internal review/audit dashboard instead of a full equity-research report.

    Governance: when valuation is not publishable, the output must NOT look like a
    finished analyst report (audit BLOCKER-02 / GOAL_OUTPUT gating). It shows data
    inventory, failed checks and required actions only.
    """
    reasons = "".join(f"<li>{_e(r)}</li>" for r in _review_reasons(vm))
    actions = "".join(f"<li>{_e(a)}</li>" for a in _REQUIRED_ACTIONS_VI)
    cp = "—" if vm.current_price is None else f"{vm.current_price.amount:,.0f} VND"
    mc = vm.market_statistics.get("Vốn hóa")
    mc_str = f"{mc:,.0f} tỷ" if isinstance(mc, (int, float)) else "—"
    shares = vm.market_statistics.get("Số lượng cổ phiếu")
    shares_str = f"{shares:,.1f} triệu" if isinstance(shares, (int, float)) else "—"

    page1 = f"""
<div class="client-report-page">
  <div class="draft-banner">{_e(vm.ticker)} — CẦN CHUYÊN VIÊN RÀ SOÁT (chưa đủ điều kiện công bố báo cáo phân tích)</div>
  <h1>{_e(vm.ticker)} — Bản rà soát nội bộ</h1>
  <p><strong>{_e(vm.company_name)}</strong> · {_e(vm.exchange)} · {_e(vm.report_date)}</p>
  <p>{_e(_client_status_sentence(vm))}</p>
  <h2>Lý do chưa thể công bố</h2>
  <ol class="source-list">{reasons}</ol>
  <h2>Thông tin thị trường (tham chiếu)</h2>
  <table class="broker-side-table"><tbody>
    <tr><td>Giá hiện tại</td><td>{_e(cp)}</td></tr>
    <tr><td>Vốn hóa</td><td>{_e(mc_str)}</td></tr>
    <tr><td>Số lượng cổ phiếu</td><td>{_e(shares_str)}</td></tr>
    <tr><td>Giá mục tiêu</td><td>Chưa công bố</td></tr>
  </tbody></table>
  {_chart(vm, "C1")}
  <h2>Hành động cần thực hiện trước khi tạo báo cáo</h2>
  <ol class="source-list">{actions}</ol>
</div>
"""
    if _table_has_data(vm.financial_summary_table):
        fin_block = (
            "<p>Các số liệu dưới đây là dữ liệu lịch sử đã ingest, chỉ dùng để rà soát; "
            "chưa phải kết luận định giá.</p>"
            + _render_table(vm.financial_summary_table)
        )
    else:
        fin_block = (
            "<p>Dữ liệu tài chính lịch sử chưa được nạp đầy đủ. Cần chạy lại quy trình "
            "ingest với nguồn chính thức (BCTC kiểm toán) trước khi rà soát số liệu — "
            "hiện chưa có canonical facts hợp lệ cho kỳ phân tích.</p>"
        )
    page2 = f"""
<div class="client-report-page">
  <h1>Dữ liệu lịch sử đã thu thập (kiểm chứng)</h1>
  {fin_block}
  <h2>Nguồn tham khảo</h2>
  {_render_key_sources(vm)}
  <h2>Tuyên bố miễn trừ trách nhiệm</h2>
  <p>{_e(vm.disclaimer)}</p>
</div>
"""
    return [
        ("review_summary", "Bản rà soát nội bộ", page1, ["C1"]),
        ("review_data", "Dữ liệu & nguồn", page2, []),
    ]


def build_client_report_sections(vm: ClientReportViewModel) -> list[dict[str, Any]]:
    # (page_id, title_vi, html, chart_ids, chapter_break)
    # chapter_break=True → explicit page break before a major editorial chapter.
    # The cover does not force a break, and related sub-sections now flow inside
    # each chapter to avoid sparse, mechanical pagination.
    pages: list[tuple[str, str, str, list[str], bool]] = [
        ("snapshot",             "Tổng quan đầu tư",                    _snapshot_page(vm),              ["C1"],                False),
        ("business_financials",  "Triển vọng kinh doanh và tài chính",  _business_financials_page(vm),   ["C2", "C4", "C5"],    True),
        ("valuation",            "Định giá và độ nhạy",                _valuation_page(vm),             [],                    True),
        ("risks_sources",        "Rủi ro và nguồn tham khảo",          _risks_sources_page(vm),         [],                    False),
        ("appendix",             "Phụ lục bảng tài chính",             _appendix_page(vm),              [],                    True),
    ]
    sections: list[dict[str, Any]] = []
    for index, (page, title, html, chart_ids, chapter_break) in enumerate(pages, start=1):
        sections.append(
            {
                "page": page,
                "page_number": index,
                "title": title,
                "markdown": html,
                "chart_ids": main_report_chart_ids(chart_ids),
                "word_count": len(html.split()),
                "chapter_break": chapter_break,
            }
        )
    return sections
