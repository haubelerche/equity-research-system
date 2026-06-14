"""Company registry — Source-Provenance Rebuild, Phase 3A (Discovery).

Whitelists each ticker's official identity + IR/disclosure URLs. The discovery pipeline
only fetches from sources reachable via this registry (or the approved exchange/SSC
connectors) — never via uncontrolled generic crawling.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompanyRecord:
    ticker: str
    company_name_vi: str
    company_name_en: str
    exchange: str            # HOSE | HNX | UPCOM
    official_website: str
    ir_urls: list[str] = field(default_factory=list)   # IR pages listing official docs
    aliases: list[str] = field(default_factory=list)
    tax_code: str | None = None
    issuer_code: str | None = None   # exchange ticker used on HOSE/HNX/SSC portals
    cafef_id: str | None = None      # CafeF symbol (Tier 2 structured data)


# MVP pharma universe. DHG is fully populated (the one-ticker E2E target); the others
# carry enough identity to discover but IR URLs can be filled as they are verified.
_COMPANIES: dict[str, CompanyRecord] = {
    "DHG": CompanyRecord(
        ticker="DHG",
        company_name_vi="Công ty Cổ phần Dược Hậu Giang",
        company_name_en="DHG Pharmaceutical Joint Stock Company",
        exchange="HOSE",
        official_website="https://dhgpharma.com.vn",
        ir_urls=[
            "https://dhgpharma.com.vn/vi/bao-cao-tai-chinh",
            "https://dhgpharma.com.vn/vi/bao-cao-thuong-nien",
        ],
        aliases=["Dược Hậu Giang", "DHG Pharma", "Hau Giang Pharmaceutical"],
        issuer_code="DHG", cafef_id="DHG",
    ),
    "IMP": CompanyRecord(
        ticker="IMP", company_name_vi="Công ty Cổ phần Dược phẩm Imexpharm",
        company_name_en="Imexpharm Corporation", exchange="HOSE",
        official_website="https://www.imexpharm.com",
        ir_urls=["https://www.imexpharm.com/quan-he-co-dong"],
        aliases=["Imexpharm"], issuer_code="IMP", cafef_id="IMP",
    ),
    "DMC": CompanyRecord(
        ticker="DMC", company_name_vi="Công ty Cổ phần Xuất nhập khẩu Y tế Domesco",
        company_name_en="Domesco Medical Import Export JSC", exchange="HOSE",
        official_website="https://www.domesco.com",
        ir_urls=["https://www.domesco.com/co-dong"], aliases=["Domesco"], issuer_code="DMC",
        cafef_id="DMC",
    ),
    "TRA": CompanyRecord(
        ticker="TRA", company_name_vi="Công ty Cổ phần Traphaco",
        company_name_en="Traphaco JSC", exchange="HOSE",
        official_website="https://www.traphaco.com.vn",
        ir_urls=["https://www.traphaco.com.vn/vi/quan-he-co-dong.html"],
        aliases=["Traphaco"], issuer_code="TRA", cafef_id="TRA",
    ),
    "DBD": CompanyRecord(
        ticker="DBD", company_name_vi="Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định",
        company_name_en="Binh Dinh Pharmaceutical and Medical Equipment JSC", exchange="HOSE",
        official_website="https://www.bidiphar.com",
        ir_urls=["https://www.bidiphar.com/quan-he-co-dong"], aliases=["Bidiphar"],
        issuer_code="DBD", cafef_id="DBD",
    ),
}

try:
    from backend.dataset.config_io import load_universe_rows

    for _row in load_universe_rows():
        _ticker = (_row.get("ticker") or "").strip().upper()
        if not _ticker:
            continue
        _COMPANIES.setdefault(
            _ticker,
            CompanyRecord(
                ticker=_ticker,
                company_name_vi=(_row.get("company_name") or _ticker).strip(),
                company_name_en=(_row.get("company_name") or _ticker).strip(),
                exchange=(_row.get("exchange") or "").strip().upper(),
                official_website="",
                ir_urls=[],
                aliases=[],
                issuer_code=_ticker,
                cafef_id=_ticker,
            ),
        )
except Exception:
    # Registry import must stay resilient for offline unit tests and early bootstrap.
    pass


def get_company(ticker: str) -> CompanyRecord:
    t = ticker.strip().upper()
    if t not in _COMPANIES:
        raise KeyError(f"ticker {t!r} not in company registry")
    return _COMPANIES[t]


def has_company(ticker: str) -> bool:
    return ticker.strip().upper() in _COMPANIES


def all_tickers() -> list[str]:
    return sorted(_COMPANIES)
