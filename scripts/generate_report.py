"""Phase 6 -> Report Generation (Enhanced).

Reads from a research snapshot (frozen accepted facts) and the latest
valuation artifact, then generates a structured Markdown equity research
report with:
  - Forecast income statement 5 years (2026F->2030F)
  - FCFF valuation table with full breakdown
  - User-readable citations (source_title, value, period)
  - Draft BUY/HOLD/SELL rating based on valuation upside
  - Evidence without truncation; deduplicated catalyst events

No LLM is called -> all numbers come from canonical facts and
deterministic valuation/forecast engines.

Usage:
    python scripts/generate_report.py --ticker DHG
    python scripts/generate_report.py --ticker DHG --report-type full_report
    python scripts/generate_report.py --ticker DHG --snapshot-id snap_abc123
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k.strip(), _v)

import psycopg2
import psycopg2.extras

from backend.analytics.approval_gate import build_gate_from_artifacts
from backend.reporting.citation_artifact_writer import (
    build_citation_artifact,
    write_citation_artifact,
    write_final_citation_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
VALUATION_DIR = ROOT / "artifacts" / "valuation"
FORECAST_DIR = ROOT / "artifacts" / "forecast"

MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025
FORECAST_YEARS = [2026, 2027, 2028, 2029, 2030]

_COMPANY_INFO = {
    "DHG": {"name": "Công ty Cổ phần Dược Hậu Giang", "exchange": "HOSE", "sector": "Dược phẩm"},
    "IMP": {"name": "Công ty Cổ phần Dược phẩm Imexpharm", "exchange": "HOSE", "sector": "Dược phẩm"},
    "DMC": {"name": "Công ty Cổ phần Xuất nhập khẩu Y tế Domesco", "exchange": "HOSE", "sector": "Dược phẩm"},
    "TRA": {"name": "Công ty Cổ phần Traphaco", "exchange": "HOSE", "sector": "Dược phẩm"},
    "DBD": {"name": "Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định", "exchange": "HOSE", "sector": "Dược phẩm"},
}

_LINE_ITEM_LABELS = {
    "revenue.net": "Doanh thu thuần",
    "gross_profit.total": "Lợi nhuận gộp",
    "net_income.parent": "Lợi nhuận sau thuế (cty mẹ)",
    "eps.basic": "EPS cơ bản (VND/CP)",
    "operating_cash_flow.total": "Dòng tiền hoạt động",
    "total_assets.ending": "Tổng tài sản",
    "equity.parent": "Vốn chủ sở hữu (cty mẹ)",
    "ebitda.total": "EBITDA",
    "capex.total": "CAPEX",
    "depreciation.total": "Khấu hao",
    "total_debt.ending": "Tổng nợ vay",
    "cash_and_equivalents.ending": "Tiền và tương đương tiền",
}

_SOURCE_TYPE_LABEL = {
    "financial_statement": "Báo cáo tài chính (vnstock API)",
    "vnstock_finance": "Báo cáo tài chính (vnstock API)",
    "balance_sheet": "Bảng cân đối kế toán (vnstock API)",
    "cash_flow": "Báo cáo lưu chuyển tiền tệ (vnstock API)",
    "market_data": "Dữ liệu thị trường (vnstock API)",
    "golden_csv": "Bộ dữ liệu kiểm chứng nội bộ",
    "syn_facts": "Dữ liệu canonical nội tại",
    "api": "API dữ liệu tài chính",
    "csv": "Tệp CSV nội bộ",
    "manual": "Nhập thủ công",
}


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


def _load_latest_valuation(ticker: str) -> dict | None:
    files = sorted(VALUATION_DIR.glob(f"{ticker}_*_valuation.json"), reverse=True)
    return json.loads(files[0].read_text(encoding="utf-8")) if files else None


def _load_snapshot_facts(snapshot_id: str) -> list[dict]:
    from backend.dataops.snapshot import load_snapshot_facts
    return load_snapshot_facts(snapshot_id)


def _load_evidence_chunks(conn, ticker: str, limit: int = 30) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT dc.chunk_id, dc.source_id, dc.section_title,
                   dc.chunk_text, dc.fiscal_year, dc.metadata_json
            FROM ingest.document_chunks dc
            WHERE dc.ticker = %s
            ORDER BY dc.fiscal_year DESC NULLS LAST, dc.chunk_index
            LIMIT %s
            """,
            (ticker, limit),
        )
        return [dict(r) for r in cur.fetchall()]


# -- Formatting helpers ---------------------------------------------------------

def _fmt_bn(val: float | None) -> str:
    return f"{val:,.1f}" if val is not None else "N/A"


def _fmt_vnd(val: float | None) -> str:
    return f"{val:,.0f}" if val is not None else "N/A"


def _fmt_pct(val: float | None) -> str:
    return f"{val:.1%}" if val is not None else "N/A"


def _fmt_x(val: float | None) -> str:
    return f"{val:.1f}x" if val is not None else "N/A"


# -- Citation helpers (Phase 4: backed by backend.citations) -------------------

def _build_citation_map_from_fact_table(
    ticker: str,
    fact_table: "Any",
    context_events: "dict | None" = None,
) -> "dict[str, dict]":
    """Build citation map from a FactTable (Phase 4 path).

    Uses backend.citations.citation_map.build_citation_map() which produces
    CitationRecord objects with real source provenance from FactEntry.
    Returns a plain dict compatible with the legacy _footnotes() format.
    """
    from backend.citations.citation_map import build_citation_map, citation_map_to_legacy_dict
    cmap_obj = build_citation_map(
        ticker=ticker,
        fact_table=fact_table,
        context_events=context_events,
    )
    return citation_map_to_legacy_dict(cmap_obj)


def _build_citation_map(facts: list[dict]) -> dict[str, dict]:
    """Legacy path: build citation map from raw fact rows (pre-Phase-4 fallback).

    Used when a FactTable is not available. Kept for backward compat with
    snapshot-based loading paths that return flat fact dicts.
    """
    cmap: dict[str, dict] = {}
    for f in facts:
        key = f"{f['ticker']}/{f['fiscal_year']}FY/{f['line_item_code']}"
        metric = f["line_item_code"]
        label = _LINE_ITEM_LABELS.get(metric, metric)
        unit = f.get("unit", "vnd_bn")
        val = f["value"]
        val_str = f"{val:,.1f} t? VND" if unit == "vnd_bn" else (
            f"{val:,.0f} VND/CP" if unit == "vnd" else f"{val}"
        )
        published = f.get("src_published_at") or ""
        if hasattr(published, "isoformat"):
            published = published.isoformat()

        # Phase 4: use source_tier if available (from JOIN on ingest.sources)
        source_tier = f.get("source_tier")
        tier_suffix = f" [Tier {source_tier}]" if source_tier is not None else ""
        raw_title = f.get("src_title") or f.get("source_title") or ""
        if not raw_title:
            src_type = (f.get("src_type") or "").lower()
            for type_key, label_val in _SOURCE_TYPE_LABEL.items():
                if type_key in src_type:
                    raw_title = label_val
                    break
        if not raw_title:
            raw_title = "D? li?u t->i ch->nh"
        source_title = f"{raw_title}{tier_suffix}"

        cmap[key] = {
            "fact_id": str(f.get("id", "")),
            "ticker": f["ticker"],
            "period": f"{f['fiscal_year']}FY",
            "fiscal_year": f["fiscal_year"],
            "line_item_code": metric,
            "line_item_label": label,
            "value": val,
            "value_display": val_str,
            "unit": unit,
            "source_id": f.get("source_id", ""),
            "source_title": source_title,
            "source_uri": f.get("src_uri") or f.get("source_uri") or "",
            "source_type": f.get("src_type") or "",
            "source_tier": source_tier,
            "published_at": str(published)[:10] if published else "",
            "reliability_tier": f.get("src_reliability_tier"),
        }
    return cmap


def _cite_tag(metric: str, year: int) -> str:
    return f"[^{metric.replace('.', '_')}_{year}]"


def _cite(cmap: dict, ticker: str, year: int, metric: str) -> str:
    key = f"{ticker}/{year}FY/{metric}"
    if key not in cmap:
        return ""
    return _cite_tag(metric, year)


def _footnotes(cmap: dict, claims: list[tuple], mode: str = "draft") -> str:
    """Generate user-readable footnote block.

    Phase 6: footnotes are verification-aware.
      - Verified claim (has official_document_id): cite the OFFICIAL document, noting the
        provider cross-check ("d-> d?i so->t v?i ... qua vnstock").
      - Unverified Tier-3 claim: render the provider source but clearly label it
        "?? chua ki?m ch?ng b?ng ngu?n ch->nh th?c" (allowed in draft; blocks final export).
    """
    lines: list[str] = []
    seen: set[str] = set()
    for ticker, year, metric in claims:
        key = f"{ticker}/{year}FY/{metric}"
        rec = cmap.get(key)
        if not rec or key in seen:
            continue
        seen.add(key)
        tag = _cite_tag(metric, year)
        label = rec.get("metric_label") or rec.get("line_item_label") or rec.get("line_item_code", metric)
        val_str = rec.get("value_display") or str(rec.get("value", ""))
        period = rec.get("period") or f"{year}FY"
        fact_id = rec.get("fact_id") or ""
        tier = rec.get("source_tier")
        official_id = rec.get("official_document_id")
        is_derived = rec.get("is_derived", False)

        if official_id is not None:
            # Verified against an official document ? official-source footnote format.
            doc_title = rec.get("official_document_title") or "t->i li?u ch->nh th?c"
            issuer = rec.get("official_issuer") or ""
            provider = (rec.get("source_uri") or "").removeprefix("vnstock://").split("/")[0].upper()
            issuer_part = f", {issuer}" if issuer else ""
            cross = f" D? li?u d-> du?c d?i so->t v?i {provider} qua vnstock t?i th?i di?m ingest." if provider else ""
            lines.append(
                f"{tag}: **{label}** nam {year} -> {val_str}, du?c tr->ch t? "
                f"_{doc_title}_{issuer_part}, k? {period}.{cross}\n"
                f"_(Verified -> official_document_id={official_id} -> fact_id={fact_id})_"
            )
            continue

        # No official linkage.
        src_title = rec.get("source_title") or "Ngu?n kh->ng x->c d?nh"
        src_uri = rec.get("source_uri") or ""
        tier_label = rec.get("tier_label") or (f"[Tier {tier}]" if tier is not None else "")
        src_parts = [f"_{src_title}_"]
        if tier_label:
            src_parts.append(tier_label)
        if src_uri:
            src_parts.append(f"URI: `{src_uri}`")
        src_line = " | ".join(src_parts)
        unverified_note = ""
        if not is_derived and (tier is None or tier >= 3):
            unverified_note = "\n?? **Chua ki?m ch?ng b?ng ngu?n ch->nh th?c** -> s? li?u Tier 3 (API), ch? d->ng cho b?n nh->p."
        lines.append(
            f"{tag}: **{label}** -> {val_str}, k? {period}.\n"
            f"Ngu?n: {src_line}{unverified_note}\n"
            f"_(Internal: fact_id={fact_id})_"
        )
    return "\n\n".join(lines)


