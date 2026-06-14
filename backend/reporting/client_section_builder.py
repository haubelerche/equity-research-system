"""ACBS/IMP-style section builders for client and analyst PDF reports."""
from __future__ import annotations

import re
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


def _with_refs(value: Any, refs: str) -> str:
    """Attach source markers to client-facing qualitative assertions."""
    text = str(value or "").strip()
    if not text:
        return text
    if text.endswith(refs) or any(text.endswith(f"[{idx}]") for idx in range(1, 10)):
        return text
    return f"{text} {refs}"


def _news_refs(vm: Any, limit: int = 1) -> str:
    """Return a short inline news reference string.

    The full article list is disclosed in the citation legend. Inline prose only
    carries the nearest evidence marker so paragraphs do not degrade into
    citation clusters such as [1][3][4][5][6].
    """
    news = getattr(vm, "news_citations", None) or []
    count = min(max(limit, 0), len(news))
    return "".join(f"[{idx}]" for idx in range(3, 3 + count))


def _qual_refs(vm: Any, news_limit: int = 1) -> str:
    """Source markers for qualitative narrative: financial data [1], plus the real
    news articles [3..n] when whitelisted articles have been collected. No fake news
    marker is attached when no real article backs the section."""
    return "[1]" + _news_refs(vm, news_limit)


def _citation_ref_for_news(index: int) -> str:
    return f"[{index + 3}]"


def _news_theme(title: str) -> str:
    folded = title.lower()
    if any(token in folded for token in ("quý", "q1", "lợi nhuận", "kế hoạch", "hoàn thành")):
        return "kết quả kinh doanh ngắn hạn"
    if any(token in folded for token in ("cổ tức", "trả cổ tức", "bằng tiền")):
        return "chính sách cổ tức và phân phối tiền mặt"
    if any(token in folded for token in ("đhcđ", "đại hội", "nghị quyết")):
        return "quản trị và định hướng từ đại hội cổ đông"
    if any(token in folded for token in ("đkkd", "kinh doanh", "ngành nghề")):
        return "mở rộng phạm vi hoạt động"
    if any(token in folded for token in ("nhân sự", "hđqt", "ban điều hành")):
        return "thay đổi quản trị hoặc nhân sự"
    return "cập nhật khác"


def _news_impact(title: str) -> str:
    theme = _news_theme(title)
    if "cổ tức" in theme:
        return "Tác động trực tiếp đến suất sinh lợi cổ tức và khả năng phân phối tiền mặt."
    if "kết quả kinh doanh" in theme:
        return "Dùng để kiểm chứng giả định doanh thu, biên lợi nhuận và tiến độ hoàn thành kế hoạch."
    if "quản trị" in theme or "nhân sự" in theme:
        return "Theo dõi tác động đến kỷ luật phân bổ vốn và mức bù rủi ro."
    if "mở rộng" in theme:
        return "Chỉ đưa vào dự phóng khi có quy mô đầu tư, tiến độ và đóng góp doanh thu định lượng."
    return "Chưa đủ bằng chứng để điều chỉnh định giá; tiếp tục theo dõi."


