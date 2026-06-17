# MTP Official Document Discovery (Phase 3A/3B)

- Generated: 2026-06-16T20:32:11.634794+00:00
- Year range: 2022–2025
- Candidates discovered: 0
- Selected (auto-promotable): 0
- Needs review (low confidence): 0
- Superseded duplicates: 0
- Fetched: 0

## Per-source counts

- company_ir: 0
- hose_disclosure: 0
- hnx_disclosure: 0
- ssc_ids: 0

## Selected candidates (ranked)

| FY | Type | Source | Conf | Title |
|----|------|--------|------|-------|

## Notes

- Controlled discovery only: sources come from the company registry + approved
  exchange/SSC connectors. No uncontrolled generic crawling.
- company IR is P0; HOSE/HNX/SSC are P1 (best-effort: their portals are JS/API-
  driven and may need official APIs to yield direct file links).
- Low-confidence candidates are flagged needs_review and NOT auto-fetched.
- Fetched files feed the existing `scripts/ingest_official_documents.py` pipeline
  (place/point extracted_facts.csv at the fetched PDF, then ingest → reconcile).