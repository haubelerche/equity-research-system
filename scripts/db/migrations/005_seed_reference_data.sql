-- Migration: 005_seed_reference_data.sql
-- Purpose: Seed MVP companies, universe, line items, and canonical formula metadata.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.
-- IMPORTANT: Formula IDs F001-F030 must match FORMULA_FINANCE.md exactly.
-- Line item codes must match financial_taxonomy_vn_pharma.yaml dot-notation keys.

INSERT INTO ref.companies
    (ticker, company_name_vi, company_name_en, exchange, sector, subsector)
VALUES
    ('DHG', N'Công ty Cổ phần Dược Hậu Giang', 'Duoc Hau Giang Pharmaceutical JSC', 'HOSE', 'pharma', 'duoc_pham'),
    ('IMP', N'Công ty Cổ phần Imexpharm', 'Imexpharm Corporation', 'HOSE', 'pharma', 'duoc_pham'),
    ('DMC', N'Công ty Cổ phần Xuất nhập khẩu Y tế Domesco', 'Domesco Medical Import-Export JSC', 'HOSE', 'pharma', 'duoc_pham'),
    ('TRA', N'Công ty Cổ phần Traphaco', 'Traphaco JSC', 'HNX', 'pharma', 'duoc_pham'),
    ('DBD', N'Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định', 'Bidiphar JSC', 'HOSE', 'pharma', 'duoc_pham_thiet_bi_y_te')
ON CONFLICT (ticker) DO UPDATE
SET company_name_vi = EXCLUDED.company_name_vi,
    company_name_en = EXCLUDED.company_name_en,
    exchange = EXCLUDED.exchange,
    sector = EXCLUDED.sector,
    subsector = EXCLUDED.subsector,
    updated_at = NOW();

INSERT INTO ref.universes (universe_id, universe_name, description)
VALUES ('vietnam_pharma_mvp_5', 'Vietnam Pharma MVP 5', 'MVP universe: DHG, IMP, DMC, TRA, DBD')
ON CONFLICT (universe_id) DO NOTHING;

INSERT INTO ref.universe_members (universe_id, ticker, peer_group, enabled_methods)
VALUES
    ('vietnam_pharma_mvp_5', 'DHG', 'duoc_pham', ARRAY['dcf', 'pe', 'pb']),
    ('vietnam_pharma_mvp_5', 'IMP', 'duoc_pham', ARRAY['dcf', 'pe', 'pb', 'ev_ebitda']),
    ('vietnam_pharma_mvp_5', 'DMC', 'duoc_pham', ARRAY['dcf', 'pe', 'pb']),
    ('vietnam_pharma_mvp_5', 'TRA', 'duoc_pham', ARRAY['dcf', 'pe', 'pb']),
    ('vietnam_pharma_mvp_5', 'DBD', 'duoc_pham_thiet_bi_y_te', ARRAY['dcf', 'pe', 'pb', 'ev_ebitda'])
ON CONFLICT (universe_id, ticker) DO UPDATE
SET peer_group = EXCLUDED.peer_group,
    enabled_methods = EXCLUDED.enabled_methods,
    is_enabled = TRUE;

-- ── ref.line_items ────────────────────────────────────────────────────────────
-- 31 items covering all formulas F001-F030.
-- Income statement (13), balance sheet (14), cash flow (2), market (2).
INSERT INTO ref.line_items
    (line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit)
