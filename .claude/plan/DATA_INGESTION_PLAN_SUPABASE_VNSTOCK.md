# DATA INGESTION PLAN — Supabase + Vnstock
## Vietnam Pharma Equity Research Agent

> Mục tiêu: xây dựng kế hoạch thu thập, chuẩn hóa, kiểm định và lưu trữ dữ liệu cho **53 cổ phiếu ngành dược/y tế Việt Nam** vào Supabase, sử dụng **Vnstock làm nguồn dữ liệu structured chính**. FireAnt không nằm trong MVP để giảm rủi ro dependency, quyền truy cập, và độ phức tạp vận hành.

---

## 1. Executive Summary

Dự án không nên thiết kế theo kiểu “agent gọi API rồi viết báo cáo trực tiếp”. Kiến trúc đúng là:

```text
Vnstock Connector
  -> Raw Payload Store
  -> Normalization Layer
  -> Data Quality Gates
  -> Canonical Financial Facts
  -> Derived Analytics / Valuation Artifacts
  -> Report Agent đọc dữ liệu đã khóa nguồn
```

Supabase đóng vai trò **canonical data warehouse + audit store**, không chỉ là database lưu response API. Mọi dữ liệu tài chính dùng cho report phải có:

- `ticker`
- `period`
- `statement_type`
- `line_item_code`
- `value`
- `unit`
- `currency`
- `source_id`
- `ingestion_run_id`
- `retrieval_timestamp`
- `parser_version`
- `quality_status`

Nguyên tắc bắt buộc:

```text
No source_id -> no report number.
No canonical fact -> no valuation input.
No data quality pass -> no agent synthesis.
```

---

## 2. Decision: Chỉ dùng Vnstock cho MVP

### 2.1. Quyết định chính thức

MVP chỉ dùng **Vnstock** cho dữ liệu structured:

| Nhóm dữ liệu | Nguồn MVP | Ghi chú |
|---|---|---|
| Giá lịch sử OHLCV | Vnstock | Dùng cho market context, trend, liquidity, returns |
| Hồ sơ công ty | Vnstock | Seed thông tin doanh nghiệp, ngành, sàn, vốn hóa nếu có |
| Báo cáo tài chính | Vnstock | Income statement, balance sheet, cash flow |
| Chỉ số tài chính | Vnstock tham khảo, nhưng tự tính lại | Không lấy ratio làm source of truth nếu có thể tự tính |
| Tin tức/catalyst | Vnstock nếu có | Chỉ dùng cho narrative/catalyst, không thay thế BCTC |
| Golden dataset | Manual CSV/YAML nội bộ | Dùng để kiểm định 3–5 mã đầu tiên |

### 2.2. Vì sao không dùng FireAnt trong MVP

| Lý do | Tác động |
|---|---|
| Tăng dependency | Dễ phát sinh lỗi access, auth, rate limit, terms of use |
| Không cần cho core valuation | DCF/multiples cần BCTC, giá, shares, peer; Vnstock đủ làm nền MVP |
| Tăng độ phức tạp reconciliation | Hai nguồn structured dễ mâu thuẫn, phải thêm conflict workflow sớm |
| Không phù hợp timeline 6 tuần | Ưu tiên data contract + quality gate hơn mở rộng nguồn |

Kết luận:

```text
Vnstock = primary connector
Manual golden dataset = audit baseline
Supabase = canonical store
FireAnt = out of MVP
```

---

## 3. Data Scope cho 53 cổ phiếu

### 3.1. Universe source of truth

Danh sách 53 mã không được hardcode trong Python. Phải quản lý bằng file config:

```text
data/universe/pharma_vn_53.yaml
```

Schema đề xuất:

```yaml
universe_name: vietnam_pharma_53
market: vietnam
currency: VND
language: vi
source_policy: vnstock_only
expected_ticker_count: 53

coverage_tiers:
  golden: [DHG, TRA, IMP, DBD, DMC]
  full: []
  partial: []
  watchlist: []

tickers:
  - ticker: DHG
    exchange: HOSE
    company_name: "Công ty Cổ phần Dược Hậu Giang"
    subsector: duoc_pham
    enabled: true
    coverage_status: golden
    peer_group: [TRA, IMP, DBD, DMC]
    enabled_valuation_methods: [dcf, pe, pb, ev_ebitda]

  - ticker: TRA
    exchange: HOSE
    company_name: "Công ty Cổ phần Traphaco"
    subsector: duoc_pham
    enabled: true
    coverage_status: golden
    peer_group: [DHG, IMP, DBD, DMC]
    enabled_valuation_methods: [dcf, pe, pb]
```

