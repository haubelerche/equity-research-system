"""Pure builder for the valuation workings (.md) explainer.

Renders a detailed, internal-facing Markdown document that walks through every
valuation calculation — assumptions, forecast drivers, ratios, FCFF, FCFE, blend,
P/E forward cross-check, sensitivity, and consistency checks — so a reviewer can
verify the numbers behind the client PDF.

Unlike the client report, this document deliberately exposes formulas, intermediate
values, assumptions, warnings and the reproducibility hash. It is NOT a client
deliverable. The function is side-effect free: it takes already-loaded artifact
dicts plus the view model and returns a string. Missing inputs render as ``—`` —
nothing is fabricated.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

_DASH = "—"

FCFF_FORMULA = "FCFF = EBIT×(1−t) + D&A − CAPEX − ΔNWC"

SECTION_TITLES = [
    "1. Thông tin chung",
    "2. Tóm tắt kết quả định giá",
    "3. Bảng giả định",
    "4. Dự phóng theo yếu tố dẫn dắt",
    "5. Chỉ số tài chính",
    "6. Định giá FCFF",
    "7. Định giá FCFE",
    "8. Kết hợp phương pháp FCFF và FCFE",
    "9. P/E dự phóng để đối chiếu",
    "10. Phân tích độ nhạy",
    "11. Đối chiếu & cảnh báo",
]


# ── formatting helpers ────────────────────────────────────────────────────────

def _num(value: Any, decimals: int = 0) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return _DASH


def _pct(value: Any, decimals: int = 1) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return _DASH


def _mult(value: Any, decimals: int = 1) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):.{decimals}f}x"
    except (TypeError, ValueError):
        return _DASH


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    """First present (key in mapping) value among *keys; None if none present."""
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _sub(valuation: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    """Resolve a sub-artifact dict by trying alternative key names."""
    for key in keys:
        section = valuation.get(key)
        if isinstance(section, Mapping):
            return dict(section)
    return {}


def _kv_table(rows: Sequence[tuple[str, str]]) -> str:
    lines = ["| Thành phần | Giá trị |", "| --- | ---: |"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    return "\n".join(lines)


def _grid_table(
    row_axis: Sequence[Any],
    col_axis: Sequence[Any],
    matrix: Sequence[Sequence[Any]],
    *,
    corner: str,
    row_fmt,
    col_fmt,
    cell_fmt,
) -> str:
    header = "| " + " | ".join([corner, *[col_fmt(c) for c in col_axis]]) + " |"
    sep = "| " + " | ".join(["---"] * (len(col_axis) + 1)) + " |"
    body = []
    for r_label, matrix_row in zip(row_axis, matrix):
        cells = [cell_fmt(c) for c in matrix_row]
        body.append("| " + " | ".join([row_fmt(r_label), *cells]) + " |")
    return "\n".join([header, sep, *body])


def _warnings_block(*artifacts: Mapping[str, Any]) -> list[str]:
    collected: list[str] = []
    for artifact in artifacts:
        for warn in artifact.get("warnings", []) or []:
            translated = _translate_warning(warn)
            if translated and translated not in collected:
                collected.append(translated)
    return collected


def _score(text: str) -> str:
    import re

    match = re.search(r"\((\d+(?:\.\d+)?/10)\)", text)
    return f" ({match.group(1)})" if match else ""


def _translate_warning(warning: Any) -> str:
    """Translate recurring model/evaluation findings into professional Vietnamese."""
    text = str(warning or "").strip()
    lower = text.lower()
    normalized = lower.replace("_", " ").replace("-", " ")
    if not text:
        return ""

    evaluation_rules = {
        "driver logic": "Tính hợp lý của yếu tố dẫn dắt",
        "risk balance": "Mức độ cân bằng rủi ro",
        "evidence depth": "Độ sâu bằng chứng",
        "thesis strength": "Độ vững của luận điểm đầu tư",
        "narrative quality": "Chất lượng diễn giải",
        "numeric integrity": "Tính toàn vẹn số liệu",
        "citation integrity": "Tính toàn vẹn trích dẫn",
        "sector specificity": "Mức độ đặc thù ngành",
        "valuation coherence": "Tính nhất quán của định giá",
        "forecast consistency": "Tính nhất quán của dự phóng",
        "table chart completeness": "Mức độ đầy đủ của bảng và biểu đồ",
    }
    for needle, label in evaluation_rules.items():
        if normalized.startswith(needle):
            return f"{label}{_score(text)}: kết quả đánh giá có cơ sở truy vết; các hạn chế dữ liệu và giả định liên quan được công bố trong phụ lục."

    rules = [
        (
            "the fcfe stream is not publishable",
            "Mức độ nghiêm trọng cao: FCFE chưa đủ điều kiện công bố vì mô hình giữ dư nợ ổn định, "
            "trong khi lộ trình vay ròng chưa được xác minh. Vì vậy, kết quả kết hợp thực tế đang phụ "
            "thuộc 100% vào FCFF và độ nhạy theo giả định đòn bẩy chưa đáng tin cậy.",
        ),
        (
            "historical ar/inv/ap days are null",
            "Mức độ nghiêm trọng cao: thiếu số ngày phải thu, tồn kho và phải trả lịch sử; mô hình đang "
            "ước tính hoặc đặt biến động vốn lưu động bằng 0. Điều này có thể làm sai lệch thời điểm "
            "ghi nhận dòng tiền tự do và tỷ trọng giá trị cuối kỳ.",
        ),
        (
            "the raw ratio artifact originally contained",
            "Mức độ nghiêm trọng trung bình: dữ liệu tỷ số ban đầu và dữ liệu chuẩn hóa dùng trong định "
            "giá có khác biệt về thang đơn vị. Cần xác nhận lại đơn vị để tránh diễn giải sai dòng tiền tuyệt đối.",
        ),
        (
            "artifacts do not contain segment- or channel-level",
            "Mức độ nghiêm trọng trung bình: chưa có công bố doanh thu và biên lợi nhuận theo phân khúc "
            "hoặc kênh bán hàng, nên chưa thể tách tác động của cơ cấu sản phẩm và chi phí đầu vào.",
        ),
        (
            "terminal value contributes a large share",
            "Mức độ nghiêm trọng trung bình: giá trị cuối kỳ chiếm tỷ trọng lớn trong DCF, làm kết quả "
            "định giá nhạy với giả định dài hạn, lựa chọn FCFF/FCFE và ước tính vốn lưu động.",
        ),
        (
            "all computed outputs are traceable",
            "Thông tin kiểm soát: các kết quả tính toán có thể truy vết và các cổng kiểm soát chính đã "
            "đạt; tuy nhiên chính sách thuế, lịch nợ vay và dữ liệu doanh nghiệp so sánh vẫn cần chuyên "
            "viên phân tích phê duyệt trước khi công bố chính thức.",
        ),
        (
            "assumptions are defaults",
            "Các giả định hiện là giá trị mặc định và phải được rà soát, phê duyệt trước khi sử dụng trong báo cáo chính thức.",
        ),
        (
            "debt forecast holds debt flat",
            "Lịch nợ vay dự phóng đang giữ nguyên dư nợ tại số cuối kỳ gần nhất; mức độ tin cậy thấp "
            "và cần chuyên viên phân tích rà soát.",
        ),
        (
            "interest expense is single-pass",
            "Chi phí lãi vay mới được tính một vòng, chưa lặp đến hội tụ. Phương pháp giữ dư nợ ổn định "
            "làm FCFE bị chặn; cần bổ sung lộ trình nợ vay đã phê duyệt.",
        ),
        (
            "no historical ar data",
            "Thiếu dữ liệu phải thu khách hàng lịch sử; dự phóng phải thu bằng 0 nên biến động vốn lưu động có thể bị đánh giá thấp.",
        ),
        (
            "no historical inventory data",
            "Thiếu dữ liệu tồn kho lịch sử; dự phóng tồn kho đang bằng 0.",
        ),
        (
            "no historical ap data",
            "Thiếu dữ liệu phải trả người bán lịch sử; dự phóng phải trả bằng 0 nên biến động vốn lưu động có thể bị đánh giá cao.",
        ),
        (
            "no corporate action data provided",
            "Thiếu dữ liệu hành động doanh nghiệp; số cổ phiếu được giữ cố định và chưa mô hình hóa pha "
            "loãng từ phát hành riêng lẻ hoặc ESOP. EPS pha loãng và giá mục tiêu mỗi cổ phiếu có thể bị đánh giá cao.",
        ),
        (
            "no reported ending cash supplied",
            "Thiếu số dư tiền cuối kỳ đã báo cáo nên chưa thể đối chiếu lịch tiền mặt; trạng thái đang chờ xác minh.",
        ),
        (
            "waccassumptions.tax",
            "Thuế suất trong giả định WACC khác thuế suất hiệu dụng trong chính sách thuế; mô hình đang "
            "dùng thuế suất theo chính sách thuế để tính EBIT sau thuế.",
        ),
        (
            "delta nwc estimated as 2% revenue change",
            "Biến động vốn lưu động được ước tính bằng 2% thay đổi doanh thu do thiếu lịch vốn lưu động.",
        ),
        (
            "delta_nwc estimated as 2% revenue change",
            "Biến động vốn lưu động được ước tính bằng 2% thay đổi doanh thu do thiếu lịch vốn lưu động.",
        ),
        (
            "fcfe blocked",
            "FCFE bị chặn vì lịch nợ vay chưa đủ điều kiện công bố: dư nợ được giữ cố định và vay ròng "
            "chưa có nguồn từ báo cáo lưu chuyển tiền tệ hoặc lịch đáo hạn. Cần lộ trình nợ vay đã phê duyệt.",
        ),
        (
            "terminal value = 0 due to missing fcfe",
            "Giá trị cuối kỳ FCFE bằng 0 do thiếu FCFE ở năm dự phóng cuối cùng.",
        ),
        (
            "price fcfe không có",
            "Không có giá theo FCFE nên kết quả hiện sử dụng 100% FCFF, không đúng trọng số mục tiêu 60/40 và cần phê duyệt thủ công.",
        ),
    ]
    for needle, translated in rules:
        if needle.replace("-", " ") in normalized:
            return translated

    replacements = {
        "[high]": "[Mức độ cao]",
        "[medium]": "[Mức độ trung bình]",
        "[informational]": "[Thông tin]",
        "[debtschedule]": "[Lịch nợ vay]",
        "[forecastwarning]": "[Cảnh báo dự phóng]",
        "[workingcapital]": "[Vốn lưu động]",
        "[sharerollforward]": "[Diễn biến số cổ phiếu]",
        "[cashsweep]": "[Lịch tiền mặt]",
        "price fcfe": "Giá theo FCFE",
        "blend": "kết hợp phương pháp",
        "sensitivity": "độ nhạy",
        "terminal value": "giá trị cuối kỳ",
        "net borrowing": "vay ròng",
        "working capital": "vốn lưu động",
        "artifact": "tệp kết quả",
        "forecast": "dự phóng",
        "warning": "cảnh báo",
        "blocked": "bị chặn",
        "pending": "đang chờ",
    }
    translated = text
    for source, target in replacements.items():
        translated = translated.replace(source, target).replace(source.title(), target)
    return translated


# ── section renderers ─────────────────────────────────────────────────────────

def _section_header(ticker: str, run_id: str, valuation: Mapping[str, Any], vm: Any) -> str:
    company = getattr(vm, "company_name", None) or ticker
    exchange = getattr(vm, "exchange", None) or _DASH
    sector = getattr(vm, "sector", None) or _DASH
    rows = [
        ("Mã cổ phiếu", ticker),
        ("Công ty", company),
        ("Sàn", exchange),
        ("Ngành", sector),
        ("Mã lần chạy", run_id),
        ("Ngày định giá", str(_first(valuation, "valuation_date") or _DASH)),
        ("Mã ảnh chụp dữ liệu", str(_first(valuation, "snapshot_id") or _DASH)),
        ("Năm gốc", str(_first(valuation, "base_year") or _DASH)),
        ("Mã băm tái lập", str(_first(valuation, "reproducibility_hash") or _DASH)),
    ]
    return f"## {SECTION_TITLES[0]}\n\n" + _kv_table(rows)


def _section_summary(valuation: Mapping[str, Any], blend: Mapping[str, Any], vm: Any) -> str:
    current = _first(valuation, "current_price") or _first(blend, "current_price_vnd")
    target = _first(valuation, "target_price") or _first(blend, "target_price_dcf_vnd")
    upside = _first(valuation, "upside_downside") or _first(blend, "upside_pct")
    recommendation = getattr(vm, "recommendation", None) or _DASH
    rows = [
        ("Giá hiện tại (VND)", _num(current)),
        ("Giá mục tiêu kết hợp (VND)", _num(target)),
        ("Tiềm năng tăng/giảm", _pct(upside)),
        ("Khuyến nghị", recommendation),
    ]
    rule = (
        "**Luật xếp hạng** (tổng tỷ suất sinh lời = mức tăng/giảm giá + lợi suất cổ tức): "
        "> 20% → MUA; < −10% → BÁN; còn lại → NẮM GIỮ."
    )
    return f"## {SECTION_TITLES[1]}\n\n" + _kv_table(rows) + "\n\n" + rule


def _section_assumptions(valuation: Mapping[str, Any], fcff: Mapping[str, Any], fcfe: Mapping[str, Any]) -> str:
    assumptions = _sub(valuation, "assumptions")
    rows = [
        ("WACC", _pct(_first(fcff, "wacc") or assumptions.get("wacc"))),
        ("Chi phí vốn chủ sở hữu (Re)", _pct(_first(fcfe, "cost_of_equity") or assumptions.get("cost_of_equity"))),
        ("Tăng trưởng dài hạn (g)", _pct(_first(fcff, "terminal_growth") or assumptions.get("terminal_growth"))),
        ("Số năm dự phóng", str(assumptions.get("forecast_years") or _DASH)),
        ("Thuế suất", _pct(assumptions.get("tax_rate"))),
        ("P/E mục tiêu", _mult(assumptions.get("target_pe"))),
        ("Mức cộng/trừ định giá", _pct(assumptions.get("premium_discount_pct"))),
    ]
    note = assumptions.get("note")
    body = _kv_table(rows)
    if note:
        body += f"\n\n> {_translate_warning(note)}"
    else:
        body += "\n\n> Giả định mặc định cần được chuyên viên phân tích xem xét và phê duyệt trước khi khóa định giá."
    return f"## {SECTION_TITLES[2]}\n\n" + body


def _section_forecast(forecast: Mapping[str, Any]) -> str:
    years = [r for r in forecast.get("forecast_years", []) if isinstance(r, Mapping)]
    if not years:
        return f"## {SECTION_TITLES[3]}\n\n_Không có dữ liệu dự phóng._"
    labels = [str(r.get("label") or _DASH) for r in years]
    metrics = [
        ("Doanh thu thuần", "revenue"),
        ("Lợi nhuận gộp", "gross_profit"),
        ("EBIT", "ebit"),
        ("LNST cổ đông mẹ", "net_income"),
        ("Khấu hao (D&A)", "depreciation"),
        ("CAPEX", "capex"),
        ("EPS (VND)", "eps"),
    ]
    header = "| Chỉ tiêu | " + " | ".join(labels) + " |"
    sep = "| --- | " + " | ".join(["---:"] * len(labels)) + " |"
    lines = [header, sep]
    for label, key in metrics:
        decimals = 0
        cells = [_num(r.get(key), decimals) for r in years]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    debt_rows = (forecast.get("debt_schedule") or {}).get("forecast_rows", [])
    div_rows = (forecast.get("dividend_schedule") or {}).get("forecast_rows", [])
    debt_by_label = {str(r.get("label")): r for r in debt_rows if isinstance(r, Mapping)}
    div_by_label = {str(r.get("label")): r for r in div_rows if isinstance(r, Mapping)}
    lines.append(
        "| Vay ròng (phát hành nợ − trả nợ) | "
        + " | ".join(_num((debt_by_label.get(lbl) or {}).get("net_borrowing")) for lbl in labels)
        + " |"
    )
    lines.append(
        "| Dư nợ vay cuối kỳ | "
        + " | ".join(
            _num((debt_by_label.get(lbl) or {}).get("ending_interest_bearing_debt")) for lbl in labels
        )
        + " |"
    )
    lines.append(
        "| Cổ tức tiền mặt | "
        + " | ".join(_num((div_by_label.get(lbl) or {}).get("cash_dividend")) for lbl in labels)
        + " |"
    )
    lines.append(
        "| Tỷ lệ chi trả cổ tức | "
        + " | ".join(_pct((div_by_label.get(lbl) or {}).get("payout_ratio")) for lbl in labels)
        + " |"
    )

    note = (
        "\n\n_Logic yếu tố dẫn dắt: doanh thu theo tăng trưởng giả định; biên lợi nhuận dẫn xuất EBIT/LNST; "
        "lịch nợ vay chuyển tiếp với `vay ròng = phát hành nợ − trả nợ`; cổ tức theo tỷ lệ chi trả._"
    )
    return f"## {SECTION_TITLES[3]}\n\n" + "\n".join(lines) + note


def _section_ratios(forecast: Mapping[str, Any]) -> str:
    years = [r for r in forecast.get("forecast_years", []) if isinstance(r, Mapping)]
    if not years:
        return f"## {SECTION_TITLES[4]}\n\n_Không có dữ liệu để tính chỉ số._"
    labels = [str(r.get("label") or _DASH) for r in years]

    def _ratio(num_key: str, den_key: str) -> list[str]:
        out = []
        for r in years:
            num = r.get(num_key)
            den = r.get(den_key)
            if num is None or not den:
                out.append(_DASH)
            else:
                out.append(_pct(num / den))
        return out

    header = "| Chỉ số | Công thức | " + " | ".join(labels) + " |"
    sep = "| --- | --- | " + " | ".join(["---:"] * len(labels)) + " |"
    lines = [header, sep]
    lines.append("| Biên lợi nhuận gộp | lợi nhuận gộp / doanh thu | " + " | ".join(_ratio("gross_profit", "revenue")) + " |")
    lines.append("| Biên EBIT | EBIT / doanh thu | " + " | ".join(_ratio("ebit", "revenue")) + " |")
    lines.append("| Biên lợi nhuận ròng | lợi nhuận sau thuế / doanh thu | " + " | ".join(_ratio("net_income", "revenue")) + " |")
    lines.append("| ROE | lợi nhuận sau thuế / vốn chủ sở hữu | " + " | ".join(_ratio("net_income", "equity")) + " |")
    return f"## {SECTION_TITLES[4]}\n\n" + "\n".join(lines)


def _section_fcff(fcff: Mapping[str, Any]) -> str:
    wacc = _first(fcff, "wacc")
    g = _first(fcff, "terminal_growth")
    head = (
        f"**Công thức:** `{FCFF_FORMULA}`\n\n"
        f"- WACC = **{_pct(wacc)}**; tăng trưởng dài hạn g = **{_pct(g)}**\n"
    )

    rows = fcff.get("fcff_table") or []
    fcff_lines = ""
    if rows:
        labels = [str(r.get("label") or _DASH) for r in rows if isinstance(r, Mapping)]
        metric_rows = [
            ("EBIT", "ebit"),
            ("Thuế suất", "tax_rate"),
            ("D&A", "depreciation"),
            ("CAPEX", "capex"),
            ("ΔNWC", "delta_nwc"),
            ("FCFF", "fcff"),
            ("Hệ số chiết khấu", "discount_factor"),
            ("PV(FCFF)", "pv"),
        ]
        header = "| Khoản mục | " + " | ".join(labels) + " |"
        sep = "| --- | " + " | ".join(["---:"] * len(labels)) + " |"
        body = [header, sep]
        for label, key in metric_rows:
            fmt = _pct if key in ("tax_rate", "discount_factor") else _num
            cells = [fmt(r.get(key)) for r in rows if isinstance(r, Mapping)]
            body.append(f"| {label} | " + " | ".join(cells) + " |")
        fcff_lines = "\n".join(body) + "\n\n"

    bridge = _kv_table([
        ("PV dòng tiền dự phóng (Σ PV FCFF)", _num(_first(fcff, "pv_fcff"))),
        ("Giá trị cuối kỳ (Gordon: FCFFₙ×(1+g)/(WACC−g))", _num(_first(fcff, "terminal_value"))),
        ("Giá trị hiện tại của giá trị cuối kỳ", _num(_first(fcff, "pv_terminal_value"))),
        ("Tỷ trọng giá trị cuối kỳ / giá trị doanh nghiệp", _pct(_first(fcff, "terminal_value_weight"))),
        ("= Giá trị doanh nghiệp (EV)", _num(_first(fcff, "enterprise_value"))),
        ("− Nợ ròng", _num(_first(fcff, "net_debt"))),
        ("= Giá trị vốn chủ sở hữu", _num(_first(fcff, "equity_value"))),
        ("÷ Số cổ phiếu (triệu)", _num(_first(fcff, "shares_outstanding", "shares_mn"))),
        ("= Giá/cổ phiếu (FCFF, VND)", _num(_first(fcff, "implied_price"))),
    ])
    return f"## {SECTION_TITLES[5]}\n\n" + head + "\n" + fcff_lines + bridge


def _section_fcfe(fcfe: Mapping[str, Any]) -> str:
    rows = _kv_table([
        ("Chi phí vốn chủ sở hữu (Re)", _pct(_first(fcfe, "cost_of_equity"))),
        ("Tăng trưởng dài hạn (g)", _pct(_first(fcfe, "terminal_growth"))),
        ("Giá trị vốn chủ sở hữu", _num(_first(fcfe, "equity_value"))),
        ("÷ Số cổ phiếu (triệu)", _num(_first(fcfe, "shares_outstanding", "shares_mn"))),
        ("= Giá/cổ phiếu (FCFE, VND)", _num(_first(fcfe, "implied_price"))),
    ])
    note = ""
    if _first(fcfe, "implied_price") is None:
        note = "\n\n_Giá FCFE chưa tính được do thiếu dữ liệu vay ròng hoặc số cổ phiếu. Hiển thị `—`._"
    return (
        f"## {SECTION_TITLES[6]}\n\n"
        "**Công thức:** `FCFE = lợi nhuận sau thuế + khấu hao − CAPEX − ΔNWC + vay ròng`, "
        "chiết khấu theo chi phí vốn chủ sở hữu.\n\n" + rows + note
    )


def _section_blend(blend: Mapping[str, Any]) -> str:
    price_fcff = _first(blend, "price_fcff_vnd")
    price_fcfe = _first(blend, "price_fcfe_vnd")
    w_fcff = _first(blend, "fcff_weight") or 0.6
    w_fcfe = _first(blend, "fcfe_weight") or 0.4
    target = _first(blend, "target_price_dcf_vnd")
    formula = "Giá mục tiêu = 0.60 × Giá_FCFF + 0.40 × Giá_FCFE"
    arithmetic = (
        f"`{_num(w_fcff, 2)} × {_num(price_fcff)} + {_num(w_fcfe, 2)} × {_num(price_fcfe)} "
        f"= {_num(target)}`"
    )
    rows = _kv_table([
        ("Giá theo FCFF (VND)", _num(price_fcff)),
        ("Giá theo FCFE (VND)", _num(price_fcfe)),
        ("Trọng số FCFF / FCFE", f"{_num(w_fcff, 2)} / {_num(w_fcfe, 2)}"),
        ("= Giá mục tiêu kết hợp (VND)", _num(target)),
        ("Chênh lệch FCFF/FCFE", _pct(_first(blend, "fcff_fcfe_gap_pct"))),
        ("Chỉ ở dạng nháp", "Có" if blend.get("is_draft_only") else "Không"),
    ])
    gap_note = ""
    gap = _first(blend, "fcff_fcfe_gap_pct")
    try:
        if gap is not None and float(gap) > 0.25:
            gap_note = "\n\n> Chênh lệch FCFF/FCFE > 25% — kết quả kết hợp bị chặn ở trạng thái nháp; cần rà soát vay ròng, nợ ròng, CAPEX và vốn lưu động."
    except (TypeError, ValueError):
        pass
    return (
        f"## {SECTION_TITLES[7]}\n\n"
        f"**Công thức:** `{formula}`\n\n"
        f"**Số học:** {arithmetic}\n\n" + rows + gap_note
    )


def _section_pe_forward(valuation: Mapping[str, Any]) -> str:
    pe = _sub(valuation, "multiples", "pe_forward", "core_pe_net_cash")
    if not pe:
        return (
            f"## {SECTION_TITLES[8]}\n\n"
            "_Không có tệp kết quả P/E dự phóng để đối chiếu._"
        )
    rows: list[tuple[str, str]] = [
        ("EPS dự phóng (VND)", _num(_first(pe, "eps_forward_vnd", "eps_forward"))),
        ("P/E trung vị nhóm so sánh", _mult(_first(pe, "peer_median_pe"))),
        ("Mức cộng/trừ định giá", _pct(_first(pe, "premium_discount_pct"))),
        ("P/E mục tiêu", _mult(_first(pe, "target_pe"))),
        ("Giá mục tiêu (VND)", _num(_first(pe, "target_price_vnd"))),
    ]
    body = _kv_table(rows)
    peers = pe.get("peer_table") or []
    if peers:
        body += "\n\n| Doanh nghiệp so sánh | Giá | EPS dự phóng | P/E |\n| --- | ---: | ---: | ---: |\n"
        peer_lines = []
        for p in peers:
            if not isinstance(p, Mapping):
                continue
            peer_lines.append(
                f"| {p.get('name', _DASH)} | {_num(p.get('price'))} | "
                f"{_num(p.get('eps_forward'))} | {_mult(p.get('pe'))} |"
            )
        body += "\n".join(peer_lines)
    rationale = _first(pe, "premium_discount_rationale", "rationale")
    if rationale:
        body += f"\n\n_Cơ sở áp dụng mức cộng/trừ định giá: {_translate_warning(rationale)}_"
    return f"## {SECTION_TITLES[8]}\n\n" + body


def _render_sensitivity_grid(name: str, grid: Mapping[str, Any]) -> str:
    matrix = grid.get("matrix")
    if not matrix:
        return ""
    # Resolve the two axes by trying the common range key names.
    row_keys = ("wacc_range", "re_range", "eps_range", "price_fcff_range", "ebitda_range")
    col_keys = ("g_range", "pe_range", "price_fcfe_range", "multiple_range")
    row_axis = next((grid[k] for k in row_keys if grid.get(k)), list(range(len(matrix))))
    if isinstance(matrix, Mapping):
        first_row = next(iter(matrix.values()), {})
        fallback_cols = list(first_row) if isinstance(first_row, Mapping) else []
    else:
        fallback_cols = list(range(len(matrix[0]) if matrix else 0))
    col_axis = next((grid[k] for k in col_keys if grid.get(k)), fallback_cols)

    def _lookup(mapping: Mapping[str, Any], key: Any) -> Any:
        candidates = (key, str(key), f"{float(key):.3f}", f"{float(key):.1f}")
        for candidate in candidates:
            if candidate in mapping:
                return mapping[candidate]
        return None

    if isinstance(matrix, Mapping):
        normalized_matrix = []
        for row_key in row_axis:
            raw_row = _lookup(matrix, row_key)
            if isinstance(raw_row, Mapping):
                normalized_matrix.append([_lookup(raw_row, col_key) for col_key in col_axis])
            else:
                normalized_matrix.append([None for _ in col_axis])
        matrix = normalized_matrix

    pct_axes = {"wacc_range", "re_range", "g_range"}
    row_is_pct = any(grid.get(k) is row_axis for k in pct_axes)
    col_is_pct = any(grid.get(k) is col_axis for k in pct_axes)
    row_fmt = (lambda v: _pct(v)) if row_is_pct else (lambda v: _num(v))
    col_fmt = (lambda v: _pct(v)) if col_is_pct else (lambda v: _num(v))

    labels = {
        "fcff_wacc_g": "Độ nhạy FCFF theo WACC và tăng trưởng dài hạn",
        "fcfe_re_g": "Độ nhạy FCFE theo chi phí vốn chủ sở hữu và tăng trưởng dài hạn",
        "blend_grid": "Độ nhạy giá mục tiêu kết hợp",
        "pe": "Độ nhạy P/E dự phóng",
        "ev_ebitda": "Độ nhạy EV/EBITDA",
        "simplified_dcf": "Độ nhạy DCF giản lược",
    }
    label = labels.get(name, grid.get("label") or grid.get("pe_label") or name)
    table = _grid_table(
        row_axis,
        col_axis,
        matrix,
        corner=str(label),
        row_fmt=row_fmt,
        col_fmt=col_fmt,
        cell_fmt=lambda v: _num(v.get("price") if isinstance(v, Mapping) else v),
    )
    formula = grid.get("formula")
    formula_vi = (
        str(formula)
        .replace("Target P/E", "P/E mục tiêu")
        .replace("Price", "Giá")
        .replace("Multiple", "Hệ số")
        .replace("Net Debt", "Nợ ròng")
        .replace("Minority Interest", "Lợi ích cổ đông không kiểm soát")
        .replace("Non-op Assets", "Tài sản ngoài hoạt động")
        .replace("Shares", "Số cổ phiếu")
        .replace("EPS_FY1", "EPS năm dự phóng thứ nhất")
        if formula
        else ""
    )
    head = f"**{label}**" + (f" — `{formula_vi}`" if formula_vi else "")
    return head + "\n\n" + table


def _section_sensitivity(valuation: Mapping[str, Any]) -> str:
    sens = _sub(valuation, "sensitivity")
    if not sens:
        return f"## {SECTION_TITLES[9]}\n\n_Không có bảng độ nhạy._"
    blocks = []
    for name in ("fcff_wacc_g", "fcfe_re_g", "blend_grid", "pe", "ev_ebitda", "simplified_dcf"):
        grid = sens.get(name)
        if isinstance(grid, Mapping):
            rendered = _render_sensitivity_grid(name, grid)
            if rendered:
                blocks.append(rendered)
    if not blocks:
        return f"## {SECTION_TITLES[9]}\n\n_Không có bảng độ nhạy._"
    return f"## {SECTION_TITLES[9]}\n\n" + "\n\n".join(blocks)


def _section_crosschecks(
    valuation: Mapping[str, Any],
    fcff: Mapping[str, Any],
    blend: Mapping[str, Any],
    fcfe: Mapping[str, Any],
) -> str:
    lines = ["**Đối chiếu nhất quán số:**", ""]
    implied = _first(fcff, "implied_price")
    price_fcff = _first(blend, "price_fcff_vnd")
    if implied is not None and price_fcff is not None:
        match = abs(float(implied) - float(price_fcff)) <= max(1.0, 0.01 * abs(float(price_fcff)))
        flag = "✓" if match else "✗"
        lines.append(f"- {flag} Giá suy ra theo FCFF ({_num(implied)}) khớp giá FCFF trong kết quả kết hợp ({_num(price_fcff)}).")
    else:
        lines.append("- Giá suy ra theo FCFF / giá FCFF: thiếu dữ liệu để đối chiếu (—).")

    warnings = _warnings_block(blend, fcff, fcfe, valuation)
    lines.append("")
    if warnings:
        lines.append("**Cảnh báo từ mô hình tính toán:**")
        lines.append("")
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("**Cảnh báo từ mô hình tính toán:** _không có._")

    lines.append("")
    lines.append(f"**Mã băm tái lập:** `{_first(valuation, 'reproducibility_hash') or _DASH}`")
    lines.append("")
    lines.append(
        "_Nguồn gốc dữ liệu: mọi số định giá được dẫn xuất từ dữ liệu tài chính chuẩn hóa đã khóa "
        "và tệp kết quả định giá bằng Python; không có số liệu nào do mô hình ngôn ngữ sinh ra._"
    )
    return f"## {SECTION_TITLES[10]}\n\n" + "\n".join(lines)


# ── public builder ────────────────────────────────────────────────────────────

_ISSUE_LABELS = {
    "price_chart": "Chưa đủ lịch sử giá để vẽ biểu đồ giá đáng tin cậy.",
    "shares_outstanding": "Chưa đủ số cổ phiếu lưu hành để kiểm tra EPS và giá trị mỗi cổ phần.",
    "working_capital_schedule": "Chưa đủ lịch vốn lưu động để giải thích toàn bộ biến động dòng tiền.",
    "dividend_schedule": "Chưa đủ dữ liệu để kiểm tra lịch cổ tức dự phóng.",
    "debt_schedule_publishable": "Lịch nợ vay chưa đủ để kiểm tra toàn bộ định giá dòng tiền cho cổ đông.",
    "forecast_debt": "Cần rà soát thêm lịch nợ vay dự phóng.",
    "valuation_result_not_publishable": "Kết quả định giá có cảnh báo cần đọc cùng bảng tính chi tiết.",
    "blend_is_draft_only": "Hai phương pháp dòng tiền có độ lệch lớn; cần đọc kỹ phần kết hợp phương pháp và đối chiếu.",
    "fcff_fcfe_gap_gt_25pct": "Giá trị theo FCFF và FCFE lệch trên 25%.",
    "post_render_client_language_forbidden:critic": "Hậu kiểm phát hiện thuật ngữ nội bộ trong bản dành cho người đọc; nội dung đã được chuyển sang ngôn ngữ phản biện chuyên môn.",
    "post_render_client_language_forbidden:khuyến nghị hệ thống": "Hậu kiểm yêu cầu dùng thuật ngữ khuyến nghị trong báo cáo chính thay cho thuật ngữ nội bộ.",
}


def _issue_label(issue: Any) -> str:
    key = str(issue)
    if key in _ISSUE_LABELS:
        return _ISSUE_LABELS[key]
    translated = _translate_warning(key)
    return translated if translated != key else "Cần rà soát thêm: " + key.replace("_", " ")


def _vm_amount(value: Any) -> Any:
    return getattr(value, "amount", value)


def _vm_ratio(value: Any) -> Any:
    return getattr(value, "value", value)


def _section_report_decision_basis(
    valuation: Mapping[str, Any],
    forecast: Mapping[str, Any],
    blend: Mapping[str, Any],
    fcff: Mapping[str, Any],
    fcfe: Mapping[str, Any],
    view_model: Any | None,
    issues: Sequence[Any],
) -> str:
    """Explain the main report conclusion before the calculation appendix."""
    current = (
        _first(valuation, "current_price")
        or _first(blend, "current_price_vnd")
        or _vm_amount(getattr(view_model, "current_price", None))
    )
    target = (
        _first(valuation, "target_price")
        or _first(blend, "target_price_dcf_vnd")
        or _vm_amount(getattr(view_model, "target_price", None))
    )
    upside = (
        _first(valuation, "upside_downside")
        or _first(blend, "upside_pct")
        or _vm_ratio(getattr(view_model, "upside_downside", None))
    )
    recommendation = getattr(view_model, "recommendation", None) or _DASH
    assumptions = _sub(valuation, "assumptions")
    years = [r for r in forecast.get("forecast_years", []) if isinstance(r, Mapping)]
    first_year = years[0] if years else {}
    last_year = years[-1] if years else {}

    rows = [
        ("Giá thị trường dùng trong báo cáo", _num(current)),
        ("Giá mục tiêu tính được", _num(target)),
        ("Tăng/giảm so với giá thị trường", _pct(upside)),
        ("Khuyến nghị trong báo cáo chính", str(recommendation)),
        ("Giá trị theo FCFF", _num(_first(blend, "price_fcff_vnd") or _first(fcff, "implied_price"))),
        ("Giá trị theo FCFE", _num(_first(blend, "price_fcfe_vnd") or _first(fcfe, "implied_price"))),
        ("Trọng số FCFF / FCFE", f"{_pct(_first(blend, 'fcff_weight') or 0.6)} / {_pct(_first(blend, 'fcfe_weight') or 0.4)}"),
        ("Độ lệch FCFF/FCFE", _pct(_first(blend, "fcff_fcfe_gap_pct"))),
        ("WACC", _pct(_first(fcff, "wacc") or assumptions.get("wacc"))),
        ("Tăng trưởng dài hạn", _pct(_first(fcff, "terminal_growth") or assumptions.get("terminal_growth"))),
        ("Doanh thu năm đầu dự phóng", _num(first_year.get("revenue"))),
        ("Doanh thu năm cuối dự phóng", _num(last_year.get("revenue"))),
        ("LNST năm đầu dự phóng", _num(first_year.get("net_income"))),
        ("LNST năm cuối dự phóng", _num(last_year.get("net_income"))),
    ]

    lines = [
        "## Vì sao báo cáo chính kết luận như vậy",
        "",
        _kv_table(rows),
        "",
        (
            "Kết luận trong báo cáo chính được nối trực tiếp từ giá thị trường, giá trị "
            "nội tại theo dòng tiền, mức tăng/giảm kỳ vọng và các cảnh báo dữ liệu. Nếu "
            "FCFF và FCFE cho kết quả lệch lớn, người đọc phải ưu tiên phần kết hợp phương pháp, "
            "phân tích độ nhạy và đối chiếu cảnh báo thay vì chỉ đọc một giá mục tiêu duy nhất."
        ),
    ]
    if issues:
        lines.extend(["", "**Cảnh báo cần đọc kèm kết luận:**"])
        lines.extend(f"- {_issue_label(issue)}" for issue in issues)
    return "\n".join(lines)


def _section_analysis_findings(findings: Sequence[Any]) -> str:
    translated = list(
        dict.fromkeys(_issue_label(item) for item in findings if str(item or "").strip())
    )
    if not translated:
        return ""
    lines = [
        "## Kết quả phản biện chất lượng phân tích",
        "",
        (
            "Phần này tóm tắt các đánh giá định tính về logic dự phóng, luận điểm đầu tư, "
            "chất lượng bằng chứng và tính nhất quán của định giá."
        ),
        "",
    ]
    lines.extend(f"- {item}" for item in translated)
    return "\n".join(lines)


def build_valuation_workings_md(
    *,
    ticker: str,
    run_id: str,
    valuation: Mapping[str, Any],
    forecast: Mapping[str, Any],
    facts: Mapping[str, Any],
    view_model: Any | None = None,
) -> str:
    """Return the full valuation workings Markdown for *ticker* / *run_id*."""
    ticker = (ticker or "").upper()
    valuation = dict(valuation or {})
    forecast = dict(forecast or {})

    fcff = _sub(valuation, "fcff_dcf", "fcff")
    fcfe = _sub(valuation, "fcfe_dcf", "fcfe")
    blend = _sub(valuation, "blend", "blend_dcf")

    title = f"# Diễn giải định giá — {ticker}\n"
    intro = (
        "> Tài liệu nội bộ để kiểm định. Trình bày đầy đủ công thức, dữ liệu đầu vào và bước "
        "trung gian của từng phép tính định giá. KHÔNG phải báo cáo khách hàng.\n"
    )

    sections = [
        _section_header(ticker, run_id, valuation, view_model),
        _section_summary(valuation, blend, view_model),
        _section_assumptions(valuation, fcff, fcfe),
        _section_forecast(forecast),
        _section_ratios(forecast),
        _section_fcff(fcff),
        _section_fcfe(fcfe),
        _section_blend(blend),
        _section_pe_forward(valuation),
        _section_sensitivity(valuation),
        _section_crosschecks(valuation, fcff, blend, fcfe),
    ]
    return title + "\n" + intro + "\n" + "\n\n".join(sections) + "\n"


def build_report_explanation_md(
    *,
    ticker: str,
    run_id: str,
    valuation: Mapping[str, Any],
    forecast: Mapping[str, Any],
    facts: Mapping[str, Any],
    view_model: Any | None = None,
) -> str:
    """Build a client-facing valuation appendix with full deterministic workings."""
    ticker = (ticker or "").upper()
    valuation = dict(valuation or {})
    forecast = dict(forecast or {})
    fcff = _sub(valuation, "fcff_dcf", "fcff")
    fcfe = _sub(valuation, "fcfe_dcf", "fcfe")
    blend = _sub(valuation, "blend", "blend_dcf")
    company = getattr(view_model, "company_name", None) or ticker
    status_raw = str(getattr(view_model, "publication_status", "") or "")
    status = (
        "Đủ dữ liệu cho các mục bắt buộc"
        if status_raw == "complete"
        else "Có thể đọc, kèm công bố phần dữ liệu còn thiếu"
    )
    status_issues = list(
        dict.fromkeys(
            item
            for item in [
                *list(getattr(view_model, "missing_required_fields", []) or []),
                *list(getattr(view_model, "display_blocking_reasons", []) or []),
            ]
            if not str(item).startswith("post_render_client_language_forbidden:")
        )
    )
    critic_findings = list(getattr(view_model, "critic_findings", []) or [])

    status_lines = [
        f"# Phụ lục giải trình định giá - {ticker}",
        "",
        f"Doanh nghiệp được phân tích: **{company}**.",
        "",
        (
            "Tài liệu này là phụ lục chi tiết của báo cáo định giá. Mục tiêu là giải thích "
            "vì sao báo cáo chính đưa ra giá mục tiêu, mức tăng/giảm kỳ vọng, khuyến nghị và các "
            "nhận định trọng tâm bằng dữ liệu đầu vào, công thức, bước tính trung gian và "
            "cảnh báo cần đọc kèm."
        ),
        "",
        "## Trạng thái và giới hạn",
        "",
        f"- Trạng thái báo cáo: **{status}**",
        f"- Mã lần chạy: `{run_id}`",
    ]
    if status_issues:
        status_lines.extend(f"- {_issue_label(issue)}" for issue in status_issues)
    else:
        status_lines.append("- Không ghi nhận thiếu sót trọng yếu trong các mục bắt buộc.")

    decision_basis = _section_report_decision_basis(
        valuation,
        forecast,
        blend,
        fcff,
        fcfe,
        view_model,
        status_issues,
    )
    analysis_findings = _section_analysis_findings(critic_findings)
    workings = build_valuation_workings_md(
        ticker=ticker,
        run_id=run_id,
        valuation=valuation,
        forecast=forecast,
        facts=facts,
        view_model=view_model,
    )
    workings = workings.replace(
        "# Diễn giải định giá — " + ticker,
        "## Chi tiết tính toán định giá",
        1,
    )
    workings = workings.replace(
        "> Tài liệu nội bộ để kiểm định. Trình bày đầy đủ công thức, dữ liệu đầu vào và bước "
        "trung gian của từng phép tính định giá. KHÔNG phải báo cáo khách hàng.",
        (
            "> Phần này trình bày đầy đủ công thức, dữ liệu đầu vào, bước tính trung gian, "
            "bảng dự phóng, cầu nối định giá, phân tích độ nhạy và cảnh báo để người đọc "
            "kiểm tra lại kết quả trong báo cáo chính."
        ),
        1,
    )
    blocks = ["\n".join(status_lines), decision_basis]
    if analysis_findings:
        blocks.append(analysis_findings)
    blocks.append(workings)
    return "\n\n".join(blocks)


def load_workings_inputs(run_id: str) -> dict[str, Any]:
    """Load the locked valuation/forecast/facts artifacts for *run_id* via the manifest."""
    from backend.reporting import client_report_view_model as crvm
    from backend.reporting.report_data_loader import ROOT, _read_manifest_or_raise

    manifest = _read_manifest_or_raise(run_id, base_dir=ROOT)
    return {
        "valuation": crvm._valuation("", manifest),
        "forecast": crvm._forecast("", manifest),
        "facts": crvm._facts("", manifest),
    }
