-- Migration: 001_ref_schema.sql
-- Purpose: Create canonical reference schema.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE IF NOT EXISTS ref.companies (
    ticker           VARCHAR(10) PRIMARY KEY,
    company_name_vi  TEXT        NOT NULL,
    company_name_en  TEXT,
    exchange         VARCHAR(10) NOT NULL,
    sector           TEXT        NOT NULL DEFAULT 'pharma',
    subsector        TEXT,
    currency         CHAR(3)     NOT NULL DEFAULT 'VND',
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ref.universes (
    universe_id      VARCHAR(64) PRIMARY KEY,
    universe_name    TEXT        NOT NULL UNIQUE,
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ref.universe_members (
    universe_id      VARCHAR(64) NOT NULL REFERENCES ref.universes(universe_id) ON DELETE CASCADE,
    ticker           VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    peer_group       TEXT,
    enabled_methods  TEXT[]      NOT NULL DEFAULT ARRAY['dcf', 'pe', 'pb'],
    is_enabled       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (universe_id, ticker)
);

CREATE TABLE IF NOT EXISTS ref.line_items (
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

CREATE TABLE IF NOT EXISTS ref.formulas (
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
