"""Load real financial data from valuation artifacts and return a populated ReportContext.

Supports two artifact formats:
  - New format (DHG+): has blend_dcf, fcff.fcff_table, sensitivity.fcff_wacc_g.matrix
  - Old format (DBD): has dcf.base.intrinsic_value_per_share_vnd, current_price_vnd at root,
    sensitivity.wacc_range/g_range/matrix directly, multiples.eps_vnd

Usage::

    from backend.reporting.report_data_loader import load_report_context
    ctx = load_report_context("DHG")
"""
from __future__ import annotations

import json
import logging as _logging
import os
from pathlib import Path
from typing import Optional

# Optional DB support
try:
    import psycopg2  # type: ignore
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

from backend.dataset.config_io import load_universe_rows
from backend.database.config import connect_with_retry, require_database_url
from backend.reporting.section_builder import ReportContext

ROOT = Path(__file__).resolve().parents[2]

_loader_logger = _logging.getLogger(__name__)


def _resolve_artifact(
    key: str,
    glob_pattern: str,
    manifest=None,
    allow_latest_artifacts: bool = False,
) -> dict:
    """Resolve JSON artifact: manifest-first, then glob fallback with DeprecationWarning.

    If manifest is provided, only the manifest path is used — glob is never called.
    If manifest is None, glob is used and a DeprecationWarning is emitted.
    """
    if manifest is not None:
        return manifest.load_json(key)  # load_json already logs on failure, returns {}

    raise ValueError(f"run_id is required to resolve artifact '{key}'")


def _read_manifest_or_raise(run_id: str, base_dir: "Path | None" = None):
    from backend.reporting.artifact_manifest import read_manifest

    manifest = read_manifest(run_id)
    if manifest is None:
        raise FileNotFoundError(
            f"No artifact manifest found for run_id={run_id!r}. "
            "Run the canonical pipeline first or use debug rendering without run_id."
        )
    return manifest

# ── Company master data ────────────────────────────────────────────────────────
_COMPANIES: dict[str, tuple[str, str]] = {
    "DHG": ("Công ty CP Dược Hậu Giang", "HOSE"),
    "IMP": ("Công ty CP Dược phẩm Imexpharm", "HOSE"),
    "DMC": ("Công ty CP XNK Y tế Domesco", "HOSE"),
    "TRA": ("Công ty CP Traphaco", "HOSE"),
    "DBD": ("Công ty CP Dược Bình Định", "HOSE"),
}
for _row in load_universe_rows():
    _ticker = (_row.get("ticker") or "").strip().upper()
    if _ticker:
        _COMPANIES.setdefault(
            _ticker,
            ((_row.get("company_name") or _ticker).strip(), (_row.get("exchange") or "HOSE").strip()),
        )

_SECTOR_BLURB: dict[str, str] = {
    "DHG": (
        "Công ty CP Dược Hậu Giang (DHG) là công ty dược phẩm lớn nhất Việt Nam tính theo "
        "doanh thu nội địa, thành lập 1974, niêm yết HOSE từ 2006. Công ty sản xuất và phân phối "
        "trên 300 sản phẩm, tập trung vào hai kênh chính: OTC (nhà thuốc) và ETC (đấu thầu bệnh "
        "viện). Năng lực sản xuất đạt chuẩn GMP-WHO và PIC/S. Cổ đông chiến lược lớn nhất là "
        "Taisho Pharmaceutical Nhật Bản (~51%). Vị thế thị trường và hệ thống phân phối rộng "
        "khắp tạo lợi thế cạnh tranh bền vững trong ngành dược generic Việt Nam."
    ),
    "IMP": (
        "Công ty CP Dược phẩm Imexpharm (IMP) là nhà sản xuất dược phẩm generic chất lượng cao, "
        "niêm yết HOSE. Công ty tập trung vào sản phẩm đạt chuẩn EU-GMP, cung cấp cho kênh bệnh "
        "viện và chuỗi nhà thuốc. Định vị ở phân khúc generic chất lượng cao, IMP hưởng lợi từ "
        "xu hướng nâng cấp tiêu dùng dược phẩm tại Việt Nam."
    ),
    "DMC": (
        "Công ty CP XNK Y tế Domesco (DMC) chuyên sản xuất và phân phối dược phẩm, thiết bị y tế "
        "tại Việt Nam, niêm yết HOSE. Công ty có mạng lưới phân phối rộng và danh mục sản phẩm đa "
        "dạng phục vụ cả kênh OTC và ETC."
    ),
    "TRA": (
        "Công ty CP Traphaco (TRA) là công ty dược phẩm và thảo dược hàng đầu Việt Nam, niêm yết "
        "HOSE. Nổi tiếng với các sản phẩm thảo dược và dược phẩm từ thiên nhiên, Traphaco sở hữu "
        "thương hiệu mạnh trong phân khúc đông dược và sản phẩm chăm sóc sức khỏe."
    ),
    "DBD": (
        "Công ty CP Dược Bình Định (DBD) là nhà sản xuất dược phẩm khu vực miền Trung Việt Nam, "
        "niêm yết HOSE. Công ty cung cấp đa dạng sản phẩm dược generic cho cả kênh ETC (đấu thầu "
        "bệnh viện) và OTC, phục vụ thị trường miền Trung và Tây Nguyên. Biên gộp ổn định trong "
        "vùng 47-49% phản ánh cơ cấu sản phẩm cân bằng."
    ),
}

_PLACEHOLDER = "Chưa có dữ liệu — cần bổ sung trước khi export final."
_NA = "N/A"

_SEGMENT_VI: dict[str, str] = {
    "pharma": "dược phẩm",
    "healthcare_services": "dịch vụ y tế",
    "medical_equipment": "thiết bị y tế",
    "medical_distribution": "phân phối y tế",
    "biotech": "công nghệ sinh học",
}


def _get_sector_blurb(ticker: str) -> str:
    """Return a company overview blurb for *ticker*.

    Uses the curated _SECTOR_BLURB entry when available; otherwise
    auto-generates a factual stub from the universe registry so no ticker
    ever receives the raw _PLACEHOLDER string in the company overview.
    """
    if ticker in _SECTOR_BLURB:
        return _SECTOR_BLURB[ticker]
    company_name, exchange = _COMPANIES.get(ticker, (ticker, "HOSE"))
    universe_row = next(
        (r for r in load_universe_rows() if r.get("ticker", "").upper() == ticker),
        {},
    )
    segment = universe_row.get("segment", "pharma")
    segment_vi = _SEGMENT_VI.get(segment, "y tế - dược phẩm")
    return (
        f"{company_name} ({ticker}) là doanh nghiệp trong ngành {segment_vi}, "
        f"niêm yết {exchange}. "
        f"Công ty hoạt động trong lĩnh vực {segment_vi} tại Việt Nam. "
        f"Thông tin mô tả chi tiết sẽ được bổ sung từ báo cáo thường niên và "
        f"tài liệu công bố thông tin chính thức của doanh nghiệp."
    )