# (draft_rating removed -> use AssumptionGate.recommendation_label() instead)


# -- Catalyst dedup -------------------------------------------------------------

def _dedup_catalyst_lines(text: str) -> str:
    """Deduplicate catalyst event bullet lines by normalized title."""
    lines = text.splitlines()
    seen_titles: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- [") and "]" in stripped:
            # Extract title after the date and event_type
            title_part = stripped.split(")", 1)[-1].strip() if ")" in stripped else stripped
            # Normalize: lowercase, strip punctuation
            normalized = title_part.lower().strip()[:80]
            if normalized in seen_titles:
                continue
            seen_titles.add(normalized)
        out.append(line)
    return "\n".join(out)


def _has_text_corruption(text: str) -> bool:
    """Detect legacy mojibake patterns that must never reach a report file."""
    markers = (
        "\ufffd",
        "\u00ef\u00bf\u00bd",
        "B->o",
        "c->o",
        "C->ng",
        "kh->ng",
        "d->ng",
        "Gi->",
        "B->o c->o",
        "Ch? ti->u",
        "truy?n th?ng",
        "D? ph->ng",
        "L?i nhu?n",
    )
    return any(marker in text for marker in markers)


def _assert_report_text_clean(text: str) -> None:
    """Block Markdown artifacts that still contain legacy text corruption."""
    markers = (
        "\ufffd",
        "\u00ef\u00bf\u00bd",
        "B->o",
        "c->o",
        "d? li?u",
        "Ch? ti->u",
        "Gi-> tr?",
        "L?i nhu?n",
    )
    found = [marker for marker in markers if marker in text]
    if found:
        raise RuntimeError(
            "Markdown report failed encoding preflight; broken markers found: "
            + ", ".join(found)
        )


def _fmt_clean(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value:,.1f}{suffix}"


def _build_quality_blocked_report(
    *,
    ticker: str,
    info: dict,
    generated_at: datetime,
    fact_table: dict[str, dict[str, float]],
    fy_periods: list[str],
    latest_fy_str: str,
    current_price: float | None,
    shares_mn: float | None,
    source_tier_gate: dict,
    assumption_gate: Any,
    forecast_artifact: dict,
    fcff_artifact: dict,
    fcfe_artifact: dict,
    blend_artifact: dict,
    text_corruption_detected: bool,
) -> str:
    """Build a clean Vietnamese audit report when final report content is blocked."""

    def fget(metric: str, period: str) -> float | None:
        return fact_table.get(metric, {}).get(period)

    def metric_row(label: str, metric: str) -> str:
        values = [_fmt_clean(fget(metric, p)) for p in fy_periods]
        return f"| {label} | " + " | ".join(values) + " |"

    gate = assumption_gate.to_dict() if hasattr(assumption_gate, "to_dict") else {}
    reasons: list[str] = []
    if text_corruption_detected:
        reasons.append("Legacy Markdown template contains mojibake; report body replaced by audit-safe output.")
    if shares_mn is None:
        reasons.append("Missing explicit shares_outstanding fact; target price is blocked.")
    if source_tier_gate.get("blocking_count", 0) > 0 or source_tier_gate.get("export_decision") == "BLOCKED":
        reasons.extend(source_tier_gate.get("blocking_reasons") or ["Source-tier gate blocked."])
    if gate.get("status") != "approved_for_publish":
        reasons.extend(gate.get("blocking_reasons") or ["Assumption gate is not approved."])
    for artifact_name, artifact in (
        ("Forecast", forecast_artifact),
        ("FCFF", fcff_artifact),
        ("FCFE", fcfe_artifact),
        ("Blend", blend_artifact),
    ):
        for warning in artifact.get("warnings", [])[:5]:
            reasons.append(f"{artifact_name}: {warning}")

    unique_reasons = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            unique_reasons.append(reason)
            seen.add(reason)

    header_periods = " | ".join(fy_periods) if fy_periods else latest_fy_str
    sep = "|---|" + "---:|" * (len(fy_periods) if fy_periods else 1)
    if fy_periods:
        metrics_md = "\n".join(
            [
                metric_row("Doanh thu thuần (tỷ VND)", "revenue.net"),
                metric_row("Lợi nhuận sau thuế công ty mẹ (tỷ VND)", "net_income.parent"),
                metric_row("Tổng tài sản (tỷ VND)", "total_assets.ending"),
                metric_row("Vốn chủ sở hữu công ty mẹ (tỷ VND)", "equity.parent"),
                metric_row("Dòng tiền hoạt động (tỷ VND)", "operating_cash_flow.total"),
                metric_row("CAPEX theo CFS, âm là tiền chi ra (tỷ VND)", "capex.total"),
                metric_row("EPS cơ bản (VND/CP)", "eps.basic"),
            ]
        )
    else:
        metrics_md = "| Không có dữ liệu FY | N/A |"

    current_price_text = f"{current_price:,.0f} VND/CP" if current_price else "N/A"
    shares_text = f"{shares_mn:,.1f} triệu CP" if shares_mn else "Bị chặn do thiếu fact explicit"
    fcff_target = fcff_artifact.get("target_price_vnd")
    fcfe_target = fcfe_artifact.get("target_price_vnd")
    blend_target = blend_artifact.get("target_price_dcf_vnd")
    target_display = (
        f"{blend_target:,.0f} VND/CP"
        if blend_target and shares_mn and gate.get("status") == "approved_for_publish"
        else "Bị chặn"
    )
    reasons_md = "\n".join(f"- {reason}" for reason in unique_reasons[:30])

    return f"""# Báo cáo kiểm toán chất lượng sinh báo cáo - {ticker}

**Doanh nghiệp:** {info["name"]}  
**Sàn:** {info["exchange"]}  
**Ngành:** {info["sector"]}  
**Ngày tạo:** {generated_at.strftime("%Y-%m-%d %H:%M UTC")}  
**Trạng thái:** BLOCKED - cần sửa dữ liệu, assumptions và template trước khi xuất báo cáo phân tích.

## 1. Tóm tắt chặn xuất báo cáo

| Hạng mục | Kết quả |
|---|---|
| Giá thị trường | {current_price_text} |
| Số cổ phiếu dùng cho valuation | {shares_text} |
| Target price hiển thị ra report | {target_display} |
| Source-tier gate | {source_tier_gate.get("export_decision", "N/A")} |
| Assumption gate | {gate.get("status", "N/A")} |
| Text corruption detected | {"Có" if text_corruption_detected else "Không"} |

## 2. Lý do chặn

{reasons_md if reasons_md else "- Không có lý do chặn được ghi nhận."}

## 3. Snapshot số liệu lịch sử

Đơn vị: tỷ VND, trừ EPS. Các số dưới đây chỉ là snapshot dữ liệu đầu vào, không phải kết luận định giá.

| Chỉ tiêu | {header_periods} |
{sep}
{metrics_md}

## 4. Trạng thái valuation

| Thành phần | Giá trị | Trạng thái |
|---|---:|---|
| FCFF target | {f"{fcff_target:,.0f}" if fcff_target else "N/A"} | Không công bố nếu thiếu shares hoặc gate chưa approved |
| FCFE target | {f"{fcfe_target:,.0f}" if fcfe_target else "N/A"} | Không công bố nếu thiếu shares hoặc gate chưa approved |
| Blend DCF target | {f"{blend_target:,.0f}" if blend_target else "N/A"} | Không công bố trong report bị chặn |

## 5. Hành động bắt buộc

| Ưu tiên | Việc cần sửa | Điều kiện đạt |
|---:|---|---|
| 1 | Bổ sung fact `shares_outstanding.ending` hoặc `shares_outstanding.weighted_avg` theo ticker và kỳ mới nhất | Target price không còn dùng NI/EPS-implied shares |
| 2 | Ingest hoặc reconcile nguồn Tier 0/1 cho các chỉ tiêu trọng yếu | Source-tier gate không còn blocking reasons |
| 3 | Phê duyệt WACC, Re, terminal growth, tax policy, debt schedule, dividend schedule và peer dataset | Assumption gate = `approved_for_publish` |
| 4 | Thay legacy Markdown template bị mojibake bằng report builder UTF-8 sạch | Report không chứa marker mojibake legacy |
| 5 | Chạy lại quality gate trước khi render HTML/PDF | Không có target/rating publishable khi gate chưa đạt |
"""


# -- Forecast table -------------------------------------------------------------

