"""ACBS/IMP-style section builders for client and analyst PDF reports."""
from __future__ import annotations

import re
import unicodedata
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


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _find_row(table: TableData | None, *tokens: str) -> tuple[str, list[Any]] | None:
    if table is None:
        return None
    folded_tokens = [_fold(token) for token in tokens]
    for label, values in table.rows:
        folded_label = _fold(label)
        if all(token in folded_label for token in folded_tokens):
            return label, values
    return None


def _numeric_points(table: TableData | None, *tokens: str, actual_only: bool = False) -> list[tuple[str, float]]:
    row = _find_row(table, *tokens)
    if not row or table is None:
        return []
    _label, values = row
    points: list[tuple[str, float]] = []
    for period, value in zip(table.periods, values):
        if actual_only and str(period).endswith("F"):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        points.append((_display_period(period), number))
    return points


def _last_two(points: list[tuple[str, float]]) -> tuple[tuple[str, float], tuple[str, float]] | None:
    if len(points) < 2:
        return None
    return points[-2], points[-1]


def _pct_text(value: float | None, signed: bool = False) -> str:
    if value is None:
        return DASH
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value * 100:.1f}%"


def _pp_text(value: float | None, signed: bool = True) -> str:
    if value is None:
        return DASH
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value * 100:.1f} điểm %"


def _growth(prev: float, latest: float) -> float | None:
    if prev == 0:
        return None
    return latest / prev - 1


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


def _target_price_text(vm: ClientReportViewModel) -> str:
    if getattr(vm, "target_price", None) is None:
        return DASH
    return f"{_format_price(vm.target_price)} VND"


def _decision_percent_text(percent: Any) -> str:
    if percent is None:
        return DASH
    return _format_percent(percent)


def _target_price_blocking_summary(vm: ClientReportViewModel, *, limit: int = 2) -> list[str]:
    reasons = [
        str(item)
        for item in (
            list(getattr(vm, "display_blocking_reasons", []) or [])
            + list(getattr(vm, "missing_required_fields", []) or [])
        )
        if str(item).strip()
    ]
    labels: list[str] = []
    for reason in dict.fromkeys(reasons):
        label = _client_issue_label(reason)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= limit:
            break
    return labels or ["Chưa có đủ dữ liệu định giá đã kiểm chứng để công bố giá mục tiêu."]


def _target_price_notice(vm: ClientReportViewModel) -> str:
    if getattr(vm, "target_price", None) is not None:
        return ""
    items = "".join(f"<li>{_e(item)}</li>" for item in _target_price_blocking_summary(vm, limit=3))
    return (
        '<div class="report-status-callout">'
        "<strong>Giá mục tiêu chưa được công bố.</strong>"
        "<p>Hệ thống không hiển thị giá mục tiêu khi mô hình định giá chưa đủ điều kiện kiểm chứng.</p>"
        f"<ul>{items}</ul>"
        "</div>"
    )


def _report_generated_at(vm: ClientReportViewModel) -> str:
    value = str(getattr(vm, "report_generated_at", "") or getattr(vm, "report_date", "") or "").strip()
    return value.replace("T", " ") if value else DASH


def _report_generated_at_compact(vm: ClientReportViewModel) -> str:
    value = _report_generated_at(vm)
    return value[:16] if len(value) >= 16 else value


def _market_price_as_of(vm: ClientReportViewModel) -> str:
    value = str(getattr(vm, "market_price_as_of", "") or "").strip()
    return value if value else DASH


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
    takeaway = _chart_takeaway(vm, chart_id)
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


def _chart_with_commentary(vm: ClientReportViewModel, chart_id: str) -> str:
    return _chart(vm, chart_id)


