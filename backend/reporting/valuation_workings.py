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
    "4. Dự phóng (driver-based)",
    "5. Chỉ số tài chính",
    "6. Định giá FCFF",
    "7. Định giá FCFE",
    "8. Blend (FCFF + FCFE)",
    "9. P/E Forward (cross-check)",
    "10. Phân tích độ nhạy (sensitivity)",
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
            if warn and str(warn) not in collected:
                collected.append(str(warn))
    return collected


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
        ("run_id", run_id),
        ("Ngày định giá", str(_first(valuation, "valuation_date") or _DASH)),
        ("snapshot_id", str(_first(valuation, "snapshot_id") or _DASH)),
        ("Năm gốc", str(_first(valuation, "base_year") or _DASH)),
        ("reproducibility_hash", str(_first(valuation, "reproducibility_hash") or _DASH)),
    ]
    return f"## {SECTION_TITLES[0]}\n\n" + _kv_table(rows)


def _section_summary(valuation: Mapping[str, Any], blend: Mapping[str, Any], vm: Any) -> str:
    current = _first(valuation, "current_price") or _first(blend, "current_price_vnd")
    target = _first(valuation, "target_price") or _first(blend, "target_price_dcf_vnd")
    upside = _first(valuation, "upside_downside") or _first(blend, "upside_pct")
    recommendation = getattr(vm, "recommendation", None) or _DASH
    rows = [
        ("Giá hiện tại (VND)", _num(current)),
        ("Giá mục tiêu — blend (VND)", _num(target)),
        ("Upside/Downside", _pct(upside)),
        ("Khuyến nghị", recommendation),
    ]
    rule = (
        "**Luật xếp hạng** (total return = upside + dividend yield): "
        "> 20% → MUA; < −10% → BÁN; còn lại → NẮM GIỮ."
    )
    return f"## {SECTION_TITLES[1]}\n\n" + _kv_table(rows) + "\n\n" + rule


def _section_assumptions(valuation: Mapping[str, Any], fcff: Mapping[str, Any], fcfe: Mapping[str, Any]) -> str:
    assumptions = _sub(valuation, "assumptions")
    rows = [
        ("WACC", _pct(_first(fcff, "wacc") or assumptions.get("wacc"))),
        ("Cost of equity (Re)", _pct(_first(fcfe, "cost_of_equity") or assumptions.get("cost_of_equity"))),
        ("Terminal growth (g)", _pct(_first(fcff, "terminal_growth") or assumptions.get("terminal_growth"))),
        ("Số năm dự phóng", str(assumptions.get("forecast_years") or _DASH)),
        ("Thuế suất", _pct(assumptions.get("tax_rate"))),
        ("Target P/E", _mult(assumptions.get("target_pe"))),
        ("Premium/Discount", _pct(assumptions.get("premium_discount_pct"))),
    ]
    note = assumptions.get("note")
    body = _kv_table(rows)
    if note:
        body += f"\n\n> ⚠️ {note}"
    else:
        body += "\n\n> ⚠️ Giả định mặc định cần được HITL xem xét và phê duyệt trước khi khóa định giá."
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
        "| Net borrowing (phát hành − trả nợ) | "
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
        "| Tỷ lệ chi trả (payout) | "
        + " | ".join(_pct((div_by_label.get(lbl) or {}).get("payout_ratio")) for lbl in labels)
        + " |"
    )

    note = (
        "\n\n_Logic driver: doanh thu theo tăng trưởng giả định; biên LN dẫn xuất EBIT/LNST; "
        "lịch nợ vay roll-forward với `net_borrowing = phát hành − trả nợ`; cổ tức theo payout._"
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
    lines.append("| Biên LN gộp | gross_profit / revenue | " + " | ".join(_ratio("gross_profit", "revenue")) + " |")
    lines.append("| Biên EBIT | ebit / revenue | " + " | ".join(_ratio("ebit", "revenue")) + " |")
    lines.append("| Biên LN ròng | net_income / revenue | " + " | ".join(_ratio("net_income", "revenue")) + " |")
    lines.append("| ROE | net_income / equity | " + " | ".join(_ratio("net_income", "equity")) + " |")
    return f"## {SECTION_TITLES[4]}\n\n" + "\n".join(lines)


def _section_fcff(fcff: Mapping[str, Any]) -> str:
    wacc = _first(fcff, "wacc")
    g = _first(fcff, "terminal_growth")
    head = (
        f"**Công thức:** `{FCFF_FORMULA}`\n\n"
        f"- WACC = **{_pct(wacc)}**; terminal growth g = **{_pct(g)}**\n"
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
        ("Terminal value (Gordon: FCFFₙ×(1+g)/(WACC−g))", _num(_first(fcff, "terminal_value"))),
        ("PV terminal value", _num(_first(fcff, "pv_terminal_value"))),
        ("Tỷ trọng TV / EV", _pct(_first(fcff, "terminal_value_weight"))),
        ("= Enterprise value (EV)", _num(_first(fcff, "enterprise_value"))),
        ("− Nợ ròng (net debt)", _num(_first(fcff, "net_debt"))),
        ("= Equity value", _num(_first(fcff, "equity_value"))),
        ("÷ Số cổ phiếu (triệu)", _num(_first(fcff, "shares_outstanding", "shares_mn"))),
        ("= Giá/cổ phiếu (FCFF, VND)", _num(_first(fcff, "implied_price"))),
    ])
    return f"## {SECTION_TITLES[5]}\n\n" + head + "\n" + fcff_lines + bridge


