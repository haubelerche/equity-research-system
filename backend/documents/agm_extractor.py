"""LLM extraction of forward-looking internal drivers from AGM (ĐHCĐ) packets.

The 2026 annual-general-meeting documents bundle the nghị quyết (resolution — only the
*list* of what shareholders approved), the báo cáo HĐQT / ban giám đốc, the báo cáo
KQKD 2025 + kế hoạch/mục tiêu 2026, and the tờ trình (detailed proposals backing each
resolution item). The operator's insight: the resolution only approves — the value is in
digging into the backing detail. So parse_agm produces a *two-layer* pack:

  • approved_resolutions  — what was approved (item_no, title, summary, page)
  • forward drivers        — the detail dug out of the tờ trình/báo cáo, each tying back
    to its approved item via linked_resolution: targets_2026, dividend/borrowing/
    investment plans, R&D + product focus, management direction.

These feed forecasting as priority drivers (with source/page provenance — never a fake
analyst-approved flag). Design mirrors llm_evidence_extractor: a pure parse_agm() does
all normalization (unit-testable, no LLM); extract_agm_from_pdf() wraps page selection +
one LLM call + parse_agm.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional, Sequence

MODEL = "gpt-5-mini"  # MAIN_MODEL — keep in sync with harness.model_adapter.PRODUCTION_MODELS


def _clamp_conf(raw: Any, default: float = 0.7) -> float:
    try:
        c = float(raw)
    except (TypeError, ValueError):
        return default
    if c != c:  # NaN
        return default
    return max(0.0, min(1.0, c))


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


def _page(item: dict) -> Optional[int]:
    n = _int(item.get("page"))
    return n if (n is not None and n > 0) else None


def _status(page: Optional[int]) -> str:
    return "observed" if page else "insufficient_evidence"


def _resolution_rows(items: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return rows
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        page = _page(item)
        rows.append({
            "item_no": str(item.get("item_no") or i + 1).strip(),
            "title": str(item.get("title") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
            "page": page,
            "status": _status(page),
        })
    return rows


def _plan_rows(items: Any) -> list[dict[str, Any]]:
    """Borrowing/investment plan rows: {year, amount, description, page, linked_resolution}.

    Shape compatible with forecasting's pdf_debt_plan consumption."""
    rows: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        page = _page(item)
        rows.append({
            "year": _int(item.get("year")),
            "amount": _float(item.get("amount")),
            "description": str(item.get("description") or "").strip(),
            "page": page,
            "linked_resolution": (str(item["linked_resolution"]).strip()
                                  if item.get("linked_resolution") is not None else None),
            "status": _status(page),
        })
    return rows