def _chart_takeaway(vm: ClientReportViewModel, chart_id: str) -> str:
    if chart_id == "C1":
        current = getattr(getattr(vm, "current_price", None), "amount", None)
        target = getattr(getattr(vm, "target_price", None), "amount", None)
        upside = getattr(getattr(vm, "upside_downside", None), "value", None)
        if current is None or target is None or upside is None:
            return "Chưa đủ dữ liệu giá mục tiêu hoặc thị giá để rút ra hàm ý định giá từ biểu đồ giá."
        return (
            f"Thị giá {_fmt_money(current)} VND so với giá mục tiêu {_fmt_money(target)} VND, "
            f"hàm ý {_pct_text(upside, signed=True)}; tín hiệu giá chỉ có giá trị khi đi cùng thanh khoản "
            f"và ngày giá {_market_price_as_of(vm)}."
        )

    if chart_id == "C2":
        revenue = _last_two(_numeric_points(vm.valuation_model_table, "doanh", "thu", actual_only=True))
        ebitda_margin = _last_two(_numeric_points(vm.valuation_model_table, "ebitda", "suat", actual_only=True))
        ebit_margin = _last_two(_numeric_points(vm.valuation_model_table, "ebit", "bien", actual_only=True))
        if not revenue or not ebitda_margin or not ebit_margin:
            return "Chưa đủ chuỗi doanh thu, biên EBITDA và biên EBIT đã kiểm chứng để kết luận xu hướng vận hành."
        (prev_period, prev_revenue), (latest_period, latest_revenue) = revenue
        (_prev_e_period, prev_ebitda), (_latest_e_period, latest_ebitda) = ebitda_margin
        (_prev_b_period, prev_ebit), (_latest_b_period, latest_ebit) = ebit_margin
        rev_growth = _growth(prev_revenue, latest_revenue)
        return (
            f"{latest_period} doanh thu {_fmt_money(latest_revenue)} tỷ đồng, "
            f"tăng {_pct_text(rev_growth, signed=True)} so với {prev_period}; biên EBITDA "
            f"{_pp_text(latest_ebitda - prev_ebitda)} và biên EBIT {_pp_text(latest_ebit - prev_ebit)}. "
            "Nếu doanh thu tăng nhưng hai biên này không mở rộng, luận điểm tăng trưởng phải dựa vào chất lượng chi phí chứ không chỉ vào quy mô."
        )

    if chart_id == "C4":
        gross_margin = _last_two(_numeric_points(vm.valuation_model_table, "bien", "gop", actual_only=True))
        net_margin = _last_two(_numeric_points(vm.valuation_model_table, "bien", "rong", actual_only=True))
        roe = _last_two(_numeric_points(vm.profitability_valuation_table, "roe", actual_only=True))
        if not gross_margin or not net_margin or not roe:
            return "Chưa đủ dữ liệu biên lợi nhuận và ROE đã kiểm chứng để đánh giá chất lượng sinh lời."
        (_gm_prev_period, gm_prev), (gm_period, gm_latest) = gross_margin
        (_nm_prev_period, nm_prev), (_nm_period, nm_latest) = net_margin
        (roe_prev_period, roe_prev), (roe_period, roe_latest) = roe
        return (
            f"{gm_period} biên gộp {_pct_text(gm_latest)} ({_pp_text(gm_latest - gm_prev)} so với kỳ trước), "
            f"biên ròng {_pct_text(nm_latest)} ({_pp_text(nm_latest - nm_prev)}), "
            f"ROE {_pct_text(roe_latest)} ({_pp_text(roe_latest - roe_prev)} so với {roe_prev_period}). "
            "Chênh lệch giữa biên lợi nhuận và ROE là tín hiệu về hiệu quả sử dụng vốn, không phải chỉ là biến động kế toán."
        )

    if chart_id == "C5":
        revenue = _numeric_points(vm.valuation_model_table, "doanh", "thu")
        gross_margin = _numeric_points(vm.valuation_model_table, "bien", "gop")
        actual_revenue = [point for point in revenue if not point[0].endswith("F")]
        forecast_revenue = [point for point in revenue if point[0].endswith("F")]
        actual_margin = [point for point in gross_margin if not point[0].endswith("F")]
        forecast_margin = [point for point in gross_margin if point[0].endswith("F")]
        if not actual_revenue or not forecast_revenue or not actual_margin or not forecast_margin:
            return "Chưa đủ dữ liệu nối tiếp giữa năm thực tế và năm dự phóng để đánh giá độ hợp lý của quỹ đạo dự phóng."
        last_actual_period, last_actual_revenue = actual_revenue[-1]
        first_forecast_period, first_forecast_revenue = forecast_revenue[0]
        (_last_margin_period, last_margin) = actual_margin[-1]
        (_first_margin_period, first_margin) = forecast_margin[0]
        implied_growth = _growth(last_actual_revenue, first_forecast_revenue)
        return (
            f"{first_forecast_period} hàm ý doanh thu tăng {_pct_text(implied_growth, signed=True)} so với {last_actual_period}, "
            f"trong khi biên gộp dự phóng {_pct_text(first_margin)} so với mức thực tế {_pct_text(last_margin)}. "
            "Đây là điểm kiểm tra trọng yếu vì sai lệch nhỏ ở tăng trưởng hoặc biên gộp sẽ truyền trực tiếp vào EBIT và FCFF."
        )

    return ""