### 3.2. Rule kiểm soát universe

Trước khi ingestion, hệ thống phải validate:

```text
- expected_ticker_count == 53
- số ticker enabled == 53, trừ khi cố ý disable
- không có ticker trùng
- mỗi ticker có exchange, company_name, subsector
- mỗi ticker có coverage_status
- golden tickers tối thiểu 3 mã
```

Nếu không đủ 53 mã, job `universe_validation` phải fail ngay.

---

## 4. Data Inventory cần thu thập

### 4.1. Nhóm dữ liệu bắt buộc

| Data domain | Bảng đích | Mục đích | Tần suất |
|---|---|---|---|
| Universe metadata | `ref.companies`, `ref.ticker_universe` | Kiểm soát phạm vi 53 mã | Khi config đổi |
| Company profile | `canonical.company_profiles` | Hồ sơ doanh nghiệp, subsector, business description | Hàng tuần |
| Daily prices | `canonical.market_prices_daily` | OHLCV, trend, return, liquidity | Hàng ngày sau giờ giao dịch |
| Market snapshot | `canonical.market_snapshots` | Giá mới nhất, vốn hóa, shares, multiples nếu có | Hàng ngày |
| Income statement | `canonical.financial_facts` | Doanh thu, lợi nhuận, margin | Theo quý/năm |
| Balance sheet | `canonical.financial_facts` | Tài sản, nợ, vốn chủ | Theo quý/năm |
| Cash flow | `canonical.financial_facts` | CFO, capex, FCF proxy | Theo quý/năm |
| Financial ratios | `derived.financial_ratios` | ROE, ROA, margin, leverage, liquidity | Sau khi financial facts đổi |
| Peer metrics | `derived.peer_metrics` | Relative valuation, comparison | Sau khi facts/snapshot đổi |
| News/events nếu Vnstock hỗ trợ | `canonical.news_events` | Catalyst và risk narrative | Hàng ngày hoặc bán tự động |
| Data quality results | `governance.data_quality_checks` | Gate trước report | Mỗi ingestion run |
| Source manifest | `governance.source_manifest` | Citation, audit trail | Mỗi source/payload |
| Fact lineage | `governance.fact_lineage` | Truy vết fact -> raw -> source | Mỗi canonical fact |

### 4.2. Dữ liệu không nên lấy trong MVP

| Dữ liệu | Lý do loại khỏi MVP |
|---|---|
| Intraday tick data | Không cần cho equity research report dài hạn |
| Order book realtime | Không phục vụ DCF hoặc full report |
| Social sentiment | Khó kiểm định, nhiễu cao |
| Dữ liệu ngoài ngành | Gây scope creep |
| Dữ liệu từ nguồn chưa rõ quyền truy cập | Rủi ro compliance/data rights |

---

## 5. Supabase Schema Architecture

### 5.1. Layering

```text
ref.*
  -> dữ liệu tham chiếu: company, universe, peer group

raw.*
  -> payload gốc từ Vnstock, có hash và ingestion_run_id

canonical.*
  -> facts đã chuẩn hóa, được phép dùng cho analytics/report

derived.*
  -> ratios, peer metrics, valuation, snapshots tính bằng code

governance.*
  -> source manifest, lineage, quality checks, conflicts, logs

ops.*
  -> job queue, cron schedule, worker lock, connector health
```

### 5.2. Reference tables

#### `ref.companies`

```sql
create schema if not exists ref;

create table if not exists ref.companies (
  company_id uuid primary key default gen_random_uuid(),
  ticker text not null unique,
  exchange text not null,
  company_name_vi text not null,
  company_name_en text,
  subsector text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

#### `ref.ticker_universe`

```sql
create table if not exists ref.ticker_universe (
  universe_id uuid primary key default gen_random_uuid(),
  universe_name text not null default 'vietnam_pharma_53',
  ticker text not null references ref.companies(ticker),
  coverage_status text not null check (
    coverage_status in ('golden', 'full', 'partial', 'watchlist', 'disabled')
  ),
  priority_rank int not null default 100,
  enabled_valuation_methods text[] not null default array['dcf', 'pe', 'pb'],
  data_quality_target numeric not null default 0.85,
  is_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (universe_name, ticker)
);
```

#### `ref.peer_groups`

```sql
create table if not exists ref.peer_groups (
  peer_group_id uuid primary key default gen_random_uuid(),
  ticker text not null references ref.companies(ticker),
  peer_ticker text not null references ref.companies(ticker),
  peer_group_name text not null,
  rationale text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (ticker, peer_ticker, peer_group_name)
);
```

---

## 6. Raw Data Store

### 6.1. `raw.ingestion_runs`

```sql
create schema if not exists raw;

