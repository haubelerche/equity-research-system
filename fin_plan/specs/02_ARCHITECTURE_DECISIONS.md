# 02 — Architecture Decisions

**Date:** 2026-05-22
**Status:** Active — update this file before any major structural change.

---

## ADR-001 — Keep Connectors in `scripts/connectors/`, not `backend/connectors/`

**Date:** 2026-05-22
**Status:** Accepted

**Context:**
CLAUDE.md proposes `backend/connectors/` as the connector location. The existing repository has connectors under `scripts/connectors/`. Both locations are valid Python packages. Moving them would require updating all imports across `backend/dataset/`, `backend/database/`, and any orchestrator integrations.

**Decision:**
Keep connectors under `scripts/connectors/` for now. Create a thin `backend/connectors/` re-export layer only when the backend agents need to call connectors directly (Phase 8+). Do not move or duplicate the connector implementations.

**Consequences:**
- Avoids large refactor before Phase 2 is even working.
- Scripts and backend share the same connector code via `scripts/connectors/`.
- Revisit for Phase 8 if the backend orchestrator needs to import connectors at runtime.

---

## ADR-002 — PostgreSQL as the Operational Store

**Date:** 2026-05-22
**Status:** Accepted

**Context:**
The existing `PostgresFactStore` and `SourceRegistry` assume a PostgreSQL database. All connectors write to Postgres tables: `financial_facts`, `price_history`, `company_profiles`, `catalyst_events`, `source_versions`.

**Decision:**
Keep PostgreSQL as the single operational store. The database schema must exist before any connector can run.

**Required tables:**
```sql
financial_facts
price_history
company_profiles
catalyst_events
source_versions
```

**Consequences:**
- All environments use Supabase PostgreSQL. `DATABASE_URL` is required; local PostgreSQL fallbacks are prohibited.
- If PostgreSQL is unavailable, connectors fail loudly — no silent degradation.

**Outstanding:** The SQL migration/init script is not yet committed to this repository. This is a blocker for new contributors. Add a `db/migrations/` or `backend/database/init_schema.sql` in Phase 2.

---

## ADR-003 — PostgreSQL/pgvector for Vector Search (Evidence Retrieval)

**Date:** 2026-05-22
**Status:** Deferred (Phase 5)

**Context:**
`backend/retrieval.py` and the chunk embedding pipeline now use PostgreSQL with `pgvector` for document chunk retrieval.

**Decision:**
Keep embeddings in `ingest.document_chunks` and use PostgreSQL as the single retrieval backend. Do not introduce a separate vector database unless scale or isolation requirements materially exceed the MVP envelope.

**Consequences:**
- Phases 2–4 have no additional vector service dependency.
- Retrieval, metadata filters, and embeddings stay in one operational store.
- The citation pipeline can run on Supabase/Postgres without Milvus.

---

## ADR-004 — Deterministic Services vs LLM Agents

**Date:** 2026-05-22
**Status:** Accepted

**Context:**
The backend `agents.py` has stubs for DataAgent, QuantAgent, ResearcherAgent, DebateAgent, AuditorAgent. The risk is that agent stubs return placeholder data, giving the illusion of functionality.

**Decision:**
Follow the CLAUDE.md separation strictly:

| Role | Implementation | LLM? |
|---|---|---|
| Ingestion | `scripts/connectors/` services | No |
| Fact normalization | `backend/facts/normalizer.py` | No |
| DQF validation | `backend/dataset/dqf.py` | No |
| Valuation | `backend/valuation/` modules | No |
| Citation validation | `backend/citations/validator.py` | Minimal |
| Evidence retrieval | `backend/retrieval/retriever.py` | No (vector search) |
| Narrative synthesis | `ResearcherAgent` | Yes |
| Audit / evaluation | `AuditorAgent` + evaluation modules | Mostly No |
| Run orchestration | `Supervisor` | No |

**Consequences:**
- DataAgent must call real connector services, not generate data.
- QuantAgent must call real valuation modules, not estimate.
- ResearcherAgent is the only module allowed to call an LLM for synthesis.
- AuditorAgent orchestrates deterministic evaluation checks; LLM only for unsupported claim detection.

