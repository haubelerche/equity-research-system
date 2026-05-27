-- Migration: 007_expand_line_items.sql
-- Purpose: Add critical financial line items that were seeded in ref.line_items in 005
--          but were missing from financial_taxonomy_vn_pharma.yaml and therefore never
--          populated from vnstock. Also registers free_cash_flow.total as a derived line
--          item so fact.financial_facts FK is satisfied if the connector ever encounters it.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

-- These items already exist in ref.line_items from migration 005.
-- This migration is a no-op for ref.line_items (all ON CONFLICT DO NOTHING).
-- Its purpose is to document the expand and update the schema_migrations record.

-- Add free_cash_flow.total as a derived line item.
-- This prevents FK violations if a vnstock ratio frame ever contains an FCF row.
INSERT INTO ref.line_items
    (line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit, is_derived)
VALUES
    ('free_cash_flow.total', 'cash_flow', N'Dòng tiền tự do', 'Free cash flow', 'vnd_bn', TRUE)
ON CONFLICT (line_item_code) DO UPDATE
SET is_derived      = TRUE,
    display_name_vi = EXCLUDED.display_name_vi,
    display_name_en = EXCLUDED.display_name_en;

-- Confirm the 12 critical expanded items are present (idempotent upsert).
-- These were seeded in 005 but the taxonomy YAML lacked aliases to populate them.
-- After this migration, financial_taxonomy_vn_pharma.yaml v2 aliases will map them.
INSERT INTO ref.line_items
    (line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit)
VALUES
    ('profit_before_tax.total',      'income_statement', N'Lợi nhuận trước thuế',                          'Profit before tax',           'vnd_bn'),
    ('interest_expense.total',       'income_statement', N'Chi phí lãi vay',                               'Interest expense',            'vnd_bn'),
    ('tax_expense.total',            'income_statement', N'Chi phí thuế thu nhập doanh nghiệp',            'Income tax expense',          'vnd_bn'),
    ('depreciation.total',           'cash_flow',        N'Khấu hao TSCĐ và BĐSĐT',                        'Depreciation & amortisation', 'vnd_bn'),
    ('accounts_receivable.ending',   'balance_sheet',    N'Phải thu khách hàng cuối kỳ',                   'Accounts receivable',         'vnd_bn'),
    ('current_assets.ending',        'balance_sheet',    N'Tài sản ngắn hạn cuối kỳ',                      'Current assets',              'vnd_bn'),
    ('current_liabilities.ending',   'balance_sheet',    N'Nợ ngắn hạn cuối kỳ',                           'Current liabilities',         'vnd_bn'),
    ('accounts_payable.ending',      'balance_sheet',    N'Phải trả người bán cuối kỳ',                    'Accounts payable',            'vnd_bn'),
    ('ppe.net',                      'balance_sheet',    N'Tài sản cố định hữu hình ròng',                  'Net PPE',                     'vnd_bn'),
    ('short_term_debt.ending',       'balance_sheet',    N'Nợ vay ngắn hạn cuối kỳ',                       'Short-term debt',             'vnd_bn'),
    ('total_liabilities.ending',     'balance_sheet',    N'Tổng nợ phải trả cuối kỳ',                      'Total liabilities',           'vnd_bn'),
    ('short_term_investments.ending','balance_sheet',    N'Đầu tư tài chính ngắn hạn cuối kỳ',             'Short-term investments',      'vnd_bn')
ON CONFLICT (line_item_code) DO UPDATE
SET statement_type  = EXCLUDED.statement_type,
    display_name_vi = EXCLUDED.display_name_vi,
    display_name_en = EXCLUDED.display_name_en,
    canonical_unit  = EXCLUDED.canonical_unit;