create table if not exists raw.ingestion_runs (
  ingestion_run_id uuid primary key default gen_random_uuid(),
  job_type text not null,
  ticker text,
  source_provider text not null default 'vnstock',
  status text not null check (
    status in ('queued', 'running', 'success', 'partial_success', 'failed')
  ),
  started_at timestamptz,
  finished_at timestamptz,
  records_fetched int not null default 0,
  records_inserted int not null default 0,
  records_rejected int not null default 0,
  connector_version text,
  parser_version text,
  error_message text,
  created_at timestamptz not null default now()
);
```

### 6.2. `raw.source_payloads`

```sql
create table if not exists raw.source_payloads (
  payload_id uuid primary key default gen_random_uuid(),
  ingestion_run_id uuid not null references raw.ingestion_runs(ingestion_run_id),
  ticker text,
  source_provider text not null default 'vnstock',
  source_endpoint text not null,
  request_params jsonb not null default '{}',
  response_payload jsonb not null,
  payload_hash text not null,
  retrieved_at timestamptz not null default now(),
  unique (source_provider, source_endpoint, payload_hash)
);
```

Raw payload giúp:

```text
- replay ingestion khi parser thay đổi
- debug số liệu sai
- kiểm tra API response gốc
- tránh mất evidence khi canonical transformation có lỗi
```

---

## 7. Canonical Tables

### 7.1. `canonical.market_prices_daily`

```sql
create schema if not exists canonical;

create table if not exists canonical.market_prices_daily (
  price_id uuid primary key default gen_random_uuid(),
  ticker text not null references ref.companies(ticker),
  trade_date date not null,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  adjusted_close numeric,
  volume numeric,
  value_traded numeric,
  source_id uuid not null,
  ingestion_run_id uuid not null references raw.ingestion_runs(ingestion_run_id),
  ingested_at timestamptz not null default now(),
  unique (ticker, trade_date, source_id)
);
```

### 7.2. `canonical.market_snapshots`

```sql
create table if not exists canonical.market_snapshots (
  snapshot_id uuid primary key default gen_random_uuid(),
  ticker text not null references ref.companies(ticker),
  as_of_date date not null,
  close_price numeric,
  market_cap numeric,
  shares_outstanding numeric,
  free_float numeric,
  pe_ttm numeric,
  pb numeric,
  ev_ebitda numeric,
  dividend_yield numeric,
  source_id uuid not null,
  ingestion_run_id uuid not null references raw.ingestion_runs(ingestion_run_id),
  ingested_at timestamptz not null default now(),
  unique (ticker, as_of_date, source_id)
);
```

### 7.3. `canonical.financial_facts`

Đây là bảng quan trọng nhất của hệ thống.

```sql
create table if not exists canonical.financial_facts (
  fact_id uuid primary key default gen_random_uuid(),
  ticker text not null references ref.companies(ticker),
  statement_type text not null check (
    statement_type in ('income_statement', 'balance_sheet', 'cash_flow')
  ),
  line_item_code text not null,
  line_item_name_vi text,
  period_type text not null check (period_type in ('annual', 'quarterly', 'ttm')),
  fiscal_year int not null,
  quarter int,
  period_start date,
  period_end date,
  value numeric not null,
  unit text not null default 'VND',
  currency text not null default 'VND',
  source_id uuid not null,
  ingestion_run_id uuid not null references raw.ingestion_runs(ingestion_run_id),
  confidence numeric not null default 0.80,
  quality_status text not null default 'pending' check (
    quality_status in ('pending', 'passed', 'warning', 'failed', 'manual_review')
  ),
  is_current boolean not null default true,
  restated_as_of date,
  ingested_at timestamptz not null default now(),
  unique (
    ticker,
    statement_type,
    line_item_code,
    period_type,
    fiscal_year,
    quarter,
    source_id
  )
);
```

### 7.4. `canonical.company_profiles`

```sql
create table if not exists canonical.company_profiles (
  profile_id uuid primary key default gen_random_uuid(),
  ticker text not null references ref.companies(ticker),
  company_name text,
  business_description text,
  industry text,
  subsector text,
  listing_date date,
  charter_capital numeric,
  employees int,
  website text,
  source_id uuid not null,
  ingestion_run_id uuid not null references raw.ingestion_runs(ingestion_run_id),
  updated_at timestamptz not null default now(),
  unique (ticker, source_id)
);
```

### 7.5. `canonical.news_events`

News từ Vnstock nếu có coverage ổn. Không dùng news làm nguồn cho số liệu định lượng.

```sql
create table if not exists canonical.news_events (
  event_id uuid primary key default gen_random_uuid(),
  ticker text references ref.companies(ticker),
  event_type text,
  title text not null,
  summary text,
  source_url text,
  published_at timestamptz,
  sentiment_label text,
  severity text check (severity in ('low', 'medium', 'high', 'unknown')) default 'unknown',
  requires_recompute boolean not null default false,
  source_id uuid not null,
  ingestion_run_id uuid not null references raw.ingestion_runs(ingestion_run_id),
  created_at timestamptz not null default now()
);
```

---

## 8. Governance Tables

### 8.1. `governance.source_manifest`

```sql
create schema if not exists governance;