---

## ADR-005 — File-Based Raw Snapshot Storage

**Date:** 2026-05-22
**Status:** Accepted

**Context:**
Each connector saves a raw JSON snapshot to disk before writing to PostgreSQL. The `SourceRegistry.save_raw_snapshot()` method writes to `data/raw/`.

**Decision:**
Keep file-based raw snapshots. Each snapshot is checksum-deduplicated and registered in `source_versions`. This provides an audit trail independent of the database.

**Directory structure:**
```text
data/raw/bctc/<ticker>/income_statement_quarter.json
data/raw/bctc/<ticker>/balance_sheet_quarter.json
data/raw/bctc/<ticker>/cash_flow_quarter.json
data/raw/bctc/<ticker>/ratio_quarter.json
data/raw/market/<date>/<ticker>_quote_history.json
data/raw/market/<date>/<ticker>_overview.json
```

**Consequences:**
- Raw data is auditable without querying PostgreSQL.
- Disk usage grows per sync; periodic cleanup of old snapshots may be needed.
- `data/` is ignored by git; source-controlled dataset config lives under `config/dataset/`.

---

## ADR-006 — Ingestion Entry Point Design

**Date:** 2026-05-22
**Status:** Accepted (Phase 2)

**Context:**
The existing connectors each have a `main()` function that can be called independently, but there is no unified entry point to ingest all data types for a single ticker in one command.

**Decision:**
Create `scripts/ingest_ticker.py` as the unified ingestion entry point. It:
1. Accepts `--ticker` and `--years` arguments.
2. Calls finance, price, and company connectors in order.
3. Calls available catalyst connectors.
4. Prints a data inventory summary to stdout.
5. Saves the inventory JSON to `artifacts/runs/<ticker>_<timestamp>_inventory.json`.
6. Exits with code 0 on success, non-zero on error.

**Consequences:**
- Analysts can ingest a ticker with a single command.
- Each sub-connector is still independently callable for partial refreshes.
- The inventory JSON becomes the input to Phase 3 (fact building).

---

## ADR-007 — No LLM Calls in Phases 0–4

**Date:** 2026-05-22
**Status:** Accepted

**Context:**
Phases 0–4 are purely about data ingestion, normalization, and valuation. Introducing LLM calls early adds cost, latency, and non-determinism before we have reliable data to feed them.

**Decision:**
No LLM API calls in Phases 0–4. All code in these phases must be deterministic Python.

**Consequences:**
- No `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` required to run Phases 0–4.
- Phase 6 (report generation) is the first phase that requires an LLM API key.
- Agent runtime is configured through `config/agents/` and executed through `backend/harness`; no standalone agent-stub package is retained.

---

## ADR-009 — vnstock 4.x API Migration and Free-Tier Empirical Limits

**Date:** 2026-05-22
**Status:** Accepted — updated 2026-05-22 with empirical coverage evidence

**Context:**
The connectors were written against the old `Vnstock(symbol, source).finance.xxx()` API. vnstock 4.0.4 (the installed version) deprecates this API. The local `vnstock/` reference folder also targets the 4.x API.

**Decision:**
Update all connectors to use `vnstock.api.*` classes:
- `Finance(source, symbol)` replaces `Vnstock.finance`
- `Quote(source, symbol)` replaces `Vnstock.quote` (parameter: `start=`, `end=`, not `start_date=`)
- `Company(source, symbol)` replaces `Vnstock.company`

**Additional changes:**
- Vietnamese labels require Unicode normalization (NFD + Mn-strip) before slugifying to match taxonomy aliases.
- The alias map must be filtered by `statement` type to prevent ratio-sheet metrics from matching income_statement taxonomy keys.
- Values from Finance API are raw VND; divide by 1e9 for `vnd_bn` unit metrics.
- Use `period="year"` (not `period="quarter"`) as the default ingestion mode. See empirical evidence below.
- Provider fallback order: VCI → KBS (for financials). KBS is preferred for ratio statements.