_REC_CSS: dict[str, str] = {
    "MUA": "buy",
    "GIỮ": "hold",
    "NẮM GIỮ": "hold", 
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
    tp_display = _target_price_text(vm)
    upside_display = _decision_percent_text(vm.upside_downside)
    return f"""
<div class="recommendation-card {_e(rec_css_class)}">
  <span class="rec-label">Khuyến nghị &nbsp;·&nbsp; {_e(vm.exchange)}: {_e(vm.ticker)}</span>
  <div class="rec-value">{_e(vm.recommendation)}</div>
  <div class="rec-sub">
    Giá mục tiêu: <strong>{_e(tp_display)}</strong>
    &nbsp;|&nbsp;
    Tiềm năng tăng/giảm: <strong>{_e(upside_display)}</strong>
    &nbsp;|&nbsp;
    Ngày giá: {_e(_market_price_as_of(vm))}
    &nbsp;|&nbsp;
    Tạo: {_e(_report_generated_at_compact(vm))}
  </div>
</div>
"""


def _snapshot_page(vm: ClientReportViewModel) -> str:
    sidebar_rows = [
        ("Giá mục tiêu", _target_price_text(vm)),
        ("Giá hiện tại (VND)", _format_price(vm.current_price)),
        ("Ngày giá thị trường", _market_price_as_of(vm)),
        ("Thời điểm tạo báo cáo", _report_generated_at_compact(vm)),
        ("Tỷ lệ tăng/giảm", _decision_percent_text(vm.upside_downside)),
        ("Tổng tỷ suất lợi nhuận", _decision_percent_text(vm.total_return)),
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
  {_target_price_notice(vm)}
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
    # When the peer-relative fallback drives the headline (no DCF leg publishable),
    # name it honestly rather than implying a DCF was used.
    if str(getattr(vm, "headline_valuation_method", "") or "").upper() == "RELATIVE_PE":
        return "định giá tương đối theo P/E doanh nghiệp cùng ngành"
    methods = [str(item).upper() for item in getattr(vm, "selected_valuation_methods", []) if item]
    if methods == ["FCFF"]:
        return "dòng tiền tự do doanh nghiệp (FCFF)"
    if methods == ["FCFE"]:
        return "dòng tiền tự do vốn chủ sở hữu (FCFE)"
    return "dòng tiền tự do doanh nghiệp và vốn chủ sở hữu (FCFF/FCFE)"


def _render_valuation_evidence(vm: ClientReportViewModel) -> str:
    evidence = getattr(vm, "valuation_evidence", {}) or {}
    if not isinstance(evidence, dict):
        return ""
    rows: list[tuple[str, str]] = []
    trace_count = evidence.get("formula_trace_count")
    if trace_count is not None:
        methods = ", ".join(item for item in evidence.get("formula_trace_methods", []) if item) or "không ghi nhận"
        rows.append(("Số vết công thức", f"{trace_count} vết; phương pháp: {methods}"))
    peer_source = evidence.get("peer_data_source")
    if peer_source:
        rows.append(("Nguồn định giá tương đối", _client_evidence_value(peer_source)))
    rv_status = evidence.get("relative_valuation_status")
    if rv_status:
        rows.append(("Trạng thái định giá tương đối", _client_evidence_value(rv_status)))
    market_bridge = evidence.get("market_sanity_bridge") or {}
    if isinstance(market_bridge, dict) and market_bridge:
        rows.append((
            "Đối chiếu thị trường",
            f"Tỷ lệ giá trị mô hình/thị giá={market_bridge.get('target_to_market')}; cầu nối={'có' if market_bridge.get('bridge_present') else 'chưa có'}",
        ))
    headline = evidence.get("headline_target_governance") or {}
    if isinstance(headline, dict) and headline:
        raw = headline.get("raw_model_target_vnd")
        display = headline.get("headline_target_vnd")
        low = headline.get("target_band_low_vnd")
        high = headline.get("target_band_high_vnd")
        adjustment = _client_evidence_value(headline.get("target_adjustment"))
        rows.append((
            "Kiểm soát giá mục tiêu",
            (
                f"Raw model={float(raw):,.0f} VND; " if isinstance(raw, (int, float)) else "Raw model=N/A; "
            )
            + (
                f"headline={float(display):,.0f} VND; " if isinstance(display, (int, float)) else "headline=N/A; "
            )
            + (
                f"band={float(low):,.0f}-{float(high):,.0f} VND; " if isinstance(low, (int, float)) and isinstance(high, (int, float)) else ""
            )
            + f"điều chỉnh={adjustment}",
        ))
    warnings = list(dict.fromkeys(
        [str(item) for item in evidence.get("model_warnings", []) if str(item).strip()]
        + [str(item) for item in evidence.get("market_data_warnings", []) if str(item).strip()]
    ))
    blockers = list(dict.fromkeys(
        [str(item) for item in evidence.get("display_blocking_reasons", []) if str(item).strip()]
        + [str(item) for item in evidence.get("policy_blocking_reasons", []) if str(item).strip()]
    ))
    body = ""
    if rows:
        table_rows = "".join(f"<tr><td>{_e(label)}</td><td>{_e(value)}</td></tr>" for label, value in rows)
        body += (
            '<table class="financial-model-table report-status-table">'
            "<thead><tr><th>Minh chứng</th><th>Chi tiết</th></tr></thead>"
            f"<tbody>{table_rows}</tbody></table>"
        )
    show_diagnostics = str(getattr(vm, "mode", "") or "").lower() == "internal_debug"
    if show_diagnostics and blockers:
        labels = list(dict.fromkeys(_client_issue_label(item) for item in blockers))
        body += "<h3>Dữ liệu và kiểm định cần bổ sung trước khi phát hành</h3><ul>" + "".join(
            f"<li>{_e(label)}</li>" for label in labels if label
        ) + "</ul>"
    if show_diagnostics and warnings:
        labels = list(dict.fromkeys(_client_issue_label(item) for item in warnings))
        body += "<h3>Cảnh báo mô hình và dữ liệu</h3><ul>" + "".join(
            f"<li>{_e(label)}</li>" for label in labels if label
        ) + "</ul>"
    return body


_CLIENT_ISSUE_LABELS = {
    "valuation_result_not_publishable": "Kết quả định giá có cảnh báo cần đọc cùng phần tính toán chi tiết và phần đối chiếu.",
    "no_eligible_valuation_method": "Thiếu phương pháp định giá chính đã được xác minh để làm cơ sở khuyến nghị.",
    "blend_is_draft_only": "Kết quả kết hợp phương pháp đang ở trạng thái rà soát do thiếu hoặc lệch một cấu phần định giá.",
    "fcff_fcfe_gap_gt_25pct": "Giá trị theo FCFF và FCFE lệch trên ngưỡng kiểm soát; cần đọc thêm phần đối chiếu phương pháp.",
    "fcff_fcfe_gap_invalid": "Độ lệch giữa FCFF và FCFE chưa tính được một cách tin cậy.",
    "market_sanity_bridge_missing": "Giá trị mô hình lệch đáng kể so với thị giá nhưng chưa có cầu nối giải thích bằng P/E, EV/EBITDA hoặc bằng chứng cơ bản.",
    "valuation_method_divergence_critical": "Các phương pháp định giá cho kết quả phân kỳ mạnh; chưa nên chuyển thành kết luận đầu tư chính thức.",
    "senior_review_required_for_severe_downside": "Mức giảm so với thị giá đủ lớn để cần rà soát cấp cao trước khi phát hành rating.",
    "distress_evidence_required_for_extreme_downside": "Mức giảm cực lớn cần bằng chứng suy giảm hoặc rủi ro tài chính rõ ràng trước khi công bố.",
    "recommendation_gate_not_allowed": "Thiếu phê duyệt cuối cho khuyến nghị đầu tư.",
    "low_confidence_primary_method": "Phương pháp định giá chính có độ tin cậy thấp và cần kiểm định giả định.",
    "fcfe_blocked_net_borrowing_unavailable": "FCFE thiếu lịch vay ròng hoặc dòng tiền cho chủ sở hữu đã được xác minh.",
    "fcfe_unavailable_for_blend": "Kết quả kết hợp chưa có đủ dữ liệu FCFE; cần đọc trọng số phương pháp kèm cảnh báo.",
    "formula_trace_missing": "Thiếu vết công thức để tái lập đầy đủ phép tính.",
    "blend_sensitivity_missing_or_constant": "Bảng độ nhạy của kết quả kết hợp chưa đủ hoặc không biến thiên.",
    "fcff_sensitivity_missing_or_constant": "Bảng độ nhạy FCFF chưa đủ hoặc không biến thiên.",
    "fcfe_sensitivity_missing_or_constant": "Bảng độ nhạy FCFE chưa đủ hoặc không biến thiên.",
    "headline_target_clamped_low": "Giá mục tiêu mô hình thấp hơn biên thị trường; headline đã được neo về cận dưới của biên -5%/+10%.",
    "headline_target_clamped_high": "Giá mục tiêu mô hình cao hơn biên thị trường; headline đã được neo về cận trên của biên -5%/+10%.",
    "headline_target_market_anchor_neutral": "Không có target mô hình đủ dùng cho headline; báo cáo dùng target trung tính bằng thị giá hiện tại.",
    "headline_target_missing_current_price": "Thiếu giá thị trường hiện tại nên chưa thể xác lập biên kiểm soát headline target.",
}


def _client_issue_label(item: Any) -> str:
    key = str(item or "").strip()
    if not key:
        return ""
    if key in _CLIENT_ISSUE_LABELS:
        return _CLIENT_ISSUE_LABELS[key]
    normalized = key.lower().replace("_", " ").replace("-", " ")
    if "no new debt policy" in normalized:
        return "Lịch nợ vay đang giả định không phát sinh nợ mới và dư nợ giảm về gần 0 ở năm cơ sở; cần kiểm tra lại chính sách vay, trả nợ và kế hoạch vốn."
    if "normalized opening nwc" in normalized:
        return "Vốn lưu động năm dự phóng đầu tiên dùng mức vốn lưu động mở đầu đã chuẩn hóa; cần đối chiếu lại với biến động phải thu, tồn kho và phải trả."
    if "no reported ending cash" in normalized:
        return "Thiếu số dư tiền cuối kỳ đã báo cáo nên chưa thể đối chiếu đầy đủ lịch tiền mặt."
    if "served from cache" in normalized or "live fetch failed" in normalized:
        return "Dữ liệu thị trường đang dùng bản đã lưu gần nhất do chưa lấy được dữ liệu trực tiếp tại thời điểm dựng báo cáo."
    if "waccassumptions.tax" in normalized or "taxpolicy.effective tax rate" in normalized:
        return "Thuế suất trong giả định WACC khác thuế suất hiệu dụng theo chính sách thuế; mô hình đang dùng thuế suất hiệu dụng để tính EBIT sau thuế."
    if "model default" in normalized and "target pe" in normalized:
        return "P/E mục tiêu đang là giả định mặc định của mô hình; cần đối chiếu với P/E trung vị nhóm doanh nghiệp so sánh trước khi dùng làm cơ sở khuyến nghị."
    if "relative valuation is pending" in normalized:
        return "Định giá tương đối thiếu bộ doanh nghiệp so sánh đã phê duyệt; P/E, P/B và EV/EBITDA chỉ nên dùng sau khi có nhóm doanh nghiệp so sánh rõ ràng."
    if "fcfe blocked" in normalized or "debt schedule unavailable" in normalized:
        return "FCFE thiếu lịch nợ vay hoặc vay ròng đã xác minh; cần bổ sung lộ trình nợ vay trước khi dùng đầy đủ phương pháp này."
    if "eps and target p/e are present" in normalized or "eps and target pe are present" in normalized:
        return "EPS dự phóng và P/E mục tiêu đã có nhưng giá suy ra theo P/E đang bị trống; đây là lỗi mapping cần kiểm tra trong bảng định giá tương đối."
    if key.startswith("failed_method_has_nonzero_weight:"):
        method = key.split(":", 1)[1] or "phương pháp"
        return f"Phương pháp {method} thiếu dữ liệu kiểm định nhưng vẫn có trọng số trong kết quả tổng hợp."
    if key.startswith("critical_warning:"):
        detail = key.split(":", 1)[1].strip().lower()
        if "relative valuation" in detail or "peer_data_source" in detail:
            return "Cảnh báo nghiêm trọng: định giá tương đối thiếu bộ doanh nghiệp so sánh đã phê duyệt."
        return "Cảnh báo nghiêm trọng: cần rà soát thêm dữ liệu đầu vào và giả định định giá."
    if key.endswith("_failed"):
        return "Một kiểm tra bắt buộc chưa đạt; cần rà soát lại dữ liệu và giả định liên quan."
    if "blocked" in normalized or "not publishable" in normalized or "not_publishable" in key:
        return "Thiếu dữ liệu hoặc phê duyệt để sử dụng kết quả này làm cơ sở khuyến nghị."
    return "Cần rà soát thêm một cảnh báo dữ liệu hoặc phương pháp chưa được phân loại trong bản phát hành."


def _client_evidence_value(value: Any) -> str:
    key = str(value or "").strip()
    normalized = key.lower().replace("_", " ").replace("-", " ")
    if key == "analyst_default_pending_peers":
        return "Giả định tạm thời của mô hình; chưa có bộ doanh nghiệp so sánh được phê duyệt."
    if key == "pending_peer_dataset":
        return "Đang chờ dữ liệu nhóm doanh nghiệp so sánh đã kiểm chứng."
    if key == "none":
        return "không điều chỉnh"
    if key == "clamped_low":
        return "neo về cận dưới"
    if key == "clamped_high":
        return "neo về cận trên"
    if key == "market_anchor_neutral":
        return "trung tính theo thị giá"
    if key == "missing_current_price":
        return "thiếu giá thị trường"
    if "peer" in normalized and "pending" in normalized:
        return "Đang chờ dữ liệu nhóm doanh nghiệp so sánh đã kiểm chứng."
    return key


def _render_report_status(vm: ClientReportViewModel) -> str:
    """Render the method and decision explanation in client-facing Vietnamese."""
    intro = _e(_client_status_sentence(vm))
    current_price = _format_price(vm.current_price)
    target_price = _target_price_text(vm)
    upside = _decision_percent_text(vm.upside_downside)
    total_return = _decision_percent_text(vm.total_return)
    recommendation = getattr(vm, "recommendation", "Giữ")
    if getattr(vm, "target_price", None) is None:
        result_sentence = (
            f"Giá hiện tại {current_price} VND; giá mục tiêu chưa được công bố vì "
            f"{_target_price_blocking_summary(vm, limit=1)[0]} Tiềm năng tăng/giảm {upside}, "
            f"tổng lợi suất kỳ vọng {total_return}, khuyến nghị: {recommendation}."
        )
    else:
        result_sentence = (
            f"Giá hiện tại {current_price} VND, giá mục tiêu {target_price}, tiềm năng "
            f"tăng/giảm {upside}, tổng lợi suất kỳ vọng {total_return}, khuyến nghị: "
            f"{recommendation}."
        )

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
            "Mua nếu >20%, Bán nếu <-10%, còn lại là Giữ; nếu thiếu target mô hình đủ dùng thì xếp Theo dõi.",
        ),
        (
            "Kết quả hiện tại",
            result_sentence,
        ),
        (
            "Thời điểm giá thị trường",
            f"Giá hiện tại được ghi nhận tại ngày {_market_price_as_of(vm)}; báo cáo được tạo lúc "
            f"{_report_generated_at(vm)}. Báo cáo ưu tiên giá thị trường mới nhất tại thời điểm tạo báo cáo.",
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
        + _render_valuation_evidence(vm)
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
        "market_price_as_of": "ngày dữ liệu của giá thị trường",
        "same_day_market_price": "giá thị trường cùng ngày tạo báo cáo",
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