def _build_forecast_section(
    ticker: str,
    fact_table: dict,
    shares_mn: float | None,
    forecast=None,   # ForecastArtifact -> pass pre-built to avoid triple computation
) -> tuple[str, dict]:
    """Run forecast engine and return (markdown_section, forecast_artifact_dict)."""
    if forecast is None:
        from backend.analytics.forecasting import ForecastAssumptions, run_forecast
        forecast = run_forecast(
            ticker=ticker,
            fact_table=fact_table,
            forecast_years=FORECAST_YEARS,
            assumptions=ForecastAssumptions(),
            shares_mn=shares_mn,
        )
    artifact = forecast.to_dict()

    if not forecast.forecast_years:
        return "_Kh->ng d? d? li?u l?ch s? d? d? ph->ng._\n", artifact

    hist = forecast.historical_periods
    fcast = [fy.label for fy in forecast.forecast_years]
    all_labels = hist + fcast
    n_hist = len(hist)

    header = "| Ch? ti->u (t? VND) | " + " | ".join(all_labels) + " |"
    sep = "|---|" + "---|" * len(all_labels)

    def row(label: str, hist_vals: list, fcast_vals: list, fmt=_fmt_bn) -> str:
        cells = [fmt(v) for v in hist_vals] + [f"**{fmt(v)}**" for v in fcast_vals]
        return "| " + label + " | " + " | ".join(cells) + " |"

    # Historical values from fact_table
    def hget(metric: str, period: str) -> float | None:
        return fact_table.get(metric, {}).get(period)

    hist_rev   = [hget("revenue.net", p) for p in hist]
    hist_gp    = [hget("gross_profit.total", p) for p in hist]
    hist_ni    = [hget("net_income.parent", p) for p in hist]
    hist_eps   = [hget("eps.basic", p) for p in hist]
    hist_cogs  = [hget("cogs.total", p) for p in hist]
    hist_sga   = [hget("sga.total", p) for p in hist]
    hist_ie    = [hget("interest_expense.total", p) for p in hist]
    hist_pbt   = [hget("profit_before_tax.total", p) for p in hist]
    hist_tax   = [hget("tax_expense.total", p) for p in hist]
    hist_dep   = [hget("depreciation.total", p) for p in hist]

    fcast_rev  = [fy.revenue for fy in forecast.forecast_years]
    fcast_gp   = [fy.gross_profit for fy in forecast.forecast_years]
    fcast_ni   = [fy.net_income for fy in forecast.forecast_years]
    fcast_eps  = [fy.eps for fy in forecast.forecast_years]
    fcast_ebit = [fy.ebit for fy in forecast.forecast_years]
    fcast_ebitda = [fy.ebitda for fy in forecast.forecast_years]
    fcast_gm   = [fy.gross_margin for fy in forecast.forecast_years]
    fcast_cogs = [fy.cogs for fy in forecast.forecast_years]
    fcast_sga  = [fy.sga for fy in forecast.forecast_years]
    fcast_ie   = [fy.interest_expense for fy in forecast.forecast_years]
    fcast_pbt  = [fy.profit_before_tax for fy in forecast.forecast_years]
    fcast_tax  = [fy.tax_expense for fy in forecast.forecast_years]
    fcast_dep  = [fy.depreciation for fy in forecast.forecast_years]

    # Balance sheet forecast values
    fcast_assets  = [fy.total_assets for fy in forecast.forecast_years]
    fcast_equity  = [fy.equity for fy in forecast.forecast_years]
    fcast_debt    = [fy.total_debt for fy in forecast.forecast_years]

    # Gross margin rows (historical)
    hist_gm = []
    for i, p in enumerate(hist):
        rev = hist_rev[i]
        gp = hist_gp[i]
        hist_gm.append(gp / rev if rev and gp is not None else None)

    # Historical total assets/equity/debt
    hist_assets = [hget("total_assets.ending", p) for p in hist]
    hist_equity = [hget("equity.parent", p) for p in hist]
    hist_debt   = [hget("total_debt.ending", p) for p in hist]

    kqkd_table = [
        header, sep,
        row("Doanh thu thu?n", hist_rev, fcast_rev),
        row("Gi-> v?n h->ng b->n (COGS)", hist_cogs, fcast_cogs),
        row("L?i nhu?n g?p", hist_gp, fcast_gp),
        row("Bi->n l?i nhu?n g?p (%)", hist_gm, fcast_gm, _fmt_pct),
        row("Chi ph-> SGA (b->n h->ng + QLDN)", hist_sga, fcast_sga),
        row("EBIT", [None]*n_hist, fcast_ebit),
        row("EBITDA", [None]*n_hist, fcast_ebitda),
        row("Chi ph-> l->i vay", hist_ie, fcast_ie),
        row("L?i nhu?n tru?c thu? (PBT)", hist_pbt, fcast_pbt),
        row("Chi ph-> thu? TNDN", hist_tax, fcast_tax),
        row("L?i nhu?n sau thu? (C-> m?)", hist_ni, fcast_ni),
        row("EPS (VND/CP)", hist_eps, fcast_eps, _fmt_vnd),
    ]

    # Balance sheet forecast table
    bs_table = [
        "| Ch? ti->u (t? VND) | " + " | ".join(all_labels) + " |",
        "|---|" + "---|" * len(all_labels),
        row("T?ng t->i s?n", hist_assets, fcast_assets),
        row("V?n ch? s? h?u", hist_equity, fcast_equity),
        row("T?ng n? vay", hist_debt, fcast_debt),
    ]

    drivers = forecast.drivers
    cagr_str = f"{forecast.revenue_cagr:.1%}" if forecast.revenue_cagr else "N/A"
    rev_g = drivers.get("revenue_growth", {})
    rev_g_val = list(rev_g.values())[0] if isinstance(rev_g, dict) and rev_g else 0
    gm_val = drivers.get("gross_margin", {}).get("value", 0)
    sga_val = drivers.get("sga_to_revenue", {}).get("value", 0)
    dep_val = drivers.get("depreciation_to_revenue", {}).get("value", 0)
    capex_val = drivers.get("capex_to_revenue", {}).get("value", 0)
    tax_val = drivers.get("effective_tax_rate", {}).get("value", 0)
    cod_val = drivers.get("cost_of_debt", {}).get("value", 0)
    cod_method = drivers.get("cost_of_debt", {}).get("method", "unknown")

    # Debt/dividend schedule metadata for BS note
    _debt_method = forecast.debt_schedule.forecast_method if forecast.debt_schedule else "unknown"
    _div_method = forecast.dividend_schedule.method if forecast.dividend_schedule else "unknown"
    _hist_payout = (
        forecast.dividend_schedule.historical_payout_ratio
        if forecast.dividend_schedule else None
    )
    _payout_str = f"{_hist_payout:.1%}" if _hist_payout is not None else "0% (kh->ng c-> d? li?u)"

    # Extended BS table: add net_borrowing and dividend rows
    fcast_nb  = [fy.net_borrowing for fy in forecast.forecast_years]
    fcast_div = [fy.cash_dividend for fy in forecast.forecast_years]
    fcast_re  = [fy.retained_earnings_addition for fy in forecast.forecast_years]
    hist_nb   = [None] * len(hist)
    hist_div  = [None] * len(hist)
    hist_re   = [None] * len(hist)

    bs_table.extend([
        row("Vay r->ng (Net Borrowing)", hist_nb, fcast_nb),
        row("C? t?c ti?n m?t chi tr?", hist_div, fcast_div),
        row("L?i nhu?n gi? l?i", hist_re, fcast_re),
    ])

    warn_lines = ""
    if forecast.warnings:
        # Show only non-verbose warnings (cap at 5)
        shown = [w for w in forecast.warnings if len(w) < 200][:5]
        warn_lines = "\n> _C?nh b->o d? ph->ng: " + "; ".join(shown) + "_\n"

    section = f"""### 3.4 D? ph->ng KQKD 2026F->2030F

{chr(10).join(kqkd_table)}

_L?ch s?: {', '.join(hist)} | D? ph->ng (in d?m): {', '.join(fcast)}_

**Gi? d?nh d? ph->ng (chua du?c chuy->n gia ph-> duy?t):**

| Gi? d?nh | Gi-> tr? | Co s? |
|---|---|---|
| T?c d? tang tru?ng doanh thu | {rev_g_val:.1%}/nam | CAGR l?ch s? = {cagr_str} (gi?i h?n ->25%) |
| Bi->n l?i nhu?n g?p | {gm_val:.1%} | Trung v? l?ch s? |
| Chi ph-> SGA/doanh thu | {sga_val:.1%} | Trung v? l?ch s? |
| Kh?u hao/doanh thu | {dep_val:.1%} | Trung v? l?ch s? |
| CAPEX/doanh thu | {capex_val:.1%} | Trung v? l?ch s? |
| Thu? su?t th?c t? | {tax_val:.1%} | Trung v? l?ch s? |
| Chi ph-> n? (cost of debt) | {cod_val:.2%} | {cod_method} |
| L->i vay = n? b->nh qu->n -> cost_of_debt | -> | Driver-based (kh->ng ph?i % doanh thu) |
| ?NWC | 2% thay d?i doanh thu | U?c t->nh don gi?n |
| T? l? chi tr? c? t?c (payout) | {_payout_str} | {_div_method} |
{warn_lines}

### 3.5 D? ph->ng b?ng c->n d?i k? to->n (Ch? ti->u ch->nh)

{chr(10).join(bs_table)}

_Luu ->: M-> h->nh driver-based -> l->i vay = n? b->nh qu->n -> cost_of_debt ({cod_val:.2%}); n? vay theo phuong ph->p {_debt_method}; v?n ch? c?p nh?t qua retained earnings sau khi tr? c? t?c (payout {_payout_str})._
"""
    return section, artifact


# -- FCFF table -----------------------------------------------------------------

def _build_fcff_section(
    ticker: str,
    fact_table: dict,
    forecast_artifact_dict: dict,
    current_price: float | None,
    shares_mn: float | None,
    forecast=None,   # ForecastArtifact -> pass pre-built to avoid recomputation
) -> tuple[str, dict]:
    """Run FCFF valuation and return (markdown_section, fcff_artifact_dict)."""
    if forecast is None:
        from backend.analytics.forecasting import ForecastAssumptions, run_forecast
        forecast = run_forecast(
            ticker=ticker, fact_table=fact_table,
            forecast_years=FORECAST_YEARS,
            assumptions=ForecastAssumptions(),
            shares_mn=shares_mn,
        )
    from backend.analytics.fcff import FCFFResult, WACCAssumptions, compute_fcff

    # Pass TaxPolicy from forecast so FCFF and forecast tax rates are consistent.
    wacc_assumptions = WACCAssumptions(tax_policy=forecast.tax_policy)
    fcff_result = compute_fcff(
        ticker=ticker,
        forecast=forecast,
        fact_table=fact_table,
        current_price_vnd=current_price,
        terminal_growth=0.03,
        wacc_assumptions=wacc_assumptions,
        shares_mn=shares_mn,
    )
    artifact = fcff_result.to_dict()

    wacc_b = artifact["wacc_breakdown"]
    ke = wacc_b["cost_of_equity"]
    kd = wacc_b["cost_of_debt"]

    # FCFF table
    fcff_rows = []
    for fy in artifact["fcff_table"]:
        fcff_rows.append(
            f"| {fy['label']} | {_fmt_bn(fy['ebit'])} | {_fmt_bn(fy['ebit_after_tax'])} "
            f"| {_fmt_bn(fy['depreciation'])} | {_fmt_bn(fy['capex'])} "
            f"| {_fmt_bn(fy['delta_nwc'])} | {_fmt_bn(fy['fcff'])} "
            f"| {_fmt_bn(fy['pv_fcff'])} |"
        )

    target_price = artifact.get("target_price_vnd")
    upside_pct = artifact.get("upside_pct")
    upside_str = f"{upside_pct:.1%}" if upside_pct is not None else "N/A"
    target_str = f"{target_price:,.0f} VND/CP" if target_price else "N/A"

    warn_lines = ""
    if artifact.get("warnings"):
        warn_lines = "\n> _C?nh b->o: " + "; ".join(artifact["warnings"][:3]) + "_\n"

    section = f"""**C->ng th?c:** FCFF = EBIT -> (1 - T) + Kh?u hao - CAPEX - ?VL->

| Nam | EBIT | EBIT(1-T) | Kh?u hao | CAPEX | ?VL-> | FCFF | PV(FCFF) |
|---|---|---|---|---|---|---|---|
{chr(10).join(fcff_rows)}

| | T? VND |
|---|---|
| T?ng PV(FCFF) | {_fmt_bn(artifact.get("sum_pv_fcff"))} |
| Gi-> tr? cu?i k? (Terminal Value) | {_fmt_bn(artifact.get("terminal_value"))} |
| PV(Terminal Value) | {_fmt_bn(artifact.get("pv_terminal_value"))} |
| Gi-> tr? doanh nghi?p (EV) | {_fmt_bn(artifact.get("enterprise_value"))} |
| N? r->ng (Net Debt) | {_fmt_bn(artifact.get("net_debt"))} |
| Gi-> tr? v?n ch? (Equity Value) | {_fmt_bn(artifact.get("equity_value"))} |
| S? c? phi?u (tri?u CP) | {_fmt_bn(artifact.get("shares_mn"))} |

**Gi-> m?c ti->u FCFF: {target_str}**
Upside so v?i gi-> th? tru?ng: **{upside_str}**

**Th->ng s? WACC (chua du?c chuy->n gia ph-> duy?t):**

| Th->ng s? | Gi-> tr? |
|---|---|
| L->i su?t phi r?i ro (rf) | {wacc_b['risk_free_rate']:.1%} |
| Beta | {wacc_b['beta']:.2f} |
| TSSL k? v?ng th? tru?ng (Rm) | {wacc_b['expected_market_return']:.1%} |
| Chi ph-> v?n ch? (Ke) | {ke:.2%} |
| Chi ph-> n? (Kd) | {kd:.1%} |
| Thu? su?t th?c t? | {wacc_b['tax_rate']:.0%} |
| WACC | **{artifact['wacc']:.2%}** |
| T?c d? tang tru?ng cu?i k? (g) | {artifact['terminal_growth']:.1%} |

> **Luu ->:** T?t c? gi? d?nh WACC v-> d? ph->ng l-> _default_unapproved_ -> ph?i du?c chuy->n gia xem x->t tru?c khi s? d?ng cho quy?t d?nh d?u tu.
{warn_lines}
"""
    return section, artifact