def _section_fcfe(fcfe: Mapping[str, Any]) -> str:
    rows = _kv_table([
        ("Cost of equity (Re)", _pct(_first(fcfe, "cost_of_equity"))),
        ("Terminal growth (g)", _pct(_first(fcfe, "terminal_growth"))),
        ("Equity value", _num(_first(fcfe, "equity_value"))),
        ("÷ Số cổ phiếu (triệu)", _num(_first(fcfe, "shares_outstanding", "shares_mn"))),
        ("= Giá/cổ phiếu (FCFE, VND)", _num(_first(fcfe, "implied_price"))),
    ])
    note = ""
    if _first(fcfe, "implied_price") is None:
        note = "\n\n_Giá FCFE chưa tính được — thiếu input (net borrowing/cổ phiếu). Hiển thị `—`._"
    return (
        f"## {SECTION_TITLES[6]}\n\n"
        "**Công thức:** `FCFE = LN ròng + D&A − CAPEX − ΔNWC + net borrowing`, "
        "chiết khấu theo cost of equity.\n\n" + rows + note
    )


def _section_blend(blend: Mapping[str, Any]) -> str:
    price_fcff = _first(blend, "price_fcff_vnd")
    price_fcfe = _first(blend, "price_fcfe_vnd")
    w_fcff = _first(blend, "fcff_weight") or 0.6
    w_fcfe = _first(blend, "fcfe_weight") or 0.4
    target = _first(blend, "target_price_dcf_vnd")
    formula = blend.get("formula") or "Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE"
    arithmetic = (
        f"`{_num(w_fcff, 2)} × {_num(price_fcff)} + {_num(w_fcfe, 2)} × {_num(price_fcfe)} "
        f"= {_num(target)}`"
    )
    rows = _kv_table([
        ("Price_FCFF (VND)", _num(price_fcff)),
        ("Price_FCFE (VND)", _num(price_fcfe)),
        ("Trọng số FCFF / FCFE", f"{_num(w_fcff, 2)} / {_num(w_fcfe, 2)}"),
        ("= Giá mục tiêu blend (VND)", _num(target)),
        ("Chênh lệch FCFF/FCFE", _pct(_first(blend, "fcff_fcfe_gap_pct"))),
        ("Chỉ ở dạng nháp (is_draft_only)", str(blend.get("is_draft_only"))),
    ])
    gap_note = ""
    gap = _first(blend, "fcff_fcfe_gap_pct")
    try:
        if gap is not None and float(gap) > 0.25:
            gap_note = "\n\n> ⚠️ Chênh lệch FCFF/FCFE > 25% — blend bị chặn (draft-only), cần rà soát net borrowing/net debt/CAPEX/NWC."
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
            "_Không có artifact P/E Forward để đối chiếu._"
        )
    rows: list[tuple[str, str]] = [
        ("EPS Forward (VND)", _num(_first(pe, "eps_forward_vnd", "eps_forward"))),
        ("Peer median P/E", _mult(_first(pe, "peer_median_pe"))),
        ("Premium/Discount", _pct(_first(pe, "premium_discount_pct"))),
        ("Target P/E", _mult(_first(pe, "target_pe"))),
        ("Target price (VND)", _num(_first(pe, "target_price_vnd"))),
    ]
    body = _kv_table(rows)
    peers = pe.get("peer_table") or []
    if peers:
        body += "\n\n| Peer | Giá | EPS Fwd | P/E |\n| --- | ---: | ---: | ---: |\n"
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
        body += f"\n\n_Rationale premium/discount: {rationale}_"
    return f"## {SECTION_TITLES[8]}\n\n" + body


