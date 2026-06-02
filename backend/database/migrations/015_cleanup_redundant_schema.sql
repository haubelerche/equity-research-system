-- Migration: 015_cleanup_redundant_schema.sql
-- Purpose: Remove dead schema objects and fix corrupted seed data.
--
-- 1. Fix corrupted Vietnamese company names in ref.companies (005 had N'' T-SQL prefix
--    that mangled multi-byte characters to '?').
-- 2. Drop fact.financial_facts_legacy view — unused alias, no code reads it.
-- 3. Drop research schema reporting tables superseded by report schema (012):
--      research.claim_evidence, research.report_claims, research.report_sections,
--      research.evaluation_results, research.valuation_results,
--      research.valuation_assumption_sets, research.metric_values.
--    Also drop the trigger + function + views that guarded those tables:
--      trg_final_report_approval_guard, final_report_approval_guard(),
--      quantitative_claims_without_evidence, invalid_claim_evidence.
--
-- What is NOT touched:
--   - research.runs, run_steps, run_approvals, run_budget_ledger, run_audit_events
--     (all actively used by runtime_store.py)
--   - research.snapshots, snapshot_items, data_quality_reports
--     (used by dataops/snapshot.py and dataops/quality_report.py)
--   - report.* tables (012) — target architecture, Python DAL pending
--   - fact.financial_facts — still the active write target
--   - fact.canonical_facts, fact_observations, fact_reconciliation
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

-- ── 1. Fix corrupted company names ────────────────────────────────────────────
-- The original seed (005) used N'...' (T-SQL national-string syntax) which caused
-- UTF-8 multi-byte characters to be stored as '?' placeholders.

UPDATE ref.companies SET
    company_name_vi = 'Công ty Cổ phần Dược Hậu Giang',
    company_name_en = 'Duoc Hau Giang Pharmaceutical JSC',
    updated_at = NOW()
WHERE ticker = 'DHG';

UPDATE ref.companies SET
    company_name_vi = 'Công ty Cổ phần Imexpharm',
    company_name_en = 'Imexpharm Corporation',
    updated_at = NOW()
WHERE ticker = 'IMP';

UPDATE ref.companies SET
    company_name_vi = 'Công ty Cổ phần Xuất nhập khẩu Y tế Domesco',
    company_name_en = 'Domesco Medical Import-Export JSC',
    updated_at = NOW()
WHERE ticker = 'DMC';

UPDATE ref.companies SET
    company_name_vi = 'Công ty Cổ phần Traphaco',
    company_name_en = 'Traphaco JSC',
    updated_at = NOW()
WHERE ticker = 'TRA';

UPDATE ref.companies SET
    company_name_vi = 'Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định',
    company_name_en = 'Bidiphar JSC',
    updated_at = NOW()
WHERE ticker = 'DBD';

-- ── 2. Drop fact.financial_facts_legacy view ──────────────────────────────────
-- Created in 011 as a backward-compat alias for fact.financial_facts.
-- No Python code uses it; the original table is still the active write target.

DROP VIEW IF EXISTS fact.financial_facts_legacy;

-- ── 3. Drop research schema guard objects ─────────────────────────────────────
-- The approval guard trigger reads from research.report_claims and
-- research.claim_evidence. Dropping it first prevents cascade errors when those
-- tables are removed. The research.run_approvals table itself stays — it is
-- actively used by runtime_store.py.

DROP TRIGGER IF EXISTS trg_final_report_approval_guard ON research.run_approvals;
DROP FUNCTION IF EXISTS research.final_report_approval_guard();

-- Views that reference the soon-to-be-dropped tables.
DROP VIEW IF EXISTS research.quantitative_claims_without_evidence;
DROP VIEW IF EXISTS research.invalid_claim_evidence;

-- ── 4. Drop unused research schema tables ─────────────────────────────────────
-- Drop in FK-dependency order (children before parents).

-- claim_evidence references report_claims
DROP TABLE IF EXISTS research.claim_evidence;

-- report_claims references report_sections (nullable FK ON DELETE SET NULL)
DROP TABLE IF EXISTS research.report_claims;

-- report_sections has no remaining downstream FK after claim tables gone
DROP TABLE IF EXISTS research.report_sections;

-- evaluation_results: standalone, no downstream FKs
DROP TABLE IF EXISTS research.evaluation_results;

-- valuation_results references valuation_assumption_sets
DROP TABLE IF EXISTS research.valuation_results;

-- valuation_assumption_sets: safe to drop once valuation_results gone
DROP TABLE IF EXISTS research.valuation_assumption_sets;

-- metric_values references ref.formulas and ref.companies only (both kept)
DROP TABLE IF EXISTS research.metric_values;