create table if not exists governance.source_manifest (
  source_id uuid primary key default gen_random_uuid(),
  source_type text not null check (
    source_type in (
      'market_data',
      'financial_statement',
      'company_profile',
      'financial_ratio_reference',
      'news',
      'manual_golden_dataset'
    )
  ),
  source_name text not null,
  source_provider text not null default 'vnstock',
  source_url text,
  ticker text,
  period text,
  retrieval_timestamp timestamptz not null default now(),
  reliability text not null check (reliability in ('high', 'medium', 'low')) default 'medium',
  checksum text,
  license_note text,
  created_at timestamptz not null default now()
);
```

### 8.2. `governance.fact_lineage`

```sql
create table if not exists governance.fact_lineage (
  lineage_id uuid primary key default gen_random_uuid(),
  fact_id uuid not null references canonical.financial_facts(fact_id),
  source_id uuid not null references governance.source_manifest(source_id),
  ingestion_run_id uuid not null references raw.ingestion_runs(ingestion_run_id),
  raw_payload_id uuid references raw.source_payloads(payload_id),
  transformation_method text not null,
  parser_version text not null,
  validation_status text not null check (
    validation_status in ('passed', 'warning', 'failed', 'manual_review')
  ),
  created_at timestamptz not null default now(),
  unique (fact_id, source_id, ingestion_run_id)
);
```

### 8.3. `governance.data_quality_checks`

```sql
create table if not exists governance.data_quality_checks (
  check_id uuid primary key default gen_random_uuid(),
  ingestion_run_id uuid references raw.ingestion_runs(ingestion_run_id),
  ticker text,
  check_type text not null,
  severity text not null check (severity in ('info', 'warning', 'error', 'critical')),
  status text not null check (status in ('passed', 'failed', 'skipped')),
  message text not null,
  affected_record_ids uuid[],
  created_at timestamptz not null default now()
);
```

---

## 9. Derived Tables

### 9.1. `derived.financial_ratios`

```sql
create schema if not exists derived;

create table if not exists derived.financial_ratios (
  ratio_id uuid primary key default gen_random_uuid(),
  ticker text not null references ref.companies(ticker),
  period_type text not null check (period_type in ('annual', 'quarterly', 'ttm')),
  fiscal_year int not null,
  quarter int,
  ratio_code text not null,
  value numeric,
  formula_version text not null,
  input_fact_ids uuid[] not null,
  quality_status text not null default 'passed',
  calculated_at timestamptz not null default now(),
  unique (ticker, period_type, fiscal_year, quarter, ratio_code, formula_version)
);
```

### 9.2. `derived.peer_metrics`

```sql
create table if not exists derived.peer_metrics (
  peer_metric_id uuid primary key default gen_random_uuid(),
  ticker text not null references ref.companies(ticker),
  peer_ticker text not null references ref.companies(ticker),
  metric_code text not null,
  fiscal_year int,
  quarter int,
  value numeric,
  source_snapshot_id uuid,
  calculated_at timestamptz not null default now(),
  unique (ticker, peer_ticker, metric_code, fiscal_year, quarter)
);
```

---

## 10. Ops Tables cho Cron và Worker

### 10.1. `ops.ingestion_jobs`

```sql
create schema if not exists ops;

