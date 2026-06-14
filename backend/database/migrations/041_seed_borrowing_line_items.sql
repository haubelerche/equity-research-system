-- backend/database/migrations/041_seed_borrowing_line_items.sql
-- Register the gross CFS financing lines emitted by the vnstock finance connector.
-- ingest.observations.metric FK-references ref.line_items(line_item_code); without
-- these rows the inserts fail with observations_metric_fkey. These two metrics let
-- the debt schedule reach method=direct_cash_flow (high confidence), which unblocks
-- FCFE publication. Idempotent: ON CONFLICT keeps the registry current.

INSERT INTO ref.line_items
    (line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit, is_derived)
VALUES
    ('proceeds_from_borrowings.total', 'cash_flow', N'Tiền thu từ đi vay',    'Proceeds from borrowings', 'vnd_bn', FALSE),
    ('repayment_of_borrowings.total',  'cash_flow', N'Tiền trả nợ gốc vay',   'Repayment of borrowings',  'vnd_bn', FALSE)
ON CONFLICT (line_item_code) DO UPDATE
SET statement_type  = EXCLUDED.statement_type,
    display_name_vi = EXCLUDED.display_name_vi,
    display_name_en = EXCLUDED.display_name_en,
    canonical_unit  = EXCLUDED.canonical_unit;
