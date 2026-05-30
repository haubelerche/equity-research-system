"""HNX/UPCoM disclosure discovery connector (P1) — Source-Provenance Rebuild, Phase 3A.

Best-effort, same pattern as the HOSE connector. HNX (hnx.vn) is also a JS/API portal;
the connector makes a controlled attempt and degrades gracefully to [].
"""
from __future__ import annotations

from backend.documents.connectors.base import (
    BaseDiscoveryConnector,
    DocumentCandidate,
    HttpGet,
    default_http_get,
    scan_file_candidates,
)


class HnxDisclosureConnector(BaseDiscoveryConnector):
    source_name = "hnx_disclosure"
    _BASE = "https://www.hnx.vn"

    def discover(self, company, from_year: int, to_year: int,
                 http_get: HttpGet | None = None) -> list[DocumentCandidate]:
        if company.exchange not in ("HNX", "UPCOM") or not company.issuer_code:
            return []
        get = http_get or default_http_get
        url = f"{self._BASE}/vi-vn/co-phieu-etfs/chi-tiet-chung-khoan-{company.issuer_code}.html"
        try:
            html = get(url)
        except Exception:  # noqa: BLE001
            return []
        return scan_file_candidates(
            html, self._BASE, ticker=company.ticker, source_name=self.source_name,
            from_year=from_year, to_year=to_year, publisher="HNX",
            base_conf=0.75, discovery_method="hnx_symbol_page_scan",
        )