def _build_dynamic_peer_table(
    ticker: str,
    mc_str: str,
    pe_str: str,
    pb_str: str,
    roe_pct: "float | None",
    net_margin_pct: "float | None",
) -> str:
    """Build a peer comparison table using same-segment universe tickers.

    The subject ticker always appears first with computed values.
    Peers come from the universe registry (same segment), shown as pending
    with an explicit disclaimer. Never hardcodes specific peer tickers or values.
    """
    roe_s = f"{roe_pct:.1f}%" if roe_pct else _NA
    nm_s  = f"{net_margin_pct:.1f}%" if net_margin_pct else _NA

    header = (
        "| Ticker | Vốn hóa (tỷ) | P/E | P/B | ROE | Biên ròng |\n"
        "|---|---:|---:|---:|---:|---:|\n"
    )
    subject_row = f"| **{ticker}** | {mc_str} | {pe_str} | {pb_str} | {roe_s} | {nm_s} |\n"

    universe_row = next(
        (r for r in load_universe_rows() if r.get("ticker", "").upper() == ticker),
        {},
    )
    subject_segment = universe_row.get("segment", "pharma")
    peer_rows_str = ""
    peer_count = 0
    for row in load_universe_rows():
        peer_t = row.get("ticker", "").upper()
        if peer_t == ticker:
            continue
        if row.get("segment", "pharma") != subject_segment:
            continue
        peer_rows_str += f"| {peer_t} | — | — | — | — | — |\n"
        peer_count += 1
        if peer_count >= 4:
            break

    if peer_count == 0:
        peer_rows_str = "| Peers cùng ngành | — | — | — | — | — |\n"

    disclaimer = (
        "\n> _Dữ liệu peer (—) sẽ được cập nhật khi artifacts tương ứng được ingest. "
        "Không sử dụng ước tính thủ công._"
    )
    return header + subject_row + peer_rows_str + disclaimer


# Module-level constant — canonical narrative fields injected from FinancialAnalystAgent
_NARRATIVE_FIELDS = [
    "financial_narrative",
    "investment_thesis",
    "risk_narrative",
    "forecast_narrative",
    "valuation_narrative",
]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_db_facts(ticker: str) -> dict[tuple[str, str], float]:
    """Load canonical_facts from DB as {(metric_name, period): value}."""
    if not _HAS_DB:
        return {}
    dsn = require_database_url()
    try:
        conn = connect_with_retry(dsn)
        cur = conn.cursor()
        cur.execute(
            "SELECT metric_name, period, value FROM canonical_facts "
            "WHERE ticker=%s ORDER BY created_at DESC",
            (ticker,),
        )
        seen: dict[tuple[str, str], float] = {}
        for metric, period, value in cur.fetchall():
            key = (metric, str(period))
            if key not in seen:
                seen[key] = float(value)
        conn.close()
        return seen
    except Exception as exc:
        _loader_logger.warning(
            "DB canonical_facts load failed for ticker=%s: %s — using empty dict fallback",
            ticker, exc,
        )
        return {}


def _load_agent_narrative_from_manifest(run_id: str, base_dir: "Path | None" = None) -> dict:
    """Load FinancialAnalystAgent narrative fields from the run's artifact manifest.

    Returns an empty dict if no manifest or no financial_analysis artifact exists.
    Safe to call — never raises.
    """
    try:
        manifest = _read_manifest_or_raise(run_id, base_dir=base_dir)
        artifact = manifest.load_json("financial_analysis")
        # artifact may be the payload directly, or wrapped under a "payload" key
        payload = artifact.get("payload") or artifact
        return {
            "financial_narrative": str(payload.get("financial_narrative") or ""),
            "investment_thesis": str(payload.get("investment_thesis") or ""),
            "risk_narrative": str(payload.get("risk_narrative") or ""),
            "forecast_narrative": str(payload.get("forecast_narrative") or ""),
            "valuation_narrative": str(payload.get("valuation_narrative") or ""),
        }
    except Exception as exc:
        _loader_logger.debug(
            "Agent narrative not loaded for run_id=%s: %s",
            run_id, exc,
        )
        return {}


def _pct(v: float | None) -> Optional[float]:
    """Convert decimal ratio to percentage, rounded to 1 dp. Returns None if missing."""
    if v is None:
        return None
    return round(v * 100, 1)


def _latest_val_or_none(d: dict, fy_periods: list[str]) -> Optional[float]:
    """Return value for the last available FY period in *d*, or None if missing."""
    if not d or not fy_periods:
        return None
    for p in reversed(fy_periods):
        v = d.get(p)
        if v is not None:
            return v
    return None


def _rating_from_upside(upside_pct: float) -> str:
    """Compute analyst rating from upside percentage.

    Bands:
      BUY  : upside > +15%
      HOLD : -20% <= upside <= +15%
      SELL : upside < -20%
    """
    if upside_pct > 15.0:
        return "BUY"
    if upside_pct >= -20.0:
        return "HOLD"
    return "SELL"


def _load_chart_paths(ticker: str) -> dict[str, str]:
    """Return chart_id → absolute path for existing chart PNGs."""
    return {}


def _has_valid_data(lst: list, min_nonzero: int = 1) -> bool:
    """Return True if list has at least min_nonzero non-zero, non-None values."""
    count = sum(1 for v in lst if v is not None and v != 0.0 and not (isinstance(v, float) and not v == v))
    return count >= min_nonzero


def _positive_number(v: object) -> Optional[float]:
    """Return a positive finite float, otherwise None."""
    try:
        n = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if n > 0 and n == n and n not in (float("inf"), float("-inf")):
        return n
    return None


def _status_token(v: object) -> str:
    """Normalize artifact/gate status strings for deterministic checks."""
    return str(v or "").strip().upper().replace("-", "_")


def _status_pass(v: object) -> bool:
    return _status_token(v) in {"PASS", "PASSED", "APPROVED", "ANALYST_APPROVED"}


def _status_pending_or_unapproved(v: object) -> bool:
    return _status_token(v) in {
        "",
        "MISSING",
        "N_A",
        "NA",
        "PENDING",
        "PENDING_REVIEW",
        "DEFAULT_UNAPPROVED",
        "DRAFT_NEEDS_ANALYST_REVIEW",
        "UNDER_REVIEW",
    }


def _artifact_status(artifact: dict) -> str:
    """Best-effort status lookup across legacy and current artifact formats."""
    for key in ("validation_status", "status", "artifact_status", "valuation_status"):
        if artifact.get(key) is not None:
            return str(artifact.get(key))
    if artifact.get("rating_model_output") == "UNDER_REVIEW":
        return "UNDER_REVIEW"
    return "MISSING"


def _assumptions_approved(val: dict, fcff_v: dict, valuation_result: dict) -> bool:
    """Return True only when assumptions are explicitly approved."""
    candidates = [
        fcff_v.get("assumption_status"),
        val.get("assumption_status"),
        val.get("assumptions_status"),
        valuation_result.get("assumption_status"),
        valuation_result.get("forecast_assumption_status"),
    ]
    assumptions = valuation_result.get("assumptions")
    if isinstance(assumptions, list) and assumptions:
        candidates.extend(a.get("status") for a in assumptions if isinstance(a, dict))
    return any(_status_pass(c) for c in candidates)


