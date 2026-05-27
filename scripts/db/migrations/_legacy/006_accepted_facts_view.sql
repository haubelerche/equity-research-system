-- Migration: 006_accepted_facts_view.sql
-- Purpose: Valuation-safe view of financial_facts.
-- Only rows with validation_status='accepted' AND fiscal_period='FY' are exposed.
-- All valuation and reporting code must read from this view, not the base table.

CREATE OR REPLACE VIEW public.accepted_financial_facts AS
SELECT
    id,
    company_ticker,
    fiscal_year,
    fiscal_period,
    taxonomy_key,
    value,
    unit,
    currency,
    source_version_id,
    parser_version,
    confidence,
    effective_date,
    ingested_at
FROM public.financial_facts
WHERE validation_status = 'accepted'
  AND fiscal_period = 'FY';

COMMENT ON VIEW public.accepted_financial_facts IS
    'Valuation-safe subset: accepted status, annual (FY) periods only. '
    'All valuation and reporting code must read from this view.';
