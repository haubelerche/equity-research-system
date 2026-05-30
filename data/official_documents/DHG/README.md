# DHG Official Documents — manual placement

This folder holds the **official verification-layer** documents for DHG. The pipeline
**never fabricates facts** — an analyst must place real documents here.

## Per fiscal year

Create `data/official_documents/DHG/<YEAR>/` with:

| File | Purpose |
|---|---|
| `metadata.json` | Document metadata — copy `_TEMPLATE/metadata.json`, fill in real values, set `fiscal_year`. |
| `extracted_facts.csv` | Facts transcribed from the document — copy `_TEMPLATE/extracted_facts.csv`. One row per metric. |
| `source_document.pdf` | The official PDF (audited BCTC / annual report / exchange disclosure). Optional but recommended; its SHA-256 is checked against `metadata.file_hash` if provided. |

## metric_id values

`metric_id` may use friendly aliases (auto-mapped to canonical `ref.line_items` codes) or
the canonical dot-notation directly. Minimum metrics per year:

```
revenue_net, gross_profit, operating_profit, profit_before_tax, net_income, eps,
total_assets, total_equity, short_term_debt, long_term_debt, operating_cash_flow, capex
```

## Ingest

```bash
python scripts/ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025
```

Until documents are placed, ingestion reports the years as `missing` and final report
export stays blocked (correct behavior).
