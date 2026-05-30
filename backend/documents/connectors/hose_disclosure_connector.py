"""HOSE disclosure discovery connector (P1) — Source-Provenance Rebuild, Phase 3A.

Best-effort. HOSE (hsx.vn) serves its listed-company disclosure list via a JS/API portal,
so a plain HTML scan often yields nothing without the official API. This connector makes
a controlled attempt against the public symbol page and returns [] gracefully when the
portal does not expose direct file links. It never falls back to uncontrolled crawling.
"""
from __future__ import annotations

from backend.documents.connectors.base import (
    BaseDiscoveryConnector,
    DocumentCandidate,
    HttpGet,
    default_http_get,
    scan_file_candidates,
)


class HoseDisclosureConnector(BaseDiscoveryConnector):
    source_name = "hose_disclosure"
    _BASE = "https://www.hsx.vn"

    def discover(self, company, from_year: int, to_year: int,
                 http_get: HttpGet | None = None) -> list[DocumentCandidate]:
        if company.exchange != "HOSE" or not company.issuer_code:
            return []
        get = http_get or default_http_get
        # Public symbol page; if the portal renders file links server-side we capture them.
        url = f"{self._BASE}/Modules/Listed/Web/Symbol/{company.issuer_code}"
        try:
            html = get(url)
        except Exception:  # noqa: BLE001
            return []
        return scan_file_candidates(
            html, self._BASE, ticker=company.ticker, source_name=self.source_name,
            from_year=from_year, to_year=to_year, publisher="HOSE",
            base_conf=0.75, discovery_method="hose_symbol_page_scan",
        )