VALUES
    -- Income Statement
    ('revenue.net',              'income_statement', N'Doanh thu thuần',                                    'Net revenue',                          'vnd_bn'),
    ('cogs.total',               'income_statement', N'Giá vốn hàng bán',                                  'Cost of goods sold',                   'vnd_bn'),
    ('gross_profit.total',       'income_statement', N'Lợi nhuận gộp',                                     'Gross profit',                         'vnd_bn'),
    ('sga.total',                'income_statement', N'Chi phí bán hàng và quản lý doanh nghiệp',          'SG&A expenses',                        'vnd_bn'),
    ('ebit.total',               'income_statement', N'Lợi nhuận trước lãi vay và thuế',                   'EBIT',                                 'vnd_bn'),
    ('ebitda.total',             'income_statement', N'EBITDA',                                            'EBITDA',                               'vnd_bn'),
    ('profit_before_tax.total',  'income_statement', N'Lợi nhuận trước thuế',                              'Profit before tax',                    'vnd_bn'),
    ('interest_expense.total',   'income_statement', N'Chi phí lãi vay',                                   'Interest expense',                     'vnd_bn'),
    ('tax_expense.total',        'income_statement', N'Chi phí thuế thu nhập doanh nghiệp',                'Income tax expense',                   'vnd_bn'),
    ('net_income.parent',        'income_statement', N'Lợi nhuận sau thuế cổ đông công ty mẹ',            'Net income attributable to parent',    'vnd_bn'),
    ('eps.basic',                'income_statement', N'EPS cơ bản',                                        'Basic EPS',                            'vnd'),
    ('depreciation.total',       'income_statement', N'Khấu hao tài sản cố định',                          'Depreciation & amortisation',          'vnd_bn'),
    ('preferred_dividends.total','income_statement', N'Cổ tức ưu đãi',                                     'Preferred dividends',                  'vnd_bn'),
    -- Balance Sheet
    ('cash_and_equivalents.ending',      'balance_sheet', N'Tiền và tương đương tiền cuối kỳ',            'Cash and equivalents',                 'vnd_bn'),
    ('short_term_investments.ending',    'balance_sheet', N'Đầu tư tài chính ngắn hạn cuối kỳ',           'Short-term investments',               'vnd_bn'),
    ('accounts_receivable.ending',       'balance_sheet', N'Phải thu khách hàng cuối kỳ',                 'Accounts receivable',                  'vnd_bn'),
    ('inventory.ending',                 'balance_sheet', N'Hàng tồn kho cuối kỳ',                        'Inventory',                            'vnd_bn'),
    ('current_assets.ending',            'balance_sheet', N'Tài sản ngắn hạn cuối kỳ',                    'Current assets',                       'vnd_bn'),
    ('ppe.net',                          'balance_sheet', N'Tài sản cố định hữu hình ròng',                'Net PPE',                              'vnd_bn'),
    ('total_assets.ending',              'balance_sheet', N'Tổng tài sản cuối kỳ',                        'Total assets',                         'vnd_bn'),
    ('accounts_payable.ending',          'balance_sheet', N'Phải trả người bán cuối kỳ',                  'Accounts payable',                     'vnd_bn'),
    ('current_liabilities.ending',       'balance_sheet', N'Nợ ngắn hạn cuối kỳ',                         'Current liabilities',                  'vnd_bn'),
    ('short_term_debt.ending',           'balance_sheet', N'Nợ vay ngắn hạn cuối kỳ',                     'Short-term debt',                      'vnd_bn'),
    ('total_debt.ending',                'balance_sheet', N'Tổng nợ vay cuối kỳ',                          'Total debt',                           'vnd_bn'),
    ('total_liabilities.ending',         'balance_sheet', N'Tổng nợ phải trả cuối kỳ',                    'Total liabilities',                    'vnd_bn'),
    ('equity.parent',                    'balance_sheet', N'Vốn chủ sở hữu công ty mẹ',                   'Equity attributable to parent',        'vnd_bn'),
    -- Cash Flow
    ('operating_cash_flow.total',        'cash_flow',     N'Lưu chuyển tiền thuần từ hoạt động kinh doanh', 'Operating cash flow',               'vnd_bn'),
    ('capex.total',                      'cash_flow',     N'Chi tiêu vốn',                                 'Capital expenditure',                  'vnd_bn'),
    -- Market
    ('shares_outstanding.weighted_avg',  'market',        N'Số cổ phiếu lưu hành bình quân gia quyền',    'Weighted average shares outstanding',  'shares'),
    ('shares_outstanding.ending',        'market',        N'Số cổ phiếu lưu hành cuối kỳ',                'Shares outstanding at period end',     'shares'),
    ('market_price.close',               'market',        N'Giá đóng cửa',                                 'Close price',                          'vnd')
ON CONFLICT (line_item_code) DO UPDATE
SET statement_type   = EXCLUDED.statement_type,
    display_name_vi  = EXCLUDED.display_name_vi,
    display_name_en  = EXCLUDED.display_name_en,
    canonical_unit   = EXCLUDED.canonical_unit;

-- ── ref.formulas F001-F030 ────────────────────────────────────────────────────
-- Canonical formula registry matching FORMULA_FINANCE.md exactly.
-- function_name matches the Python function in src/financial_formulas/.
INSERT INTO ref.formulas
    (formula_id, formula_name, formula_group, function_name, formula_text, output_unit, description)