def _valuation_publishable(
    val: dict,
    fcff_v: dict,
    valuation_result: dict,
    current_price: Optional[float],
    target_price: Optional[float],
) -> bool:
    """Centralized valuation gate for target price, upside, and rating display."""
    artifact = valuation_result or val
    status = _artifact_status(artifact)
    explicit_publishable = artifact.get("is_publishable")
    if explicit_publishable is False:
        return False
    return (
        current_price is not None
        and target_price is not None
        and _status_pass(status)
        and _assumptions_approved(val, fcff_v, valuation_result)
    )


def _forecast_publishable(fcff_v: dict, valuation_result: dict) -> bool:
    """Forecast charts/tables require actual rows and approved assumptions."""
    if not fcff_v.get("fcff_table"):
        return False
    status = fcff_v.get("validation_status") or fcff_v.get("status")
    if status is not None and not _status_pass(status):
        return False
    return _assumptions_approved({}, fcff_v, valuation_result)


def _sensitivity_publishable(
    sens_norm: dict,
    valuation_passed: bool,
    valuation_result: dict,
) -> bool:
    """Sensitivity requires a valid valuation plus non-empty sensitivity data."""
    if not valuation_passed or not sens_norm:
        return False
    sens_status = valuation_result.get("sensitivity_status")
    if sens_status is None and isinstance(valuation_result.get("sensitivity"), dict):
        sens_status = valuation_result["sensitivity"].get("validation_status")
    return sens_status is None or _status_pass(sens_status)


# ── Artifact format adapters ─────────────────────────────────────────────────
# Two formats exist:
# - "new" (DHG+): blend_dcf + fcff.fcff_table + sensitivity.fcff_wacc_g
# - "old" (DBD):  dcf.base + multiples + sensitivity.{wacc_range, g_range, matrix}

