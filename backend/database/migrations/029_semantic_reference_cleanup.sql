-- Migration 029: simplify reference data and remove legacy workflow policy.
--
-- The previous peer-group model was copied from legacy universe segments and
-- mixed valuation-method policy into reference membership. The canonical
-- reference model now stores only named peer groups and their members.

DELETE FROM ref.peer_group_members;
DELETE FROM ref.peer_groups;

INSERT INTO ref.peer_groups (peer_group_id, peer_group_name, sector, description)
VALUES (
    'vn_pharma_listed',
    'Vietnam Listed Pharmaceutical Companies',
    'pharma',
    'Canonical listed-pharmaceutical peer universe'
);

INSERT INTO ref.peer_group_members (peer_group_id, ticker)
SELECT 'vn_pharma_listed', ticker
FROM ref.companies
ORDER BY ticker;

ALTER TABLE ref.peer_group_members
    DROP COLUMN enabled_methods,
    DROP COLUMN is_active,
    DROP COLUMN added_at;

ALTER TABLE ref.peer_groups
    DROP COLUMN sector,
    DROP COLUMN description;

ALTER TABLE ref.companies
    DROP COLUMN is_active;

ALTER TABLE ref.line_items
    DROP COLUMN is_active,
    DROP COLUMN description;

ALTER TABLE ref.formulas
    DROP COLUMN version,
    DROP COLUMN is_active;

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_029',
    'ref.*',
    jsonb_build_object(
        'migration', '029_semantic_reference_cleanup',
        'peer_group', 'vn_pharma_listed',
        'removed_columns', jsonb_build_array(
            'ref.peer_group_members.enabled_methods',
            'ref.peer_group_members.is_active',
            'ref.peer_group_members.added_at',
            'ref.peer_groups.sector',
            'ref.peer_groups.description',
            'ref.companies.is_active',
            'ref.line_items.is_active',
            'ref.line_items.description',
            'ref.formulas.version',
            'ref.formulas.is_active'
        )
    )
);