VALUES
    ('F001', 'CAGR',                      'growth',           'cagr',                       '(V_end / V_begin) ** (1 / n) - 1',                                              'ratio',            'Compound annual growth rate.'),
    ('F002', 'YoY Revenue Growth',         'growth',           'yoy_revenue_growth',          '(current_revenue - previous_revenue) / previous_revenue',                        'ratio',            'Year-over-year revenue growth.'),
    ('F003', 'YoY Net Income Growth',      'growth',           'yoy_net_income_growth',       '(current_net_income - previous_net_income) / previous_net_income',               'ratio',            'Year-over-year net income growth.'),
    ('F004', 'Component Ratio',            'growth',           'component_ratio',             'component_value / total_value',                                                  'ratio',            'Component as share of total.'),
    ('F005', 'EPS',                        'market_valuation', 'eps',                         '(net_income_after_tax - preferred_dividends) / weighted_avg_common_shares',       'currency_per_share','Earnings per share.'),
    ('F006', 'P/E',                        'market_valuation', 'pe_ratio',                    'market_price_per_share / eps_value',                                              'multiple',         'Price to earnings ratio.'),
    ('F007', 'P/B',                        'market_valuation', 'pb_ratio',                    'market_price_per_share / bvps_value',                                             'multiple',         'Price to book ratio.'),
    ('F008', 'P/S',                        'market_valuation', 'ps_ratio',                    'market_price_per_share / sales_per_share_value',                                  'multiple',         'Price to sales ratio.'),
    ('F009', 'EV/EBITDA',                  'market_valuation', 'ev_to_ebitda',                'enterprise_value / ebitda',                                                       'multiple',         'Enterprise value to EBITDA.'),
    ('F010', 'BVPS',                       'market_valuation', 'bvps',                        '(total_equity - intangible_assets) / common_shares_outstanding',                  'currency_per_share','Book value per share.'),
    ('F011', 'ROA',                        'profitability',    'roa',                         'net_income_after_tax / average_total_assets',                                     'ratio',            'Return on assets.'),
    ('F012', 'ROE',                        'profitability',    'roe',                         'net_income_after_tax / average_total_equity',                                     'ratio',            'Return on equity.'),
    ('F013', 'ROS',                        'profitability',    'ros',                         'net_income_after_tax / net_revenue',                                              'ratio',            'Return on sales.'),
    ('F014', 'Debt to Equity',             'capital_structure','debt_to_equity',              'total_debt_or_liabilities / total_equity',                                        'multiple',         'Debt-to-equity ratio.'),
    ('F015', 'Cash Ratio',                 'liquidity',        'cash_ratio',                  '(cash_and_equivalents + short_term_investments) / current_liabilities',            'multiple',         'Cash ratio.'),
    ('F016', 'DSO',                        'operating_cycle',  'days_sales_outstanding',      '(average_accounts_receivable / net_revenue) * days',                              'days',             'Days sales outstanding.'),
    ('F017', 'DIO',                        'operating_cycle',  'days_inventory_outstanding',  '(average_inventory / cost_of_goods_sold) * days',                                 'days',             'Days inventory outstanding.'),
    ('F018', 'Quick Ratio',                'liquidity',        'quick_ratio',                 '(current_assets - inventory) / current_liabilities',                              'multiple',         'Quick ratio.'),
    ('F019', 'DPO',                        'operating_cycle',  'days_payable_outstanding',    '(average_accounts_payable / cost_of_goods_sold) * days',                          'days',             'Days payable outstanding.'),
    ('F020', 'Gross Profit Margin',        'profitability',    'gross_profit_margin',         '(net_revenue - cost_of_goods_sold) / net_revenue',                                'ratio',            'Gross profit margin.'),
    ('F021', 'Net Profit Margin',          'profitability',    'net_profit_margin',           'net_income_after_tax / net_revenue',                                              'ratio',            'Net profit margin.'),
    ('F022', 'Current Ratio',              'liquidity',        'current_ratio',               'current_assets / current_liabilities',                                            'multiple',         'Current ratio.'),
    ('F023', 'Fixed Asset Turnover',       'operating_cycle',  'fixed_asset_turnover',        'net_revenue / average_net_fixed_assets',                                          'turnover',         'Fixed asset turnover.'),
    ('F024', 'FCFF',                       'cash_flow',        'fcff',                        'EBIT * (1 - tax_rate) + depreciation - CAPEX - change_in_net_working_capital',    'currency',         'Free cash flow to firm.'),
    ('F025', 'EBIT',                       'cash_flow',        'ebit',                        'profit_before_tax + interest_expense',                                            'currency',         'Earnings before interest and tax.'),
    ('F026', 'Straight-Line Depreciation', 'cash_flow',        'straight_line_depreciation',  '(cost - salvage_value) / useful_life_years',                                      'currency',         'Straight-line depreciation.'),
    ('F027', 'CAPEX',                      'cash_flow',        'capex',                       'delta_ppe + depreciation',                                                        'currency',         'Capital expenditure.'),
    ('F028', 'Change in NWC',              'cash_flow',        'change_in_nwc',               'current_nwc - previous_nwc',                                                      'currency',         'Change in net working capital.'),
    ('F029', 'WACC',                       'cost_of_capital',  'wacc',                        '(E/V * Re) + (D/V * Rd * (1 - tax_rate))',                                        'ratio',            'Weighted average cost of capital.'),
    ('F030', 'CAPM Cost of Equity',        'cost_of_capital',  'capm_cost_of_equity',         'risk_free_rate + beta * (market_return - risk_free_rate)',                         'ratio',            'Cost of equity using CAPM.')
ON CONFLICT (formula_id) DO UPDATE
SET formula_name  = EXCLUDED.formula_name,
    formula_group = EXCLUDED.formula_group,
    function_name = EXCLUDED.function_name,
    formula_text  = EXCLUDED.formula_text,
    output_unit   = EXCLUDED.output_unit,
    description   = EXCLUDED.description,
    is_active     = TRUE;