**Empirical Free-Tier Coverage (measured 2026-05-22 via `scripts/debug_vnstock_financial_coverage.py`):**

vnstock announces at runtime: *"Phiên bản cộng đồng: Báo cáo tài chính được giới hạn tối đa 4 kỳ"*
(Community version: financial statements limited to 4 periods maximum)

| period= | What is returned | Fiscal years covered | Notes |
|---------|-----------------|---------------------|-------|
| `year` | 4 most recent fiscal years | 2022, 2023, 2024, 2025 | **Recommended for trend analysis** |
| `quarter` | 4 most recent quarters | 2025 Q1–Q4 or 2025–2026 | Limited; only ~1 year of data |

Coverage results for all 5 MVP tickers (measured 2026-05-22, VCI provider, `period=year`):

| Ticker | IS ok | BS ok | CF ok | Years | Notes |
|--------|-------|-------|-------|-------|-------|
| DHG | yes | yes | yes | 4 (2022–2025) | pass |
| IMP | yes | yes | yes | 4 (2022–2025) | pass |
| DMC | yes | yes | yes | 4 (2022–2025) | pass |
| TRA | yes | yes | yes | 4 (2022–2025) | pass |
| DBD | yes | yes | yes | 4 (2022–2025) | pass |

All 5 tickers: `status=ok`, `years=4`, `periods=4`, nonzero cells 80–120+ per statement.
No ticker returned 5 years on the community tier. The hard cap is 4 fiscal years for financial statements.

VCI ratio/year anomaly: returns 16 columns but all from 2018 with 0 nonzero cells. Use KBS for ratio data.

Rate limits (measured):
- Guest (no key): 20 req/min → hits limit after 1 ticker (16 fetches/ticker)
- Community (free API key): 60 req/min
- Mitigation: 65 s sleep between tickers in `debug_vnstock_financial_coverage.py --inter-ticker-sleep 65`

**Consequences:**
- Connectors now produce correct `vnd_bn` values (e.g., DHG FY2025 gross_profit ≈ 798 VND bn).
- `period="year"` is the default in `sync_financial_for_ticker` and `ingest_ticker.py --period year`.
- On the free tier, 4 years of annual history is the maximum available regardless of `--years` flag value.
- To obtain more than 4 years of annual data or more than 4 recent quarters, a paid vnstock subscription is required. This is a hard API constraint, not a connector limitation.
- Price history (Quote API) is not subject to the 4-period cap; full history is returned.
- `artifacts/data_quality/unmatched_financial_items.csv` records all Vietnamese labels not matched by the taxonomy, enabling iterative taxonomy expansion without silent drops.

---

## ADR-010 — MVP Financial Pipeline is FY-Only (2021FY–2025FY)

**Date:** 2026-05-23
**Status:** Accepted

**Context:**
Early ingestion runs stored both annual (FY) and quarterly (Q1–Q4) financial facts in the
database. The quarterly data was returned by the vnstock community API as part of its 4-period
response even when `period="quarter"` was not explicitly requested, or from prior experimental
runs. Mixing annual and quarterly facts caused two problems:

1. `build_facts.py` computed completeness and freshness over a mix of period types, inflating
   scores and masking missing annual years (e.g., `2026Q1` was counted toward freshness while
   `2021FY` was absent).
2. `latest_fiscal_year` could be inferred as `2026` from a quarterly period, giving a false
   impression of current data.

**Decision:**
For the MVP financial pipeline, the only accepted periods are the five annual fiscal years:

```
2021FY  2022FY  2023FY  2024FY  2025FY
```

Enforcement is layered across three modules:

| Layer | File | Rule enforced |
|---|---|---|
| Ingestion guard | `scripts/ingest_ticker.py` | `--period quarter` is rejected with exit code 1 |
| Connector filter | `scripts/connectors/vnstock_finance_connector.py` | Facts with `fiscal_period != 'FY'` or `fiscal_year` outside [from_year, to_year] are dropped before upsert |
| Fact-build filter | `scripts/build_facts.py` | Raw DB rows are filtered to `YYYYFY` with `2021 ≤ YYYY ≤ 2025` before building the fact table; forbidden periods are logged |
| Gate | `backend/facts/completeness.py` | `gate_status = "pass"` only when all five FY periods are present and all five core keys exist for each period |
| Cleanup | `scripts/cleanup_financial_facts.py` | Safely removes existing quarterly rows; defaults to `--dry-run` |

