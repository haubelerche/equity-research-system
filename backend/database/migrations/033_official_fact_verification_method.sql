-- Add the deterministic official-document verification method used by the
-- governed DHG remediation path. This does not change any quality threshold.

ALTER TABLE ingest.observations
    DROP CONSTRAINT IF EXISTS observations_extraction_method_check;

ALTER TABLE ingest.observations
    ADD CONSTRAINT observations_extraction_method_check
    CHECK (extraction_method IN (
        'api_structured',
        'pdf_ocr',
        'manual',
        'csv',
        'legacy_import',
        'exact_official_document_match_v1'
    ));

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_033',
    'ingest.observations',
    jsonb_build_object(
        'migration', '033_official_fact_verification_method',
        'added_extraction_method', 'exact_official_document_match_v1'
    )
);
