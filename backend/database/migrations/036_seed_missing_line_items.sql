-- Seed line_items defined in the financial taxonomy but missing from ref.line_items.
-- ingest.observations.metric has a FK to ref.line_items(line_item_code); the
-- vnstock finance connector emits these taxonomy metrics, so they must be
-- registered or observation inserts fail with observations_metric_fkey.
-- Idempotent: ON CONFLICT keeps the registry current without duplicating rows.

INSERT INTO ref.line_items
    (line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit, is_derived)
VALUES
    ('operating_profit.total',          'income_statement', N'Lợi nhuận thuần từ hoạt động kinh doanh', 'Operating profit',                          'vnd_bn', FALSE),
    ('financial_income.total',          'income_statement', N'Doanh thu hoạt động tài chính',           'Financial income',                          'vnd_bn', FALSE),
    ('financial_expense.total',         'income_statement', N'Chi phí tài chính',                       'Financial expense',                         'vnd_bn', FALSE),
    ('long_term_debt.ending',           'balance_sheet',    N'Vay dài hạn',                             'Long-term debt',                            'vnd_bn', FALSE),
    ('non_current_liabilities.ending',  'balance_sheet',    N'Nợ dài hạn',                              'Non-current liabilities',                   'vnd_bn', FALSE),
    ('investing_cash_flow.total',       'cash_flow',        N'Lưu chuyển tiền thuần từ hoạt động đầu tư',  'Net cash flow from investing activities',   'vnd_bn', FALSE),
    ('financing_cash_flow.total',       'cash_flow',        N'Lưu chuyển tiền thuần từ hoạt động tài chính', 'Net cash flow from financing activities', 'vnd_bn', FALSE),
    ('change_in_working_capital.total', 'cash_flow',        N'Thay đổi vốn lưu động',                   'Change in working capital',                 'vnd_bn', FALSE),
    ('dividends_paid.total',            'cash_flow',        N'Cổ tức đã trả',                           'Dividends paid',                            'vnd_bn', FALSE),
    ('dividends_per_share.cash',        'other',            N'Cổ tức tiền mặt trên mỗi cổ phiếu',       'Cash dividend per share',                   'vnd',    FALSE)
ON CONFLICT (line_item_code) DO UPDATE
SET statement_type  = EXCLUDED.statement_type,
    display_name_vi = EXCLUDED.display_name_vi,
    display_name_en = EXCLUDED.display_name_en,
    canonical_unit  = EXCLUDED.canonical_unit;