create table if not exists ops.ingestion_jobs (
  job_id uuid primary key default gen_random_uuid(),
  job_type text not null check (
    job_type in (
      'universe_validation',
      'company_profile_refresh',
      'daily_price_refresh',
      'market_snapshot_refresh',
      'financial_statement_refresh',
      'news_refresh',
      'data_quality_recheck',
      'derived_ratio_recompute'
    )
  ),
  ticker text,
  priority int not null default 100,
  status text not null default 'queued' check (
    status in ('queued', 'running', 'success', 'failed', 'cancelled')
  ),
  scheduled_for timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  attempt_count int not null default 0,
  max_attempts int not null default 3,
  payload jsonb not null default '{}',
  locked_by text,
  locked_at timestamptz,
  error_message text,
  created_at timestamptz not null default now()
);
```

---

## 11. Cron Schedule đề xuất

Cron chỉ nên enqueue job. Python worker mới là nơi gọi Vnstock và xử lý dữ liệu.

| Job | Lịch | Scope | Mục tiêu |
|---|---|---|---|
| `universe_validation` | Mỗi ngày 07:00 | 53 mã | Đảm bảo universe config hợp lệ |
| `company_profile_refresh` | Chủ nhật 01:00 | 53 mã | Refresh hồ sơ công ty |
| `daily_price_refresh` | Ngày giao dịch 17:00 | 53 mã | Lấy OHLCV sau giờ đóng cửa |
| `market_snapshot_refresh` | Ngày giao dịch 17:15 | 53 mã | Cập nhật close price, market cap, multiples |
| `financial_statement_refresh` | Mỗi ngày 18:00 trong mùa BCTC | 53 mã | Check BCTC quý/năm mới |
| `news_refresh` | 08:00 và 17:30 | 53 mã | Cập nhật tin tức nếu Vnstock hỗ trợ |
| `data_quality_recheck` | Chủ nhật 02:00 | 53 mã | Recompute completeness/conflict/staleness |
| `derived_ratio_recompute` | Sau financial update | Ticker changed | Tính lại ratios/peer metrics |

### 11.1. Cron enqueue example

```sql
insert into ops.ingestion_jobs (job_type, ticker, priority, payload)
select
  'daily_price_refresh',
  ticker,
  50,
  jsonb_build_object('source_provider', 'vnstock')
from ref.ticker_universe
where universe_name = 'vietnam_pharma_53'
  and is_enabled = true;
```

---

## 12. Python Worker Design

### 12.1. Module structure

```text
backend/app/
├── connectors/
│   ├── vnstock_client.py
│   └── source_registry.py
├── dataops/
│   ├── ingestion.py
│   ├── normalization.py
│   ├── quality_checks.py
│   ├── source_manifest.py
│   ├── lineage.py
│   └── job_runner.py
├── repositories/
│   ├── supabase_client.py
│   ├── raw_repository.py
│   ├── canonical_repository.py
│   ├── governance_repository.py
│   └── ops_repository.py
└── scripts/
    ├── seed_universe.py
    ├── backfill_53_tickers.py
    ├── refresh_daily_prices.py
    ├── refresh_financial_statements.py
    └── run_data_quality.py
```

### 12.2. Worker lifecycle

```text
1. Poll ops.ingestion_jobs where status='queued'.
2. Lock job bằng locked_by + locked_at.
3. Tạo raw.ingestion_runs.
4. Gọi Vnstock connector.
5. Lưu raw.source_payloads.
6. Normalize response thành canonical rows.
7. Tạo source_manifest.
8. Insert/upsert canonical tables.
9. Tạo fact_lineage.
10. Chạy data quality checks.
11. Nếu pass, mark canonical records quality_status='passed'.
12. Nếu fail, mark manual_review/failed và không cho report sử dụng.
13. Update job status + ingestion run status.
```

### 12.3. Idempotency rules

Worker phải idempotent:

```text
- Cùng ticker + period + line_item + source_id không tạo duplicate.
- Payload trùng hash không ingest lại nếu parser_version không đổi.
- Nếu parser_version đổi, cho phép replay raw payload.
- Job retry không được tạo nhiều canonical facts giống nhau.
```

---

## 13. Normalization Contract

### 13.1. Financial line item taxonomy

Không dùng tên line item raw từ Vnstock trực tiếp trong valuation. Phải map vào taxonomy nội bộ.

Ví dụ:

```yaml
income_statement:
  revenue:
    vi: "Doanh thu thuần"
    aliases:
      - "Doanh thu bán hàng và cung cấp dịch vụ"
      - "Doanh thu thuần về bán hàng và cung cấp dịch vụ"
  gross_profit:
    vi: "Lợi nhuận gộp"
  operating_profit:
    vi: "Lợi nhuận thuần từ hoạt động kinh doanh"
  profit_before_tax:
    vi: "Lợi nhuận trước thuế"
  net_income:
    vi: "Lợi nhuận sau thuế"

