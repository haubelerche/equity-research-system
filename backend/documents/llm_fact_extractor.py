"""LLM-based financial fact extraction from PDF/OCR page text.

The heuristic line-pairing extractor (pdf_extractor / extract_facts_from_ocr)
mis-pairs labels and values on columnar scanned Vietnamese BCTC, producing
nonsense (years parsed as charter capital, prior-year columns mislabeled, wrong
unit scale). This module instead feeds the page text to a production LLM that
reads the statement in context and returns structured facts mapped to the
canonical ``ref.line_items`` vocabulary, with page provenance.

Design:
  - The PDF the user collected IS the authoritative source (Tier 0). We do not
    reconcile against CafeF/vnstock — the LLM extracts directly and we trust the
    audited statement, after deterministic sanity validation.
  - Output ``metric`` values are restricted to the 44 canonical line_item_code
    values so they can be written straight into ``fact.canonical_facts``.
  - Values are normalised to tỷ VND (vnd_bn) for the report year only; prior-year
    comparison columns and Mã-số template codes are dropped.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

# Static fallback of the canonical ref.line_items vocabulary (44 codes) so the
# extractor and its tests run without a DB connection. load_metric_catalog()
# prefers the live ref.line_items table when reachable.
_FALLBACK_CATALOG: list[dict[str, str]] = [
    {"line_item_code": "revenue.net", "statement_type": "income_statement", "display_name_vi": "Doanh thu thuần"},
    {"line_item_code": "cogs.total", "statement_type": "income_statement", "display_name_vi": "Giá vốn hàng bán"},
    {"line_item_code": "gross_profit.total", "statement_type": "income_statement", "display_name_vi": "Lợi nhuận gộp"},
    {"line_item_code": "financial_income.total", "statement_type": "income_statement", "display_name_vi": "Doanh thu hoạt động tài chính"},
    {"line_item_code": "financial_expense.total", "statement_type": "income_statement", "display_name_vi": "Chi phí tài chính"},
    {"line_item_code": "interest_expense.total", "statement_type": "income_statement", "display_name_vi": "Chi phí lãi vay"},
    {"line_item_code": "sga.total", "statement_type": "income_statement", "display_name_vi": "Chi phí bán hàng và quản lý doanh nghiệp"},
    {"line_item_code": "operating_profit.total", "statement_type": "income_statement", "display_name_vi": "Lợi nhuận thuần từ hoạt động kinh doanh"},
    {"line_item_code": "profit_before_tax.total", "statement_type": "income_statement", "display_name_vi": "Lợi nhuận trước thuế"},
    {"line_item_code": "tax_expense.total", "statement_type": "income_statement", "display_name_vi": "Chi phí thuế thu nhập doanh nghiệp"},
    {"line_item_code": "net_income.parent", "statement_type": "income_statement", "display_name_vi": "Lợi nhuận sau thuế của cổ đông công ty mẹ"},
    {"line_item_code": "eps.basic", "statement_type": "income_statement", "display_name_vi": "Lãi cơ bản trên cổ phiếu (EPS)"},
    {"line_item_code": "ebit.total", "statement_type": "income_statement", "display_name_vi": "Lợi nhuận trước lãi vay và thuế (EBIT)"},
    {"line_item_code": "ebitda.total", "statement_type": "income_statement", "display_name_vi": "EBITDA"},
    {"line_item_code": "depreciation.total", "statement_type": "income_statement", "display_name_vi": "Khấu hao"},
    {"line_item_code": "total_assets.ending", "statement_type": "balance_sheet", "display_name_vi": "Tổng cộng tài sản"},
    {"line_item_code": "current_assets.ending", "statement_type": "balance_sheet", "display_name_vi": "Tài sản ngắn hạn"},
    {"line_item_code": "cash_and_equivalents.ending", "statement_type": "balance_sheet", "display_name_vi": "Tiền và các khoản tương đương tiền"},
    {"line_item_code": "short_term_investments.ending", "statement_type": "balance_sheet", "display_name_vi": "Đầu tư tài chính ngắn hạn"},
    {"line_item_code": "accounts_receivable.ending", "statement_type": "balance_sheet", "display_name_vi": "Các khoản phải thu ngắn hạn"},
    {"line_item_code": "inventory.ending", "statement_type": "balance_sheet", "display_name_vi": "Hàng tồn kho"},
    {"line_item_code": "ppe.net", "statement_type": "balance_sheet", "display_name_vi": "Tài sản cố định hữu hình (giá trị còn lại)"},
    {"line_item_code": "current_liabilities.ending", "statement_type": "balance_sheet", "display_name_vi": "Nợ ngắn hạn"},
    {"line_item_code": "non_current_liabilities.ending", "statement_type": "balance_sheet", "display_name_vi": "Nợ dài hạn"},
    {"line_item_code": "total_liabilities.ending", "statement_type": "balance_sheet", "display_name_vi": "Nợ phải trả"},
    {"line_item_code": "accounts_payable.ending", "statement_type": "balance_sheet", "display_name_vi": "Phải trả người bán ngắn hạn"},
    {"line_item_code": "short_term_debt.ending", "statement_type": "balance_sheet", "display_name_vi": "Vay và nợ thuê tài chính ngắn hạn"},
    {"line_item_code": "long_term_debt.ending", "statement_type": "balance_sheet", "display_name_vi": "Vay và nợ thuê tài chính dài hạn"},
    {"line_item_code": "total_debt.ending", "statement_type": "balance_sheet", "display_name_vi": "Tổng nợ vay"},
    {"line_item_code": "equity.parent", "statement_type": "balance_sheet", "display_name_vi": "Vốn chủ sở hữu"},
    {"line_item_code": "shares_outstanding.ending", "statement_type": "balance_sheet", "display_name_vi": "Số cổ phiếu đang lưu hành"},
    {"line_item_code": "operating_cash_flow.total", "statement_type": "cash_flow", "display_name_vi": "Lưu chuyển tiền thuần từ hoạt động kinh doanh"},
    {"line_item_code": "investing_cash_flow.total", "statement_type": "cash_flow", "display_name_vi": "Lưu chuyển tiền thuần từ hoạt động đầu tư"},
    {"line_item_code": "financing_cash_flow.total", "statement_type": "cash_flow", "display_name_vi": "Lưu chuyển tiền thuần từ hoạt động tài chính"},
    {"line_item_code": "capex.total", "statement_type": "cash_flow", "display_name_vi": "Tiền chi mua sắm, xây dựng TSCĐ"},
    {"line_item_code": "proceeds_from_borrowings.total", "statement_type": "cash_flow", "display_name_vi": "Tiền thu từ đi vay"},
    {"line_item_code": "repayment_of_borrowings.total", "statement_type": "cash_flow", "display_name_vi": "Tiền trả nợ gốc vay"},
    {"line_item_code": "dividends_paid.total", "statement_type": "cash_flow", "display_name_vi": "Cổ tức, lợi nhuận đã trả cho chủ sở hữu"},
    {"line_item_code": "free_cash_flow.total", "statement_type": "cash_flow", "display_name_vi": "Dòng tiền tự do"},
    {"line_item_code": "change_in_working_capital.total", "statement_type": "cash_flow", "display_name_vi": "Thay đổi vốn lưu động"},
    {"line_item_code": "dividends_per_share.cash", "statement_type": "income_statement", "display_name_vi": "Cổ tức bằng tiền trên mỗi cổ phiếu"},
    {"line_item_code": "market_price.close", "statement_type": "income_statement", "display_name_vi": "Giá đóng cửa"},
    {"line_item_code": "shares_outstanding.weighted_avg", "statement_type": "income_statement", "display_name_vi": "Số cổ phiếu bình quân gia quyền"},
    {"line_item_code": "preferred_dividends.total", "statement_type": "income_statement", "display_name_vi": "Cổ tức cổ phiếu ưu đãi"},
]

# Statement-header keywords (diacritic-stripped, lowercase) used to pre-filter
# pages worth sending to the LLM.
_STATEMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "balance_sheet": ("bang can doi ke toan", "can doi ke toan", "tai san", "nguon von"),
    "income_statement": ("ket qua hoat dong kinh doanh", "bao cao ket qua", "doanh thu thuan", "loi nhuan"),
    "cash_flow": ("luu chuyen tien te", "luu chuyen tien thuan", "bao cao luu chuyen"),
}

# Note pages whose detail the statement face omits. Vietnamese BCTC often shows
# only an aggregate on the balance-sheet face and breaks short-/long-term
# borrowings down in the thuyết minh (note V.19) — pulling these note pages into
# the balance_sheet pass is what lifts short_term_debt / long_term_debt recall.
_NOTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "balance_sheet": (
        "vay va no thue tai chinh", "vay ngan han ngan hang", "vay dai han ngan hang",
        "vay ngan han", "vay dai han",
    ),
}

MODEL = "gpt-5-mini"  # MAIN_MODEL — keep in sync with harness.model_adapter.PRODUCTION_MODELS


@dataclass
class ExtractedFact:
    metric: str          # canonical line_item_code
    value: float         # tỷ VND (vnd_bn)
    fiscal_year: int
    statement_type: str
    page_number: int
    source_label: str
    confidence: float
    period_type: str = "FY"

    @property
    def period(self) -> str:
        return f"{self.fiscal_year}{self.period_type}"


def _strip_diacritics(text: str) -> str:
    import unicodedata

    norm = unicodedata.normalize("NFD", text)
    out = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return out.replace("đ", "d").replace("Đ", "D").lower()


def load_metric_catalog() -> list[dict[str, str]]:
    """Return canonical line-item catalog. Prefers live ref.line_items, else fallback."""
    try:
        from backend.database.canonical.connection import get_conn

        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "select line_item_code, statement_type, display_name_vi from ref.line_items order by line_item_code"
            )
            rows = [
                {"line_item_code": r[0], "statement_type": r[1], "display_name_vi": r[2] or ""}
                for r in cur.fetchall()
            ]
        if rows:
            return rows
    except Exception:  # noqa: BLE001 — offline / no DB → static vocabulary
        pass
    return list(_FALLBACK_CATALOG)


def allowed_codes(catalog: Optional[Sequence[dict[str, str]]] = None) -> set[str]:
    cat = catalog if catalog is not None else load_metric_catalog()
    return {row["line_item_code"] for row in cat}


def select_financial_pages(
    pages: Sequence[tuple[int, str]],
    *,
    context: int = 1,
    max_pages: int = 24,
    statement: Optional[str] = None,
) -> list[tuple[int, str]]:
    """Pick pages whose text contains a financial-statement header, plus neighbours.

    Keeps token cost bounded: only statement pages (+/- *context* pages) are sent
    to the LLM rather than the whole 60-100 page annual report. When *statement*
    is given, only that statement's header keywords are matched (targeted pass);
    the value pages of a statement often re-declare no header, so neighbours are
    pulled in via *context*.
    """
    if not pages:
        return []
    if statement is not None:
        keyword_groups = [_STATEMENT_KEYWORDS.get(statement, ())]
    else:
        keyword_groups = list(_STATEMENT_KEYWORDS.values())
    ordered = sorted(pages, key=lambda p: p[0])
    by_number = {n: t for n, t in ordered}
    hit_numbers: set[int] = set()
    for n, text in ordered:
        slug = _strip_diacritics(text[:1500])
        if any(kw in slug for kws in keyword_groups for kw in kws):
            for d in range(-context, context + 1):
                if (n + d) in by_number:
                    hit_numbers.add(n + d)
    if not hit_numbers:
        # No header detected (poor OCR). For a targeted pass return nothing so the
        # caller can fall back; for the broad pass send the first max_pages pages.
        return [] if statement is not None else ordered[:max_pages]
    selected = [(n, by_number[n]) for n in sorted(hit_numbers)]
    return selected[:max_pages]


def required_facts_union() -> set[str]:
    """Union of canonical facts every valuation method needs (the 'must-find' set).

    Sourced from backend.valuation.data_requirements so the extractor hunts exactly
    what the valuation preflight will check.
    """
    try:
        from backend.valuation.data_requirements import VALUATION_DATA_REQUIREMENTS

        req: set[str] = set()
        for r in VALUATION_DATA_REQUIREMENTS.values():
            req.update(r.required_facts)
        return req
    except Exception:  # noqa: BLE001 — keep extraction working without the valuation pkg
        return {
            "revenue.net", "profit_before_tax.total", "tax_expense.total",
            "depreciation.total", "capex.total", "cash_and_equivalents.ending",
            "short_term_debt.ending", "long_term_debt.ending", "shares_outstanding.ending",
            "operating_cash_flow.total", "proceeds_from_borrowings.total",
            "repayment_of_borrowings.total", "eps.basic",
        }


# Some metrics live in more than one place. depreciation appears in the indirect
# cash-flow statement; shares_outstanding & eps sit near the income-statement EPS
# line and on the cover/notes — hunt them in extra passes to lift recall.
_EXTRA_STATEMENT_HOMES: dict[str, set[str]] = {
    "cash_flow": {"depreciation.total"},
    "income_statement": {"shares_outstanding.ending"},
    "balance_sheet": {"eps.basic"},
}


def catalog_for_statement(
    statement: str, catalog: Sequence[dict[str, str]]
) -> list[dict[str, str]]:
    """Return the catalog rows belonging to *statement* (+ cross-listed extras)."""
    extra = _EXTRA_STATEMENT_HOMES.get(statement, set())
    return [r for r in catalog if r["statement_type"] == statement or r["line_item_code"] in extra]


def select_note_pages(
    pages: Sequence[tuple[int, str]], statement: str, *, max_pages: int = 6
) -> list[tuple[int, str]]:
    """Return note (thuyết minh) pages whose detail the *statement* face omits."""
    keywords = _NOTE_KEYWORDS.get(statement, ())
    if not keywords:
        return []
    out: list[tuple[int, str]] = []
    for n, text in sorted(pages, key=lambda p: p[0]):
        slug = _strip_diacritics(text[:3000])
        if any(kw in slug for kw in keywords):
            out.append((n, text))
    return out[:max_pages]


def build_system_prompt(catalog: Sequence[dict[str, str]]) -> str:
    lines = [
        "Bạn là chuyên viên trích xuất dữ liệu báo cáo tài chính (BCTC) Việt Nam.",
        "Đầu vào là văn bản OCR/text của các trang BCTC đã kiểm toán của MỘT công ty cho MỘT năm tài chính.",
        "Nhiệm vụ: trích các chỉ tiêu tài chính của ĐÚNG năm báo cáo được yêu cầu (bỏ qua cột số liệu năm trước/so sánh).",
        "",
        "QUY TẮC BẮT BUỘC:",
        "1. Chỉ trả về các metric nằm trong danh mục mã chuẩn dưới đây (metric = line_item_code). Bỏ qua mọi chỉ tiêu không khớp.",
        "2. Giá trị (value) PHẢI quy về đơn vị TỶ ĐỒNG (vnd_bn). Ví dụ '419.496.000.000 đồng' -> 419.496; '1.234 triệu đồng' -> 1.234.",
        "   EPS và cổ tức/cổ phiếu để nguyên đồng/cổ phiếu (không đổi sang tỷ). shares_outstanding để nguyên số cổ phiếu.",
        "3. KHÔNG lấy 'Mã số' (các số 100, 200, 300... trong cột mã chỉ tiêu) làm giá trị. KHÔNG lấy số năm (2022, 2023) làm giá trị.",
        "4. Chỉ lấy số từ BẢNG báo cáo tài chính, KHÔNG lấy số trong văn xuôi/thuyết minh diễn giải.",
        "5. Mỗi metric chỉ trả 1 lần (giá trị của năm báo cáo). Kèm page (số trang) và source_label (nhãn tiếng Việt gốc trong báo cáo).",
        "6. confidence trong [0,1]: mức độ chắc chắn nhãn khớp đúng metric và đọc đúng số.",
        "",
        "DANH MỤC MÃ CHUẨN (line_item_code | statement_type | nhãn tiếng Việt):",
    ]
    for row in catalog:
        lines.append(f"- {row['line_item_code']} | {row['statement_type']} | {row.get('display_name_vi','')}")
    lines += [
        "",
        'Trả về JSON object đúng dạng: {"facts": [{"metric": "...", "value": <number>, "statement_type": "...", "page": <int>, "source_label": "...", "confidence": <number>}]}',
        "Nếu không trích được gì, trả {\"facts\": []}.",
    ]
    return "\n".join(lines)


_STATEMENT_VI = {
    "balance_sheet": "BẢNG CÂN ĐỐI KẾ TOÁN",
    "income_statement": "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH",
    "cash_flow": "BÁO CÁO LƯU CHUYỂN TIỀN TỆ",
}


def build_statement_system_prompt(
    statement: str, catalog_subset: Sequence[dict[str, str]], required_codes: set[str]
) -> str:
    """Focused prompt for one statement — lists only that statement's metrics and
    explicitly names the must-find (valuation-required) ones to maximise recall."""
    must = [r["line_item_code"] for r in catalog_subset if r["line_item_code"] in required_codes]
    lines = [
        f"Bạn là chuyên viên trích xuất {_STATEMENT_VI.get(statement, statement)} từ BCTC kiểm toán Việt Nam.",
        "Đầu vào là văn bản OCR/text các trang của MỘT công ty cho MỘT năm tài chính.",
        f"Chỉ trích các chỉ tiêu thuộc {_STATEMENT_VI.get(statement, statement)} của ĐÚNG năm báo cáo được yêu cầu (bỏ cột năm trước).",
        "",
        "QUY TẮC BẮT BUỘC:",
        "1. metric = line_item_code, CHỈ trong danh mục dưới đây. Bỏ qua chỉ tiêu khác.",
        "2. value quy về TỶ ĐỒNG (vnd_bn): '419.496.000.000 đồng'->419.496; '1.234 triệu'->1.234. "
        "EPS/cổ tức trên cổ phiếu để nguyên đồng; shares_outstanding để nguyên số cổ phiếu.",
        "3. KHÔNG lấy 'Mã số' (100,200,...) hay số năm (2022,2023) làm value. Chỉ lấy số trong BẢNG, không lấy số trong văn xuôi.",
        "4. Cố gắng tìm ĐỦ các chỉ tiêu BẮT BUỘC (nếu báo cáo có): "
        + (", ".join(must) if must else "(không có)") + ".",
        "5. Mỗi metric 1 lần. Kèm page và source_label (nhãn tiếng Việt gốc). confidence trong [0,1].",
        "",
        "DANH MỤC MÃ CHUẨN (line_item_code | nhãn tiếng Việt):",
    ]
    for r in catalog_subset:
        tag = "  [BẮT BUỘC]" if r["line_item_code"] in required_codes else ""
        lines.append(f"- {r['line_item_code']} | {r.get('display_name_vi','')}{tag}")
    lines += [
        "",
        'Trả về JSON: {"facts": [{"metric": "...", "value": <number>, "statement_type": "'
        + statement + '", "page": <int>, "source_label": "...", "confidence": <number>}]}',
        'Nếu không trích được gì, trả {"facts": []}.',
    ]
    return "\n".join(lines)


def build_user_prompt(ticker: str, fiscal_year: int, pages: Sequence[tuple[int, str]]) -> str:
    header = (
        f"Công ty: {ticker}. Năm tài chính cần trích: {fiscal_year} (chỉ lấy số của năm {fiscal_year}).\n"
        f"Văn bản các trang BCTC:\n"
    )
    body = []
    for n, text in pages:
        body.append(f"\n===== TRANG {n} =====\n{text}")
    return header + "".join(body)


def parse_llm_facts(
    raw: dict[str, Any],
    ticker: str,
    fiscal_year: int,
    valid_codes: set[str],
) -> list[ExtractedFact]:
    """Validate + coerce the LLM JSON into ExtractedFact objects.

    Drops facts whose metric is not a canonical code, whose value is not finite,
    or that look like Mã-số template codes / year numbers. Dedupes by metric,
    keeping the highest-confidence reading.
    """
    items = raw.get("facts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []

    best: dict[str, ExtractedFact] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric", "")).strip()
        if metric not in valid_codes:
            continue
        value = _coerce_number(item.get("value"))
        if value is None:
            continue
        # Reject a bare year mistaken as a value (the classic OCR artifact, e.g.
        # 2008 read as charter capital). Whole-number values are otherwise kept —
        # real BCTC figures like 687 tỷ are legitimate. The LLM is instructed to
        # skip Mã-số template codes, so we trust it rather than filter 1..999.
        if value == int(value):
            iv = int(value)
            if 1990 <= iv <= fiscal_year + 1 and metric not in ("shares_outstanding.ending", "shares_outstanding.weighted_avg"):
                continue
        try:
            page = int(item.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        conf = _coerce_number(item.get("confidence"))
        conf = 0.8 if conf is None else max(0.0, min(1.0, conf))
        fact = ExtractedFact(
            metric=metric,
            value=float(value),
            fiscal_year=fiscal_year,
            statement_type=str(item.get("statement_type", "")).strip() or _statement_for(metric),
            page_number=page,
            source_label=str(item.get("source_label", "")).strip()[:200],
            confidence=conf,
        )
        prev = best.get(metric)
        if prev is None or fact.confidence > prev.confidence:
            best[metric] = fact
    return list(best.values())


def _statement_for(code: str) -> str:
    for row in _FALLBACK_CATALOG:
        if row["line_item_code"] == code:
            return row["statement_type"]
    return ""


def _coerce_number(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            f = float(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        return f if f == f and abs(f) != float("inf") else None
    s = str(raw).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(" ", "")
    # If both separators present, assume '.' thousands and ',' decimal (VN) → drop dots, comma→dot
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    val = float(s)
    return -val if neg else val


def _resolve_client(client: Any, model: str, timeout: int) -> Any:
    if client is not None:
        return client
    from backend.harness.model_adapter import _resolve_openai_client, validate_production_model

    validate_production_model(model)
    resolved, _ = _resolve_openai_client(timeout)
    return resolved


def _complete_json(client: Any, system_prompt: str, user_prompt: str, model: str) -> dict[str, Any]:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=16384,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def extract_facts(
    pages: Sequence[tuple[int, str]],
    ticker: str,
    fiscal_year: int,
    *,
    client: Any = None,
    model: str = MODEL,
    timeout: int = 180,
    catalog: Optional[Sequence[dict[str, str]]] = None,
) -> list[ExtractedFact]:
    """Single-pass extraction: select statement pages → one LLM call → validate."""
    cat = list(catalog) if catalog is not None else load_metric_catalog()
    valid = {row["line_item_code"] for row in cat}
    selected = select_financial_pages(pages)
    if not selected:
        return []
    client = _resolve_client(client, model, timeout)
    raw = _complete_json(
        client, build_system_prompt(cat), build_user_prompt(ticker, fiscal_year, selected), model
    )
    return parse_llm_facts(raw, ticker, fiscal_year, valid)


def extract_facts_targeted(
    pages: Sequence[tuple[int, str]],
    ticker: str,
    fiscal_year: int,
    *,
    client: Any = None,
    model: str = MODEL,
    timeout: int = 180,
    catalog: Optional[Sequence[dict[str, str]]] = None,
) -> list[ExtractedFact]:
    """Targeted extraction — one focused LLM pass per statement (balance_sheet,
    income_statement, cash_flow), each hunting that statement's required metrics.

    Recall is higher than the single pass because the model isn't diluted across
    all 44 codes and gets the right pages per statement. Falls back to the broad
    page set for a statement whose header wasn't detected (poor OCR). Results are
    merged, deduped by metric (highest confidence wins).
    """
    cat = list(catalog) if catalog is not None else load_metric_catalog()
    valid = {row["line_item_code"] for row in cat}
    required = required_facts_union()
    client = _resolve_client(client, model, timeout)

    merged: dict[str, ExtractedFact] = {}
    broad = select_financial_pages(pages)  # fallback page set
    for statement in ("balance_sheet", "income_statement", "cash_flow"):
        subset = catalog_for_statement(statement, cat)
        if not subset:
            continue
        stmt_pages = select_financial_pages(pages, context=3, max_pages=30, statement=statement) or broad
        # Add note pages (e.g. borrowings note V.19) whose detail the face omits.
        note_pages = select_note_pages(pages, statement)
        if note_pages:
            seen = {n for n, _ in stmt_pages}
            stmt_pages = stmt_pages + [(n, t) for n, t in note_pages if n not in seen]
        if not stmt_pages:
            continue
        raw = _complete_json(
            client,
            build_statement_system_prompt(statement, subset, required),
            build_user_prompt(ticker, fiscal_year, stmt_pages),
            model,
        )
        for fact in parse_llm_facts(raw, ticker, fiscal_year, valid):
            prev = merged.get(fact.metric)
            if prev is None or fact.confidence > prev.confidence:
                merged[fact.metric] = fact
    return list(merged.values())