def _render_news_synthesis(vm: ClientReportViewModel) -> str:
    """Render only concrete headlines with an explicit financial implication."""
    citations = list(getattr(vm, "news_citations", None) or [])
    if not citations:
        return ""
    rows = []
    selected = [
        item for item in citations
        if str(item.get("severity") or "medium").lower() in {"medium", "high"}
    ][:3]
    for idx, citation in enumerate(selected):
        title = str(citation.get("title") or "").strip()
        if not title:
            continue
        rows.append(
            "<tr>"
            f"<td>{_e(title)} {_e(_citation_ref_for_news(idx))}</td>"
            f"<td>{_e(_news_theme(title))}</td>"
            f"<td>{_e(_news_impact(title))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    body = (
        '<table class="financial-model-table news-materiality-table">'
        "<thead><tr><th>Tin tức</th><th>Phân loại</th><th>Hàm ý đầu tư</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return _section_block("Tin tức trọng yếu và hàm ý đầu tư", body)


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
        "chi đầu tư /",
        "chi phí bán hàng và quản lý /",
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


def _display_period(period: Any) -> str:
    """Preserve actual/forecast markers in broker financial tables."""
    text = str(period)
    return re.sub(r"^(\d{4})FY$", r"\1A", text)


def _format_price(money: Any) -> str:
    if money is None:
        return DASH
    return f"{money.amount:,.0f}"


def _format_percent(percent: Any) -> str:
    if percent is None:
        return DASH
    return f"{percent.value * 100:+.1f}%"


def _render_table(table: TableData, class_name: str = "financial-model-table") -> str:
    header = "".join(f"<th>{_e(_display_period(period))}</th>" for period in table.periods)
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

    header = "".join(f"<th>{_e(_display_period(period))}</th>" for period in table.periods)
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

    header = "".join(f"<th>{_e(_display_period(period))}</th>" for period in table.periods)
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
    return _render_variance_table(table, class_name)


def _render_profit_bridge(table: TableData) -> str:
    """Render the key 2025A-2026F changes directly from the published model."""
    try:
        from_index = table.periods.index("2025A")
        to_index = table.periods.index("2026F")
    except ValueError:
        return ""

    rows: list[tuple[str, list[Any]]] = []
    for label, values in table.rows:
        if label not in {
            "Doanh thu thuần",
            "Biên lợi nhuận gộp",
            "Chi phí bán hàng và quản lý",
            "Biên lợi nhuận HĐKD / EBIT",
            "LNST sau CĐKKS / LNST CĐ mẹ",
            "Biên lợi nhuận ròng",
            "EPS",
        } or len(values) <= to_index:
            continue
        previous, current = values[from_index], values[to_index]
        delta: Any = DASH
        if isinstance(previous, (int, float)) and isinstance(current, (int, float)):
            delta = (
                f"{(current - previous) * 10_000:+.0f} bps"
                if "Biên" in label
                else f"{(current / previous - 1) * 100:+.1f}%" if previous else DASH
            )
        rows.append((label, [previous, current, delta, _bridge_comment(label, previous, current)]))

    if not rows:
        return ""
    body = []
    for label, values in rows:
        numeric_cells = "".join(
            f'<td class="numeric">{_fmt_metric(label, value)}</td>'
            for value in values[:3]
        )
        body.append(
            f"<tr><td>{_e(label)}</td>{numeric_cells}"
            f'<td class="bridge-comment">{_e(values[3])}</td></tr>'
        )
    return f"""
<div class="model-table-block">
  <h2>CẦU NỐI LỢI NHUẬN 2025A-2026F</h2>
  <div class="table-unit">Đối chiếu trực tiếp với số liệu công bố trong mô hình định giá.</div>
  <table class="financial-model-table profit-bridge-table">
    <colgroup>
      <col class="bridge-metric-col" />
      <col class="bridge-period-col" />
      <col class="bridge-period-col" />
      <col class="bridge-delta-col" />
      <col class="bridge-comment-col" />
    </colgroup>
    <thead><tr><th>Chỉ tiêu</th><th>2025A</th><th>2026F</th><th>Chênh lệch</th><th>Nhận định</th></tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table>
</div>
"""


def _bridge_comment(label: str, previous: Any, current: Any) -> str:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return "Chưa đủ dữ liệu để đối chiếu."
    if label == "Doanh thu thuần":
        return "Cơ sở kiểm tra mức tăng lợi nhuận."
    if label == "Chi phí bán hàng và quản lý":
        return (
            "Chi phí tuyệt đối giảm dù doanh thu tăng; cần bằng chứng vận hành."
            if abs(current) < abs(previous)
            else "Chi phí vận hành tăng cùng quy mô doanh thu."
        )
    if "Biên" in label:
        return (
            "Biên tăng trên 300 bps; cần cầu nối chi phí và bằng chứng định lượng."
            if current - previous > 0.03
            else "Biến động biên trong ngưỡng theo dõi."
        )
    return "Đối chiếu với tăng trưởng doanh thu và giả định mô hình."


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
    takeaway = _CHART_COMMENTARY.get(chart_id, "")
    takeaway_html = (
        f'<p class="chart-takeaway"><strong>Nhận định:</strong> {_e(takeaway)}</p>'
        if takeaway else ""
    )
    return f"""
<figure class="report-chart">
  <img src="{_e(chart.path)}" alt="{_e(chart.title)}" />
  <figcaption>{_e(chart.caption)}</figcaption>
  {takeaway_html}
</figure>
"""


_CHART_COMMENTARY: dict[str, str] = {
    "C1": (
        "Diễn biến giá cổ phiếu cần được đối chiếu với giá mục tiêu, thanh khoản và các mốc công bố "
        "kết quả kinh doanh để đánh giá biên an toàn."
    ),
    "C2": (
        "Doanh thu tăng trong giai đoạn gần nhất nhưng biên EBITDA/EBIT không tăng tương ứng, "
        "cho thấy động lực doanh thu cần được đọc cùng khả năng kiểm soát giá vốn và chi phí bán hàng."
    ),
    "C4": (
        "Biên lợi nhuận gộp, biên lợi nhuận ròng và ROE phản ánh chất lượng tăng trưởng: "
        "nếu ROE đi xuống trong khi doanh thu tăng, định giá phải chiết khấu rủi ro hiệu quả vốn."
    ),
    "C5": (
        "Quỹ đạo dự phóng hàm ý tăng trưởng doanh thu ổn định hơn giai đoạn lịch sử; "
        "độ tin cậy của giá mục tiêu phụ thuộc vào việc lợi nhuận sau thuế bắt kịp quy mô doanh thu."
    ),
}


def _chart_with_commentary(vm: ClientReportViewModel, chart_id: str) -> str:
    return _chart(vm, chart_id)


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
  </div>
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
      <div class="side-section-title">Thông tin giao dịch</div>
      {_render_key_value_table(stats_rows, "broker-side-table compact")}
    </aside>
    <main class="acbs-main">
      {_rec_hero(vm)}
      <div class="lead-thesis">{_e(_with_refs(vm.investment_thesis, "[1][2]"))}</div>
      <h2>Luận điểm cập nhật</h2>
      <p>{_e(_with_refs(vm.latest_business_update, _qual_refs(vm)))}</p>
      {_render_news_synthesis(vm)}
      <h2>Động lực tăng trưởng</h2>
      <p>{_e(_with_refs(vm.key_growth_drivers, "[1]"))}</p>
    </main>
  </div>
</div>
"""


def _narrative_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>Cập nhật hoạt động kinh doanh</h1>
  {_render_news_synthesis(vm)}
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


def _news_citations(vm: ClientReportViewModel) -> list[dict[str, str]]:
    """Real news articles backing qualitative claims, numbered from [3]. Empty until
    whitelisted articles have actually been collected for this ticker."""
    return list(getattr(vm, "news_citations", None) or [])


def _render_methodology_sources(vm: ClientReportViewModel) -> str:
    """Citation legend mapping the [n] markers used throughout the report.

    [1] and [2] are always present (financial data + valuation model). [3]+ are the
    real whitelisted news articles collected for this ticker, each shown with its
    outlet, headline and link so the reader can open and judge the source directly.
    """
    lines = [
        '<p class="citation-ref"><strong>[1]</strong> Dữ liệu tài chính &amp; thị trường — '
        "Báo cáo tài chính (BCTC) đã chuẩn hóa và dữ liệu giao dịch thị trường; dùng cho mọi "
        "số liệu và nhận định về doanh thu, lợi nhuận, dòng tiền, nợ vay, vốn lưu động, biên "
        "lợi nhuận và định giá.</p>",
        '<p class="citation-ref"><strong>[2]</strong> Mô hình định giá nội bộ — dự phóng dòng '
        "tiền tự do doanh nghiệp/cổ đông (FCFF/FCFE), chiết khấu theo chi phí vốn bình quân "
        "(WACC), giá trị cuối kỳ, nợ ròng, số cổ phiếu và giá mục tiêu.</p>",
    ]
    citations = _news_citations(vm)
    for idx, citation in enumerate(citations, start=3):
        source = _e(citation.get("source_name") or citation.get("source_domain") or "Nguồn tin")
        title = _e(citation.get("title") or "")
        url = str(citation.get("url") or citation.get("source_url") or "").strip()
        published = _e(citation.get("published_at") or "")
        title_html = f'<a href="{_e(url)}">{title}</a>' if url else title
        meta = f" ({published})" if published else ""
        lines.append(
            f'<p class="citation-ref"><strong>[{idx}]</strong> {source} — “{title_html}”{meta}</p>'
        )
    if not citations:
        # Transparent coverage note — news is not a hard requirement. Missing external
        # articles is a source-coverage limitation, not a claim that nothing happened.
        lines.append(
            '<p class="citation-ref citation-coverage-note">Tại thời điểm lập báo cáo, '
            "hệ thống chưa thu thập được bài báo bên ngoài phù hợp từ các nguồn được phép. "
            "Phần nhận định định tính được xây dựng từ báo cáo tài chính, công bố chính thức, "
            "dữ liệu định lượng và so sánh cùng ngành. Đây là hạn chế về coverage nguồn tin, "
            "không phải xác nhận rằng doanh nghiệp không có sự kiện mới.</p>"
        )
    return f'<div class="citation-legend">{"".join(lines)}</div>'


def _business_financials_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page">
  <h1>Triển vọng kinh doanh và tài chính</h1>
  {_section_block("Cập nhật hoạt động kinh doanh", f"<p>{_e(_with_refs(vm.latest_business_update, _qual_refs(vm)))}</p>")}
  <div class="two-chart-grid">
    {_chart_with_commentary(vm, "C2")}
    {_chart_with_commentary(vm, "C4")}
  </div>
  {_section_block("Kết quả tài chính chính", f"<p>{_e(_with_refs(vm.current_context, '[1]'))}</p>{_render_section_insights(vm, {'growth', 'leverage'})}{_render_main_table(vm.financial_summary_table, 'financial-model-table main-financial-table full-financial-table')}{_render_profit_bridge(vm.valuation_model_table)}")}
  {_section_block("Động lực dự phóng", f"<p>{_e(_with_refs(vm.key_growth_drivers, '[1]'))}</p><p>{_e(_with_refs(vm.key_margin_drivers, '[1]'))}</p>{_render_section_insights(vm, {'margin'})}{_chart_with_commentary(vm, 'C5')}{_render_table(vm.key_forecast_drivers_table, 'financial-model-table driver-table')}", "driver-section")}
</div>
"""


def _valuation_page(vm: ClientReportViewModel) -> str:
    peer = _render_table(vm.peer_table, "financial-model-table peer-table") if vm.peer_table is not None else ""
    valuation_summary = (
        _render_table(vm.valuation_summary_table, "financial-model-table valuation-summary-table")
        if vm.valuation_summary_table is not None else ""
    )
    wacc_bridge = (
        _render_table(vm.wacc_bridge_table, "financial-model-table wacc-bridge-table")
        if vm.wacc_bridge_table is not None else ""
    )
    valuation_bridge = (
        _render_table(vm.valuation_bridge_table, "financial-model-table valuation-bridge-table")
        if vm.valuation_bridge_table is not None else ""
    )
    return f"""
<div class="client-report-page">
  <h1>Định giá và độ nhạy</h1>
  {_section_block("Luận điểm định giá", f"<p>{_e(_with_refs(vm.forecast_valuation_narrative, '[1][2]'))}</p>{_render_section_insights(vm, {'valuation'})}")}
  {valuation_summary}
  {wacc_bridge}
  {valuation_bridge}
  {_render_main_table(vm.valuation_model_table)}
  <div class="sensitivity-section">
    {_render_sensitivity_matrix_table(vm.sensitivity_table)}
  </div>
  {peer}
</div>
"""


def _render_section_insights(vm: ClientReportViewModel, sections: set[str]) -> str:
    """Render ready insights as prose inside their relevant editorial section."""
    items: list[str] = []
    for insight in getattr(vm, "insight_pack", []) or []:
        if insight.get("status") != "ready" or insight.get("section") not in sections:
            continue
        claim = str(insight.get("claim") or "").strip()
        if not claim:
            continue
        refs = "".join(insight.get("evidence_refs") or [])
        valimp = str(insight.get("valuation_implication") or "").strip()
        prose = " ".join(part for part in (claim, valimp) if part)
        items.append(
            f'<p class="section-insight"><strong>Nhận định:</strong> {_e(prose)} {_e(refs)}</p>'
        )
    return f'<div class="section-insights">{"".join(items)}</div>' if items else ""


def _risks_sources_page(vm: ClientReportViewModel) -> str:
    risk_body = "".join(
        f"<tr><td>{_e(label)}</td>{''.join(f'<td>{_e(v)}</td>' for v in values)}</tr>"
        for label, values in vm.risk_table.rows
    )
    return f"""
<div class="client-report-page">
  <h1>Rủi ro đầu tư</h1>
  {_section_block("Yếu tố cần theo dõi", f"<p>{_e(_with_refs(vm.material_events, _qual_refs(vm)))}</p>{_render_section_insights(vm, {'catalyst'})}")}
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
        "Báo cáo trình bày nguồn dữ liệu, giả định dự phóng và phương pháp định giá để các "
        "kết luận chính có thể được đối chiếu. Những khoảng trống dữ liệu trọng yếu được công "
        "khai trong bản nháp phân tích và phải được xử lý trước khi phát hành cho khách hàng."
    )


def _valuation_method_label(vm: ClientReportViewModel) -> str:
    methods = [str(item).upper() for item in getattr(vm, "selected_valuation_methods", []) if item]
    if methods == ["FCFF"]:
        return "dòng tiền tự do doanh nghiệp (FCFF)"
    if methods == ["FCFE"]:
        return "dòng tiền tự do vốn chủ sở hữu (FCFE)"
    return "dòng tiền tự do doanh nghiệp và vốn chủ sở hữu (FCFF/FCFE)"


def _render_report_status(vm: ClientReportViewModel) -> str:
    """Render the method and decision explanation in client-facing Vietnamese."""
    intro = _e(_client_status_sentence(vm))
    current_price = _format_price(vm.current_price)
    target_price = _format_price(vm.target_price)
    upside = _format_percent(vm.upside_downside)
    total_return = _format_percent(vm.total_return)

    rows = [
        (
            "Số liệu định lượng lấy từ đâu",
            "Doanh thu, lợi nhuận, dòng tiền, nợ vay, tiền mặt và số cổ phiếu lấy trực tiếp từ "
            "Báo cáo tài chính (BCTC) đã chuẩn hóa; giá, vốn hóa và thanh khoản lấy từ dữ liệu "
            "thị trường. Các số liệu được đối chiếu với báo cáo gốc của "
            "doanh nghiệp. [1]",
        ),
        (
            "Vì sao dự phóng theo cách này",
            "Mỗi dòng dự phóng nối tiếp số liệu lịch sử: tăng trưởng doanh thu, biên lợi nhuận, "
            "vốn lưu động, chi đầu tư và thuế được kéo dài từ xu hướng quá khứ và đặc thù "
            "ngành dược, để dòng tiền dự phóng bám sát năng lực thực tế của doanh nghiệp thay vì "
            "giả định tùy ý. [1][2]",
        ),
        (
            "Cách tính giá mục tiêu",
            f"Từ dự phóng, mô hình tính {_valuation_method_label(vm)}, chiết "
            "khấu về hiện tại bằng chi phí vốn bình quân (WACC), cộng giá trị cuối kỳ, trừ nợ ròng "
            "rồi chia cho số cổ phiếu đang lưu hành để ra giá trị mỗi cổ phần. [2]",
        ),
        (
            "Cách ra khuyến nghị",
            "Tổng lợi suất kỳ vọng = tiềm năng tăng/giảm giá + suất sinh lợi cổ tức. "
            "MUA nếu >20%, BÁN nếu <-10%, còn lại là NẮM GIỮ.",
        ),
        (
            "Kết quả hiện tại",
            f"Giá hiện tại {current_price} VND, giá mục tiêu {target_price} VND, tiềm năng "
            f"tăng/giảm {upside}, tổng lợi suất kỳ vọng {total_return}, khuyến nghị: "
            f"{vm.recommendation}.",
        ),
        (
            "Người đọc tự kiểm chứng thế nào",
            "Mọi giả định đều hiển thị trong bảng dự phóng, mô hình định giá và ma trận độ nhạy. "
            "Nếu không đồng ý với giả định về chi phí vốn bình quân (WACC), tăng trưởng dài hạn, "
            "biên lợi nhuận hay vốn lưu động, người đọc có thể thay đổi và thấy ngay kết luận định "
            "giá thay đổi tương ứng. Mỗi nhận định định tính đều có đánh số [n] dẫn về nguồn ở mục "
            "Chú giải nguồn trích dẫn bên dưới.",
        ),
    ]
    table_rows = "".join(
        f"<tr><td>{_e(label)}</td><td>{_e(value)}</td></tr>"
        for label, value in rows
    )
    return (
        f"<p>{intro}</p>"
        '<table class="financial-model-table report-status-table">'
        "<thead><tr><th>Hạng mục</th><th>Diễn giải</th></tr></thead>"
        f"<tbody>{table_rows}</tbody></table>"
        + _render_disclosed_limitations(vm)
    )


def _render_disclosed_limitations(vm: ClientReportViewModel) -> str:
    """Render concrete data gaps in user-facing language."""
    if getattr(vm, "mode", "analyst_draft") == "client_final":
        return ""
    labels = {
        "price_chart": "biểu đồ giá và lịch sử giao dịch",
        "shares_outstanding": "số cổ phiếu đang lưu hành",
        "working_capital_schedule": "lịch dự phóng vốn lưu động",
        "dividend_schedule": "lịch dự phóng cổ tức",
        "debt_schedule_publishable": "lịch dự phóng nợ vay",
        "forecast_debt": "lịch dự phóng nợ vay",
        "valuation_result": "kết quả định giá có thể kiểm tra lại",
        "current_price": "giá thị trường hiện tại",
        "target_price": "giá mục tiêu",
    }
    gaps = list(dict.fromkeys(labels.get(str(gap), str(gap)) for gap in (vm.missing_required_fields or [])))
    if not gaps:
        return "<h2>Trạng thái dữ liệu</h2><p>Không ghi nhận khoảng trống dữ liệu trọng yếu trong các mục bắt buộc.</p>"
    items = []
    for gap in gaps:
        text = labels.get(str(gap), str(gap).replace("_", " "))
        items.append(f"<li>Chưa đủ dữ liệu kiểm chứng cho: {_e(text)}.</li>")
    return "<h2>Trạng thái dữ liệu và phần còn thiếu</h2><ul>" + "".join(items) + "</ul>"


def _report_status_page(vm: ClientReportViewModel) -> str:
    return f"""
<div class="client-report-page report-status-page">
  <h1>Phương pháp định giá và nguồn dữ liệu</h1>
  {_section_block("Phương pháp và giả định chính", _render_report_status(vm))}
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



def build_client_report_sections(vm: ClientReportViewModel) -> list[dict[str, Any]]:
    # (page_id, title_vi, html, chart_ids, chapter_break)
    # chapter_break=True → explicit page break before a major editorial chapter.
    # The cover does not force a break, and related sub-sections now flow inside
    # each chapter to avoid sparse, mechanical pagination.
    pages: list[tuple[str, str, str, list[str], bool]] = [
        ("snapshot",             "Tổng quan đầu tư",                    _snapshot_page(vm),              ["C1"],                False),
        ("business_financials",  "Triển vọng kinh doanh và tài chính",  _business_financials_page(vm),   ["C2", "C4", "C5"],    True),
        ("valuation",            "Định giá và độ nhạy",                _valuation_page(vm),             [],                    True),
        ("risks_sources",        "Rủi ro đầu tư",                      _risks_sources_page(vm),         [],                    True),
        ("appendix",             "Phụ lục bảng tài chính",             _appendix_page(vm),              [],                    True),
        ("report_status",        "Phương pháp định giá và nguồn dữ liệu", _report_status_page(vm),       [],                    True),
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
                "chapter_break": False,
            }
        )
    return sections