balance_sheet:
  total_assets:
    vi: "Tổng tài sản"
  cash_and_equivalents:
    vi: "Tiền và tương đương tiền"
  short_term_debt:
    vi: "Vay và nợ thuê tài chính ngắn hạn"
  long_term_debt:
    vi: "Vay và nợ thuê tài chính dài hạn"
  total_liabilities:
    vi: "Nợ phải trả"
  total_equity:
    vi: "Vốn chủ sở hữu"

cash_flow:
  operating_cash_flow:
    vi: "Lưu chuyển tiền thuần từ hoạt động kinh doanh"
  investing_cash_flow:
    vi: "Lưu chuyển tiền thuần từ hoạt động đầu tư"
  financing_cash_flow:
    vi: "Lưu chuyển tiền thuần từ hoạt động tài chính"
  capex:
    vi: "Chi mua sắm, xây dựng TSCĐ"
```

### 13.2. Unit policy

Canonical layer phải thống nhất đơn vị:

```text
currency = VND
unit = VND
```

Nếu Vnstock trả về nghìn đồng, triệu đồng hoặc tỷ đồng, normalization phải convert về VND và lưu transformation method:

```text
raw_value=1234
raw_unit='billion_vnd'
canonical_value=1234000000000
unit='VND'
transformation_method='multiply_by_1e9_from_billion_vnd'
```

---

## 14. Data Quality Gates

### 14.1. Gate cho financial facts

Một ticker chỉ được phép chạy full report nếu pass các checks sau:

| Check | Rule |
|---|---|
| Revenue availability | Có `revenue` tối thiểu 3 năm |
| Net income availability | Có `net_income` tối thiểu 3 năm |
| Total assets availability | Có `total_assets` tối thiểu 3 năm |
| Total equity availability | Có `total_equity` tối thiểu 3 năm |
| Cash flow availability | Có `operating_cash_flow` tối thiểu 3 năm, nếu không phải flag warning |
| Market price availability | Có close price mới nhất |
| Source manifest | Mỗi fact có source_id hợp lệ |
| Lineage | Mỗi fact có fact_lineage |
| Unit consistency | Các facts tài chính dùng cùng currency/unit canonical |
| Freshness | Market data không quá stale so với ngày chạy report |

### 14.2. Completeness score

```text
completeness_score =
  0.25 * price_data_score
+ 0.35 * financial_statement_score
+ 0.15 * company_profile_score
+ 0.10 * peer_data_score
+ 0.10 * source_lineage_score
+ 0.05 * news_event_score
```

Interpretation:

| Score | Action |
|---:|---|
| `>= 0.85` | Được chạy full report |
| `0.70 - 0.85` | Partial report hoặc needs human review |
| `< 0.70` | Không chạy valuation/report tự động |

### 14.3. Hard fail conditions

```text
- Missing revenue
- Missing net_income
- Missing total_assets
- Missing total_equity
- Missing latest market price
- source_manifest empty
- financial_facts without source_id
- fact_lineage missing
- fiscal_year < 3 years available
- unit cannot be normalized
```

---

## 15. Backfill Plan cho 53 mã

### 15.1. Backfill order

Không backfill ngẫu nhiên. Chạy theo coverage tier:

```text
Phase A: Golden tickers
  DHG, TRA, IMP, DBD, DMC hoặc danh sách golden đã chốt

Phase B: Full coverage candidates
  10-15 mã có dữ liệu tốt nhất

Phase C: Remaining enabled tickers
  toàn bộ 53 mã

Phase D: Watchlist/manual review
  mã thiếu dữ liệu hoặc có lỗi parser
