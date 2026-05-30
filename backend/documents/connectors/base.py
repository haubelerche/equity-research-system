"""Discovery connector base — Source-Provenance Rebuild, Phase 3A.

A discovery connector turns a (company, year-range) into DOCUMENT CANDIDATES. It does
NOT fetch the file (that is Phase 3B / the fetcher). HTTP is injected via `http_get` so
connectors are unit-testable offline.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass

# Controlled document-type taxonomy for discovery.
DOCUMENT_TYPES: frozenset[str] = frozenset({
    "annual_report",
    "audited_financial_statement",
    "financial_statement",       # quarterly / interim
    "disclosure",                # CBTT / giải trình
    "governance_report",
    "sustainability_report",
})

# Source priority tier for ranking (lower = more authoritative).
SOURCE_PRIORITY: dict[str, int] = {
    "company_ir": 0,
    "hose_disclosure": 1,
    "hnx_disclosure": 1,
    "ssc_ids": 1,
    "official_regulator": 2,
    "reputable_mirror": 3,
    "media": 4,
}


@dataclass
class DocumentCandidate:
    ticker: str
    fiscal_year: int | None
    document_type: str
    title: str
    source_name: str
    source_url: str
    publisher: str = ""
    discovery_method: str = ""
    confidence: float = 0.0
    ranking_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def default_http_get(url: str, timeout: int = 25) -> str:
    """Fetch a URL with TLS verification ON and return decoded text."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "maer-doc-discovery/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (verified TLS)
        return resp.read().decode("utf-8", "replace")


HttpGet = Callable[[str], str]

_YEAR_RE = re.compile(r"20(1[5-9]|2[0-9])")


def infer_fiscal_year(text: str) -> int | None:
    """Extract a plausible fiscal year (2015–2029) from a filename/title."""
    # Prefer a year attached to a quarter token e.g. Q4.2025 / 6T.2025
    m = re.search(r"(?:Q[1-4]|[0-9]T)\.?(20\d{2})", text)
    if m:
        return int(m.group(1))
    years = [int(y) for y in re.findall(r"20\d{2}", text) if 2015 <= int(y) <= 2029]
    return max(years) if years else None


def infer_document_type(text: str) -> tuple[str, float]:
    """Classify a document type from filename/title. Returns (type, confidence)."""
    t = text.lower()
    if re.search(r"thuong[\s\-]?nien|annual[\s\-]?report", t):
        return "annual_report", 0.95
    if re.search(r"ben[\s\-]?vung|sustainab", t):
        return "sustainability_report", 0.9
    if re.search(r"quan[\s\-]?tri|governance", t):
        return "governance_report", 0.9
    # Audited / reviewed full-year financial statement
    if re.search(r"audited|kiem[\s\-]?toan", t) and re.search(r"fs|bctc|financial", t):
        return "audited_financial_statement", 0.95
    if re.search(r"cbtt|giai[\s\-]?trinh|disclosure", t):
        return "disclosure", 0.85
    if re.search(r"bctc|financial[\s\-]?statement|bao[\s\-]?cao[\s\-]?tai[\s\-]?chinh", t):
        # Quarterly/interim if it has a quarter token, else treat as FS
        if re.search(r"q[1-4]|[0-9]t\.", t):
            return "financial_statement", 0.85
        if re.search(r"soat[\s\-]?xet", t):
            return "financial_statement", 0.85
        return "audited_financial_statement", 0.8
    return "disclosure", 0.4


_FILE_HREF_RE = re.compile(r'href=["\']([^"\']+\.(?:pdf|xls|xlsx))["\']', re.IGNORECASE)


def scan_file_candidates(
    html: str, origin: str, *, ticker: str, source_name: str,
    from_year: int, to_year: int, publisher: str, base_conf: float,
    discovery_method: str,
) -> list[DocumentCandidate]:
    """Extract file links from an HTML page and build classified candidates.

    Shared by IR + exchange/SSC connectors. TLS-verified fetching happens in the caller.
    """
    from urllib.parse import unquote, urljoin, urlparse
    out: list[DocumentCandidate] = []
    seen: set[str] = set()
    for raw in _FILE_HREF_RE.findall(html):
        abs_url = urljoin(origin, raw)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        fname = unquote(urlparse(abs_url).path.rsplit("/", 1)[-1])
        year = infer_fiscal_year(fname)
        if year is None or not (from_year <= year <= to_year):
            continue
        doc_type, type_conf = infer_document_type(fname)
        out.append(DocumentCandidate(
            ticker=ticker, fiscal_year=year, document_type=doc_type, title=fname,
            source_name=source_name, source_url=abs_url, publisher=publisher,
            discovery_method=discovery_method,
            confidence=round(base_conf * type_conf, 3),
        ))
    return out


class BaseDiscoveryConnector:
    """Interface for a discovery connector. Subclasses implement `discover`."""

    source_name: str = "base"

    def discover(self, company, from_year: int, to_year: int,
                 http_get: HttpGet | None = None) -> list[DocumentCandidate]:
        raise NotImplementedError