def _dividend_rows(items: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        page = _page(item)
        rows.append({
            "year": _int(item.get("year")),
            "cash_per_share": _float(item.get("cash_per_share")),
            "payout_pct": _float(item.get("payout_pct")),
            "page": page,
            "status": _status(page),
        })
    return rows


def _named_rows(items: Any) -> list[dict[str, Any]]:
    """R&D / product-focus and business-direction rows: {name, description|value, page}."""
    rows: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        page = _page(item)
        rows.append({
            "name": str(item.get("name") or "").strip(),
            "value": (str(item["value"]).strip() if item.get("value") is not None else None),
            "description": str(item.get("description") or "").strip(),
            "page": page,
            "linked_resolution": (str(item["linked_resolution"]).strip()
                                  if item.get("linked_resolution") is not None else None),
            "status": _status(page),
        })
    return rows


def _targets(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    page = _page(raw)
    out = {
        "revenue": _float(raw.get("revenue")),
        "npat": _float(raw.get("npat")),
        "revenue_growth_pct": _float(raw.get("revenue_growth_pct")),
        "page": page,
        "status": _status(page),
    }
    # An all-empty targets block is reported as absent ({}).
    if out["revenue"] is None and out["npat"] is None and out["revenue_growth_pct"] is None:
        return {}
    return out


def parse_agm(raw: dict[str, Any], ticker: str, meeting_year: int) -> dict[str, Any]:
    """Normalize the LLM AGM JSON into the agm_pack shape."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "ticker": ticker.upper(),
        "meeting_year": int(meeting_year),
        "approved_resolutions": _resolution_rows(raw.get("approved_resolutions")),
        "targets_2026": _targets(raw.get("targets_2026")),
        "dividend_plan": _dividend_rows(raw.get("dividend_plan")),
        "borrowing_plan": _plan_rows(raw.get("borrowing_plan")),
        "investment_plan": _plan_rows(raw.get("investment_plan")),
        "rnd_and_product_focus": _named_rows(raw.get("rnd_and_product_focus")),
        "business_direction": _named_rows(raw.get("business_direction")),
    }


# ---------------------------------------------------------------------------
# Page selection + prompts + LLM wrapper
# ---------------------------------------------------------------------------

# Keywords (diacritic-stripped) marking AGM pages worth sending to the LLM: the
# resolution, the board/management reports, the 2026 plan, and the backing proposals.
_AGM_KEYWORDS: tuple[str, ...] = (
    "nghi quyet", "dai hoi dong co dong", "dai hoi co dong", "to trinh",
    "bao cao hoi dong quan tri", "bao cao ban giam doc", "bao cao ban dieu hanh",
    "ket qua kinh doanh", "ke hoach kinh doanh", "ke hoach san xuat", "muc tieu",
    "phuong an phan phoi loi nhuan", "co tuc", "ke hoach dau tu", "vay von", "vay",
    "dinh huong", "chien luoc", "dau tu", "xay dung", "nghien cuu", "san pham",
)


def _slug(text: str) -> str:
    norm = unicodedata.normalize("NFD", text)
    out = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return out.replace("đ", "d").replace("Đ", "D").lower()


def select_agm_pages(
    pages: Sequence[tuple[int, str]], *, max_pages: int = 40
) -> list[tuple[int, str]]:
    """Pick resolution/plan pages by keyword; fall back to all pages (capped)."""
    if not pages:
        return []
    ordered = sorted(pages, key=lambda p: p[0])
    hits = [(n, t) for n, t in ordered if any(kw in _slug(t[:2500]) for kw in _AGM_KEYWORDS)]
    selected = hits or ordered
    return selected[:max_pages]


def build_agm_system_prompt() -> str:
    return "\n".join([
        "Bạn là chuyên viên phân tích đọc tài liệu ĐẠI HỘI ĐỒNG CỔ ĐÔNG (ĐHCĐ) của MỘT công ty dược Việt Nam.",
        "Tài liệu gồm: nghị quyết (chỉ LIỆT KÊ các nội dung được THÔNG QUA), báo cáo HĐQT/ban giám đốc,",
        "báo cáo kết quả kinh doanh năm trước, và các TỜ TRÌNH chi tiết cho từng nội dung.",
        "LƯU Ý NGÔN NGỮ: tài liệu có thể trộn tiếng Việt và tiếng Anh (English) — ví dụ phần nghị quyết bằng",
        "tiếng Anh nhưng báo cáo ban giám đốc / kế hoạch kinh doanh bằng tiếng Việt. Đọc CẢ HAI ngôn ngữ.",
        "",
        "Nhiệm vụ: (1) liệt kê các nội dung ĐÃ ĐƯỢC THÔNG QUA; (2) ĐÀO chi tiết trong tờ trình/báo cáo để",
        "trích các DRIVER hướng tới tương lai cho dự báo (mục tiêu kinh doanh, cổ tức, vay vốn, đầu tư/xây dựng,",
        "nghiên cứu & mặt hàng tập trung, định hướng ban lãnh đạo). Mỗi mục PHẢI kèm page (số trang).",
        "",
        "QUAN TRỌNG NHẤT — SỐ LIỆU KẾ HOẠCH (đừng bỏ sót, đây là phần giá trị nhất):",
        "• Tìm BẢNG 'KẾ HOẠCH KINH DOANH/SẢN XUẤT KINH DOANH NĂM 2026' (hoặc 'business plan 2026', mục",
        "  'KẾ HOẠCH KINH DOANH'). Trích chỉ tiêu KẾ HOẠCH 2026: Doanh thu thuần (revenue), Lợi nhuận sau thuế",
        "  (npat/LNST), và nếu có % tăng trưởng so với 2025 (revenue_growth_pct). Số đơn vị tỷ VND.",
        "• Nếu chỉ có doanh thu/LNST kế hoạch 2026 mà KHÔNG có % tăng, vẫn điền revenue/npat; có thể bỏ trống growth.",
        "• Cổ tức: tìm 'tỷ lệ cổ tức', 'phương án phân phối lợi nhuận' — điền payout_pct (%) hoặc cash_per_share (VND/cp).",
        "• Vay/đầu tư: tìm 'kế hoạch vay vốn', 'đầu tư', 'xây dựng nhà máy', 'capex' — điền amount (tỷ VND).",
        "  Nếu nghị quyết ghi rõ KHÔNG vay mới / không có kế hoạch vay, điền một dòng amount=0.",
        "",
        "QUY TẮC:",
        "1. Chỉ dùng thông tin CÓ trong văn bản; KHÔNG bịa. linked_resolution = item_no của nội dung đã thông qua liên quan (nếu có).",
        "2. approved_resolutions: [{item_no, title, summary, page}].",
        "3. targets_2026: {revenue (tỷ VND), npat (LNST tỷ VND), revenue_growth_pct (%), page}. PHẢI điền nếu tài liệu có bảng kế hoạch 2026.",
        "4. dividend_plan: [{year, cash_per_share (VND/cp), payout_pct (%), page}].",
        "5. borrowing_plan/investment_plan: [{year, amount (tỷ VND, 0 nếu không vay mới), description, page, linked_resolution}].",
        "6. rnd_and_product_focus: [{name, description, page}]; business_direction: [{name, value, page}].",
        "",
        'Trả về JSON object với đúng các khóa trên. Nếu không có dữ liệu cho khóa nào, trả [] hoặc {}.',
    ])


def build_agm_user_prompt(
    ticker: str, meeting_year: int, pages: Sequence[tuple[int, str]]
) -> str:
    header = (
        f"Công ty: {ticker}. Đại hội năm: {meeting_year}.\n"
        f"Văn bản các trang tài liệu ĐHCĐ:\n"
    )
    body = [f"\n===== TRANG {n} =====\n{text}" for n, text in pages]
    return header + "".join(body)


def extract_agm_from_pdf(
    pages: Sequence[tuple[int, str]],
    ticker: str,
    meeting_year: int,
    *,
    client: Any = None,
    model: str = MODEL,
    timeout: int = 180,
    max_pages: int = 40,
) -> dict[str, Any]:
    """Select AGM pages → one LLM call → parse into an agm_pack.

    Returns a well-formed empty pack when there are no pages."""
    selected = select_agm_pages(pages, max_pages=max_pages)
    if not selected:
        return parse_agm({}, ticker, meeting_year)
    from backend.documents.llm_fact_extractor import _complete_json, _resolve_client

    client = _resolve_client(client, model, timeout)
    raw = _complete_json(
        client,
        build_agm_system_prompt(),
        build_agm_user_prompt(ticker, meeting_year, selected),
        model,
    )
    return parse_agm(raw, ticker, meeting_year)
