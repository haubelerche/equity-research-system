# AGP Auto-Ingest Report

- Generated: 2026-06-15T09:54:08.715381+00:00
- Channels: pdf
- Dry run: False

| Year | IngestStatus | CafeF | PDF | Ingested | Promoted |
|------|-------------|-------|-----|----------|----------|
| 2022 | `LOW_CONFIDENCE` | 0 | 4 | 0 | 0 |

**Total ingested:** 0  
**Total promoted:** 0  
**Total errors:** 3  
**Total notes:** 0  

## Errors

- FY2022: FY2022: conflicting PDF values for profit_before_tax.total
- FY2022: FY2022: ignored rows belonging to fiscal years 2018, 2020
- FY2022: ingest: insert or update on table "source_documents" violates foreign key constraint "source_documents_ticker_fkey"
DETAIL:  Key (ticker)=(AGP) is not present in table "companies".