```

### 15.2. Backfill sequence cho mỗi ticker

```text
1. Validate ticker exists in pharma_vn_53.yaml.
2. Fetch company profile from Vnstock.
3. Fetch historical OHLCV prices.
4. Fetch financial statements: income statement, balance sheet, cash flow.
5. Fetch market snapshot and available multiples.
6. Optional: fetch news/events if Vnstock supports it reliably.
7. Save raw payloads.
8. Normalize into canonical tables.
9. Generate source manifest.
10. Generate fact lineage.
11. Run data quality checks.
12. Compute derived ratios.
13. Mark ticker coverage_status based on completeness_score.
```

### 15.3. Expected milestones

| Tuần | Mục tiêu dữ liệu | Done criteria |
|---|---|---|
| Week 1 | Supabase schema + universe config | 53 mã validate pass |
| Week 2 | Backfill profile + prices | 53/53 có profile cơ bản và price history |
| Week 3 | Backfill BCTC golden | 3–5 golden tickers có BCTC 3–5 năm |
| Week 4 | Backfill BCTC toàn universe | >= 80% ticker có financial facts tối thiểu |
| Week 5 | Data quality + derived ratios | Golden tickers completeness >= 0.85 |
| Week 6 | Report-ready dataset | Golden tickers chạy report package có citation |

---

## 16. Golden Dataset Strategy

### 16.1. Golden tickers đề xuất

```text
DHG
TRA
IMP
DBD
DMC
```

Lý do chọn nhóm này:

```text
- Có tính đại diện cho ngành dược niêm yết.
- Thường có dữ liệu công bố tương đối đầy đủ.
- Phù hợp để kiểm thử DCF, multiples và peer comparison.
```

### 16.2. Golden dataset files

```text
data/golden/
├── DHG/
│   ├── company_profile.yaml
│   ├── financial_facts_audited.csv
│   ├── market_prices_sample.csv
│   ├── expected_ratios.csv
│   ├── valuation_assumptions.yaml
│   └── source_manifest.yaml
├── TRA/
├── IMP/
├── DBD/
└── DMC/
```

### 16.3. Golden validation targets

| Metric | Target |
|---|---:|
| Field extraction accuracy | >= 98% |
| Unit normalization accuracy | 100% |
| Required line item coverage | >= 95% |
| Source lineage coverage | 100% |
| Ratio recomputation consistency | 100% unit tests pass |
| Numeric consistency in report | >= 99% |

---

## 17. Integration với Report Agent

Agent không được gọi Vnstock trực tiếp. Agent chỉ đọc:

```text
canonical.financial_facts
canonical.market_prices_daily
canonical.market_snapshots
canonical.company_profiles
derived.financial_ratios
derived.peer_metrics
governance.source_manifest
governance.fact_lineage
```

Luồng report:

```text
User chọn ticker
  -> Orchestrator tạo research_run
  -> Data readiness check
  -> Nếu completeness_score >= 0.85
  -> Core Analyst đọc canonical/derived tables
  -> Valuation engine tính bằng code
  -> Synthesis Agent viết report từ artifacts
  -> Auditor kiểm citation/numeric consistency
```

Không cho phép:

```text
- LLM tự tạo số liệu.
- LLM tự gọi Vnstock.
- LLM dùng raw payload trực tiếp để suy luận số cuối.
- Report xuất hiện số không có fact_id/source_id.
```

---

## 18. Monitoring Queries

### 18.1. Kiểm tra số ticker trong universe

```sql
select
  universe_name,
  count(*) filter (where is_enabled = true) as enabled_count,
  count(*) as total_count
from ref.ticker_universe
group by universe_name;
```

### 18.2. Kiểm tra ticker thiếu giá

```sql
select u.ticker
from ref.ticker_universe u
left join canonical.market_prices_daily p
  on u.ticker = p.ticker
where u.is_enabled = true
group by u.ticker
having count(p.price_id) = 0;
```

### 18.3. Kiểm tra ticker thiếu BCTC

```sql
select u.ticker
from ref.ticker_universe u
left join canonical.financial_facts f
  on u.ticker = f.ticker
where u.is_enabled = true
group by u.ticker
having count(f.fact_id) = 0;
```

### 18.4. Kiểm tra financial facts thiếu lineage

```sql
select f.fact_id, f.ticker, f.line_item_code, f.fiscal_year, f.quarter
from canonical.financial_facts f
left join governance.fact_lineage l
  on f.fact_id = l.fact_id
