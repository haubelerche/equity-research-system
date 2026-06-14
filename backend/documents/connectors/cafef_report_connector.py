"""CafeF FinanceReport.ashx connector — accountable tier-2 audited statement evidence.

Fetches per-year audited **income statement** (Type=1) and **balance sheet** (Type=2)
summary line items from cafef.vn's machine-readable ``FinanceReport.ashx`` endpoint and
turns them into evidence records with full provenance (exact ``api_url`` + audited flag).

This is NOT the original audited PDF — CafeF does not expose that file. It is the parsed
audited figures CafeF aggregates from HOSE/HNX filings, so it is **tier 2**. Cash-flow
(Type=3) is not served by this endpoint and yields no records (no fabrication).

Units: ``FinanceReport.ashx`` returns values in **thousand VND**. Verified against DBD
FY2025: ``DoanhThu = 1,946,612,660`` (thousand) -> 1,946.6 tỷ đồng, matching the figure
Bidiphar reported. ``value_ty_dong = value_thousand_vnd / 1_000_000``.

Endpoint (discovered from the page JS ``path = /du-lieu/Ajax/PageNew/``):
    GET https://cafef.vn/du-lieu/Ajax/PageNew/FinanceReport.ashx
        ?Type={1|2}&Symbol={ticker}&TotalRow={n}&EndDate={end_year}&ReportType=NAM&Sort=DESC

    Type=1 -> KQKD (income statement)
    Type=2 -> CĐKT (balance sheet)
    ReportType=NAM -> full-year (annual). EndDate is the most-recent year; the response
    returns that year plus the preceding ``TotalRow``-1 years, newest first.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import asdict, dataclass, field

_BASE_URL = "https://cafef.vn/du-lieu/Ajax/PageNew/FinanceReport.ashx"

# Type code -> canonical statement_type. Only IS + BS are served by this endpoint.
STATEMENT_TYPES: dict[int, str] = {
    1: "income_statement",
    2: "balance_sheet",
}

_STATEMENT_LABEL_VI: dict[str, str] = {
    "income_statement": "Báo cáo kết quả kinh doanh",
    "balance_sheet": "Bảng cân đối kế toán",
}


@dataclass
class CafeFReportEvidence:
    """One year's audited statement summary, as an accountable evidence record."""

    ticker: str
    fiscal_year: int
    statement_type: str          # "income_statement" | "balance_sheet"
    audited: bool                # parsed from CafeF "Conten" ("Đã kiểm toán")
    source_tier: int             # 2 — parsed aggregator, not the original PDF
    api_url: str                 # exact endpoint URL used (provenance)
    line_items: list[dict] = field(default_factory=list)
    evidence_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _default_http_get(url: str, timeout: int = 25) -> str:
    """Fetch URL with TLS verification ON and a descriptive User-Agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "maer-doc-discovery/1.0",
            "Referer": "https://cafef.vn/du-lieu/tai-bao-cao-tai-chinh/",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (TLS verified)
        return resp.read().decode("utf-8", "replace")


def _format_vnd_thousand(value_thousand_vnd: float) -> str:
    """Render a thousand-VND figure with thousands separators (vi locale uses '.')."""
    return f"{int(round(value_thousand_vnd)):,}".replace(",", ".")


class CafeFReportConnector:
    """Fetches accountable tier-2 audited statement evidence from cafef.vn."""

    source_name = "cafef_finance_report"
    source_tier = 2

    def build_url(self, ticker: str, statement_type_code: int, end_year: int,
                  total_row: int = 10) -> str:
        return (
            f"{_BASE_URL}?Type={statement_type_code}&Symbol={ticker.upper()}"
            f"&TotalRow={total_row}&EndDate={end_year}&ReportType=NAM&Sort=DESC"
        )

    def fetch_statement(
        self,
        ticker: str,
        statement_type_code: int,
        end_year: int,
        total_row: int = 10,
        http_get=None,
    ) -> list[CafeFReportEvidence]:
        """Fetch one statement type across the years CafeF returns. Empty on any failure."""
        statement_type = STATEMENT_TYPES.get(statement_type_code)
        if statement_type is None:
            return []
        get = http_get or _default_http_get
        url = self.build_url(ticker, statement_type_code, end_year, total_row)
        try:
            payload = json.loads(get(url))
        except Exception:  # noqa: BLE001 — any network/parse error -> no records
            return []
        if not payload.get("Success"):
            return []
        years = ((payload.get("Data") or {}).get("Value")) or []
        out: list[CafeFReportEvidence] = []
        for year_block in years:
            record = self._build_record(ticker, statement_type, url, year_block)
            if record is not None:
                out.append(record)
        return out

    def fetch_evidence(
        self,
        ticker: str,
        from_year: int,
        to_year: int,
        total_row: int = 10,
        http_get=None,
    ) -> list[CafeFReportEvidence]:
        """Fetch IS + BS evidence for ``ticker``, filtered to [from_year, to_year]."""
        out: list[CafeFReportEvidence] = []
        for code in sorted(STATEMENT_TYPES):
            for rec in self.fetch_statement(ticker, code, to_year, total_row, http_get):
                if from_year <= rec.fiscal_year <= to_year:
                    out.append(rec)
        out.sort(key=lambda r: (r.fiscal_year, r.statement_type))
        return out

    def _build_record(
        self, ticker: str, statement_type: str, api_url: str, year_block: dict,
    ) -> CafeFReportEvidence | None:
        try:
            fiscal_year = int(year_block.get("Year"))
        except (TypeError, ValueError):
            return None
        audited = "kiểm toán" in str(year_block.get("Conten") or "").lower()
        line_items: list[dict] = []
        for li in year_block.get("Value") or []:
            raw = li.get("Value")
            if raw is None:
                continue
            value_thousand = float(raw)
            line_items.append({
                "code": li.get("Code"),
                "name": li.get("Name"),
                "value_thousand_vnd": value_thousand,
                "value_ty_dong": round(value_thousand / 1_000_000.0, 3),
            })
        if not line_items:
            return None
        return CafeFReportEvidence(
            ticker=ticker.upper(),
            fiscal_year=fiscal_year,
            statement_type=statement_type,
            audited=audited,
            source_tier=self.source_tier,
            api_url=api_url,
            line_items=line_items,
            evidence_text=self._render_text(ticker, statement_type, fiscal_year, audited, line_items),
        )

    def _render_text(
        self, ticker: str, statement_type: str, fiscal_year: int,
        audited: bool, line_items: list[dict],
    ) -> str:
        label = _STATEMENT_LABEL_VI.get(statement_type, statement_type)
        audited_tag = "Đã kiểm toán" if audited else "Chưa kiểm toán"
        header = (
            f"{label} {ticker.upper()} năm {fiscal_year} ({audited_tag}) — nguồn CafeF "
            f"(tổng hợp từ công bố HOSE/HNX):"
        )
        lines = [header]
        for li in line_items:
            lines.append(
                f"- {li['name']}: {_format_vnd_thousand(li['value_thousand_vnd'])} nghìn đồng "
                f"(≈ {li['value_ty_dong']:,.1f} tỷ đồng)".replace(",", ".")
            )
        return "\n".join(lines)
