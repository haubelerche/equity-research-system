-- Migration: 016_v2_ref_layer.sql
-- Purpose: Data Warehouse v2, Step 1 — create v2_ref schema with clean reference tables.
-- Built side-by-side with legacy ref.* schemas; does not touch any existing table.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS v2_ref;

-- ── v2_ref.companies ──────────────────────────────────────────────────────────
-- Canonical company master. Migrated from ref.companies (names already fixed in 015).
CREATE TABLE IF NOT EXISTS v2_ref.companies (
    ticker           VARCHAR(10)  PRIMARY KEY,
    company_name_vi  TEXT         NOT NULL,
    company_name_en  TEXT,
    exchange         VARCHAR(10)  NOT NULL CHECK (exchange IN ('HOSE', 'HNX', 'UPCOM')),
    sector           TEXT         NOT NULL DEFAULT 'pharma',
    subsector        TEXT,
    currency         CHAR(3)      NOT NULL DEFAULT 'VND',
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE v2_ref.companies IS
    'v2: Canonical company master. Written by migration runner only. '
    'Exchange constraint enforced (HOSE/HNX/UPCOM).';

-- ── v2_ref.line_items ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_ref.line_items (
    line_item_code   VARCHAR(100) PRIMARY KEY,
    statement_type   VARCHAR(40)  NOT NULL CHECK (
        statement_type IN ('income_statement', 'balance_sheet', 'cash_flow', 'market', 'assumption', 'other')
    ),
    display_name_vi  TEXT         NOT NULL,
    display_name_en  TEXT,
    canonical_unit   VARCHAR(40)  NOT NULL,
    is_derived       BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    description      TEXT
);

COMMENT ON TABLE v2_ref.line_items IS
    'v2: Line item code dictionary. is_derived items must NOT be stored as canonical facts.';

-- ── v2_ref.formulas ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_ref.formulas (
    formula_id       VARCHAR(20)  PRIMARY KEY,
    formula_name     TEXT         NOT NULL,
    formula_group    TEXT         NOT NULL,
    function_name    TEXT         NOT NULL,
    formula_text     TEXT         NOT NULL,
    output_unit      VARCHAR(40)  NOT NULL,
    description      TEXT,
    version          VARCHAR(20)  NOT NULL DEFAULT 'v1',
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE
);

-- ── v2_ref.peer_groups ────────────────────────────────────────────────────────
-- Replaces the ref.universes / ref.universe_members model with a simpler peer group structure.
CREATE TABLE IF NOT EXISTS v2_ref.peer_groups (
    peer_group_id    VARCHAR(64)  PRIMARY KEY,
    peer_group_name  TEXT         NOT NULL,
    sector           TEXT         NOT NULL,
    description      TEXT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS v2_ref.peer_group_members (
    peer_group_id    VARCHAR(64)  NOT NULL REFERENCES v2_ref.peer_groups(peer_group_id) ON DELETE CASCADE,
    ticker           VARCHAR(10)  NOT NULL REFERENCES v2_ref.companies(ticker),
    enabled_methods  TEXT[]       NOT NULL DEFAULT ARRAY['fcff', 'fcfe', 'pe_forward'],
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    added_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (peer_group_id, ticker)
);

-- ── Seed v2_ref from legacy ref.* ─────────────────────────────────────────────
-- Idempotent: ON CONFLICT DO UPDATE keeps data fresh.

INSERT INTO v2_ref.companies
    (ticker, company_name_vi, company_name_en, exchange, sector, subsector, currency, is_active)
SELECT
    ticker, company_name_vi, company_name_en, exchange, sector, subsector, currency, is_active
FROM ref.companies
ON CONFLICT (ticker) DO UPDATE
SET company_name_vi = EXCLUDED.company_name_vi,
    company_name_en = EXCLUDED.company_name_en,
    exchange        = EXCLUDED.exchange,
    sector          = EXCLUDED.sector,
    subsector       = EXCLUDED.subsector,
    is_active       = EXCLUDED.is_active,
    updated_at      = NOW();

INSERT INTO v2_ref.line_items
    (line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit, is_derived, is_active)
SELECT
    line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit, is_derived, is_active
FROM ref.line_items
ON CONFLICT (line_item_code) DO UPDATE
SET statement_type  = EXCLUDED.statement_type,
    display_name_vi = EXCLUDED.display_name_vi,
    display_name_en = EXCLUDED.display_name_en,
    canonical_unit  = EXCLUDED.canonical_unit,
    is_derived      = EXCLUDED.is_derived,
    is_active       = EXCLUDED.is_active;

INSERT INTO v2_ref.formulas
    (formula_id, formula_name, formula_group, function_name, formula_text, output_unit, description, version, is_active)
SELECT
    formula_id, formula_name, formula_group, function_name, formula_text, output_unit, description, version, is_active
FROM ref.formulas
ON CONFLICT (formula_id) DO UPDATE
SET formula_name  = EXCLUDED.formula_name,
    formula_group = EXCLUDED.formula_group,
    function_name = EXCLUDED.function_name,
    formula_text  = EXCLUDED.formula_text,
    output_unit   = EXCLUDED.output_unit,
    description   = EXCLUDED.description,
    is_active     = TRUE;

-- Seed peer groups from legacy universe_members.peer_group values.
INSERT INTO v2_ref.peer_groups (peer_group_id, peer_group_name, sector)
SELECT DISTINCT
    peer_group            AS peer_group_id,
    peer_group            AS peer_group_name,
    'pharma'              AS sector
FROM ref.universe_members
WHERE peer_group IS NOT NULL
ON CONFLICT (peer_group_id) DO NOTHING;

INSERT INTO v2_ref.peer_group_members (peer_group_id, ticker, enabled_methods, is_active)
SELECT
    peer_group            AS peer_group_id,
    ticker,
    enabled_methods,
    is_enabled            AS is_active
FROM ref.universe_members
WHERE peer_group IS NOT NULL
ON CONFLICT (peer_group_id, ticker) DO UPDATE
SET enabled_methods = EXCLUDED.enabled_methods,
    is_active       = EXCLUDED.is_active;