def _render_sensitivity_grid(name: str, grid: Mapping[str, Any]) -> str:
    matrix = grid.get("matrix")
    if not matrix:
        return ""
    # Resolve the two axes by trying the common range key names.
    row_keys = ("wacc_range", "re_range", "eps_range", "price_fcff_range", "ebitda_range")
    col_keys = ("g_range", "pe_range", "price_fcfe_range", "multiple_range")
    row_axis = next((grid[k] for k in row_keys if grid.get(k)), list(range(len(matrix))))
    col_axis = next((grid[k] for k in col_keys if grid.get(k)), list(range(len(matrix[0]) if matrix else 0)))

    pct_axes = {"wacc_range", "re_range", "g_range"}
    row_is_pct = any(grid.get(k) is row_axis for k in pct_axes)
    col_is_pct = any(grid.get(k) is col_axis for k in pct_axes)
    row_fmt = (lambda v: _pct(v)) if row_is_pct else (lambda v: _num(v))
    col_fmt = (lambda v: _pct(v)) if col_is_pct else (lambda v: _num(v))

    label = grid.get("label") or grid.get("pe_label") or name
    table = _grid_table(
        row_axis,
        col_axis,
        matrix,
        corner=str(label),
        row_fmt=row_fmt,
        col_fmt=col_fmt,
        cell_fmt=lambda v: _num(v),
    )
    formula = grid.get("formula")
    head = f"**{name}**" + (f" — `{formula}`" if formula else "")
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
        lines.append(f"- {flag} FCFF implied price ({_num(implied)}) khớp Price_FCFF trong blend ({_num(price_fcff)}).")
    else:
        lines.append("- FCFF implied price / Price_FCFF: thiếu dữ liệu để đối chiếu (—).")

    warnings = _warnings_block(blend, fcff, fcfe, valuation)
    lines.append("")
    if warnings:
        lines.append("**Cảnh báo từ engine:**")
        lines.append("")
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("**Cảnh báo từ engine:** _không có._")

    lines.append("")
    lines.append(f"**reproducibility_hash:** `{_first(valuation, 'reproducibility_hash') or _DASH}`")
    lines.append("")
    lines.append(
        "_Lineage: mọi số định giá dẫn xuất từ canonical facts đã khóa và artifact định "
        "giá Python; không có số nào do LLM sinh._"
    )
    return f"## {SECTION_TITLES[10]}\n\n" + "\n".join(lines)


# ── public builder ────────────────────────────────────────────────────────────

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
        "> Tài liệu nội bộ để kiểm định. Trình bày đầy đủ công thức, input và bước "
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