**Core keys required per FY period for gate pass:**
```
revenue.net
net_income.parent
total_assets.ending
equity.parent
operating_cash_flow.total
```

**vnstock free-tier implication:**
The community API returns at most 4 fiscal years. This means `2021FY` will be absent for all
tickers unless a fallback source is used. The correct system response is:

```
gate_status   = fail
valuation_ready = false
run_status    = needs_fallback
```

**Fallback source (future):** `config/dataset/golden/financials/{ticker}.csv` — annual FY rows only,
no quarterly rows permitted. If fallback provides `2021FY`, merge with vnstock annual data for
`2022FY–2025FY`. Every merged fact must preserve source lineage.

**Quarterly data must not be used for:**
- canonical financial facts
- completeness or freshness scoring
- valuation readiness
- annual report generation
- fallback reconstruction

**Consequences:**
- All tickers will report `gate_status = fail` until a `2021FY` fallback is implemented.
- `latest_fiscal_year` will correctly report `2025` (not `2026` from a stale quarterly row).
- `2026Q1` and all other quarterly periods are silently ignored at the fact-build layer.
- `scripts/cleanup_financial_facts.py --ticker <T> --remove-quarterly --confirm` can purge
  legacy quarterly rows from the database.
- Scaling to valuation (Phase 4) is blocked until all 5 FY periods pass the gate.

---

## ADR-008 — `--years` Argument Maps to Price History Days

**Date:** 2026-05-22
**Status:** Accepted (Phase 2)

**Context:**
`scripts/ingest_ticker.py --ticker DHG --years 5` should control how much historical data to fetch. Price history uses `days_back`; financial statements return all available quarters from vnstock regardless.

**Decision:**
- `--years N` → `days_back = N * 365` for price history.
- Financial statements: fetch all available quarters (vnstock returns its full history by default; no year filter applied since filtering is done post-ingestion).
- `--years` is advisory for price; financial statements always return the full available history.

**Consequences:**
- The `--years 5` flag is semantically accurate for price data.
- Financial statement history depends on vnstock's API, not our filter.

---

## ADR: Source-Provenance Rebuild adapted onto the Data Trust Layer (2026-05-30)

**Context:** The `.claude/claude_source_provenance_plans/` (8 phases) specify literal new
tables — `acquisition_sources`, `official_documents`, `verified_financial_facts`,
`fact_reconciliation_results`. The repo already has an applied Data Trust Layer
(migrations 009–012) implementing ~80% of that under different names.

**Decision:** Adapt the plans onto the existing schema rather than create duplicate
tables (CLAUDE.md §3 source-of-truth priority; §6 "adapt carefully instead of creating
duplicate structures"). Mapping:

| Plan table | Realized as |
|---|---|
| acquisition_sources | `ingest.sources` + `ingest.raw_payloads` + `ingest.parser_runs` |
| official_documents | **NEW** `ingest.official_documents` (migration 013) |
| verified_financial_facts | `fact.canonical_facts` + verification columns + view `fact.verified_financial_facts` |
| fact_reconciliation_results | `fact.fact_reconciliation` |

**Verification-layer rule:** `ingest.official_documents` is Tier 0–2 only (CHECK). A
canonical fact cannot be marked `matched_official`/`manual_reviewed` without an
`official_document_id` (CHECK `chk_verified_requires_official_doc`). Final reports read
numeric claims from `fact.verified_financial_facts`.

**Consequences:** No competing fact model; the acquisition vs verification separation is
enforced at the DB layer. Missing official PDFs ⇒ `verified_financial_facts` is empty ⇒
final export correctly blocked until documents are ingested (Phase 3).