where l.lineage_id is null;
```

### 18.5. Kiểm tra job fail gần nhất

```sql
select *
from ops.ingestion_jobs
where status = 'failed'
order by finished_at desc nulls last, created_at desc
limit 50;
```

---

## 19. Acceptance Criteria

### 19.1. Data foundation done

```text
- Supabase có đầy đủ schemas: ref, raw, canonical, derived, governance, ops.
- data/universe/pharma_vn_53.yaml validate đúng 53 mã.
- Backfill profile và price history chạy được cho 53 mã.
- Backfill BCTC chạy được cho ít nhất 3–5 golden tickers.
- Mỗi canonical financial fact có source_id và lineage.
- Data quality checks sinh kết quả cho từng ticker.
```

### 19.2. Report readiness done

```text
- Golden tickers có completeness_score >= 0.85.
- Report agent không gọi Vnstock trực tiếp.
- Valuation engine chỉ đọc canonical/derived artifacts.
- 100% claim định lượng trong report golden có source_id.
- Numeric consistency >= 99% trên golden reports.
```

### 19.3. Cron/worker done

```text
- Cron enqueue job theo lịch.
- Python worker xử lý job idempotent.
- Retry không tạo duplicate canonical facts.
- Job failures được log vào ops.ingestion_jobs và raw.ingestion_runs.
- Có query monitor coverage, freshness, failed jobs.
```

---

## 20. Implementation Prompts cho Claude/Codex

### Prompt 1 — Supabase schema

```text
Task: Implement Supabase SQL schema for Vnstock-only data ingestion.

Scope:
- Create schemas: ref, raw, canonical, derived, governance, ops.
- Implement tables exactly from DATA_INGESTION_PLAN_SUPABASE_VNSTOCK.md.
- Add primary keys, unique constraints, check constraints, and required foreign keys.

Files allowed:
- supabase/migrations/*.sql
- docs/DATA_INGESTION_PLAN_SUPABASE_VNSTOCK.md only if needed

Acceptance criteria:
- Migration runs without error.
- Tables exist with expected constraints.
- No FireAnt tables or connector-specific dependencies.
```

### Prompt 2 — Vnstock connector

```text
Task: Implement Vnstock-only connector adapter.

Scope:
- Create backend/app/connectors/vnstock_client.py.
- Methods: fetch_company_profile, fetch_price_history, fetch_market_snapshot, fetch_financial_statements, fetch_news_events_optional.
- Do not expose Vnstock raw API calls outside this adapter.

Acceptance criteria:
- Connector returns typed Python objects or dicts normalized enough for dataops layer.
- All calls include ticker, source_endpoint, request_params, retrieved_at.
- No direct Vnstock imports outside vnstock_client.py.
```

### Prompt 3 — Ingestion worker

```text
Task: Implement ingestion job runner for Supabase + Vnstock.

Scope:
- Poll ops.ingestion_jobs.
- Lock queued jobs.
- Create raw.ingestion_runs.
- Call vnstock_client.
- Save raw.source_payloads.
- Normalize to canonical tables.
- Create source_manifest and fact_lineage.
- Run quality checks.

Acceptance criteria:
- Worker is idempotent.
- Retry does not duplicate canonical facts.
- Job status and ingestion_run status are always updated.
- Failed jobs include error_message.
```

### Prompt 4 — Data quality gates

```text
Task: Implement data quality checks for canonical financial facts.

Scope:
- Required field checks.
- Unit normalization checks.
- Minimum 3 fiscal years for golden tickers.
- Missing revenue/net_income/total_assets/total_equity hard fail.
- Completeness score calculation.

Acceptance criteria:
- Golden tickers produce data quality reports.
- Records failing hard checks are not marked quality_status='passed'.
- Completeness score can determine full_report eligibility.
```

---

## 21. Final Decision Record

```text
Decision ID: DATA-001
Title: Use Vnstock as the only structured data source for MVP
Status: Accepted
Date: 2026-05-07

Context:
The project needs reliable, reproducible, Python-based data ingestion for 53 Vietnamese pharma/healthcare stocks into Supabase. The MVP prioritizes canonical facts, data lineage, code-first valuation, and citation-first reporting.

Decision:
Use Vnstock as the only structured data connector in MVP. Do not integrate FireAnt in MVP. Use manual golden datasets for validation and official documents later only as audit references when needed.

Consequences:
- Lower implementation complexity.
- Faster 6-week delivery.
- Easier Python worker integration.
- Less source reconciliation overhead.
- Need strong data quality checks because Vnstock data still cannot be treated as unverified truth.

Non-negotiable rule:
Every report number must trace back to canonical facts with source_id and lineage.
```
