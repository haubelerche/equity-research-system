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


def _with_refs(value: Any, refs: str) -> str:
    """Attach source markers to client-facing qualitative assertions."""
    text = str(value or "").strip()
    if not text:
        return text
    if text.endswith(refs) or any(text.endswith(f"[{idx}]") for idx in range(1, 10)):
        return text
    return f"{text} {refs}"


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
    method_note = (
        '\n  <div class="rec-draft-note">Giá mục tiêu và khuyến nghị được tính từ mô hình định lượng; xem trang giải trình phương pháp ở cuối báo cáo</div>'
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
  </div>{method_note}
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
    <div class="fpts-cover-brand">Nghiên cứu cổ phiếu</div>
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
      <div class="lead-thesis">{_e(_with_refs(_excerpt(vm.investment_thesis, 1050), "[1][2]"))}</div>
      <h2>Luận điểm cập nhật</h2>
      <p>{_e(_with_refs(_excerpt(vm.latest_business_update, 900), "[1][3]"))}</p>
      <h2>Động lực tăng trưởng</h2>
      <p>{_e(_with_refs(_excerpt(vm.key_growth_drivers, 700), "[1][3]"))}</p>
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
  <p>{_e(_with_refs(vm.key_growth_drivers, "[1][3]"))}</p>
  <h2>Động lực biên lợi nhuận</h2>
  <p>{_e(_with_refs(vm.key_margin_drivers, "[1][3]"))}</p>
  <h2>Sự kiện trọng yếu</h2>
  <p>{_e(_with_refs(vm.material_events, "[1][3]"))}</p>
  {_render_table(vm.key_forecast_drivers_table)}
</div>
"""


def _forecast_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>Dự phóng và định giá</h1>
  <p>{_e(_with_refs(vm.forecast_valuation_narrative, "[1][2]"))}</p>
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
        return "<p>Nguồn dữ liệu sẽ được bổ sung khi tài liệu nguồn được nạp.</p>"
    items = "".join(f"<li>{_e(s.get('label', ''))}</li>" for s in vm.key_sources)
    return f'<ol class="source-list">{items}</ol>'


def _render_methodology_sources(vm: ClientReportViewModel) -> str:
    base_sources = "".join(
        f"<li>{_e(s.get('label', ''))}</li>"
        for s in getattr(vm, "key_sources", [])
        if s.get("label")
    )
    base_sources_block = (
        '<p><strong>Nguồn dữ liệu cụ thể trong bản này:</strong></p>'
        f'<ol class="source-list">{base_sources}</ol>'
        if base_sources
        else ""
    )
    return (
        '<ol class="source-list">'
        "<li><strong>[1]</strong> Dữ liệu tài chính công ty, dữ liệu thị trường và các bảng đã chuẩn hóa trong quy trình xử lý; dùng cho nhận định về doanh thu, lợi nhuận, dòng tiền, nợ, vốn lưu động, biên lợi nhuận và định giá.</li>"
        "<li><strong>[2]</strong> Mô hình định giá nội bộ; dùng cho dự phóng dòng tiền tự do doanh nghiệp, dòng tiền tự do cổ đông, chi phí vốn bình quân, giá trị cuối kỳ, nợ ròng, số cổ phiếu và giá mục tiêu.</li>"
        "<li><strong>[3]</strong> Mô-đun tin tức; chỉ dùng cho nhận định định tính về sự kiện tác động, rủi ro và động lực kinh doanh khi có bài báo đã nạp từ VnExpress, VnEconomy, CafeF hoặc Vietstock. Bản DHG hiện tại không dùng bài báo riêng lẻ làm nguồn trực tiếp cho số liệu định lượng.</li>"
        "</ol>"
        + base_sources_block
    )


def _business_financials_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>Triển vọng kinh doanh và tài chính</h1>
  {_section_block("Cập nhật hoạt động kinh doanh", f"<p>{_e(_with_refs(vm.latest_business_update, '[1][3]'))}</p>")}
  <div class="two-chart-grid">
    {_chart(vm, "C2")}
    {_chart(vm, "C4")}
  </div>
  {_section_block("Kết quả tài chính chính", f"<p>{_e(_with_refs(vm.current_context, '[1]'))}</p>{_render_main_table(vm.financial_summary_table)}")}
  {_section_block("Động lực dự phóng", f"<p>{_e(_with_refs(vm.key_growth_drivers, '[1][3]'))}</p><p>{_e(_with_refs(vm.key_margin_drivers, '[1][3]'))}</p>{_chart(vm, 'C5')}{_render_table(vm.key_forecast_drivers_table, 'financial-model-table driver-table')}", "driver-section")}
</div>
"""


def _valuation_page(vm: ClientReportViewModel) -> str:
    peer = _render_table(vm.peer_table, "financial-model-table peer-table") if vm.peer_table is not None else ""
    return f"""
<div class="client-report-page">
  <h1>Định giá và độ nhạy</h1>
  {_section_block("Luận điểm định giá", f"<p>{_e(_with_refs(vm.forecast_valuation_narrative, '[1][2]'))}</p>")}
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
  <h1>Rủi ro đầu tư</h1>
  {_section_block("Yếu tố cần theo dõi", f"<p>{_e(_with_refs(vm.material_events, '[1][3]'))}</p>")}
  <div class="fpts-section">
  <div class="fpts-section-title">Rủi ro đầu tư</div>
  <table class="financial-model-table">
    <thead><tr><th>Rủi ro</th>{''.join(f'<th>{_e(p)}</th>' for p in vm.risk_table.periods)}</tr></thead>
    <tbody>{risk_body}</tbody>
  </table>
  </div>
</div>
"""


def _client_status_sentence(vm: ClientReportViewModel) -> str:
    """Client-facing status line — no backend tokens (gate keys, artifact names) in the PDF.

    Audit rule: client-facing report must not leak backend jargon such as
    'analyst_review_only; blockers: valuation_gap_gt_25pct'.
    """
    return (
        "Hệ thống tổng hợp dữ liệu tài chính, dữ liệu thị trường, bằng chứng tin tức "
        "và mô hình định giá để tạo ra kết luận định lượng; người đọc có thể kiểm tra "
        "chuỗi dữ liệu, công thức và ngưỡng quyết định bên dưới để tự đánh giá mức độ tin cậy."
    )


def _render_report_status(vm: ClientReportViewModel) -> str:
    """Render the method and decision explanation in client-facing Vietnamese."""
    intro = _e(_client_status_sentence(vm))
    current_price = _format_price(vm.current_price)
    target_price = _format_price(vm.target_price)
    upside = _format_percent(vm.upside_downside)
    total_return = _format_percent(vm.total_return)

    rows = [
        (
            "Dữ liệu định lượng",
            "Số liệu doanh thu, lợi nhuận, dòng tiền, nợ vay, tiền mặt, số cổ phiếu và giá thị trường được lấy từ lớp dữ liệu tài chính chuẩn hóa và dữ liệu thị trường; tin tức không được dùng làm nguồn số liệu định lượng trực tiếp.",
        ),
        (
            "Tin tức và sự kiện tác động",
            "Mô-đun tin tức chỉ thu thập bằng chứng từ danh sách nguồn được phép gồm VnExpress, VnEconomy, CafeF và Vietstock; bài báo chỉ được dùng để giải thích sự kiện tác động, rủi ro, động lực kinh doanh hoặc điều kiện bác bỏ luận điểm khi có bằng chứng liên kết.",
        ),
        (
            "Cách tính giá mục tiêu",
            "Mô hình dự phóng doanh thu, biên lợi nhuận, vốn lưu động, chi đầu tư và thuế để tính dòng tiền tự do doanh nghiệp/cổ đông (FCFF/FCFE); sau đó chiết khấu bằng chi phí vốn bình quân, cộng giá trị cuối kỳ, điều chỉnh nợ ròng và chia cho số cổ phiếu để ra giá mục tiêu.",
        ),
        (
            "Cách ra khuyến nghị",
            "Tổng lợi suất kỳ vọng = tiềm năng tăng/giảm giá + suất sinh lợi cổ tức; MUA nếu >20%, BÁN nếu <-10%, còn lại là NẮM GIỮ.",
        ),
        (
            "Kết quả hiện tại",
            f"Giá hiện tại {current_price} VND, giá mục tiêu {target_price} VND, tiềm năng tăng/giảm {upside}, tổng lợi suất kỳ vọng {total_return}, khuyến nghị hệ thống: {vm.recommendation}.",
        ),
        (
            "Cách kiểm tra đúng sai",
            "Người đọc có thể đối chiếu từng giả định trong bảng dự phóng, bảng định giá, ma trận độ nhạy và nguồn tham khảo; nếu không đồng ý với giả định chi phí vốn bình quân, tăng trưởng dài hạn, biên lợi nhuận hoặc vốn lưu động, có thể thay đổi giả định và kết luận định giá sẽ thay đổi tương ứng.",
        ),
    ]
    table_rows = "".join(
        f"<tr><td>{_e(label)}</td><td>{_e(value)}</td></tr>"
        for label, value in rows
    )
    body = (
        f"<p>{intro}</p>"
        '<table class="financial-model-table report-status-table">'
        "<thead><tr><th>Hạng mục</th><th>Diễn giải</th></tr></thead>"
        f"<tbody>{table_rows}</tbody></table>"
    )

    reasons = _review_reasons(vm)
    items = "".join(f"<li>{_e(reason)}</li>" for reason in reasons[:5])
    return (
        body
        + f"<p><strong>Các điểm nhạy cảm cần người đọc kiểm tra khi sử dụng kết quả:</strong></p>"
        + f"<ol class=\"source-list\">{items}</ol>"
    )


def _report_status_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page report-status-page">
  <h1>Giải trình phương pháp và quyết định</h1>
  {_section_block("Hệ thống tính toán và ra quyết định như thế nào", _render_report_status(vm))}
  {_section_block("Chú giải nguồn trích dẫn", _render_methodology_sources(vm))}
  {_section_block("Tuyên bố miễn trừ trách nhiệm", f"<p>{_e(vm.disclaimer)}</p>")}
</div>
"""


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
    "blend_is_draft_only": "Mô hình định giá hợp nhất giữa dòng tiền tự do doanh nghiệp và dòng tiền tự do cổ đông đang phụ thuộc vào giả định cấu trúc vốn; người đọc nên kiểm tra cầu nối định giá trước khi sử dụng kết quả.",
    "valuation_gap_gt_25pct": "Chênh lệch giữa định giá dòng tiền tự do doanh nghiệp và dòng tiền tự do cổ đông vượt ngưỡng kiểm định (>25%), cần soát lại giả định nợ vay, chi đầu tư và vốn lưu động.",
    "valuation_result_not_publishable": "Kết quả định giá cần được đối chiếu lại với bảng giả định và cầu nối giá mục tiêu để xác nhận khả năng tái lập.",
    "current_price": "Thiếu giá thị trường hiện tại đã xác thực.",
    "target_price": "Chưa tính được giá mục tiêu hợp lệ.",
    "upside_downside": "Chưa xác định được tiềm năng tăng/giảm.",
    "forecast_years": "Thiếu bảng dự phóng 5 năm hợp lệ.",
    "fcff_table": "Thiếu bảng dòng tiền FCFF chi tiết.",
    "price_chart": "Thiếu biểu đồ diễn biến giá.",
    "shares_outstanding": "Thiếu số lượng cổ phiếu đang lưu hành đã xác thực (EPS không reconcile được).",
    "approval_status": "Giả định định giá là điểm người đọc cần tự kiểm tra: chi phí vốn, tăng trưởng dài hạn, vốn lưu động, nợ vay và số cổ phiếu quyết định trực tiếp giá mục tiêu.",
}

def _review_reasons(vm: ClientReportViewModel) -> list[str]:
    codes = list(dict.fromkeys(list(vm.display_blocking_reasons) + list(vm.missing_required_fields)))
    reasons = [_BLOCKER_REASONS_VI.get(c) for c in codes]
    reasons = [r for r in reasons if r]
    if not reasons:
        reasons = ["Mô hình định giá cần được đối chiếu thêm để xác nhận khả năng tái lập của kết quả."]
    return reasons


def build_client_report_sections(vm: ClientReportViewModel) -> list[dict[str, Any]]:
    # (page_id, title_vi, html, chart_ids, chapter_break)
    # chapter_break=True → explicit page break before a major editorial chapter.
    # The cover does not force a break, and related sub-sections now flow inside
    # each chapter to avoid sparse, mechanical pagination.
    pages: list[tuple[str, str, str, list[str], bool]] = [
        ("snapshot",             "Tổng quan đầu tư",                    _snapshot_page(vm),              ["C1"],                False),
        ("business_financials",  "Triển vọng kinh doanh và tài chính",  _business_financials_page(vm),   ["C2", "C4", "C5"],    True),
        ("valuation",            "Định giá và độ nhạy",                _valuation_page(vm),             [],                    True),
        ("risks_sources",        "Rủi ro đầu tư",                      _risks_sources_page(vm),         [],                    False),
        ("appendix",             "Phụ lục bảng tài chính",             _appendix_page(vm),              [],                    True),
        ("report_status",        "Giải trình phương pháp và quyết định", _report_status_page(vm),       [],                    True),
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
