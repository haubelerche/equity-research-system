"""8-section report builder per GOAL_OUTPUT.md page spec.

Produces structured output with \\pagebreak markers between pages.
All content comes from ReportContext fields — never invented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from typing import Any


DISCLAIMER_TEXT = (
    "Báo cáo này chỉ nhằm mục đích nghiên cứu và tham khảo học thuật/sản phẩm. "
    "Nội dung không phải là khuyến nghị đầu tư cá nhân hóa, không phải lời mời "
    "mua/bán chứng khoán, và không thay thế tư vấn từ chuyên gia được cấp phép. "
    "Rating trong báo cáo là kết luận mô hình dựa trên dữ liệu, giả định và mức "
    "sinh lời kỳ vọng tại thời điểm lập báo cáo; không phải khuyến nghị đầu tư "
    "cá nhân hóa."
)

_PLACEHOLDER = "_[Nội dung chưa có]_"


def _fmt_price(price: float) -> str:
    """Format a price as integer with thousands commas, e.g. 94400 → '94,400'."""
    return f"{int(round(price)):,}"


def _or_placeholder(text: str) -> str:
    """Return text or Vietnamese placeholder if empty."""
    return text.strip() if text.strip() else _PLACEHOLDER


_RATING_LABELS: dict[str, str] = {
    "BUY": "Mua",
    "MUA": "Mua",
    "HOLD": "Giữ",
    "GIỮ": "Giữ",
    "NẮM GIỮ": "Giữ",
    "SELL": "Bán",
    "BÁN": "Bán",
}


def _rating_label(rating: str) -> str:
    """Return the Vietnamese display label for a rating code, or the raw code if unknown."""
    return _RATING_LABELS.get((rating or "").upper(), rating or "")


@dataclass
class ReportContext:
    # Required
    ticker: str
    company_name: str
    exchange: str
    report_date: str        # "2026-06-01"
    data_cutoff: str        # "2025-12-31"
    rating: str             # "BUY" | "HOLD" | "SELL" | "UNDER_REVIEW"
    current_price: float
    target_price: float
    upside_pct: float       # e.g. 45.1 (not 0.451)
    risk_level: str
    data_confidence: str
    status: str             # "DRAFT" | "NEEDS_REVIEW" | "PENDING_APPROVAL" | "APPROVED" | "BLOCKED" | "FINAL_EXPORTABLE"

    # Optional — default empty string or 0
    market_cap_bn: float = 0.0
    revenue_latest_bn: float = 0.0
    revenue_growth_pct: float = 0.0
    gross_margin_pct: float = 0.0
    net_margin_pct: float = 0.0
    roe_pct: float = 0.0
    roa_pct: float = 0.0
    eps_vnd: float = 0.0
    pe_x: float = 0.0
    pb_x: float = 0.0
    fiscal_year: str = "2024"
    horizon: str = "12 tháng"
    wacc_pct: float = 0.0
    terminal_growth_pct: float = 0.0
    source_coverage_pct: float = 0.0
    numeric_consistency: str = "PENDING"
    valuation_reproducibility: str = "PENDING"
    human_review: str = "PENDING"

    # Prebuilt markdown content (populated by generate_report.py)
    investment_thesis: str = ""
    company_overview: str = ""
    business_driver_table: str = ""
    financial_summary_table: str = ""
    financial_narrative: str = ""
    forecast_table: str = ""
    driver_table: str = ""
    assumptions_table: str = ""
    forecast_narrative: str = ""
    dcf_table: str = ""
    valuation_summary_table: str = ""
    valuation_assumptions_table: str = ""
    valuation_narrative: str = ""
    sensitivity_matrix: str = ""
    scenario_table: str = ""
    peer_table: str = ""
    sensitivity_narrative: str = ""
    catalysts_table: str = ""
    risks_table: str = ""
    risk_narrative: str = ""
    key_takeaways: str = ""
    quality_summary_table: str = ""
    key_sources_table: str = ""

    valuation_bridge: str = ""    # Prebuilt markdown bridge: EV → Equity → Price steps
    citation_appendix: str = ""   # Full citation appendix in markdown

    # Chart paths: chart_id → relative file path
    chart_paths: dict = field(default_factory=dict)

    # Internal display flags — set by loaders, never invented by section builder
    _current_price_missing: bool = False
    _target_price_missing: bool = False
    _upside_missing: bool = False
    _has_valuation: bool = False
    _has_sensitivity: bool = False
    _has_forecast_table: bool = False


@dataclass(frozen=True)
class ReportSectionContract:
    section_id: str
    allowed_content_types: tuple[str, ...]
    required_artifacts: tuple[str, ...] = ()
    max_words: int = 650
    chart_slots: int = 0
    table_slots: int = 0


REPORT_SECTION_CONTRACTS: dict[str, ReportSectionContract] = {
    "snapshot": ReportSectionContract(
        section_id="snapshot",
        allowed_content_types=("investment_snapshot", "rating_status", "market_snapshot"),
        required_artifacts=("facts", "valuation_result"),
        chart_slots=1,
        table_slots=1,
    ),
    "company_overview": ReportSectionContract(
        section_id="company_overview",
        allowed_content_types=("business_update", "company_profile", "ownership"),
        required_artifacts=("facts",),
        chart_slots=2,
        table_slots=1,
    ),
    "financial_performance": ReportSectionContract(
        section_id="financial_performance",
        allowed_content_types=("financials", "margin_drivers", "cash_flow", "ratios"),
        required_artifacts=("facts",),
        table_slots=3,
    ),
    "forecast_drivers": ReportSectionContract(
        section_id="forecast_drivers",
        allowed_content_types=("forecast", "guidance", "operating_drivers"),
        required_artifacts=("forecast",),
        table_slots=2,
    ),
    "valuation_model": ReportSectionContract(
        section_id="valuation_model",
        allowed_content_types=("valuation", "bridge", "assumptions"),
        required_artifacts=("valuation_result", "fcff", "fcfe"),
        table_slots=2,
    ),
    "sensitivity_peer": ReportSectionContract(
        section_id="sensitivity_peer",
        allowed_content_types=("sensitivity", "peer_check"),
        required_artifacts=("valuation_result",),
        table_slots=2,
    ),
    "risks_catalysts": ReportSectionContract(
        section_id="risks_catalysts",
        allowed_content_types=("material_events", "risk", "catalyst"),
        required_artifacts=("facts", "evidence"),
        table_slots=2,
    ),
    "conclusion_sources": ReportSectionContract(
        section_id="conclusion_sources",
        allowed_content_types=("conclusion", "quality_status", "sources", "disclaimer"),
        required_artifacts=("citation",),
        table_slots=2,
    ),
}


def section_coherence_gate(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect obvious content-class leakage across contracted report sections."""
    violations: list[dict[str, str]] = []
    valuation_terms = ("target price", "price_fcff", "price_fcfe", "fcff", "fcfe", "wacc", "valuation", "dcf")
    risk_terms = ("risk", "downside", "impairment", "litigation", "catalyst", "headwind")
    business_only_sections = {"company_overview"}
    driver_sections = {"financial_performance", "forecast_drivers"}

    for section in sections:
        section_id = str(section.get("page") or section.get("section_id") or "")
        text = str(section.get("markdown") or section.get("content") or "").lower()
        if section_id in business_only_sections and any(term in text for term in valuation_terms):
            violations.append({"section_id": section_id, "reason": "valuation_content_in_business_section"})
        if section_id in driver_sections and any(term in text for term in ("target price", "price_fcff", "price_fcfe")):
            violations.append({"section_id": section_id, "reason": "target_price_content_in_driver_section"})
        if section_id not in {"risks_catalysts", "conclusion_sources"} and any(term in text for term in risk_terms):
            if section_id in business_only_sections:
                violations.append({"section_id": section_id, "reason": "risk_content_in_business_section"})

    return {
        "status": "PASS" if not violations else "FAIL",
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _chart_ref(ctx: ReportContext, chart_id: str, fallback_note: str = "") -> str:
    """Return an image reference or a blockquote placeholder.

    Returns ``![{chart_id}]({path})`` if chart_id is in ctx.chart_paths,
    otherwise returns a blockquote note.
    """
    path = ctx.chart_paths.get(chart_id)
    if path:
        return f"![{chart_id}]({path})"
    note = fallback_note if fallback_note else f"Biểu đồ {chart_id} chưa được tạo."
    return f"> _{note}_"


def _build_valuation_bridge_md(
    sum_pv_fcff: float | None,
    pv_tv_fcff: float | None,
    ev_fcff: float | None,
    net_debt: float | None,
    equity_value_fcff: float | None,
    shares_mn: float | None,
    price_fcff: float | None,
    sum_pv_fcfe: float | None,
    pv_tv_fcfe: float | None,
    equity_value_fcfe: float | None,
    price_fcfe: float | None,
    target_price: float | None,
    current_price: float | None,
    fcff_weight: float = 0.60,
    fcfe_weight: float = 0.40,
) -> str:
    """Build a valuation bridge markdown table showing every step from FCF to target price.

    Returns a markdown string with two bridge tables (FCFF and FCFE) and the blend line.
    Uses '—' for any missing value rather than crashing.
    """

    def _fv(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v:,.1f}"

    def _fv_price(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{int(round(v)):,}"

    def _net_debt_display(v: float | None) -> str:
        if v is None:
            return "—"
        if v < 0:
            return f"({abs(v):,.1f}) _(Net Cash)_"
        return f"{v:,.1f}"

    # Upside/downside
    if target_price is not None and current_price is not None and current_price != 0:
        upside_pct = (target_price - current_price) / current_price * 100
        upside_sign = "+" if upside_pct >= 0 else ""
        upside_str = f"{upside_sign}{upside_pct:.1f}%"
    else:
        upside_str = "—"

    fcff_weight_pct = int(round(fcff_weight * 100))
    fcfe_weight_pct = int(round(fcfe_weight * 100))

    fcff_block = f"""\
### FCFF Bridge

| Bước | Giá trị (tỷ VND) |
|---|---|
| Σ PV(FCFF 2026–2030) | {_fv(sum_pv_fcff)} |
| + PV(Terminal Value FCFF) | {_fv(pv_tv_fcff)} |
| = Enterprise Value | {_fv(ev_fcff)} |
| − Net Debt (âm = Net Cash) | {_net_debt_display(net_debt)} |
| = Equity Value (FCFF) | {_fv(equity_value_fcff)} |
| ÷ Số cổ phiếu pha loãng (triệu CP) | {_fv(shares_mn)} |
| **= Price_FCFF (VNĐ/CP)** | **{_fv_price(price_fcff)}** |"""

    fcfe_block = f"""\
### FCFE Bridge

| Bước | Giá trị (tỷ VND) |
|---|---|
| Σ PV(FCFE 2026–2030) | {_fv(sum_pv_fcfe)} |
| + PV(Terminal Value FCFE) | {_fv(pv_tv_fcfe)} |
| = Equity Value (FCFE) | {_fv(equity_value_fcfe)} |
| ÷ Số cổ phiếu pha loãng (triệu CP) | {_fv(shares_mn)} |
| **= Price_FCFE (VNĐ/CP)** | **{_fv_price(price_fcfe)}** |"""

    blend_block = f"""\
### Giá mục tiêu gộp

| | |
|---|---|
| Price_FCFF | {_fv_price(price_fcff)} VNĐ/CP |
| Price_FCFE | {_fv_price(price_fcfe)} VNĐ/CP |
| **Target Price ({fcff_weight_pct}% FCFF + {fcfe_weight_pct}% FCFE)** | **{_fv_price(target_price)} VNĐ/CP** |
| Giá thị trường hiện tại | {_fv_price(current_price)} VNĐ/CP |
| **Tiềm năng tăng/giảm** | **{upside_str}** |"""

    return f"{fcff_block}\n\n{fcfe_block}\n\n{blend_block}"


# ---------------------------------------------------------------------------
# Section builders (internal)
# ---------------------------------------------------------------------------

def _build_cover_snapshot(ctx: ReportContext) -> dict:
    """Page 1 — Cover / Snapshot."""
    upside_sign = "+" if ctx.upside_pct >= 0 else ""
    thesis = _or_placeholder(ctx.investment_thesis)

    md = f"""\
# {ctx.ticker} — {ctx.company_name}
**Sàn:** {ctx.exchange} | **Ngày báo cáo:** {ctx.report_date}

---

## Snapshot

| Chỉ số | Giá trị |
|---|---|
| **Giá hiện tại (VNĐ)** | {_fmt_price(ctx.current_price)} |
| **Giá mục tiêu (VNĐ)** | {_fmt_price(ctx.target_price)} |
| **Tiềm năng tăng/giảm** | {upside_sign}{ctx.upside_pct:.1f}% |
| **Rating** | **{ctx.rating}** |
| **Khung thời gian** | {ctx.horizon} |
| **Mức rủi ro** | {ctx.risk_level} |
| **Dữ liệu đến** | {ctx.data_cutoff} |
| **Độ tin cậy dữ liệu** | {ctx.data_confidence} |

---

## Luận điểm đầu tư

{thesis}
"""
    return {
        "page": "cover_snapshot",
        "page_number": 1,
        "title": f"{ctx.ticker} — Cover & Snapshot",
        "markdown": md,
        "chart_ids": [],
        "word_count": len(md.split()),
    }


def _build_company_overview(ctx: ReportContext) -> dict:
    """Page 2 — Company Overview."""
    overview = _or_placeholder(ctx.company_overview)
    driver_table = _or_placeholder(ctx.business_driver_table)
    chart = _chart_ref(ctx, "C1", "Cơ cấu doanh thu theo phân khúc")

    md = f"""\
# Tổng quan công ty — {ctx.ticker}

{overview}

## Động lực kinh doanh

{driver_table}

## Biểu đồ cơ cấu doanh thu (C1)

{chart}
"""
    return {
        "page": "company_overview",
        "page_number": 2,
        "title": "Tổng quan công ty",
        "markdown": md,
        "chart_ids": ["C1"],
        "word_count": len(md.split()),
    }


def _build_financial_performance(ctx: ReportContext) -> dict:
    """Page 3 — Financial Performance."""
    fin_table = _or_placeholder(ctx.financial_summary_table)
    narrative = _or_placeholder(ctx.financial_narrative)
    chart_rev = _chart_ref(ctx, "C2", "Doanh thu & EBITDA Trend")
    chart_eps = _chart_ref(ctx, "C3", "EPS & P/E Trend")
    chart_margin = _chart_ref(ctx, "C4", "Biên lợi nhuận & ROE Trend")

    md = f"""\
# Kết quả tài chính lịch sử — {ctx.ticker}

## Bảng tóm tắt tài chính (FY {ctx.fiscal_year})

{fin_table}

## Biểu đồ doanh thu & EBITDA (C2)

{chart_rev}

## Biểu đồ EPS & P/E (C3)

{chart_eps}

## Biểu đồ biên lợi nhuận & ROE (C4)

{chart_margin}

## Phân tích

{narrative}
"""
    return {
        "page": "financial_performance",
        "page_number": 3,
        "title": "Kết quả tài chính lịch sử",
        "markdown": md,
        "chart_ids": ["C2", "C3", "C4"],
        "word_count": len(md.split()),
    }


def _build_forecast_assumptions(ctx: ReportContext) -> dict:
    """Page 4 — Forecast & Assumptions."""
    forecast_table = _or_placeholder(ctx.forecast_table)
    driver_table = _or_placeholder(ctx.driver_table)
    assumptions_table = _or_placeholder(ctx.assumptions_table)
    narrative = _or_placeholder(ctx.forecast_narrative)
    chart = _chart_ref(ctx, "C5", "Dự phóng doanh thu & lợi nhuận")

    md = f"""\
# Dự phóng & Giả định — {ctx.ticker}

## Bảng dự phóng tài chính

{forecast_table}

## Driver kinh doanh → Giả định

{driver_table}

## Bảng giả định chi tiết

{assumptions_table}

## Biểu đồ dự phóng (C5)

{chart}

## Phân tích dự phóng

{narrative}
"""
    return {
        "page": "forecast_assumptions",
        "page_number": 4,
        "title": "Dự phóng & Giả định",
        "markdown": md,
        "chart_ids": ["C5"],
        "word_count": len(md.split()),
    }


def _build_valuation(ctx: ReportContext) -> dict:
    """Page 5 — Valuation."""
    dcf_table = _or_placeholder(ctx.dcf_table)
    val_summary = _or_placeholder(ctx.valuation_summary_table)
    val_assumptions = _or_placeholder(ctx.valuation_assumptions_table)
    narrative = _or_placeholder(ctx.valuation_narrative)
    chart = _chart_ref(ctx, "C6", "DCF Value Bridge")

    bridge_section = ""
    if ctx.valuation_bridge:
        bridge_section = f"\n## Valuation Bridge\n\n{ctx.valuation_bridge}\n"

    md = f"""\
# Định giá — {ctx.ticker}

## DCF FCFF

**WACC:** {ctx.wacc_pct:.1f}% | **Tăng trưởng dài hạn:** {ctx.terminal_growth_pct:.1f}%

{dcf_table}
{bridge_section}
## Tổng hợp định giá

{val_summary}

## Giả định định giá

{val_assumptions}

## Biểu đồ định giá (C6)

{chart}

## Nhận xét định giá

{narrative}
"""
    return {
        "page": "valuation",
        "page_number": 5,
        "title": "Định giá",
        "markdown": md,
        "chart_ids": ["C6"],
        "word_count": len(md.split()),
    }


def _build_sensitivity_peer(ctx: ReportContext) -> dict:
    """Page 6 — Sensitivity & Peer Comparison."""
    sensitivity_matrix = _or_placeholder(ctx.sensitivity_matrix)
    scenario_table = _or_placeholder(ctx.scenario_table)
    peer_table = _or_placeholder(ctx.peer_table)
    narrative = _or_placeholder(ctx.sensitivity_narrative)
    chart = _chart_ref(ctx, "C7", "Sensitivity Heatmap")
    chart_peer = _chart_ref(ctx, "C8", "Biểu đồ so sánh đồng ngành chưa được tạo.")

    md = f"""\
# Phân tích độ nhạy & So sánh đồng ngành — {ctx.ticker}

## Ma trận độ nhạy (WACC × Tăng trưởng dài hạn)

{sensitivity_matrix}

## Kịch bản (Bull / Base / Bear)

{scenario_table}

## So sánh đồng ngành

{peer_table}

## Biểu đồ độ nhạy (C7)

{chart}

## Biểu đồ so sánh đồng ngành (C8)

{chart_peer}

## Nhận xét

{narrative}
"""
    return {
        "page": "sensitivity_peer",
        "page_number": 6,
        "title": "Phân tích độ nhạy & So sánh đồng ngành",
        "markdown": md,
        "chart_ids": ["C7", "C8"],
        "word_count": len(md.split()),
    }


def _build_catalysts_risks(ctx: ReportContext) -> dict:
    """Page 7 — Catalysts & Risks."""
    catalysts_table = _or_placeholder(ctx.catalysts_table)
    risks_table = _or_placeholder(ctx.risks_table)
    narrative = _or_placeholder(ctx.risk_narrative)

    md = f"""\
# Catalyst & Rủi ro — {ctx.ticker}

## Catalyst tích cực

{catalysts_table}

## Rủi ro chính

{risks_table}

## Đánh giá rủi ro tổng thể

**Mức rủi ro:** {ctx.risk_level}

{narrative}
"""
    return {
        "page": "catalysts_risks",
        "page_number": 7,
        "title": "Catalyst & Rủi ro",
        "markdown": md,
        "chart_ids": [],
        "word_count": len(md.split()),
    }


def _build_conclusion(ctx: ReportContext) -> dict:
    """Page 8 — Conclusion, Audit Summary, Disclaimer."""
    key_takeaways = _or_placeholder(ctx.key_takeaways)
    quality_table = _or_placeholder(ctx.quality_summary_table)
    sources_table = _or_placeholder(ctx.key_sources_table)
    upside_sign = "+" if ctx.upside_pct >= 0 else ""

    citation_section = ""
    if ctx.citation_appendix:
        citation_section = f"\n## Phụ lục Citation\n\n{ctx.citation_appendix}\n"

    md = f"""\
# Kết luận & Phụ lục kiểm định — {ctx.ticker}

## Kết luận đầu tư

**Rating:** {ctx.rating} | **Giá mục tiêu:** {_fmt_price(ctx.target_price)} VNĐ | **Tiềm năng:** {upside_sign}{ctx.upside_pct:.1f}%

{key_takeaways}

## Kiểm định chất lượng báo cáo

| Gate | Kết quả |
|---|---|
| Numeric Consistency | {ctx.numeric_consistency} |
| Valuation Reproducibility | {ctx.valuation_reproducibility} |
| Human Review | {ctx.human_review} |
| Source Coverage | {ctx.source_coverage_pct:.0f}% |

{quality_table}

## Nguồn dữ liệu chính

{sources_table}
{citation_section}
---

## Tuyên bố miễn trách nhiệm

> {DISCLAIMER_TEXT}

---

_Báo cáo sinh ngày {ctx.report_date} | Dữ liệu đến {ctx.data_cutoff}_
"""
    return {
        "page": "conclusion",
        "page_number": 8,
        "title": "Kết luận & Phụ lục kiểm định",
        "markdown": md,
        "chart_ids": [],
        "word_count": len(md.split()),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report_sections(ctx: ReportContext) -> list[dict]:
    """Build exactly 8 page sections from ReportContext.

    Returns a list of dicts, one per page, with keys:
        page, page_number, title, markdown, chart_ids, word_count
    """
    builders = [
        _build_cover_snapshot,
        _build_company_overview,
        _build_financial_performance,
        _build_forecast_assumptions,
        _build_valuation,
        _build_sensitivity_peer,
        _build_catalysts_risks,
        _build_conclusion,
    ]
    return [fn(ctx) for fn in builders]


def assemble_markdown(sections: list[dict]) -> str:
    """Join all section markdowns with \\pagebreak markers between them.

    Returns a string containing exactly 7 \\pagebreak occurrences (one between
    each of the 8 sections).
    """
    return "\n\\pagebreak\n".join(s["markdown"] for s in sections)


# ---------------------------------------------------------------------------
# Citations appendix
# ---------------------------------------------------------------------------

_INTERNAL_TERMS = frozenset({
    "tier", "confidence", "parser", "gate", "chunk_id",
    "source_tier", "parser_version", "validation_status",
    "ingested_at", "is_validated", "reliability_tier",
})


def build_citations_appendix(claim_ledger: dict) -> str:
    """Build a clean HTML 'Nguồn & Trích dẫn' appendix from a serialised ClaimLedger dict.

    Returns an HTML string safe for embedding in the report.
    Only exposes document titles and URLs — no internal audit terms.
    Sources are deduplicated and grouped by report section.
    """
    if not claim_ledger or not isinstance(claim_ledger, dict):
        return ""

    claims: list[dict] = claim_ledger.get("claims", [])
    if not claims:
        return ""

    # Collect unique source_doc traces, keyed by (section, document_title, document_url)
    # Preserve insertion order; deduplicate by (title, url) pair within each section.
    from collections import defaultdict
    by_section: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()

    for claim in claims:
        section = str(claim.get("section") or "").strip()
        for trace in claim.get("traces", []):
            if trace.get("trace_type") != "source_doc":
                continue
            title = str(trace.get("document_title") or "").strip()
            url = str(trace.get("document_url") or "").strip()
            if not title:
                continue
            key = (title, url)
            if key not in seen:
                seen.add(key)
                by_section[section].append((title, url))

    if not by_section:
        return ""

    _SECTION_LABELS: dict[str, str] = {
        "financial_performance": "Kết quả tài chính",
        "valuation": "Định giá",
        "forecast_drivers": "Dự phóng",
        "sensitivity_peer": "Độ nhạy & đồng ngành",
        "risks_catalysts": "Rủi ro & Catalyst",
        "company_overview": "Tổng quan công ty",
        "conclusion_sources": "Kết luận & nguồn",
    }

    items_html: list[str] = []
    counter = 1
    for section in sorted(by_section.keys()):
        label = _SECTION_LABELS.get(section, section.replace("_", " ").title())
        section_header = f'<li class="citation-section-header"><em>{escape(label)}</em></li>'
        items_html.append(section_header)
        for title, url in by_section[section]:
            if url:
                link = f'<a href="{escape(url)}" target="_blank">{escape(url)}</a>'
                entry = f"<li>{counter}. {escape(title)} — {link}</li>"
            else:
                entry = f"<li>{counter}. {escape(title)}</li>"
            items_html.append(entry)
            counter += 1

    list_html = "\n    ".join(items_html)
    return f"""<div class="citations-appendix">
  <h2>Nguồn &amp; Trích dẫn</h2>
  <ol class="source-list">
    {list_html}
  </ol>
</div>"""