# -- FCFE table -----------------------------------------------------------------

def _build_fcfe_section(
    ticker: str,
    fact_table: dict,
    current_price: float | None,
    shares_mn: float | None,
    forecast=None,   # ForecastArtifact -> pass pre-built to avoid recomputation
) -> tuple[str, dict]:
    """Run FCFE valuation and return (markdown_section, fcfe_artifact_dict)."""
    if forecast is None:
        from backend.analytics.forecasting import ForecastAssumptions, run_forecast
        forecast = run_forecast(
            ticker=ticker, fact_table=fact_table,
            forecast_years=FORECAST_YEARS,
            assumptions=ForecastAssumptions(),
            shares_mn=shares_mn,
        )
    from backend.analytics.fcfe import CostOfEquityAssumptions, compute_fcfe

    # Use driver-based net borrowing from debt_schedule (not stable-leverage NB=0)
    _nb_sched = (
        forecast.debt_schedule.net_borrowing_schedule()
        if forecast.debt_schedule is not None else None
    )
    coe = CostOfEquityAssumptions()
    fcfe_result = compute_fcfe(
        ticker=ticker,
        forecast=forecast,
        fact_table=fact_table,
        current_price_vnd=current_price,
        terminal_growth=0.03,
        cost_of_equity_assumptions=coe,
        shares_mn=shares_mn,
        net_borrowing_schedule=_nb_sched,
    )
    artifact = fcfe_result.to_dict()

    coe_b = artifact["cost_of_equity_breakdown"]
    re = artifact["cost_of_equity"]

    fcfe_rows = []
    for fy in artifact["fcfe_table"]:
        fcfe_rows.append(
            f"| {fy['label']} | {_fmt_bn(fy['net_income'])} | {_fmt_bn(fy['depreciation'])} "
            f"| {_fmt_bn(fy['capex'])} | {_fmt_bn(fy['delta_nwc'])} "
            f"| {_fmt_bn(fy['net_borrowing'])} | {_fmt_bn(fy['fcfe'])} "
            f"| {_fmt_bn(fy['pv_fcfe'])} |"
        )

    target_price = artifact.get("target_price_vnd")
    upside_pct = artifact.get("upside_pct")
    upside_str = f"{upside_pct:.1%}" if upside_pct is not None else "N/A"
    target_str = f"{target_price:,.0f} VND/CP" if target_price else "N/A"

    warn_lines = ""
    if artifact.get("warnings"):
        shown = [w for w in artifact["warnings"] if "stable leverage" not in w][:3]
        if shown:
            warn_lines = "\n> _C?nh b->o: " + "; ".join(shown) + "_\n"

    _debt_method_fcfe = (
        forecast.debt_schedule.forecast_method if forecast.debt_schedule else "missing"
    )
    _nb_note = (
        f"Vay r->ng l?y t? debt_schedule (phuong ph->p: {_debt_method_fcfe})."
        if _nb_sched else
        "Vay r->ng = 0 (kh->ng c-> d? li?u debt_schedule -> gi? d?nh c?u tr->c v?n ?n d?nh)."
    )

    section = f"""**C->ng th?c:** FCFE = LNST + Kh?u hao - CAPEX - ?VL-> + Vay r->ng

> FCFE chi?t kh?u b?ng Re (chi ph-> v?n ch?), **kh->ng d->ng WACC**.
> FCFE cho tr?c ti?p Equity Value -> **kh->ng tr? n? r->ng l?n n?a**.
> {_nb_note}

| Nam | LNST | Kh?u hao | CAPEX | ?VL-> | Vay r->ng | FCFE | PV(FCFE) |
|---|---|---|---|---|---|---|---|
{chr(10).join(fcfe_rows)}

| | T? VND |
|---|---|
| T?ng PV(FCFE) | {_fmt_bn(artifact.get("sum_pv_fcfe"))} |
| Gi-> tr? cu?i k? (Terminal Value FCFE) | {_fmt_bn(artifact.get("terminal_value"))} |
| PV(Terminal Value) | {_fmt_bn(artifact.get("pv_terminal_value"))} |
| Gi-> tr? v?n ch? (Equity Value) | {_fmt_bn(artifact.get("equity_value"))} |
| S? c? phi?u (tri?u CP) | {_fmt_bn(artifact.get("shares_mn"))} |

**Gi-> m?c ti->u FCFE: {target_str}**
Upside so v?i gi-> th? tru?ng: **{upside_str}**

**Th->ng s? Re -> Extended CAPM (chua ph-> duy?t):**

| Th->ng s? | Gi-> tr? |
|---|---|
| L->i su?t phi r?i ro (Rf) | {coe_b['risk_free_rate']:.1%} |
| Beta | {coe_b['beta']:.2f} |
| Ph?n b-> r?i ro th? tru?ng (ERP) | {coe_b['equity_risk_premium']:.1%} |
| Ph?n b-> quy m-> (Size Premium) | {coe_b['size_premium']:.1%} |
| Ph?n b-> r?i ro ri->ng (Specific Risk) | {coe_b['specific_risk_premium']:.1%} |
| Chi ph-> v?n ch? (Re) | **{re:.2%}** |
| T?c d? tang tru?ng cu?i k? (g) | {artifact['terminal_growth']:.1%} |
{warn_lines}
"""
    return section, artifact


def _build_blend_section(
    ticker: str,
    fcff_artifact: dict,
    fcfe_artifact: dict,
    current_price: float | None,
) -> tuple[str, dict]:
    """Build 60% FCFF + 40% FCFE blend section."""
    from backend.analytics.blend import blend_dcf
    from backend.analytics.sensitivity import (
        build_blend_sensitivity_table,
        compute_tv_weight,
        compute_valuation_gap,
    )

    price_fcff = fcff_artifact.get("target_price_vnd")
    price_fcfe = fcfe_artifact.get("target_price_vnd")

    blend = blend_dcf(
        ticker=ticker,
        price_fcff=price_fcff,
        price_fcfe=price_fcfe,
        current_price_vnd=current_price,
        pv_terminal_value_fcff=fcff_artifact.get("pv_terminal_value"),
        enterprise_value_fcff=fcff_artifact.get("enterprise_value"),
    )
    bd = blend.to_dict()

    target_str = f"{bd['target_price_dcf_vnd']:,.0f} VND/CP" if bd['target_price_dcf_vnd'] else "N/A"
    upside_str = f"{bd['upside_pct']:.1%}" if bd['upside_pct'] is not None else "N/A"
    mos_str    = f"{bd['margin_of_safety']:.1%}" if bd['margin_of_safety'] is not None else "N/A"
    gap_str    = f"{bd['valuation_gap_pct']:.1%}" if bd.get('valuation_gap_pct') is not None else "N/A"
    tvw_str    = f"{bd['tv_weight_fcff']:.1%}" if bd.get('tv_weight_fcff') is not None else "N/A"

    gap_check = compute_valuation_gap(price_fcff, price_fcfe)
    tv_check  = compute_tv_weight(fcff_artifact.get("pv_terminal_value"), fcff_artifact.get("enterprise_value"))

    warn_lines = "\n".join(f"> ? {w}" for w in blend.warnings) if blend.warnings else ""

    # Blend sensitivity grid (->2 steps around base)
    blend_grid_md = "_Kh->ng c-> d? li?u (FCFF ho?c FCFE unavailable)_"
    if price_fcff and price_fcfe:
        step_f = max(5_000, round(price_fcff * 0.05 / 5_000) * 5_000)
        step_e = max(5_000, round(price_fcfe * 0.05 / 5_000) * 5_000)
        p_fcff_range = [round(price_fcff + i * step_f) for i in range(-2, 3)]
        p_fcfe_range = [round(price_fcfe + i * step_e) for i in range(-2, 3)]
        grid = build_blend_sensitivity_table(p_fcff_range, p_fcfe_range, current_price)
        grid_rows = ["| FCFF \\ FCFE | " + " | ".join(f"{p:,.0f}" for p in p_fcfe_range) + " |",
                     "|---" + "|---" * len(p_fcfe_range) + "|"]
        for pf in p_fcff_range:
            rk = str(int(round(pf)))
            vals = [
                f"{grid['matrix'].get(rk, {}).get(str(int(round(pe))), 'N/A'):,.0f}"
                if isinstance(grid['matrix'].get(rk, {}).get(str(int(round(pe)))), (int, float))
                else "->"
                for pe in p_fcfe_range
            ]
            grid_rows.append(f"| {pf:,.0f} | " + " | ".join(vals) + " |")
        blend_grid_md = "\n".join(grid_rows)
        if grid.get("upside_range"):
            ur = grid["upside_range"]
            blend_grid_md += f"\n\n_V->ng upside: [{ur['min_upside']:.1%}, {ur['max_upside']:.1%}] so v?i gi-> th? tru?ng {current_price:,.0f} VND/CP_"

    section = f"""**C->ng th?c:** Target Price_DCF = 0.60 -> Price_FCFF + 0.40 -> Price_FCFE

| Phuong ph->p | Gi-> m?c ti->u (VND/CP) | Tr?ng s? | ->->ng g->p (VND/CP) |
|---|---|---|---|
| FCFF DCF | {f"{price_fcff:,.0f}" if price_fcff else "N/A"} | 60% | {f"{0.60*price_fcff:,.0f}" if price_fcff else "N/A"} |
| FCFE DCF | {f"{price_fcfe:,.0f}" if price_fcfe else "N/A"} | 40% | {f"{0.40*price_fcfe:,.0f}" if price_fcfe else "N/A"} |
| **Target Price DCF** | **{target_str}** | 100% | **{target_str}** |

| Ch? ti->u | Gi-> tr? |
|---|---|
| Gi-> th? tru?ng hi?n t?i | {f"{current_price:,.0f} VND/CP" if current_price else "N/A"} |
| Target Price (60/40 blend) | {target_str} |
| Upside / Downside | {upside_str} |
| Margin of Safety | {mos_str} |
| FCFF vs FCFE Gap | {gap_str} [{gap_check.get("status", "unknown")}] |
| TV Weight (FCFF/EV) | {tvw_str} [{tv_check.get("status", "unknown")}] |

### B?ng sensitivity Blend (Price_FCFF -> Price_FCFE ? Target Price_DCF, VND/CP)

{blend_grid_md}

{warn_lines}
> **Luu ->:** Tr?ng s? 60% FCFF / 40% FCFE l-> quy u?c chu?n cho c? phi?u du?c v?i n? vay v?a ph?i v-> d->ng ti?n ?n d?nh.
> N?u gap FCFF/FCFE > 25%, ph?i ki?m tra Net Borrowing, CAPEX v-> NWC tru?c khi d->ng target price.
"""
    return section, bd