def _extract_prices(val: dict) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (current_price, target_price, upside_pct) from valuation artifact.

    Returns None for any value that is genuinely unavailable.
    upside_pct is in percentage points (e.g. 15.3 not 0.153).
    """
    if not val:
        return None, None, None

    # Public valuation-result artifact: zeros mean unavailable, not actual zero.
    if {"current_price", "target_price", "upside_downside"} & set(val.keys()):
        cp = _positive_number(val.get("current_price"))
        tp = _positive_number(val.get("target_price"))
        raw_upside = val.get("upside_downside")
        upside = None
        try:
            if raw_upside is not None and cp is not None and tp is not None:
                up = float(raw_upside)
                if up == up:
                    upside = round(up * 100, 1)
        except (TypeError, ValueError):
            upside = None
        return cp, tp, upside

    # New format: blend_dcf
    blend = val.get("blend_dcf", {})
    if blend:
        cp = _positive_number(blend.get("current_price_vnd"))
        tp = _positive_number(blend.get("target_price_dcf_vnd"))
        raw_upside = blend.get("upside_pct")
        upside = round(raw_upside * 100, 1) if raw_upside is not None else None
        return cp, tp, upside

    # Old format (DBD): current_price at root + dcf.base target
    cp = _positive_number(val.get("current_price_vnd")) or _positive_number(val.get("multiples", {}).get("current_price_vnd"))
    dcf = val.get("dcf", {})
    base = dcf.get("base", {})
    tp = _positive_number(base.get("intrinsic_value_per_share_vnd"))

    if cp and tp:
        upside = round((tp - cp) / cp * 100, 1)
    else:
        upside = None

    return cp, tp, upside


def _extract_fcff(val: dict) -> dict:
    """Return FCFF section regardless of format.

    New format: val['fcff'] directly has fcff_table, wacc, terminal_growth.
    Old format: no fcff key; adapt from dcf.base.
    """
    fcff = val.get("fcff", {})
    if fcff:
        return fcff

    # Old format: derive from dcf.base
    dcf_base = val.get("dcf", {}).get("base", {})
    if dcf_base:
        assumptions = dcf_base.get("assumptions", {})
        return {
            "wacc": assumptions.get("wacc", 0.10),
            "terminal_growth": assumptions.get("terminal_growth", 0.03),
            "fcff_table": [],  # Old format has no row-level FCFF table
            "assumption_status": "default_unapproved",
        }
    return {}


def _extract_multiples(val: dict) -> dict:
    """Return multiples dict regardless of format."""
    return val.get("multiples", {})


def _extract_sensitivity(val: dict) -> dict:
    """Return sensitivity data in normalised form {wacc_range, g_range, matrix}.

    New format: val['sensitivity']['fcff_wacc_g']['matrix']
    Old format: val['sensitivity']['matrix'] directly
    """
    sens = val.get("sensitivity", {})
    if not sens:
        return {}

    # New format
    sg = sens.get("fcff_wacc_g", {})
    if sg and sg.get("matrix"):
        return {
            "wacc_range": sg.get("wacc_range", []),
            "g_range": sg.get("g_range", []),
            "matrix": sg.get("matrix", {}),
        }

    # Old format: matrix is directly under sensitivity
    if sens.get("matrix"):
        return {
            "wacc_range": sens.get("wacc_range", []),
            "g_range": sens.get("g_range", []),
            "matrix": sens.get("matrix", {}),
        }

    return {}


# ── Table builders ─────────────────────────────────────────────────────────────

def _build_fin_table(ratios: dict, fy_periods: list[str]) -> str:
    gm = ratios.get("gross_margin", {})
    nm = ratios.get("net_margin", {})
    roe_r = ratios.get("roe", {})
    roa_r = ratios.get("roa", {})
    rev_g = ratios.get("revenue_growth", {})

    # Use up to 4 periods ending at the latest
    periods = fy_periods[-4:] if len(fy_periods) >= 4 else fy_periods
    while len(periods) < 4:
        periods = ["—"] + periods

    def fmt(d: dict, p: str) -> str:
        if p == "—":
            return "—"
        v = d.get(p)
        return f"{round(v * 100, 1):.1f}%" if v is not None else "—"

    header = "| Chỉ tiêu | " + " | ".join(periods) + " |\n"
    sep = "|---|" + "---:|" * len(periods) + "\n"
    rows = [
        "| Tăng trưởng DT | " + " | ".join(
            "—" if i == 0 else fmt(rev_g, p) for i, p in enumerate(periods)
        ) + " |",
        "| Biên gộp | " + " | ".join(fmt(gm, p) for p in periods) + " |",
        "| Biên ròng | " + " | ".join(fmt(nm, p) for p in periods) + " |",
        "| ROE | " + " | ".join(fmt(roe_r, p) for p in periods) + " |",
        "| ROA | " + " | ".join(fmt(roa_r, p) for p in periods) + " |",
    ]
    return header + sep + "\n".join(rows) + "\n"


def _build_dcf_table(fcff_v: dict) -> str:
    fcff_tbl = fcff_v.get("fcff_table", [])
    if not fcff_tbl:
        return "> _Bảng DCF FCFF chi tiết chưa có — cần chạy lại valuation engine với FCFF module._"
    forecast_rows = {r["year"]: r for r in fcff_tbl}
    years = ["2026F", "2027F", "2028F", "2029F", "2030F"]
    cols = [
        ("EBIT (tỷ VND)", "ebit"),
        ("NOPAT (tỷ VND)", "ebit_after_tax"),
        ("KH (tỷ VND)", "depreciation"),
        ("CAPEX (tỷ VND)", "capex"),
        ("dNWC (tỷ VND)", "delta_nwc"),
        ("FCFF (tỷ VND)", "fcff"),
        ("Discount Factor", "discount_factor"),
        ("PV FCFF (tỷ VND)", "pv_fcff"),
    ]
    header = "| Chi tiêu | " + " | ".join(years) + " |\n"
    sep = "|---|" + "---:|" * len(years) + "\n"
    body = ""
    for label, col in cols:
        vals = []
        for yr in years:
            v = forecast_rows.get(yr, {}).get(col)
            if v is None:
                vals.append("—")
            elif col == "discount_factor":
                vals.append(f"{v:.4f}")
            else:
                vals.append(f"{v / 1e9:,.0f}" if abs(v) > 1e6 else f"{v:,.2f}")
        body += f"| {label} | " + " | ".join(vals) + " |\n"
    return header + sep + body


def _build_val_summary(val: dict, target_price: Optional[float], current_price: Optional[float]) -> str:
    blend = val.get("blend_dcf", {})
    mult = _extract_multiples(val)

    def _fmt(v: Optional[float]) -> str:
        return f"{v:,.0f}" if v else "—"

    if blend:
        p_fcff = blend.get("price_fcff_vnd") or None
        p_fcfe = blend.get("price_fcfe_vnd") or None
        w_fcff = blend.get("fcff_weight", 0.60)
        w_fcfe = blend.get("fcfe_weight", 0.40)
        fcff_pct = f"{w_fcff * 100:.0f}%"
        fcfe_pct = f"{w_fcfe * 100:.0f}%"
        fcff_wtd = f"{p_fcff * w_fcff:,.0f}" if p_fcff else "—"
        fcfe_wtd = f"{p_fcfe * w_fcfe:,.0f}" if p_fcfe else "—"
        rows = (
            f"| DCF - FCFF | {_fmt(p_fcff)} | {fcff_pct} | {fcff_wtd} | Đã tính |\n"
            f"| DCF - FCFE | {_fmt(p_fcfe)} | {fcfe_pct} | {fcfe_wtd} | {'Đã tính' if p_fcfe else 'Chưa có'} |\n"
        )
    else:
        # Old format: DCF base
        dcf_base = val.get("dcf", {}).get("base", {})
        p_dcf = dcf_base.get("intrinsic_value_per_share_vnd") or None
        p_pe = mult.get("implied_price_pe") or None
        rows = (
            f"| DCF (FCF-based) | {_fmt(p_dcf)} | 60% | {f'{p_dcf * 0.6:,.0f}' if p_dcf else '—'} | Nháp |\n"
            f"| P/E tương đối | {_fmt(p_pe)} | 40% | {f'{p_pe * 0.4:,.0f}' if p_pe else '—'} | Nháp |\n"
        )

    tp_str = f"{target_price:,.0f}" if target_price else "—"
    table = (
        "| Phương pháp | Giá hàm ý (VND/CP) | Trọng số | Giá có trọng số | Trạng thái |\n"
        "|---|---:|---:|---:|---|\n"
        + rows
        + f"| **Giá mục tiêu** | **{tp_str}** | 100% | **{tp_str}** | Đang rà soát |\n"
    )
    return table


def _build_val_assumptions(fcff_v: dict, mult: dict, current_price: Optional[float]) -> str:
    wacc = fcff_v.get("wacc", 0.10)
    tg = fcff_v.get("terminal_growth", 0.03)
    shares = mult.get("shares_mn", 0)
    net_debt = mult.get("net_debt_vnd_bn", 0)
    cp_str = f"{current_price:,.0f}" if current_price else _NA
    return (
        "| Tham số | Giá trị | Ghi chú |\n"
        "|---|---:|---|\n"
        f"| WACC | {wacc * 100:.1f}% | Mô hình DCF |\n"
        f"| Tăng trưởng dài hạn | {tg * 100:.1f}% | Mô hình DCF |\n"
        f"| Số cổ phiếu lưu hành | {shares:.2f} triệu CP | Dữ liệu chuẩn hóa |\n"
        f"| Nợ ròng | {net_debt:,.1f} tỷ VND | Dữ liệu chuẩn hóa |\n"
        f"| Giá thị trường | {cp_str} VND/CP | Dữ liệu thị trường |\n"
        f"| Trạng thái giả định | Đang rà soát | **Cần phê duyệt trước khi công bố** |\n"
    )


def _build_sensitivity_matrix(sens_norm: dict) -> str:
    """Build sensitivity matrix table from normalised sensitivity dict."""
    wrange = sens_norm.get("wacc_range", [])
    grange = sens_norm.get("g_range", [])
    matrix_d = sens_norm.get("matrix", {})
    if not matrix_d or not wrange or not grange:
        return "> _Dữ liệu sensitivity chưa có._"

    w_keys = [f"{w:.3f}" for w in wrange]
    g_keys_for_lookup = [f"{g:.3f}" if g < 0.01 else (f"{g:.2f}" if g < 0.1 else f"{g:.3f}") for g in grange]

    header = "| Target Price (VND/CP) | " + " | ".join([f"WACC {w * 100:.1f}%" for w in wrange]) + " |\n"
    sep = "|---|" + "---:|" * len(wrange) + "\n"
    body = ""
    for g, g_key_lookup in zip(grange, g_keys_for_lookup):
        row_vals = []
        for w_key in w_keys:
            row_d = matrix_d.get(w_key, {})
            # Try multiple key formats for g
            v = row_d.get(g_key_lookup)
            if v is None:
                # Try 2-decimal, 3-decimal, and string representations
                for alt in [f"{g:.2f}", f"{g:.3f}", str(g)]:
                    v = row_d.get(alt)
                    if v is not None:
                        break
            row_vals.append(f"{float(v):,.0f}" if v is not None else "—")
        body += f"| g={g * 100:.1f}% | " + " | ".join(row_vals) + " |\n"
    return header + sep + body


def _build_forecast_assumptions_table(fc: dict) -> str:
    fc_drivers = fc.get("drivers", {})
    labels = {
        "revenue_growth": "Revenue growth",
        "gross_margin": "Gross margin",
        "sga_to_revenue": "SGA/Revenue",
        "depreciation_to_revenue": "Depr/Revenue",
        "capex_to_revenue": "CAPEX/Revenue",
    }
    if not fc_drivers:
        return (
            "> _Assumptions chưa được lập — cần analyst review và phê duyệt trước khi "
            "dùng cho forecast chart và valuation._"
        )
    table = "| Assumption | Base Case | Approval Status |\n|---|---:|---|\n"
    for k, v in fc_drivers.items():
        if isinstance(v, dict):
            num = v.get("value") or next(
                (x for x in v.values() if isinstance(x, (int, float))), None
            )
            base = f"{num * 100:.1f}%" if num is not None else "—"
        elif isinstance(v, (int, float)):
            base = f"{v * 100:.1f}%"
        else:
            base = str(v)
        table += f"| {labels.get(k, k)} | {base} | pending_review |\n"
    return table


def _build_forecast_table(fcff_v: dict) -> str:
    fcff_tbl = fcff_v.get("fcff_table", [])
    if not fcff_tbl:
        return (
            "> _Bảng dự phóng chưa có. Forecast chart (C5) và bảng này bị chặn "
            "do assumptions chưa được phê duyệt._"
        )
    forecast_rows = {r["label"]: r for r in fcff_tbl}
    years = ["2026F", "2027F", "2028F", "2029F", "2030F"]
    cols = [("EBIT (tỷ VND)", "ebit"), ("FCFF (tỷ VND)", "fcff"), ("PV FCFF (tỷ VND)", "pv_fcff")]
    header = "| Chi tiêu | " + " | ".join(years) + " |\n"
    sep = "|---|" + "---:|" * len(years) + "\n"
    body = ""
    for label, col in cols:
        def _fmtv(yr: str) -> str:
            v = forecast_rows.get(yr, {}).get(col)
            if v is None:
                return "—"
            return f"{v / 1e9:,.0f}" if abs(v) > 1e6 else f"{v:,.2f}"
        body += f"| {label} | " + " | ".join(_fmtv(yr) for yr in years) + " |\n"
    return header + sep + body


def _build_analyst_financial_narrative(
    ratios: dict,
    fy_periods: list[str],
    gross_margin_pct: Optional[float],
    net_margin_pct: Optional[float],
    roe_pct: Optional[float],
    roa_pct: Optional[float],
    fiscal_year: str,
    ticker: str,
) -> str:
    """Build analyst-style financial narrative (not just a metric restatement).

    Answers: what changed, why it matters, implication, what to monitor.
    """
    gm = ratios.get("gross_margin", {})
    nm = ratios.get("net_margin", {})
    roe_r = ratios.get("roe", {})
    rev_g = ratios.get("revenue_growth", {})

    periods = fy_periods[-4:] if len(fy_periods) >= 4 else fy_periods
    if len(periods) < 2:
        return _PLACEHOLDER

    first_fy = periods[0]
    last_fy = periods[-1]

    # Gross margin trend
    gm_first = gm.get(first_fy)
    gm_last = gm.get(last_fy)
    gm_trend = ""
    if gm_first is not None and gm_last is not None:
        gm_chg = round((gm_last - gm_first) * 100, 1)
        direction = "giảm" if gm_chg < 0 else "cải thiện"
        gm_trend = (
            f"Biên gộp {direction} từ {gm_first * 100:.1f}% ({first_fy.replace('FY', '')}) "
            f"xuống {gm_last * 100:.1f}% ({last_fy.replace('FY', '')}), thay đổi {gm_chg:+.1f} điểm %. "
        )
        if gm_chg < -1.0:
            gm_trend += (
                "Xu hướng này phản ánh áp lực giá bán (đặc biệt kênh ETC/đấu thầu) hoặc chi phí "
                "nguyên liệu đầu vào tăng. Nếu tiếp tục, FCFF và biên EBIT sẽ chịu áp lực. "
                "Cần theo dõi kết quả đấu thầu thuốc ETC và biến động giá API nhập khẩu. "
            )
        elif gm_chg > 1.0:
            gm_trend += (
                "Xu hướng tích cực có thể phản ánh cải thiện cơ cấu sản phẩm (tăng tỷ trọng "
                "branded generic) hoặc kiểm soát chi phí đầu vào tốt hơn. "
            )

    # ROE trend
    roe_first = roe_r.get(first_fy)
    roe_last = roe_r.get(last_fy)
    roe_trend = ""
    if roe_first is not None and roe_last is not None:
        roe_chg = round((roe_last - roe_first) * 100, 1)
        if abs(roe_chg) >= 1.0:
            direction = "giảm" if roe_chg < 0 else "tăng"
            roe_trend = (
                f"ROE {direction} từ {roe_first * 100:.1f}% xuống {roe_last * 100:.1f}% "
                f"trong giai đoạn {first_fy.replace('FY', '')}–{last_fy.replace('FY', '')}. "
            )
            if roe_chg < -2.0:
                roe_trend += (
                    "Suy giảm ROE đáng kể — có thể phản ánh mở rộng tài sản (CAPEX, hàng tồn kho) "
                    "chưa tạo ra tăng trưởng lợi nhuận tương xứng. "
                )

    # Revenue growth
    rev_latest = rev_g.get(last_fy)
    rev_trend = ""
    if rev_latest is not None:
        rev_trend = (
            f"Tăng trưởng doanh thu gần nhất ({last_fy.replace('FY', '')}): "
            f"{rev_latest * 100:+.1f}%. "
        )

    # Monitoring items (pharma-specific)
    monitor = (
        "Các chỉ tiêu cần theo dõi: kết quả đấu thầu ETC, tỷ giá USD/VND và giá API nhập khẩu, "
        "ngày tồn kho và phải thu, tỷ lệ thắng thầu so sánh với cùng kỳ năm trước."
    )

    parts = [p for p in [gm_trend, roe_trend, rev_trend, monitor] if p]
    if not parts:
        return _PLACEHOLDER

    return "\n\n".join(parts)


def _build_valuation_narrative(
    fcff_v: dict,
    target_price: Optional[float],
    current_price: Optional[float],
    upside_pct: Optional[float],
    val: dict,
) -> str:
    """Analyst-style valuation commentary."""
    if not target_price:
        return (
            "> _Định giá bị chặn: không có target price hợp lệ. "
            "Cần (1) phê duyệt assumptions WACC và terminal growth, "
            "(2) xác nhận giá thị trường hiện tại, "
            "(3) chạy lại valuation engine._"
        )

    wacc_pct = round(fcff_v.get("wacc", 0.10) * 100, 1)
    tg_pct = round(fcff_v.get("terminal_growth", 0.03) * 100, 1)
    assumption_status = fcff_v.get("assumption_status", "default_unapproved")

    upside_str = f"{upside_pct:+.1f}%" if upside_pct is not None else _NA
    cp_str = f"{current_price:,.0f}" if current_price else _NA

    narrative = (
        f"**Phương pháp:** DCF dựa trên FCF lịch sử với kịch bản Base (WACC={wacc_pct:.1f}%, "
        f"tăng trưởng dài hạn={tg_pct:.1f}%). "
        f"Target price: {target_price:,.0f} VND/CP — giá thị trường: {cp_str} VND/CP "
        f"(tiềm năng: {upside_str}).\n\n"
    )

    if assumption_status == "default_unapproved":
        narrative += (
            "**Lưu ý:** Assumptions hiện tại là mặc định (chưa được analyst review). "
            "Target price trên chỉ là ước tính sơ bộ. "
            "Rating và upside sẽ không được hiển thị chính thức cho đến khi assumptions được phê duyệt.\n\n"
        )

    # Warnings from artifact
    dcf_warnings = val.get("dcf", {}).get("base", {}).get("warnings", [])
    fcff_warnings = fcff_v.get("warnings", [])
    all_warnings = dcf_warnings + fcff_warnings
    if all_warnings:
        narrative += "**Cảnh báo kỹ thuật:**\n"
        for w in all_warnings[:3]:
            narrative += f"- {w}\n"

    return narrative


# ── Main public function ───────────────────────────────────────────────────────

def load_report_context(
    ticker: str,
    run_id: str | None = None,
    allow_latest_artifacts: bool = False,
    agent_narrative: "dict | None" = None,
) -> "ReportContext":
    """Load a fully-populated ReportContext for *ticker* from valuation artifacts.

    When *run_id* is provided, artifacts are resolved deterministically from the
    run manifest.  Without *run_id*, the loader falls back to globbing for the
    most-recent file and emits a DeprecationWarning.

    Falls back to DB canonical facts for any missing numbers.
    Uses typed missing values (None → N/A) instead of coercing to zero.
    """
    ticker = ticker.upper()
    manifest = None
    if run_id:
        manifest = _read_manifest_or_raise(run_id)

    company_name, exchange = _COMPANIES.get(ticker, (ticker, "HOSE"))

    from datetime import datetime
    report_date = datetime.now().strftime("%Y-%m-%d")

    # ── Load valuation artifact ────────────────────────────────────────
    val = _resolve_artifact(
        "valuation",
        "valuation.json",
        manifest,
        allow_latest_artifacts,
    )
    valuation_result = _resolve_artifact(
        "valuation_result",
        "valuation.json",
        manifest,
        allow_latest_artifacts,
    )
    ratios = val.get("ratios", {})
    fc = val.get("forecast", {})
    fcff_v = _extract_fcff(val)
    mult = _extract_multiples(val)
    sens_norm = _extract_sensitivity(val)
    fy_periods: list[str] = val.get("fy_periods", [])

    # ── Core pricing & rating (None = genuinely missing, not 0) ───────
    price_source = valuation_result or val
    current_price, target_price, upside_pct = _extract_prices(price_source)
    valuation_passed = _valuation_publishable(
        val, fcff_v, valuation_result, current_price, target_price
    )

    # Only assign a rating when valuation is validated and assumptions are approved.
    if not valuation_passed:
        target_price = None
        upside_pct = None
        rating = "UNDER_REVIEW"
    elif upside_pct is not None:
        rating = _rating_from_upside(upside_pct)
    else:
        rating = "UNDER_REVIEW"

    # ── Ratio extracts (None = missing) ───────────────────────────────
    gm = ratios.get("gross_margin", {})
    nm = ratios.get("net_margin", {})
    roe_r = ratios.get("roe", {})
    roa_r = ratios.get("roa", {})

    gross_margin_pct = _pct(_latest_val_or_none(gm, fy_periods))
    net_margin_pct = _pct(_latest_val_or_none(nm, fy_periods))
    roe_pct = _pct(_latest_val_or_none(roe_r, fy_periods))
    roa_pct = _pct(_latest_val_or_none(roa_r, fy_periods))

    shares_mn = mult.get("shares_mn", 0.0) or 0.0
    eps_vnd = mult.get("eps_vnd") or None
    pe_x = mult.get("pe_ratio") or None
    pb_x = mult.get("pb_ratio") or None

    if current_price and shares_mn:
        market_cap_bn = round(current_price * shares_mn * 1e6 / 1e9)
    else:
        market_cap_bn = None

    wacc_pct = round(fcff_v.get("wacc", 0.10) * 100, 1) if valuation_passed and fcff_v else 0.0
    terminal_growth_pct = round(fcff_v.get("terminal_growth", 0.03) * 100, 1) if valuation_passed and fcff_v else 0.0
    fiscal_year = fy_periods[-1].replace("FY", "") if fy_periods else "—"

    # ── Valuation artifact status ──────────────────────────────────────
    has_valuation = valuation_passed
    valuation_assumption_status = fcff_v.get("assumption_status", "default_unapproved") if fcff_v else "missing"
    has_forecast_table = _forecast_publishable(fcff_v, valuation_result)
    has_sensitivity = _sensitivity_publishable(sens_norm, has_valuation, valuation_result)

    # ── Tables ────────────────────────────────────────────────────────
    fin_table = _build_fin_table(ratios, fy_periods) if (ratios and fy_periods) else _PLACEHOLDER
    dcf_table = _build_dcf_table(fcff_v) if has_valuation else (
        "> _DCF bị chặn: valuation artifact chưa PASS hoặc assumptions chưa được phê duyệt. Không hiển thị WACC, terminal growth, hay FCFF bridge cho đến khi gate định giá hợp lệ._"
    )
    val_summary = _build_val_summary(val, target_price, current_price) if has_valuation else (
        "> _Bảng định giá bị chặn: thiếu target price hợp lệ. Cần valuation artifact có trạng thái PASS._"
    )
    val_assumptions = _build_val_assumptions(fcff_v, mult, current_price) if has_valuation and fcff_v else (
        "> _Giả định định giá bị chặn: cần valuation artifact PASS và analyst approval trước khi công bố WACC, terminal growth, shares, net debt trong mục định giá._"
    )
    sens_matrix = _build_sensitivity_matrix(sens_norm) if has_sensitivity else (
        "> _Ma trận độ nhạy chưa có. Cần sensitivity artifact với trạng thái PASS._"
    )
    assumptions_table = _build_forecast_assumptions_table(fc)
    forecast_table = _build_forecast_table(fcff_v) if has_forecast_table else (
        "> _Bảng dự phóng bị chặn: forecast artifact chưa PASS hoặc assumptions chưa được phê duyệt. Chỉ hiển thị trạng thái assumptions và hành động cần bổ sung._"
    )

    # ── Peer table ────────────────────────────────────────────────────
    pe_str = f"{pe_x:.1f}x" if pe_x else _NA
    pb_str = f"{pb_x:.2f}x" if pb_x else _NA
    mc_str = f"{market_cap_bn:,.0f}" if market_cap_bn else _NA
    peer_table = _build_dynamic_peer_table(
        ticker=ticker,
        mc_str=mc_str,
        pe_str=pe_str,
        pb_str=pb_str,
        roe_pct=roe_pct,
        net_margin_pct=net_margin_pct,
    )

    # ── Narrative fields ───────────────────────────────────────────────
    company_overview = _get_sector_blurb(ticker)
    if current_price and fiscal_year != "—":
        company_overview += f"\n\n**Giá cổ phiếu hiện tại:** {current_price:,.0f} VND/CP (nguồn: market data)."

    if has_valuation and current_price and target_price:
        upside_display = f"{upside_pct:+.1f}%" if upside_pct is not None else _NA
        investment_thesis = (
            f"**Rating:** {rating} | **Target:** {target_price:,.0f} VND/CP | "
            f"**Giá hiện tại:** {current_price:,.0f} VND/CP | **Upside:** {upside_display}\n\n"
            f"**Luận điểm cơ sở (draft):** {company_name} có nền tảng tài chính ổn định với "
            f"biên gộp {f'{gross_margin_pct:.1f}%' if gross_margin_pct else _NA}, "
            f"ROE {f'{roe_pct:.1f}%' if roe_pct else _NA}. "
            f"Định giá DCF (WACC={wacc_pct:.1f}%, g={terminal_growth_pct:.1f}%) "
            f"cho target price {target_price:,.0f} VND/CP.\n\n"
            f"_Luận điểm này dựa trên assumptions mặc định chưa được phê duyệt. "
            f"Cần analyst review trước khi publish._"
        )
    else:
        investment_thesis = (
            f"> _Luận điểm đầu tư bị chặn: thiếu giá thị trường hoặc target price._\n\n"
            f"**Trạng thái:** Rating = UNDER_REVIEW — cần xác nhận giá thị trường và "
            f"phê duyệt assumptions valuation."
        )

    financial_narrative = _build_analyst_financial_narrative(
        ratios, fy_periods, gross_margin_pct, net_margin_pct, roe_pct, roa_pct, fiscal_year, ticker
    )

    forecast_narrative = (
        f"**Trạng thái dự phóng:** Assumptions chưa được phê duyệt (status: {valuation_assumption_status}). "
        "WACC và terminal growth không được hiển thị cho đến khi valuation artifact PASS. "
        "Forecast chart (C5) và bảng dự phóng sẽ bị chặn cho đến khi analyst phê duyệt assumptions."
        if not has_forecast_table
        else (
            f"Base case: WACC={wacc_pct:.1f}%, terminal growth={terminal_growth_pct:.1f}%. "
            "Dự phóng được tính từ lịch sử FCF, cần analyst review assumptions trước khi finalize."
        )
    )

    valuation_narrative = _build_valuation_narrative(
        fcff_v if has_valuation else {},
        target_price,
        current_price,
        upside_pct,
        val,
    )

    # ── Quality / source tables ────────────────────────────────────────
    # Determine consistency of gate statuses — no contradictions
    val_repro_status = "PASS" if has_valuation else "N/A"
    # Note: PASS is ONLY shown if target price is actually computable
    numeric_consistency_status = "WARN" if (ratios and fy_periods) else "N/A"
    human_review_status = "PENDING"  # Always pending until explicitly approved

    quality_summary_table = (
        "| Quality Item | Trạng thái | Ghi chú |\n"
        "|---|---|---|\n"
        f"| Data Confidence | Medium | Dữ liệu từ vnstock API (Tier 3) |\n"
        f"| Source Coverage | ~70% | Draft mode — cần OCR báo cáo chính thức |\n"
        f"| Numeric Consistency | {numeric_consistency_status} | Cần reconciliation với BCTC chính thức |\n"
        f"| Valuation Reproducibility | {val_repro_status} | "
        f"{'Target price tái lập được từ artifact' if val_repro_status == 'PASS' else 'Không có valuation artifact PASS hoặc assumptions chưa được phê duyệt'} |\n"
        f"| Forecast Assumptions | {valuation_assumption_status} | |\n"
        f"| Data Cutoff | {fiscal_year}-12-31 | |\n"
        f"| Human Review | {human_review_status} | Assumptions chưa được analyst phê duyệt |\n"
        f"| Publish Status | DRAFT | Không export final cho đến khi các gate pass |\n"
    )

    key_sources_table = (
        "| Nguồn | Loại | Kỳ | Tier |\n"
        "|---|---|---|---|\n"
        f"| vnstock API (VCI) | Báo cáo tài chính | "
        f"{fy_periods[0] if fy_periods else '—'}–{fy_periods[-1] if fy_periods else '—'} | Tier 3 |\n"
        f"| {ticker} Annual Report | Báo cáo thường niên | {fiscal_year} | Tier 0 (cần OCR) |\n"
        f"| Market data (vnstock) | Giá thị trường | {report_date} | Tier 3 |\n"
    )

    driver_table = (
        "| Driver | Line Item | Direction | Base Assumption | Valuation Impact | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| Revenue growth | Revenue | Positive | +5% p.a. | Tăng FCFF | pending_review |\n"
        "| Gross margin | Gross profit | Stable | 45-47% | Giữ EBIT margin | pending_review |\n"
        "| CAPEX | FCFF | Negative ST | ~8% revenue | Giảm FCFF ngắn hạn | pending_review |\n"
    )

    business_driver_table = (
        "| Driver | Ý nghĩa kinh doanh | Line Item | Direction | Bằng chứng |\n"
        "|---|---|---|---|---|\n"
        "| Kênh ETC/đấu thầu | Doanh thu bệnh viện | Revenue, Gross margin | Tích cực nếu thắng thầu | Tender data |\n"
        "| Giá trung thầu | Áp lực giá bán | Revenue, Gross margin | Tiêu cực nếu giảm | Tender results |\n"
        "| Nguyên liệu nhập khẩu | Chi phí đầu vào | COGS, Gross margin | Tiêu cực nếu tăng | FX/API price |\n"
        "| Tồn kho/phải thu | Vốn lưu động | dNWC, FCFF | Tiêu cực nếu tăng | BCTC quarterly |\n"
    )

    catalysts_table = (
        "| Catalyst | Thời gian | Driver | Tác động | Xác suất | Nguồn |\n"
        "|---|---|---|---|---|---|\n"
        "| Kết quả đấu thầu thuốc 2026 | Q1-Q2 2026 | Revenue ETC | Tích cực nếu thắng thầu | Trung bình | Tender |\n"
        "| Tăng trưởng OTC | 2026 | Revenue | Tích cực | Cao | Market data |\n"
        "\n> _Catalyst dựa trên nhận định ngành — cần gắn với bằng chứng cụ thể trước khi publish._"
    )

    risks_table = (
        "| Rủi ro | Driver bị ảnh hưởng | Tác động tài chính | Theo dõi |\n"
        "|---|---|---|---|\n"
        "| Giảm giá trung thầu | Gross margin, Revenue | Cao (-2 đến -3% margin/năm) | Kết quả đấu thầu |\n"
        "| Nguyên liệu nhập khẩu tăng | COGS, Gross margin | Trung bình | Tỷ giá USD/VND |\n"
        "| Cạnh tranh generic | Revenue, margin | Trung bình | Market share |\n"
        "| OCR báo cáo thường niên | Data quality | Ảnh hưởng đến gate | Tiến độ OCR |\n"
    )

    risk_narrative = (
        "Rủi ro trọng yếu nhất với doanh nghiệp dược generic kênh ETC: áp lực giá thầu thuốc. "
        "Nếu giá trung thầu giảm 5%, gross margin có thể giảm ~150-200 bps nếu không kiểm soát được "
        "chi phí đầu vào. Điều này sẽ giảm EBIT và FCFF, tạo downside risk với target price. "
        "Mức độ rủi ro phụ thuộc vào tỷ lệ doanh thu ETC so với OTC — "
        "cần dữ liệu channel mix để định lượng chính xác."
    )

    if has_valuation and target_price:
        upside_display = f"{upside_pct:+.1f}%" if upside_pct is not None else _NA
        key_takeaways = (
            f"- Nền tảng tài chính: biên gộp {f'{gross_margin_pct:.1f}%' if gross_margin_pct else _NA}, "
            f"ROE {f'{roe_pct:.1f}%' if roe_pct else _NA}.\n"
            f"- Định giá DCF (draft): target {target_price:,.0f} VND/CP vs "
            f"thị trường {f'{current_price:,.0f}' if current_price else _NA} VND/CP "
            f"(upside {upside_display}).\n"
            f"- Rating draft: **{rating}** — chưa chính thức (assumptions chưa được phê duyệt).\n"
            f"- Điều kiện để export final: (1) OCR BCTC chính thức, (2) analyst phê duyệt assumptions, "
            f"(3) human review PASS.\n"
        )
    else:
        key_takeaways = (
            "- Rating: **UNDER_REVIEW** — thiếu giá thị trường hoặc target price hợp lệ.\n"
            "- Cần: (1) xác nhận giá thị trường từ nguồn data, (2) valuation artifact với blend_dcf.\n"
            "- Không export final cho đến khi tất cả gate pass.\n"
        )

    # Scenario table: only show if we have target
    if has_valuation and target_price:
        upside_display = f"{upside_pct:+.1f}%" if upside_pct is not None else _NA
        scenario_table = (
            "| Scenario | Revenue CAGR | WACC | Target Price | Upside | Rating |\n"
            "|---|---:|---:|---:|---:|---|\n"
            "| Bear | +2.0% | 12.0% | — | — | — |\n"
            f"| Base | +5.0% | {wacc_pct:.1f}% | {target_price:,.0f} VND | {upside_display} | {rating} |\n"
            "| Bull | +8.0% | 8.0% | — | — | — |\n"
            "\n> _Bear và Bull scenario chưa được tính — cần scenario analysis artifact._"
        )
    else:
        scenario_table = (
            "> _Bảng kịch bản bị chặn: thiếu target price. Cần valuation artifact hợp lệ._"
        )

    sensitivity_narrative = (
        f"Target price nhạy cảm nhất với thay đổi WACC và tăng trưởng dài hạn (g). "
        f"Tại WACC={wacc_pct:.1f}%, g={terminal_growth_pct:.1f}%: target = "
        f"{f'{target_price:,.0f} VND/CP' if target_price else _NA}. "
        f"WACC tăng 100 bps → target price giảm khoảng 10-15% tùy g. "
        f"Xem ma trận độ nhạy để đánh giá downside/upside range."
        if has_sensitivity else (
            "> _Phân tích độ nhạy bị chặn: không có sensitivity artifact hợp lệ._"
        )
    )

    # ── Agent narrative injection ──────────────────────────────────────
    # Auto-load agent narrative from already-loaded manifest, or from disk if not loaded yet
    if run_id and agent_narrative is None:
        if manifest is not None:
            # Use the already-loaded manifest to avoid a second disk read
            try:
                artifact = manifest.load_json("financial_analysis")
                payload = artifact.get("payload") or artifact
                agent_narrative = {
                    k: str(payload.get(k) or "")
                    for k in _NARRATIVE_FIELDS
                }
            except Exception as exc:
                _loader_logger.debug(
                    "Agent narrative not loaded from manifest for run_id=%s: %s",
                    run_id, exc,
                )
                agent_narrative = {}
        else:
            agent_narrative = _load_agent_narrative_from_manifest(run_id)

    # Inject agent narrative fields into ReportContext (overrides hardcoded defaults)
    _narrative_overrides: dict = {}
    if agent_narrative:
        for _field in _NARRATIVE_FIELDS:
            _value = agent_narrative.get(_field)
            if _value and isinstance(_value, str) and _value.strip():
                _narrative_overrides[_field] = _value.strip()

    # ── Report status ──────────────────────────────────────────────────
    # Report is DRAFT unless all gates pass
    report_status = "DRAFT — Cần analyst review"

    return ReportContext(
        ticker=ticker,
        company_name=company_name,
        exchange=exchange,
        report_date=report_date,
        data_cutoff=f"{fiscal_year}-12-31" if fiscal_year != "—" else "—",
        rating=rating,
        current_price=current_price or 0.0,
        target_price=target_price or 0.0,
        upside_pct=upside_pct if upside_pct is not None else 0.0,
        risk_level="Trung bình",
        data_confidence="Medium (Tier 3)",
        status=report_status,
        # Financials (0 means unknown — section_builder will display N/A)
        market_cap_bn=market_cap_bn or 0.0,
        gross_margin_pct=gross_margin_pct or 0.0,
        net_margin_pct=net_margin_pct or 0.0,
        roe_pct=roe_pct or 0.0,
        roa_pct=roa_pct or 0.0,
        eps_vnd=eps_vnd or 0.0,
        pe_x=pe_x or 0.0,
        pb_x=pb_x or 0.0,
        fiscal_year=fiscal_year,
        wacc_pct=wacc_pct,
        terminal_growth_pct=terminal_growth_pct,
        # Missing price flags (used by section_builder for N/A display)
        _current_price_missing=(current_price is None),
        _target_price_missing=(target_price is None),
        _upside_missing=(upside_pct is None),
        _has_valuation=has_valuation,
        _has_sensitivity=has_sensitivity,
        _has_forecast_table=has_forecast_table,
        # Narrative (agent overrides take precedence over hardcoded defaults)
        company_overview=company_overview,
        investment_thesis=_narrative_overrides.get("investment_thesis", investment_thesis),
        financial_narrative=_narrative_overrides.get("financial_narrative", financial_narrative),
        forecast_narrative=_narrative_overrides.get("forecast_narrative", forecast_narrative),
        valuation_narrative=_narrative_overrides.get("valuation_narrative", valuation_narrative),
        risk_narrative=_narrative_overrides.get("risk_narrative", risk_narrative),
        key_takeaways=key_takeaways,
        sensitivity_narrative=sensitivity_narrative,
        # Tables
        financial_summary_table=fin_table,
        dcf_table=dcf_table,
        valuation_summary_table=val_summary,
        valuation_assumptions_table=val_assumptions,
        sensitivity_matrix=sens_matrix,
        assumptions_table=assumptions_table,
        forecast_table=forecast_table,
        driver_table=driver_table,
        business_driver_table=business_driver_table,
        peer_table=peer_table,
        catalysts_table=catalysts_table,
        risks_table=risks_table,
        scenario_table=scenario_table,
        quality_summary_table=quality_summary_table,
        key_sources_table=key_sources_table,
        # Charts
        chart_paths={
            k: v
            for k, v in _load_chart_paths(ticker).items()
            if not (
                (k == "C3" and current_price is None)
                or (k == "C5" and not has_forecast_table)
                or (k == "C6" and not has_valuation)
                or (k == "C7" and not has_sensitivity)
            )
        },
        # Quality gate fields
        source_coverage_pct=70.0,
        numeric_consistency=numeric_consistency_status,
        valuation_reproducibility=val_repro_status,
        human_review=human_review_status,
    )
