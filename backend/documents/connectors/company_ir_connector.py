"""Company IR discovery connector (P0) — Source-Provenance Rebuild, Phase 3A.

Discovers official document candidates from a company's own IR pages by extracting
linked files (PDF/XLS) and classifying their type + fiscal year. Highest-priority
source (a company's own disclosures).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, unquote

from backend.documents.connectors.base import (
    BaseDiscoveryConnector,
    DocumentCandidate,
    HttpGet,
    default_http_get,
    infer_document_type,
    infer_fiscal_year,
)

_FILE_LINK_RE = re.compile(r'href=["\']([^"\']+\.(?:pdf|xls|xlsx))["\']', re.IGNORECASE)


class CompanyIRConnector(BaseDiscoveryConnector):
    source_name = "company_ir"

    def discover(self, company, from_year: int, to_year: int,
                 http_get: HttpGet | None = None) -> list[DocumentCandidate]:
        get = http_get or default_http_get
        seen: set[str] = set()
        candidates: list[DocumentCandidate] = []

        for ir_url in company.ir_urls:
            try:
                html = get(ir_url)
            except Exception:  # noqa: BLE001 — one bad IR page must not kill discovery
                continue
            origin = f"{urlparse(ir_url).scheme}://{urlparse(ir_url).netloc}"
            for raw_href in _FILE_LINK_RE.findall(html):
                abs_url = urljoin(origin, raw_href)
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                fname = unquote(urlparse(abs_url).path.rsplit("/", 1)[-1])
                year = infer_fiscal_year(fname)
                if year is None or not (from_year <= year <= to_year):
                    continue
                doc_type, type_conf = infer_document_type(fname)
                # IR source is authoritative → base 0.9, modulated by type confidence.
                confidence = round(0.9 * type_conf + 0.05, 3)
                candidates.append(DocumentCandidate(
                    ticker=company.ticker,
                    fiscal_year=year,
                    document_type=doc_type,
                    title=fname,
                    source_name=self.source_name,
                    source_url=abs_url,
                    publisher=company.company_name_vi,
                    discovery_method="ir_page_link_scan",
                    confidence=confidence,
                ))
        return candidates