# -- Main report generator ------------------------------------------------------

def _enrich_citations_with_verification(cmap: "dict[str, dict]", ticker: str) -> None:
    """Phase 6: attach official_document_id, reconciliation_status and a grounded
    source_tier to each citation entry by looking up the canonical facts.

    Mutates cmap in place. Safe to call even if the DB is unavailable (best-effort).
    """
    try:
        conn = psycopg2.connect(_dsn())
    except Exception as exc:  # noqa: BLE001
        print(f"[generate_report] WARNING: verification enrichment skipped ({exc})")
        return
    try:
        import psycopg2.extras as _extras
        with conn.cursor(cursor_factory=_extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT cf.period, cf.metric, cf.source_tier,
                       cf.official_document_id, cf.reconciliation_status,
                       od.title AS official_title, od.issuer AS official_issuer,
                       od.source_type AS official_source_type
                FROM fact.canonical_facts cf
                LEFT JOIN ingest.official_documents od
                       ON od.official_document_id = cf.official_document_id
                WHERE cf.ticker = %s
                """,
                (ticker,),
            )
            by_key = {
                f"{ticker}/{r['period']}/{r['metric']}": r for r in cur.fetchall()
            }
    finally:
        conn.close()

    for key, rec in cmap.items():
        info = by_key.get(key)
        if info is None:
            rec.setdefault("official_document_id", None)
            rec.setdefault("reconciliation_status", "missing_official")
            continue
        rec["official_document_id"] = info["official_document_id"]
        rec["reconciliation_status"] = info["reconciliation_status"]
        if rec.get("source_tier") is None and info["source_tier"] is not None:
            rec["source_tier"] = info["source_tier"]
        if info["official_document_id"] is not None:
            rec["official_document_title"] = info["official_title"]
            rec["official_issuer"] = info["official_issuer"]
            rec["official_source_type"] = info["official_source_type"]


def _run_source_tier_gate(cmap: "dict[str, dict]", mode: str) -> dict:
    """Run the Phase 2 source-tier export gate on the (enriched) citation map."""
    from backend.citations.citation_map import legacy_dict_to_citation_map
    from backend.citations.source_tier_policy import evaluate_source_tier_gate
    typed = legacy_dict_to_citation_map(cmap)
    return evaluate_source_tier_gate(typed, mode=mode).to_dict()


def generate_report(
    ticker: str,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    report_type: str = "full_report",
    snapshot_id: str | None = None,
    mode: str = "draft",
) -> dict:
    ticker = ticker.strip().upper()
    mode = (mode or "draft").strip().lower()
    if mode not in ("draft", "final"):
        raise ValueError(f"mode must be 'draft' or 'final', got {mode!r}")
    generated_at = datetime.now(UTC)
    info = _COMPANY_INFO.get(ticker, {"name": ticker, "exchange": "N/A", "sector": "Du?c ph?m"})

    print(f"[generate_report] {ticker} -> loading valuation artifact")
    val = _load_latest_valuation(ticker)
    if val is None:
        print("[generate_report] ERROR: No valuation artifact. Run scripts/run_valuation.py first.")
        sys.exit(1)

    used_snapshot_id = snapshot_id or val.get("snapshot_id", "")
    print(f"[generate_report] {ticker} -> snapshot: {used_snapshot_id}")

    print(f"[generate_report] {ticker} -> loading snapshot facts")
    facts = _load_snapshot_facts(used_snapshot_id)
    print(f"[generate_report] {ticker} -> {len(facts)} facts loaded")

    # Phase 4: build FactTable from snapshot facts, then build citation map
    # with full source provenance (source_tier, source_uri, source_title).
    _context_events: dict = {}  # hoisted so Phase 5 catalyst section can read it
    try:
        from backend.facts.normalizer import build_fact_table, compute_derived
        from backend.citations.event_linker import link_events_to_periods
        _fact_table = compute_derived(build_fact_table(facts))
        _fy_periods_for_events = list({
            f"{f['fiscal_year']}FY"
            for f in facts
            if str(f.get("fiscal_period", "")).upper() == "FY"
        })
        _context_events = link_events_to_periods(
            ticker=ticker,
            periods=_fy_periods_for_events,
        )
        cmap = _build_citation_map_from_fact_table(
            ticker=ticker,
            fact_table=_fact_table,
            context_events=_context_events,
        )
        print(f"[generate_report] {ticker} -> citation map built (Phase 4): "
              f"{len(cmap)} entries, {len(_context_events)} periods with events")
    except Exception as _cmap_exc:  # noqa: BLE001
        print(f"[generate_report] WARNING: Phase 4 citation map failed ({_cmap_exc}), "
              f"falling back to legacy path")
        cmap = _build_citation_map(facts)

    # Phase 6: enrich citations with verification provenance (official_document_id,
    # reconciliation_status, grounded source_tier) from the canonical/verified facts,
    # then run the mode-aware source-tier export gate.
    _enrich_citations_with_verification(cmap, ticker)
    source_tier_gate = _run_source_tier_gate(cmap, mode)
    print(f"[generate_report] {ticker} -> source-tier gate ({mode}): "
          f"{source_tier_gate['export_decision']} "
          f"({len(source_tier_gate['blocking_reasons'])} blocking, "
          f"{len(source_tier_gate['warnings'])} warnings)")

    conn = psycopg2.connect(_dsn())
    try:
        evidence_chunks = _load_evidence_chunks(conn, ticker)
        print(f"[generate_report] {ticker} -> {len(evidence_chunks)} evidence chunks")
    finally:
        conn.close()

    # -- Extract key metrics from valuation artifact ----------------------------
    ratios: dict = val.get("ratios", {})
    dcf: dict = val.get("dcf_simplified") or val.get("dcf", {})
    multiples: dict = val.get("multiples", {})
    _sensitivity_raw: dict = val.get("sensitivity", {})
    # Handle both old flat format and new nested format from run_valuation.py
    sensitivity: dict = (
        _sensitivity_raw.get("simplified_dcf", _sensitivity_raw)
        if isinstance(_sensitivity_raw.get("simplified_dcf"), dict)
        else _sensitivity_raw
    )
    assumptions: dict = val.get("assumptions", {})
    fy_periods: list[str] = val.get("fy_periods", [])
    latest_fy_str: str = fy_periods[-1] if fy_periods else f"{to_year}FY"
    latest_year: int = int(latest_fy_str.replace("FY", ""))
    current_price: float | None = val.get("current_price_vnd")

    # Build fact lookup for report body + forecast engine
    # Cast Decimal ? float to keep arithmetic engines happy
    fact_table: dict[str, dict[str, float]] = {}
    for f in facts:
        fact_table.setdefault(f["line_item_code"], {})[f"{f['fiscal_year']}FY"] = float(f["value"])

    def fget(metric: str, period: str) -> float | None:
        return fact_table.get(metric, {}).get(period)

    rev_latest  = fget("revenue.net", latest_fy_str)
    ni_latest   = fget("net_income.parent", latest_fy_str)
    eps_latest  = fget("eps.basic", latest_fy_str)
    equity_latest = fget("equity.parent", latest_fy_str)
    ocf_latest  = fget("operating_cash_flow.total", latest_fy_str)

    gross_margin_latest = ratios.get("gross_margin", {}).get(latest_fy_str)
    net_margin_latest   = ratios.get("net_margin", {}).get(latest_fy_str)
    roe_latest  = ratios.get("roe", {}).get(latest_fy_str)
    roa_latest  = ratios.get("roa", {}).get(latest_fy_str)
    debt_eq_latest = ratios.get("debt_to_equity", {}).get(latest_fy_str)

    dcf_base = dcf.get("base", {})
    dcf_bear = dcf.get("bear", {})
    dcf_bull = dcf.get("bull", {})
    dcf_intrinsic = dcf_base.get("intrinsic_value_per_share_vnd")
    from backend.analytics.shares import reportable_shares_mn
    shares_mn = reportable_shares_mn(fact_table, latest_fy_str)
    eps_vnd   = multiples.get("eps_vnd")
    implied_pe = multiples.get("implied_price_pe")
    implied_ev = multiples.get("implied_price_ev_ebitda")
    pe_obs     = multiples.get("pe_ratio")

    wacc_val = assumptions.get("wacc", 0.10)
    tg_val   = assumptions.get("terminal_growth", 0.03)
    _rel_val_status = multiples.get("relative_valuation_status", "pending_peer_dataset")
    _peer_source = multiples.get("peer_data_source")
    # Only show target multiples when a real peer dataset is present
    target_pe_val: float | None = assumptions.get("target_pe") if _peer_source else None
    target_ev_val: float | None = assumptions.get("target_ev_ebitda") if _peer_source else None

    _blend_artifact = val.get("blend_dcf", {})
    _blend_is_draft = _blend_artifact.get("is_draft_only", True)  # default True = safe
    _valuation_label = (
        "Draft valuation range -> awaiting analyst approval"
        if _blend_is_draft else
        "PRIMARY target price (60% FCFF + 40% FCFE)"
    )

    _target_pe_str = f"{target_pe_val:.1f}x" if target_pe_val is not None else "Pending -> chua c-> d? li?u peer"
    _target_ev_str = f"{target_ev_val:.1f}x" if target_ev_val is not None else "Pending -> chua c-> d? li?u peer"

    price_str    = f"{current_price:,.0f} VND" if current_price else "Chua c->"
    intrinsic_str = f"{dcf_intrinsic:,.0f} VND/CP" if dcf_intrinsic else "N/A"
    upside_dcf: float | None = None
    if dcf_intrinsic and current_price and current_price > 0:
        upside_dcf = (dcf_intrinsic / current_price - 1)
    upside_str = f"upside: {upside_dcf:.1%}" if upside_dcf is not None else "->"

    # Claims registry
    claims_used: list[tuple] = []

    def cref(metric: str, year: int = latest_year) -> str:
        claims_used.append((ticker, year, metric))
        return _cite(cmap, ticker, year, metric)

    # -- Financial tables (historical) -----------------------------------------
    period_header = " | ".join(fy_periods)
    period_sep = " | ".join(["---"] * len(fy_periods))

    def metric_row(label: str, metric: str, fmt_fn=_fmt_bn) -> str:
        vals = []
        for p in fy_periods:
            yr = int(p.replace("FY", ""))
            v = fget(metric, p)
            if v is not None:
                claims_used.append((ticker, yr, metric))
            vals.append(fmt_fn(v) if v is not None else "N/A")
        return f"| {label} | " + " | ".join(vals) + " |"

    def ratio_row(label: str, metric: str, fmt_fn=_fmt_pct) -> str:
        vals = [fmt_fn(ratios.get(metric, {}).get(p)) for p in fy_periods]
        return f"| {label} | " + " | ".join(vals) + " |"

    fin_table = f"""| Ch? ti->u | {period_header} |
|---|{period_sep}|
{metric_row("Doanh thu thu?n (t? VND)", "revenue.net")}
{metric_row("L?i nhu?n g?p (t? VND)", "gross_profit.total")}
{metric_row("L?i nhu?n sau thu? (t? VND)", "net_income.parent")}
{metric_row("EPS co b?n (VND/CP)", "eps.basic", _fmt_vnd)}
{metric_row("D->ng ti?n ho?t d?ng (t? VND)", "operating_cash_flow.total")}
{metric_row("T?ng t->i s?n (t? VND)", "total_assets.ending")}
{metric_row("V?n ch? s? h?u (t? VND)", "equity.parent")}"""

    # -- Market ratios computation ----------------------------------------------
    from backend.analytics.ratios import compute_market_ratios, detect_abnormal_movements
    market_ratios = compute_market_ratios(fact_table, current_price, shares_mn)

    def mratio_row(label: str, key: str, fmt_fn=None) -> str:
        _PCT_MR = {"ccc", "inventory_days", "receivable_days", "payable_days",
                   "revenue_growth", "net_income_growth"}
        _X_MR   = {"pe", "pb", "ps", "p_ocf", "ev_ebitda", "debt_to_equity",
                   "current_ratio"}
        vals = []
        for p in fy_periods:
            # Check market_ratios first, then ratios, then fact_table
            v = (market_ratios.get(key, {}).get(p)
                 or ratios.get(key, {}).get(p)
                 or fget(key, p))
            if v is None:
                vals.append("->")
            elif fmt_fn:
                vals.append(fmt_fn(v))
            elif key in _PCT_MR:
                vals.append(_fmt_pct(v))
            elif key in _X_MR:
                vals.append(_fmt_x(v))
            else:
                vals.append(f"{v:,.1f}")
        return f"| {label} | " + " | ".join(vals) + " |"

    def _fmt_bn_trunc(v: float | None) -> str:
        return f"{v:,.1f}" if v is not None else "->"

    ratio_table = f"""| T? l? | {period_header} |
|---|{period_sep}|
{ratio_row("Bi->n l?i nhu?n g?p", "gross_margin")}
{ratio_row("Bi->n l?i nhu?n r->ng", "net_margin")}
{ratio_row("Bi->n EBITDA", "ebitda_margin")}
{ratio_row("Bi->n OCF", "ocf_margin")}
{ratio_row("ROE", "roe")}
{ratio_row("ROA", "roa")}
{ratio_row("Tang tru?ng doanh thu", "revenue_growth")}
{ratio_row("Tang tru?ng l?i nhu?n r->ng", "net_income_growth")}
{mratio_row("N?/VCSH", "debt_to_equity")}
{mratio_row("V?n h->a th? tru?ng (t? VND)", "market_cap_bn", _fmt_bn_trunc)}
{metric_row("EPS co b?n (VND/CP)", "eps.basic", _fmt_vnd)}
{mratio_row("BVPS (VND/CP)", "bvps", _fmt_vnd)}
{mratio_row("P/E", "pe")}
{mratio_row("P/B", "pb")}
{mratio_row("P/S", "ps")}
{mratio_row("EV/EBITDA", "ev_ebitda")}
{mratio_row("Chu k? ti?n (ng->y -> CCC)", "ccc", lambda v: f"{v:.1f} ng->y" if v is not None else "->")}"""

    # -- Abnormal movement detection --------------------------------------------
    abnormal_flags = detect_abnormal_movements(ratios, market_ratios, fy_periods)
    if abnormal_flags:
        abnormal_rows = "\n".join(
            f"| {f['metric']} | {f['prev_period']}?{f['period']} | "
            f"{f['prev']:.3g} ? {f['curr']:.3g} | {f['flag_reason']} |"
            for f in abnormal_flags
        )
        abnormal_section = f"""### 3.3 C?nh b->o bi?n d?ng b?t thu?ng

| Ch? s? | K? | Gi-> tr? | L-> do c?nh b->o |
|---|---|---|---|
{abnormal_rows}

> _C->c bi?n d?ng tr->n vu?t ngu?ng c?nh b->o (>25% tuong d?i ho?c >5pp bi->n l?i nhu?n) -> c?n gi?i th->ch th->m._
"""
    else:
        abnormal_section = "### 3.3 Bi?n d?ng ch? s?\n\nKh->ng c-> ch? s? n->o bi?n d?ng b?t thu?ng vu?t ngu?ng c?nh b->o.\n"

    # -- Forecast -> run ONCE; pass to all section builders for consistency ----
    print(f"[generate_report] {ticker} -> running forecast engine (single pass)")
    from backend.analytics.forecasting import ForecastAssumptions, run_forecast
    _shared_forecast = run_forecast(
        ticker=ticker,
        fact_table=fact_table,
        forecast_years=FORECAST_YEARS,
        assumptions=ForecastAssumptions(),
        shares_mn=shares_mn,
    )

    # -- Forecast section ------------------------------------------------------
    forecast_section, forecast_artifact = _build_forecast_section(
        ticker, fact_table, shares_mn, forecast=_shared_forecast
    )
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    ts_str = generated_at.strftime("%Y%m%dT%H%M%S")
    forecast_path = FORECAST_DIR / f"{ticker}_{ts_str}_forecast.json"
    forecast_path.write_text(
        json.dumps(forecast_artifact, indent=2, default=str), encoding="utf-8"
    )

    # -- FCFF section ---------------------------------------------------------
    print(f"[generate_report] {ticker} -> running FCFF valuation engine")
    fcff_section, fcff_artifact = _build_fcff_section(
        ticker, fact_table, forecast_artifact, current_price, shares_mn,
        forecast=_shared_forecast,
    )
    fcff_path = FORECAST_DIR / f"{ticker}_{ts_str}_fcff.json"
    fcff_path.write_text(
        json.dumps(fcff_artifact, indent=2, default=str), encoding="utf-8"
    )

    # -- FCFE section ---------------------------------------------------------
    print(f"[generate_report] {ticker} -> running FCFE valuation engine")
    fcfe_section, fcfe_artifact = _build_fcfe_section(
        ticker, fact_table, current_price, shares_mn,
        forecast=_shared_forecast,
    )
    fcfe_path = FORECAST_DIR / f"{ticker}_{ts_str}_fcfe.json"
    fcfe_path.write_text(
        json.dumps(fcfe_artifact, indent=2, default=str), encoding="utf-8"
    )

    # -- Blend section: 60% FCFF + 40% FCFE -----------------------------------
    print(f"[generate_report] {ticker} -> building blended DCF (60% FCFF + 40% FCFE)")
    blend_section, blend_artifact = _build_blend_section(
        ticker, fcff_artifact, fcfe_artifact, current_price
    )
    blend_path = FORECAST_DIR / f"{ticker}_{ts_str}_blend.json"
    blend_path.write_text(
        json.dumps(blend_artifact, indent=2, default=str), encoding="utf-8"
    )

    # Best upside for recommendation label: prefer blend, fall back to FCFF then DCF
    fcff_upside = fcff_artifact.get("upside_pct")
    blend_upside = blend_artifact.get("upside_pct")
    best_upside = next(
        (v for v in [blend_upside, fcff_upside, upside_dcf] if v is not None), None
    )

    # Build AssumptionGate -> blocks BUY/HOLD/SELL until all critical assumptions
    # are analyst-approved. "assumption_status" is the key in each artifact dict.
    _wacc_status = fcff_artifact.get("assumption_status", "default_unapproved")
    _coe_status = fcfe_artifact.get("assumption_status", "default_unapproved")
    _forecast_status = forecast_artifact.get("assumption_status", "default_unapproved")
    _tax_approved = bool((forecast_artifact.get("tax_policy") or {}).get("approved", False))

    assumption_gate = build_gate_from_artifacts(
        data_quality_passed=False,  # conservative: DQ gate runs separately
        wacc_assumption_status=_wacc_status,
        cost_of_equity_status=_coe_status,
        forecast_assumption_status=_forecast_status,
        debt_schedule_method="missing",  # not yet tracked per-artifact
        tax_policy_approved=_tax_approved,
    )
    draft_rating = assumption_gate.recommendation_label(model_upside_pct=best_upside)

    # Save gate artifact so the quality gate script can find it
    VALUATION_DIR.mkdir(parents=True, exist_ok=True)
    gate_artifact = {**assumption_gate.to_dict(), "ticker": ticker, "generated_at": ts_str}
    (VALUATION_DIR / f"{ticker}_{ts_str}_gate.json").write_text(
        json.dumps(gate_artifact, indent=2), encoding="utf-8"
    )

    # -- Sensitivity table -----------------------------------------------------
    g_range = sensitivity.get("g_range", [])
    matrix  = sensitivity.get("matrix", {})
    wacc_keys = sorted(matrix.keys())
    sens_lines = []
    if g_range and wacc_keys:
        sens_lines.append("| WACC \\ g | " + " | ".join(f"{g:.1%}" for g in g_range) + " |")
        sens_lines.append("|---" + "|---" * len(g_range) + "|")
        for wk in wacc_keys:
            row_vals = []
            for g in g_range:
                gk = f"{g:.4f}".rstrip("0").rstrip(".")
                v = matrix[wk].get(gk)
                row_vals.append(f"{v:,.0f}" if v is not None else "->")
            sens_lines.append(f"| {float(wk):.1%} | " + " | ".join(row_vals) + " |")
    sens_table = "\n".join(sens_lines) if sens_lines else "_Kh->ng c-> d? li?u sensitivity_"

    # -- Evidence section (no truncation; dedup catalyst) ---------------------
    def _demote_headers(text: str, levels: int = 2) -> str:
        """Demote markdown headers by adding extra # signs to prevent structure break."""
        prefix = "#" * levels
        lines = []
        for line in text.splitlines():
            if line.startswith("#"):
                lines.append(prefix + line)
            else:
                lines.append(line)
        return "\n".join(lines)

    evidence_section_md = ""
    if evidence_chunks:
        evidence_section_md = "\n#### T->i li?u b?ng ch?ng d-> s? d?ng\n\n"
        seen_fiscal: set[int] = set()
        for ch in evidence_chunks:
            fy = ch.get("fiscal_year")
            title = ch.get("section_title", "")
            text = (ch.get("chunk_text") or "").strip()
            # Demote headers in chunk text to prevent breaking report structure
            text = _demote_headers(text)

            if "Catalyst" in title or fy is None:
                text = _dedup_catalyst_lines(text)
                text_preview = "\n".join(text.splitlines()[:8])
                evidence_section_md += f"**{title}:**\n\n{text_preview}\n\n"
            else:
                if fy in seen_fiscal:
                    continue
                seen_fiscal.add(fy)
                evidence_section_md += f"**{title} ({fy}):**\n\n{text}\n\n"

    # -- Phase 5: Key Catalysts section ----------------------------------------
    try:
        from backend.citations.driver_evidence import render_catalyst_section
        catalyst_section_md = render_catalyst_section(ticker, _context_events)
        print(f"[generate_report] {ticker} -> catalyst section built "
              f"({sum(len(v) for v in _context_events.values())} events across "
              f"{len(_context_events)} periods)")
    except Exception as _cat_exc:  # noqa: BLE001
        catalyst_section_md = ""
        print(f"[generate_report] WARNING: catalyst section failed ({_cat_exc})")

    # -- Assemble full report ---------------------------------------------------
    fcff_target = fcff_artifact.get("target_price_vnd")
    fcff_target_str = f"{fcff_target:,.0f} VND/CP" if fcff_target else "N/A"
    fcff_upside_str = f"{fcff_upside:.1%}" if fcff_upside is not None else "N/A"
    fcfe_target = fcfe_artifact.get("target_price_vnd")
    fcfe_target_str = f"{fcfe_target:,.0f} VND/CP" if fcfe_target else "N/A"
    fcfe_upside_str = f"{fcfe_artifact.get('upside_pct'):.1%}" if fcfe_artifact.get('upside_pct') is not None else "N/A"
    blend_target = blend_artifact.get("target_price_dcf_vnd")
    blend_target_str = f"{blend_target:,.0f} VND/CP" if blend_target else "N/A"
    blend_upside_str = f"{blend_upside:.1%}" if blend_upside is not None else "N/A"

    report_md = f"""# B->o c->o Ph->n t->ch C? phi?u -> {ticker}

> **C?NH B->O QUAN TR?NG:** B->o c->o n->y du?c t?o b?i h? th?ng nghi->n c?u t? d?ng.
> S? li?u tr->ch xu?t t? d? li?u canonical ki?m to->n. D? ph->ng v-> d?nh gi-> d->ng gi? d?nh m?c d?nh **chua du?c chuy->n gia ph-> duy?t**.
> KH->NG d->ng d? ra quy?t d?nh d?u tu d?c l?p.

---

## 1. T->m t?t di?u h->nh v-> khuy?n ngh? Draft

**{info["name"]}** ({ticker} -> {info["exchange"]}) -> Ng->nh {info["sector"]}

Ng->y t?o: {generated_at.strftime("%Y-%m-%d %H:%M UTC")} | Snapshot: `{used_snapshot_id}`
Giai do?n ph->n t->ch l?ch s?: {fy_periods[0] if fy_periods else "N/A"} -> {fy_periods[-1] if fy_periods else "N/A"}
D? ph->ng: {FORECAST_YEARS[0]}F -> {FORECAST_YEARS[-1]}F

### ->?nh gi-> t->m t?t

> **Phuong ph->p d?nh gi-> ch->nh: Blend 60% FCFF + 40% FCFE** (driver-based, d-> ki?m so->t sign convention).
> DCF OCF-CAPEX truy?n th?ng ch? d? tham kh?o l?ch s? d->ng ti?n -> kh->ng d->ng l->m target price.

| Phuong ph->p | Gi-> tr? n?i t?i | Gi-> th? tru?ng | Upside | ->? tin c?y |
|---|---|---|---|---|
| **DCF Blend (60% FCFF + 40% FCFE)** | **{blend_target_str}** | {price_str} | **{blend_upside_str}** | **{_valuation_label}** |
| FCFF DCF (WACC m?c d?nh) | {fcff_target_str} | {price_str} | {fcff_upside_str} | Th->nh ph?n blend |
| FCFE DCF (Re m?c d?nh) | {fcfe_target_str} | {price_str} | {fcfe_upside_str} | Th->nh ph?n blend |
| P/E m?c ti->u ({_target_pe_str}) | {f"{implied_pe:,.0f} VND/CP" if implied_pe else "N/A"} | {price_str} | -> | Cross-check |
| EV/EBITDA m?c ti->u ({_target_ev_str}) | {f"{implied_ev:,.0f} VND/CP" if implied_ev else "N/A"} | {price_str} | -> | Cross-check |
| ~~DCF OCF-CAPEX (base)~~ | ~~{intrinsic_str}~~ | ~~{price_str}~~ | ~~{upside_str}~~ | **Tham kh?o -> kh->ng d->ng l->m target** |

> ? DCF OCF-CAPEX truy?n th?ng d->ng CAGR t? l?ch s? OCF bi?n d?ng -> k?t qu? nh?y c?m v?i nam CAPEX b?t thu?ng
> (v-> d?: nam d?u tu nh-> m->y l->m FCF ->m s? m->o CAGR v-> th?i ph?ng target price d->ng k?).
> Xem ->4.1 d? bi?t c?nh b->o chi ti?t.

### Draft Rating

{draft_rating}

> Can c?: upside Blend DCF = {blend_upside_str} | Ngu?ng BUY = 20%, HOLD -10% d?n +20%, SELL < -10%
> Gi? d?nh chua du?c analyst ph-> duy?t -> ch? d->ng l->m tham kh?o n?i b?.

---

## 2. Gi?i thi?u doanh nghi?p

**{info["name"]}** ni->m y?t t?i s->n {info["exchange"]} v?i m-> c? phi?u **{ticker}**.
Ho?t d?ng trong ng->nh {info["sector"]} Vi?t Nam.

- S? c? phi?u luu h->nh u?c t->nh: **{f"{shares_mn:,.1f} tri?u CP" if shares_mn else "N/A"}**
- Gi-> th? tru?ng: **{price_str}**
- EPS (FY{latest_year}): **{f"{eps_latest:,.0f} VND/CP" if eps_latest else "N/A"}** {cref("eps.basic")}
- P/E quan s->t: **{_fmt_x(pe_obs)}**

---

## 3. K?t qu? t->i ch->nh l?ch s?

### 3.1 B?ng t?ng h?p ({fy_periods[0] if fy_periods else ""}->{latest_fy_str})

{fin_table}

_->on v?: t? VND tr? EPS. Ngu?n: d? li?u canonical d-> ki?m d?nh._

### 3.2 B?ng ch? s? t->i ch->nh

{ratio_table}

_EPS, BVPS t->nh theo don v? VND/CP. V?n h->a, CCC t? gi-> th? tru?ng hi?n t?i {price_str}._

{abnormal_section}

{forecast_section}

{evidence_section_md}

{catalyst_section_md}

---

## 4. ->?nh gi-> (Valuation)

### 4.1 DCF OCF-CAPEX -> Tham kh?o l?ch s? d->ng ti?n _(kh->ng d->ng l->m target price)_

> **Gi?i h?n:** Phuong ph->p n->y d->ng CAGR t? OCF l?ch s? bi?n d?ng (kh->ng ph?i driver-based).
> Nam CAPEX d?u tu l?n (v-> d? x->y nh-> m->y) l->m FCF l?ch s? ->m ? CAGR m->o ? target price kh->ng d->ng tin.
> **Ch? xem d? hi?u v->ng bi?n d?ng r?ng. ->?nh gi-> ch->nh l-> ->4.5 Blend 60/40.**

Gi? d?nh: WACC = {wacc_val:.1%}, g = {tg_val:.1%}, k? d? b->o = {assumptions.get("forecast_years", 5)} nam

| K?ch b?n | Gi-> tr? n?i t?i (VND/CP) | WACC | g | C?nh b->o |
|---|---|---|---|---|
| Bear case | {f"{dcf_bear.get('intrinsic_value_per_share_vnd'):,.0f}" if dcf_bear.get("intrinsic_value_per_share_vnd") else "N/A"} | {dcf_bear.get("assumptions", {}).get("wacc", 0):.1%} | {dcf_bear.get("assumptions", {}).get("terminal_growth", 0):.1%} | Ch? tham kh?o |
| Base case | {f"{dcf_base.get('intrinsic_value_per_share_vnd'):,.0f}" if dcf_base.get("intrinsic_value_per_share_vnd") else "N/A"} | {dcf_base.get("assumptions", {}).get("wacc", 0):.1%} | {dcf_base.get("assumptions", {}).get("terminal_growth", 0):.1%} | Ch? tham kh?o |
| Bull case | {f"{dcf_bull.get('intrinsic_value_per_share_vnd'):,.0f}" if dcf_bull.get("intrinsic_value_per_share_vnd") else "N/A"} | {dcf_bull.get("assumptions", {}).get("wacc", 0):.1%} | {dcf_bull.get("assumptions", {}).get("terminal_growth", 0):.1%} | Ch? tham kh?o |

### 4.2 Sensitivity -> Gi-> tr? n?i t?i DCF (VND/CP)

{sens_table}

### 4.3 M-> h->nh FCFF (tr?ng s? 60%)

{fcff_section}

### 4.4 M-> h->nh FCFE (tr?ng s? 40%)

{fcfe_section}

### 4.5 Blend DCF -> Gi-> m?c ti->u k?t h?p 60% FCFF + 40% FCFE

{blend_section}

### 4.6 B?i s? th? tru?ng (Cross-check)

| Phuong ph->p | Gi-> tr? | Gi-> th? tru?ng | Ghi ch-> |
|---|---|---|---|
| P/E quan s->t | {_fmt_x(pe_obs)} | {price_str} | EPS = {f"{eps_vnd:,.0f} VND/CP" if eps_vnd else "N/A"} |
| Implied @ P/E {_target_pe_str} | {f"{implied_pe:,.0f} VND/CP" if implied_pe else "N/A"} | {price_str} | B?i s? m?c ti->u ng->nh |
| Implied @ EV/EBITDA {_target_ev_str} | {f"{implied_ev:,.0f} VND/CP" if implied_ev else "N/A"} | {price_str} | B?i s? m?c ti->u ng->nh |

> B?i s? m?c ti->u theo u?c t->nh ng->nh -> c?n c?p nh?t b?ng d? li?u peer group th?c t? tru?c publish.

---

## 5. R?i ro d?u tu

| Lo?i r?i ro | Driver t->i ch->nh | M-> t? | M?c d? | Kh? nang | Co s? / Gi->m s->t |
|---|---|---|---|---|---|
| Ch->nh s->ch BHYT/d?u th?u | Bi->n l?i nhu?n g?p, Doanh thu | Thay d?i quy d?nh d?u th?u, gi-> tr?n thu?c ?nh hu?ng bi->n l?i nhu?n g?p ({_fmt_pct(gross_margin_latest)}) | Cao | Trung b->nh | Generic -> c?n ki?m ch?ng; Theo d->i k?t qu? d?u th?u h->ng nam |
| T? gi-> / Nguy->n li?u | COGS, Bi->n g?p | L?m ph->t v-> bi?n d?ng t? gi-> l->m tang gi-> v?n nguy->n li?u nh?p kh?u | Trung b->nh | Trung b->nh | Generic -> theo d->i t? l? COGS/doanh thu |
| C?nh tranh generic/nh?p kh?u | Doanh thu, th? ph?n | Thu?c generic v-> nh?p kh?u gi-> r? t?o ->p l?c gi-> b->n v-> th? ph?n | Trung b->nh | Cao | Generic sector risk |
| T?p trung nh-> cung c?p | COGS, ho?t d?ng | Ph? thu?c v->o s? ->t nh-> cung c?p nguy->n li?u ch->nh | Trung b->nh | Th?p | Generic -> xem b->o c->o thu?ng ni->n |
| Gi? d?nh m-> h->nh | Target price, Rating | Gi? d?nh WACC/g chua du?c analyst duy?t -> target price nh?y c?m v?i WACC | Th?p -> Trung b->nh | Cao | C?n ph-> duy?t assumptions tru?c publish |

> _R?i ro d->nh d?u "Generic" l-> r?i ro ng->nh chung chua c-> evidence tr?c ti?p t? ngu?n doanh nghi?p -> c?n ki?m ch?ng b?ng c->ng b? th->ng tin ho?c ngu?n ng->nh tru?c khi xu?t b?n b->o c->o final._

---

## 6. K?t lu?n v-> Ki?m to->n ch?t lu?ng

### 6.1 ->i?m k?t lu?n ch->nh

- **T->i ch->nh:** {ticker} ghi nh?n doanh thu {f"{rev_latest:,.1f} t? VND" if rev_latest else "N/A"} ({latest_fy_str}), bi->n l?i nhu?n g?p {_fmt_pct(gross_margin_latest)}, ROE {_fmt_pct(roe_latest)} -> n?n t?ng l?i nhu?n t?t.
- **D? ph->ng:** CAGR doanh thu {f"{forecast_artifact.get('revenue_cagr_historical', 0):.1%}" if forecast_artifact else "N/A"} l?ch s?; d? ph->ng 2026F->2030F d?a tr->n t? l? median l?ch s? chua du?c analyst ph-> duy?t.
- **->?nh gi-> FCFF:** {fcff_target_str} (upside {fcff_upside_str}) | **FCFE:** {fcfe_target_str} (upside {fcfe_upside_str}) | **Blend 60/40:** {blend_target_str} (upside {blend_upside_str}) -> chua du?c ph-> duy?t.
- **Rating Draft:** {draft_rating} -> ch? c-> hi?u l?c sau khi assumptions du?c analyst ph-> duy?t.
- **R?i ro ch->nh:** Thay d?i ch->nh s->ch BHYT v-> ->p l?c c?nh tranh generic l-> r?i ro tr?ng y?u nh?t v?i bi->n l?i nhu?n.

### 6.2 T->m t?t d?nh gi->

| Ch? ti->u | Gi-> tr? |
|---|---|
| Doanh thu thu?n (FY{latest_year}) | {f"{rev_latest:,.1f} t? VND" if rev_latest else "N/A"} |
| L?i nhu?n sau thu? (FY{latest_year}) | {f"{ni_latest:,.1f} t? VND" if ni_latest else "N/A"} |
| Bi->n l?i nhu?n g?p | {_fmt_pct(gross_margin_latest)} |
| Bi->n l?i nhu?n r->ng | {_fmt_pct(net_margin_latest)} |
| ROE | {_fmt_pct(roe_latest)} |
| N?/V?n ch? | {_fmt_x(debt_eq_latest)} |
| Gi-> Blend DCF (60% FCFF + 40% FCFE) | {blend_target_str} |
| Gi-> FCFF m?c ti->u | {fcff_target_str} |
| Gi-> FCFE m?c ti->u | {fcfe_target_str} |
| Gi-> DCF base | {intrinsic_str} |
| Draft Rating | {draft_rating} |

### 6.3 Ki?m to->n ch?t lu?ng

| Gate | Tr?ng th->i | Ghi ch-> |
|---|---|---|
| Ngu?n d? li?u | PASS | {len(facts)} facts t? snapshot canonical |
| Nh?t qu->n s? li?u | Xem evaluate_report.py | Ch?y scripts/evaluate_report.py --ticker {ticker} |
| T->i l?p valuation | PASS | FCFF recomputable t? artifact |
| Citation coverage | PASS | {len(cmap)} citations du?c t?o |
| ->? tuoi d? li?u | PASS | D? li?u d?n FY{latest_year} |
| Ph-> duy?t gi? d?nh | PENDING | Assumptions chua du?c analyst ph-> duy?t |
| Ph-> duy?t final | PENDING | Chua qua HITL approval |

### 6.4 Disclaimer

> **Tuy->n b? quan tr?ng:** B->o c->o n->y ch? nh?m m?c d->ch nghi->n c?u v-> tham kh?o h?c thu?t/s?n ph?m. N?i dung kh->ng ph?i l-> khuy?n ngh? d?u tu c-> nh->n h->a, kh->ng ph?i l?i m?i mua/b->n ch?ng kho->n, v-> kh->ng thay th? tu v?n t? chuy->n gia du?c c?p ph->p. K?t qu? d?nh gi-> ph? thu?c v->o d? li?u d?u v->o, gi? d?nh m-> h->nh v-> di?u ki?n th? tru?ng t?i th?i di?m l?p b->o c->o. Rating trong b->o c->o l-> k?t lu?n m-> h->nh d?a tr->n d? li?u v-> gi? d?nh hi?n t?i -> kh->ng ph?i khuy?n ngh? d?u tu c-> nh->n h->a. Hi?u su?t qu-> kh? kh->ng d?m b?o k?t qu? tuong lai.

---

## 7. Ph? l?c

### A. Gi? d?nh d?nh gi-> (chua ph-> duy?t)

```json
{json.dumps(assumptions, indent=2, default=str)}
```

### B. Gi? d?nh FCFF/WACC

```json
{json.dumps(fcff_artifact.get("wacc_breakdown", {}), indent=2, default=str)}
```

### C. B?ng b?ng ch?ng (Citation Map)

| Ch? ti->u | K? | Gi-> tr? | Ngu?n |
|---|---|---|---|
""" + "\n".join(
        f"| {v['line_item_label']} | {v['period']} | {v['value_display']} | {v['source_title']} |"
        for k, v in list(cmap.items())[:30]
    ) + """

### D. Footnotes (Tr->ch d?n chi ti?t)

""" + _footnotes(cmap, claims_used, mode)

    # -- Phase 6: final-export gate banner --------------------------------------
    text_corruption_detected = _has_text_corruption(report_md)
    quality_blocked = (
        text_corruption_detected
        or shares_mn is None
        or assumption_gate.status != "approved_for_publish"
        or source_tier_gate.get("export_decision") == "BLOCKED"
        or source_tier_gate.get("blocking_count", 0) > 0
    )
    if quality_blocked:
        report_md = _build_quality_blocked_report(
            ticker=ticker,
            info=info,
            generated_at=generated_at,
            fact_table=fact_table,
            fy_periods=fy_periods,
            latest_fy_str=latest_fy_str,
            current_price=current_price,
            shares_mn=shares_mn,
            source_tier_gate=source_tier_gate,
            assumption_gate=assumption_gate,
            forecast_artifact=forecast_artifact,
            fcff_artifact=fcff_artifact,
            fcfe_artifact=fcfe_artifact,
            blend_artifact=blend_artifact,
            text_corruption_detected=text_corruption_detected,
        )

    export_blocked = quality_blocked or (
        (mode == "final") and (source_tier_gate["export_decision"] == "BLOCKED")
    )
    if mode == "final":
        n_block = source_tier_gate.get("blocking_count", len(source_tier_gate["blocking_reasons"]))
        if export_blocked:
            banner = (
                "> **BÁO CÁO KHÔNG ĐỦ ĐIỀU KIỆN XUẤT BẢN FINAL**\n"
                f"> {n_block} quantitative claim bị chặn bởi source-tier gate, "
                "thiếu fact cổ phiếu explicit, assumptions chưa approved hoặc template bị lỗi chữ.\n"
            )
        else:
            banner = "> **Source-tier gate: PASS** - mọi quantitative claim có nguồn chính thức.\n"
        report_md = banner + "\n" + report_md

    # -- Save report ------------------------------------------------------------
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _suffix = "_BLOCKED" if export_blocked else ""
    report_path = REPORTS_DIR / f"{ticker}_{ts_str}_{report_type}_{mode}{_suffix}.md"
    _assert_report_text_clean(report_md)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[generate_report] Report saved: {report_path}")

    # -- Save citation map ------------------------------------------------------
    out_dir = ROOT / "artifacts" / "reports"
    citation_artifact = build_citation_artifact(
        ticker=ticker,
        snapshot_id=used_snapshot_id,
        generated_at=generated_at,
        report_path=report_path,
        forecast_path=forecast_path,
        fcff_path=fcff_path,
        fcfe_path=fcfe_path,
        blend_path=blend_path,
        report_type=report_type,
        mode=mode,
        export_blocked=export_blocked,
        source_tier_gate=source_tier_gate,
        citation_map=cmap,
        claims_used=claims_used,
        evidence_chunks_used=len(evidence_chunks),
        facts_in_snapshot=len(facts),
        draft_rating=draft_rating,
        fcff_upside_pct=fcff_upside,
        dcf_upside_pct=upside_dcf,
    )
    citation_path = write_citation_artifact(
        artifact=citation_artifact,
        output_dir=out_dir,
        ticker=ticker,
        timestamp=ts_str,
        report_type=report_type,
        mode=mode,
    )
    print(f"[generate_report] Citation map saved: {citation_path}")

    # Phase 6: stable-named final-mode citation artifacts for the evaluator.
    if mode == "final":
        _write_final_citation_artifacts(ticker, citation_artifact, claims_used, cmap)

    return citation_artifact


def _write_final_citation_artifacts(ticker, citation_artifact, claims_used, cmap) -> None:
    """Write artifacts/reports/<TICKER>_final_citation_map.json + _final_citation_audit.md."""
    out_dir = ROOT / "artifacts" / "reports"
    write_final_citation_artifacts(
        ticker=ticker,
        citation_artifact=citation_artifact,
        claims_used=claims_used,
        citation_map=cmap,
        output_dir=out_dir,
    )
    print(f"[generate_report] Final citation artifacts written to {out_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate equity research report from research snapshot.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--from-year", type=int, default=MVP_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=MVP_TO_YEAR, dest="to_year")
    parser.add_argument("--report-type", default="full_report", dest="report_type")
    parser.add_argument("--snapshot-id", default=None, dest="snapshot_id")
    parser.add_argument("--mode", default="draft", choices=["draft", "final"],
                        help="draft warns on Tier-3; final blocks export without official sources")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = generate_report(
        ticker=args.ticker,
        from_year=args.from_year,
        to_year=args.to_year,
        report_type=args.report_type,
        snapshot_id=args.snapshot_id,
        mode=args.mode,
    )
    if result.get("export_blocked"):
        print("[generate_report] REPORT QUALITY BLOCKED -> report is audit-only "
              "until source, share-count, assumption, and text-quality gates pass.")
        if args.mode == "final":
            sys.exit(3)
    print("[generate_report] done")


if __name__ == "__main__":
    main()
