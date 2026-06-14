-- 043_cafef_financial_source_type.sql
-- Allow 'cafef_financial' as a source_type for ingest.source_documents.
--
-- CafeF's FinanceReport.ashx serves PARSED audited financial-statement figures
-- aggregated from HOSE/HNX filings (tier 2). It is NOT the original audited PDF, so
-- it must not be labelled 'audited_financial_statement' (which implies a tier 0/1
-- primary document). A dedicated, explicit type keeps provenance honest: a reviewer
-- filtering by source_type sees exactly which rows came from the CafeF aggregator.

ALTER TABLE ingest.source_documents
    DROP CONSTRAINT IF EXISTS source_documents_source_type_check;

ALTER TABLE ingest.source_documents
    ADD CONSTRAINT source_documents_source_type_check
    CHECK (source_type IN (
        'audited_financial_statement', 'annual_report', 'exchange_disclosure',
        'company_ir', 'regulatory_notice', 'vnstock_financial', 'vnstock_price',
        'vnstock_company', 'golden_csv', 'manual', 'news', 'industry_report',
        'cafef_financial'
    ));
