"""Repair deterministic metadata defects in ingest.source_documents.

The repair is intentionally conservative:
- infer ticker only when every linked observation agrees;
- populate human-readable titles and connector names from known URI patterns;
- correct DAV regulatory endpoints misclassified as vnstock financial sources;
- preserve optional fields whose absence is semantically valid.

Usage:
    python scripts/database/repair_source_metadata.py
    python scripts/database/repair_source_metadata.py --apply
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


REPAIR_SQL = """
WITH inferred AS (
    SELECT source_doc_id, MIN(ticker) AS ticker
    FROM ingest.observations
    WHERE source_doc_id IS NOT NULL
    GROUP BY source_doc_id
    HAVING COUNT(DISTINCT ticker) = 1
)
UPDATE ingest.source_documents sd
SET ticker = inferred.ticker,
    source_title = COALESCE(
        sd.source_title,
        'VNStock financial data - ' || inferred.ticker || ' - ' ||
        REPLACE(SPLIT_PART(sd.source_uri, '/', 5), '_', ' ')
    ),
    connector_name = COALESCE(sd.connector_name, 'vnstock_finance_connector'),
    metadata_json = sd.metadata_json || '{"metadata_repaired": true}'::jsonb
FROM inferred
WHERE sd.source_doc_id = inferred.source_doc_id
  AND (sd.ticker IS NULL OR sd.source_title IS NULL OR sd.connector_name IS NULL);

UPDATE ingest.source_documents
SET ticker = SPLIT_PART(SPLIT_PART(source_uri, '/', 6), '?', 1),
    source_title = COALESCE(
        source_title,
        'VNStock financial data - ' ||
        SPLIT_PART(SPLIT_PART(source_uri, '/', 6), '?', 1) || ' - ' ||
        REPLACE(SPLIT_PART(source_uri, '/', 5), '_', ' ')
    ),
    connector_name = COALESCE(connector_name, 'vnstock_finance_connector'),
    metadata_json = metadata_json || '{"metadata_repaired": true}'::jsonb
WHERE source_type = 'vnstock_financial'
  AND source_uri LIKE 'vnstock://%/finance/%'
  AND (ticker IS NULL OR source_title IS NULL OR connector_name IS NULL);

UPDATE ingest.source_documents
SET source_title = COALESCE(
        source_title,
        'VNStock company ' ||
        CASE WHEN source_uri LIKE '%/events/%' THEN 'events' ELSE 'news' END ||
        ' - ' || ticker
    ),
    connector_name = COALESCE(connector_name, 'vnstock_company_connector'),
    metadata_json = metadata_json || '{"metadata_repaired": true}'::jsonb
WHERE source_type = 'news'
  AND (source_title IS NULL OR connector_name IS NULL);

UPDATE ingest.source_documents
SET source_title = COALESCE(source_title, 'VNStock company officers - ' || ticker),
    connector_name = COALESCE(connector_name, 'vnstock_company_connector'),
    metadata_json = metadata_json || '{"metadata_repaired": true}'::jsonb
WHERE source_type = 'vnstock_company'
  AND (source_title IS NULL OR connector_name IS NULL);

UPDATE ingest.source_documents
SET source_title = COALESCE(source_title, 'VNStock price history - ' || ticker),
    connector_name = COALESCE(connector_name, 'vnstock_price_connector'),
    metadata_json = metadata_json || '{"metadata_repaired": true}'::jsonb
WHERE source_type = 'vnstock_price'
  AND (source_title IS NULL OR connector_name IS NULL);

UPDATE ingest.source_documents
SET source_type = 'regulatory_notice',
    source_title = COALESCE(source_title, 'Drug Administration of Vietnam regulatory feed'),
    issuer = COALESCE(issuer, 'Drug Administration of Vietnam'),
    connector_name = COALESCE(connector_name, 'catalyst_dav_connector'),
    metadata_json = metadata_json || '{"metadata_repaired": true, "corrected_source_type": true}'::jsonb
WHERE source_type = 'vnstock_financial'
  AND source_uri LIKE 'https://dav.gov.vn/%';

UPDATE ingest.source_documents
SET issuer = COALESCE(issuer, 'Drug Administration of Vietnam'),
    connector_name = COALESCE(connector_name, 'catalyst_dav_connector'),
    metadata_json = metadata_json || '{"metadata_repaired": true}'::jsonb
WHERE source_type = 'regulatory_notice'
  AND source_uri LIKE 'https://dav.gov.vn/%'
  AND (issuer IS NULL OR connector_name IS NULL);

UPDATE ingest.source_documents
SET connector_name = COALESCE(connector_name, 'official_document_registration'),
    metadata_json = metadata_json || '{"metadata_repaired": true}'::jsonb
WHERE source_type IN ('annual_report', 'audited_financial_statement')
  AND connector_name IS NULL;

UPDATE ingest.source_documents
SET source_title = REPLACE(source_title, '�', '-'),
    connector_name = COALESCE(connector_name, 'build_index'),
    metadata_json = metadata_json || '{"metadata_repaired": true}'::jsonb
WHERE source_uri LIKE 'internal://canonical_facts/%'
  AND (connector_name IS NULL OR source_title LIKE '%�%');
"""


def _quality_counts(cur) -> dict[str, int]:
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE ticker IS NULL) AS ticker_null,
            COUNT(*) FILTER (WHERE source_title IS NULL) AS title_null,
            COUNT(*) FILTER (WHERE connector_name IS NULL) AS connector_null,
            COUNT(*) FILTER (
                WHERE source_type = 'vnstock_financial'
                  AND source_uri LIKE 'https://dav.gov.vn/%'
            ) AS misclassified_dav
        FROM ingest.source_documents
        """
    )
    row = cur.fetchone()
    return {
        "ticker_null": row[0],
        "title_null": row[1],
        "connector_null": row[2],
        "misclassified_dav": row[3],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    _load_env()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is not configured")

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            before = _quality_counts(cur)
            if args.apply:
                cur.execute(REPAIR_SQL)
                cur.execute(
                    """
                    INSERT INTO audit.events (event_type, actor, target_table, payload_json)
                    VALUES (
                        'data_promotion',
                        'repair_source_metadata',
                        'ingest.source_documents',
                        jsonb_build_object('repair', 'deterministic_source_metadata')
                    )
                    """
                )
                after = _quality_counts(cur)
            else:
                after = before
                conn.rollback()

    mode = "apply" if args.apply else "dry-run"
    print({"mode": mode, "before": before, "after": after})


if __name__ == "__main__":
    main()
