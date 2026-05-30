"""SSC / IDS disclosure discovery connector (P1) — Source-Provenance Rebuild, Phase 3A.

Best-effort against the SSC public disclosure portal (congbothongtin.ssc.gov.vn).
The portal is JS/search-driven; this connector makes a controlled attempt and returns []
gracefully when no direct file links are exposed. Never uncontrolled crawling.
"""
from __future__ import annotations

from backend.documents.connectors.base import (
    BaseDiscoveryConnector,
    DocumentCandidate,
    HttpGet,
    default_http_get,
    scan_file_candidates,
)


class SscDisclosureConnector(BaseDiscoveryConnector):
    source_name = "ssc_ids"
    _BASE = "https://congbothongtin.ssc.gov.vn"

    def discover(self, company, from_year: int, to_year: int,
                 http_get: HttpGet | None = None) -> list[DocumentCandidate]:
        get = http_get or default_http_get
        # Public search landing; capture any server-rendered file links for the issuer.
        url = f"{self._BASE}/faces/NewsSearch?keyword={company.issuer_code or company.ticker}"
        try:
            html = get(url)
        except Exception:  # noqa: BLE001
            return []
        return scan_file_candidates(
            html, self._BASE, ticker=company.ticker, source_name=self.source_name,
            from_year=from_year, to_year=to_year, publisher="SSC/IDS",
            base_conf=0.7, discovery_method="ssc_ids_search_scan",
        )
