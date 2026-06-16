"""LLM-based qualitative-evidence extraction from annual-report PDF page text.

The linear pipeline collects financial *facts* (vnstock + PDF) but no qualitative
company evidence — so build_company_research_pack produces an empty pack and the
REPORT_QUALITY / PACKAGE / SENIOR_CRITIC gates fail. This module reads the annual
report PDF (the authoritative source the user already collected) and extracts a
structured evidence pack: business segments, market share, catalysts, risks, and
the company's disclosed borrowing/investment plans (used for debt forecasting).

Design mirrors llm_fact_extractor: a pure parse_evidence() does all normalization
(fully unit-testable, no LLM), and extract_evidence_from_pdf() wraps page
selection + one LLM call + parse_evidence. Output matches the shape consumed by
backend.documents.company_research_pack.build_company_research_pack: each business
topic is a {name: record} mapping; catalysts/risks are lists; every record carries
{value, as_of, status, confidence, evidence_refs:[page], source_class}.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional, Sequence

MODEL = "gpt-5-mini"  # MAIN_MODEL — keep in sync with harness.model_adapter.PRODUCTION_MODELS

# Business topics build_company_research_pack reads as {name: record} mappings.
BUSINESS_TOPICS: tuple[str, ...] = (
    "company_profile",
    "business_segments",
    "revenue_by_channel",
    "revenue_by_product_group",
    "market_share",
    "peer_positioning",
    "capacity_and_factory_status",
    "regulatory_and_gmp_status",
    "api_exposure",
    "distribution_network",
    "major_shareholders",
    "dividend_policy",
    "capex_projects",
    "fx_exposure",
)


def _clamp_conf(raw: Any, default: float = 0.7) -> float:
    try:
        c = float(raw)
    except (TypeError, ValueError):
        return default
    if c != c:  # NaN
        return default
    return max(0.0, min(1.0, c))


def _page_refs(item: dict) -> list[str]:
    page = item.get("page")
    try:
        n = int(page)
    except (TypeError, ValueError):
        return []
    return [f"page {n}"] if n > 0 else []


def _evidence_record(item: dict, fiscal_year: int, *, source_class: str = "company") -> dict[str, Any]:
    """Normalize one LLM item into a company_research_pack record.

    A record with a page reference is 'observed'; without one it is
    'insufficient_evidence' (and stays uncovered by _topic_covered).
    """
    refs = _page_refs(item)
    return {
        "value": item.get("value"),
        "as_of": str(item.get("as_of") or fiscal_year),
        "status": "observed" if refs else "insufficient_evidence",
        "confidence": _clamp_conf(item.get("confidence")),
        "evidence_refs": refs,
        "source_class": source_class,
    }


def _records_from_items(items: Any, fiscal_year: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        return out
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"item_{i+1}").strip() or f"item_{i+1}"
        out[name] = _evidence_record(item, fiscal_year)
    return out


def _list_records(items: Any, fiscal_year: int, *, source_class: str = "company") -> list[dict[str, Any]]:
    """Build a list of records (catalysts/risks). Each carries an 'observation' so
    build_analyst_insights can read it, plus evidence_refs for topic coverage."""
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        rec = _evidence_record(item, fiscal_year, source_class=source_class)
        if item.get("name"):
            rec["title"] = str(item["name"]).strip()
        rec["observation"] = item.get("value")
        out.append(rec)
    return out


def _int(raw: Any) -> Optional[int]:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _float(raw: Any) -> Optional[float]:
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _plan_rows(items: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append({
            "year": _int(item.get("year")),
            "amount": _float(item.get("amount")),
            "description": str(item.get("description") or "").strip(),
            "page": _int(item.get("page")),
        })
    return rows


def parse_evidence(raw: dict[str, Any], ticker: str, fiscal_year: int) -> dict[str, Any]:
    """Normalize the LLM evidence JSON into the company_research_pack evidence_pack shape."""
    raw = raw if isinstance(raw, dict) else {}
    business_topics = raw.get("business_topics") if isinstance(raw.get("business_topics"), dict) else {}

    business_evidence: dict[str, Any] = {}
    for topic in BUSINESS_TOPICS:
        records = _records_from_items(business_topics.get(topic), fiscal_year)
        if records:
            business_evidence[topic] = records

    # risks are consumed as a list (build_company_research_pack._first_list).
    risks = _list_records(raw.get("risks"), fiscal_year)
    if risks:
        business_evidence["risks"] = risks

    pharma_catalyst_evidence: dict[str, Any] = {}
    catalysts = _list_records(raw.get("catalysts"), fiscal_year)
    if catalysts:
        pharma_catalyst_evidence["catalysts"] = catalysts
    events = _list_records(raw.get("events"), fiscal_year)
    if events:
        pharma_catalyst_evidence["events"] = events
    for topic in ("regulatory_and_gmp_status", "api_exposure", "fx_exposure"):
        recs = _records_from_items((raw.get("business_topics") or {}).get(topic), fiscal_year)
        if recs:
            pharma_catalyst_evidence[topic] = recs

    company_plans: dict[str, Any] = {}
    for plan_key in ("borrowing_plan", "investment_plan"):
        rows = _plan_rows(raw.get(plan_key))
        if rows:
            company_plans[plan_key] = rows

    return {
        "ticker": ticker.upper(),
        "fiscal_year": fiscal_year,
        "business_evidence": business_evidence,
        "pharma_catalyst_evidence": pharma_catalyst_evidence,
        "company_plans": company_plans,
        "source_map": {},
    }


# ---------------------------------------------------------------------------
# Page selection + prompts + LLM wrapper
# ---------------------------------------------------------------------------

# Narrative/plan keywords (diacritic-stripped) marking pages worth sending to the
# LLM. Qualitative evidence + company plans live in the management discussion /
# ĐHCĐ resolution pages, NOT the audited financial statements.
_EVIDENCE_KEYWORDS: tuple[str, ...] = (
    "tong quan", "mo hinh kinh doanh", "linh vuc kinh doanh", "san pham",
    "co cau doanh thu", "thi phan", "kenh phan phoi", "phan phoi",
    "nha may", "cong suat", "gmp", "eu-gmp", "nguyen lieu", "api",
    "ke hoach", "dinh huong", "chien luoc", "dau tu", "vay von", "vay",
    "co dong", "co tuc", "rui ro", "trien vong", "nghi quyet", "dai hoi dong co dong",
)


def _slug(text: str) -> str:
    norm = unicodedata.normalize("NFD", text)
    out = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return out.replace("đ", "d").replace("Đ", "D").lower()


def select_evidence_pages(
    pages: Sequence[tuple[int, str]], *, max_pages: int = 30
) -> list[tuple[int, str]]:
    """Pick narrative/plan pages by keyword; fall back to the first max_pages.

    Vietnamese annual reports front-load the narrative (business model, segments,
    plans, risks) before the audited statements, so the first pages are a safe
    fallback when no keyword is detected (poor OCR)."""
    if not pages:
        return []
    ordered = sorted(pages, key=lambda p: p[0])
    hits = [(n, t) for n, t in ordered if any(kw in _slug(t[:2000]) for kw in _EVIDENCE_KEYWORDS)]
    selected = hits or ordered
    return selected[:max_pages]


def build_evidence_system_prompt() -> str:
    return "\n".join([
        "Bạn là chuyên viên phân tích cổ phiếu đọc báo cáo thường niên (đã kiểm toán) của MỘT công ty Việt Nam.",
        "Nhiệm vụ: trích bằng chứng ĐỊNH TÍNH về doanh nghiệp và KẾ HOẠCH công ty, kèm số trang.",
        "",
        "QUY TẮC:",
        "1. Chỉ dùng thông tin CÓ trong văn bản; KHÔNG bịa. Mỗi mục kèm page (số trang) làm bằng chứng.",
        "2. business_topics: gom theo chủ đề. Các chủ đề hợp lệ: " + ", ".join(BUSINESS_TOPICS) + ".",
        "   Mỗi mục: {name, value (mô tả ngắn tiếng Việt), page, confidence∈[0,1]}.",
        "3. catalysts/risks: danh sách {name, value, page} — động lực tăng trưởng / rủi ro chính.",
        "4. borrowing_plan/investment_plan: kế hoạch vay vốn / đầu tư công bố (nghị quyết ĐHCĐ, ban lãnh đạo).",
        "   Mỗi mục: {year, amount (tỷ VND, 0 nếu không vay mới), description, page}.",
        "",
        'Trả về JSON object: {"business_topics": {"<topic>": [..]}, "catalysts": [..], "risks": [..], '
        '"borrowing_plan": [..], "investment_plan": [..]}. Nếu không có, trả {}.',
    ])


def build_evidence_user_prompt(
    ticker: str, fiscal_year: int, pages: Sequence[tuple[int, str]]
) -> str:
    header = (
        f"Công ty: {ticker}. Năm báo cáo: {fiscal_year}.\n"
        f"Văn bản các trang báo cáo thường niên:\n"
    )
    body = [f"\n===== TRANG {n} =====\n{text}" for n, text in pages]
    return header + "".join(body)


def extract_evidence_from_pdf(
    pages: Sequence[tuple[int, str]],
    ticker: str,
    fiscal_year: int,
    *,
    client: Any = None,
    model: str = MODEL,
    timeout: int = 180,
    max_pages: int = 30,
) -> dict[str, Any]:
    """Select narrative pages → one LLM call → parse into an evidence pack.

    Returns an empty (but well-formed) pack when there are no pages."""
    selected = select_evidence_pages(pages, max_pages=max_pages)
    if not selected:
        return parse_evidence({}, ticker, fiscal_year)
    from backend.documents.llm_fact_extractor import _complete_json, _resolve_client

    client = _resolve_client(client, model, timeout)
    raw = _complete_json(
        client,
        build_evidence_system_prompt(),
        build_evidence_user_prompt(ticker, fiscal_year, selected),
        model,
    )
    return parse_evidence(raw, ticker, fiscal_year)
