from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, UTC
from typing import Any

import psycopg2
from psycopg2.extras import Json


REQUIRED_SCHEMA_VERSION = "015_cleanup_redundant_schema"

DB_TO_PUBLIC_STATUS = {
    "initialized": "INIT",
    "running": "ANALYZING",
    "data_ready": "ANALYZING",
    "analysis_ready": "ANALYZING",
    "valuation_ready": "VALUATING",
    "report_ready": "SYNTHESIZING",
    "needs_human_review": "NEEDS_REVIEW",
    "approved": "PUBLISHED",
    "failed": "FAILED",
    "cancelled": "FAILED",
}

PUBLIC_TO_DB_STATUS = {
    "INIT": "initialized",
    "INGESTING": "running",
    "ANALYZING": "analysis_ready",
    "VALUATING": "valuation_ready",
    "SYNTHESIZING": "report_ready",
    "AUDITING": "analysis_ready",
    "WAITING_ASSUMPTIONS_APPROVAL": "needs_human_review",
    "WAITING_FINAL_APPROVAL": "needs_human_review",
    "PUBLISHED": "approved",
    "NEEDS_REVIEW": "needs_human_review",
    "FAILED": "failed",
}


def to_db_status(status: str) -> str:
    return PUBLIC_TO_DB_STATUS.get(status, status)


def to_public_status(status: str) -> str:
    return DB_TO_PUBLIC_STATUS.get(status, status)


STEP_STATUS_ALIASES = {
    "STARTED": "running",
    "RUNNING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "SKIPPED": "skipped",
    "PENDING": "pending",
}


def to_db_step_status(status: str) -> str:
    return STEP_STATUS_ALIASES.get(status, status).lower()


class RuntimeStore:
    """Persistence layer for orchestration/runtime metadata (research.* schema)."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")

    @contextmanager
    def conn(self):
        connection = psycopg2.connect(self.dsn)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def check_schema_version(self) -> None:
        """Verify the database schema is at the required version.

        Raises RuntimeError if public.schema_migrations does not contain
        REQUIRED_SCHEMA_VERSION. Does NOT apply migrations; run
        python -m backend.database.migrate first.
        """
        with self.conn() as connection:
            with connection.cursor() as cur:
                try:
                    cur.execute(
                        "SELECT 1 FROM public.schema_migrations WHERE version = %s",
                        (REQUIRED_SCHEMA_VERSION,),
                    )
                    if cur.fetchone() is None:
                        raise RuntimeError(
                            f"DB schema out of date: version '{REQUIRED_SCHEMA_VERSION}' not applied. "
                            "Run: python -m backend.database.migrate"
                        )
                except psycopg2.errors.UndefinedTable as exc:
                    raise RuntimeError(
                        "public.schema_migrations table missing; run: python -m backend.database.migrate"
                    ) from exc

    def create_run(
        self,
        run_id: str,
        ticker: str,
        run_type: str,
        objective: str,
        flags: dict[str, Any],
        org_id: str | None = None,
        requested_by: str | None = None,
        idempotency_key: str | None = None,
        request_json: dict[str, Any] | None = None,
        config_snapshot_json: dict[str, Any] | None = None,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.runs
                    (run_id, ticker, run_type, objective, status, current_stage,
                     org_id, requested_by, flags_json, idempotency_key, request_json, config_snapshot_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        ticker,
                        run_type,
                        objective,
                        "initialized",
                        "initialized",
                        org_id,
                        requested_by,
                        Json(flags),
                        idempotency_key,
                        Json(request_json or {}),
                        Json(config_snapshot_json or {}),
                    ),
                )

    def update_run_state(
        self,
        run_id: str,
        status: str,
        stage: str,
        flags: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE research.runs
                    SET status        = %s,
                        current_stage = %s,
                        flags_json    = COALESCE(%s, flags_json),
                        updated_at    = NOW(),
                        finished_at   = CASE WHEN %s THEN NOW() ELSE finished_at END
                    WHERE run_id = %s
                    """,
                    (to_db_status(status), stage, Json(flags) if flags is not None else None, finished, run_id),
                )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, ticker, run_type, status, current_stage,
                           flags_json, request_json, config_snapshot_json,
                           created_at, updated_at, finished_at
                    FROM research.runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "run_id":               row[0],
            "ticker":               row[1],
            "run_type":             row[2],
            "status":               row[3],
            "current_stage":        row[4],
            "flags_json":           row[5] or {},
            "request_json":         row[6] or {},
            "config_snapshot_json": row[7] or {},
            "created_at":           row[8].isoformat(),
            "updated_at":           row[9].isoformat(),
            "finished_at":          row[10].isoformat() if row[10] else None,
        }

    def add_step(
        self,
        run_id: str,
        step_name: str,
        agent_name: str,
        status: str,
        policy_reason: str | None = None,
        input_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.run_steps
                    (run_id, step_name, agent_name, status, policy_reason, input_hash, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (run_id, step_name, agent_name, to_db_step_status(status), policy_reason, input_hash, Json(metadata or {})),
                )
                step_id = cur.fetchone()[0]
        return int(step_id)

    def close_step(
        self,
        step_id: int,
        status: str,
        output_hash: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE research.run_steps
                    SET status        = %s,
                        ended_at      = NOW(),
                        duration_ms   = CAST(EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000 AS BIGINT),
                        output_hash   = COALESCE(%s, output_hash),
                        error_message = COALESCE(%s, error_message),
                        metadata_json = COALESCE(metadata_json, '{}'::jsonb) || %s
                    WHERE id = %s
                    """,
                    (to_db_step_status(status), output_hash, error_message, Json(metadata or {}), step_id),
                )

    def increment_step_retry(self, step_id: int) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE research.run_steps SET retry_count = retry_count + 1 WHERE id = %s",
                    (step_id,),
                )

    def save_artifact(
        self,
        artifact_id: str,
        run_id: str,
        artifact_type: str,
        payload: dict[str, Any],
        section_key: str | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        confidence: float | None = None,
        created_by_agent: str | None = None,
        version: int = 1,
        storage_path: str | None = None,
        checksum: str | None = None,
        is_locked: bool = False,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.run_artifacts
                    (artifact_id, run_id, artifact_type, section_key, version,
                     payload_json, evidence_refs_json, confidence, created_by_agent,
                     storage_path, checksum, is_locked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (artifact_id) DO UPDATE
                    SET payload_json       = EXCLUDED.payload_json,
                        evidence_refs_json = EXCLUDED.evidence_refs_json,
                        confidence         = EXCLUDED.confidence,
                        created_by_agent   = EXCLUDED.created_by_agent,
                        storage_path       = EXCLUDED.storage_path,
                        checksum           = EXCLUDED.checksum
                    """,
                    (
                        artifact_id,
                        run_id,
                        artifact_type,
                        section_key,
                        version,
                        Json(payload),
                        Json(evidence_refs or []),
                        confidence,
                        created_by_agent,
                        storage_path,
                        checksum,
                        is_locked,
                    ),
                )

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT artifact_id, artifact_type, section_key, version,
                           payload_json, confidence, created_by_agent, storage_path, is_locked, created_at
                    FROM research.run_artifacts
                    WHERE run_id = %s
                    ORDER BY created_at
                    """,
                    (run_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "artifact_id":     row[0],
                "artifact_type":   row[1],
                "section_key":     row[2],
                "version":         row[3],
                "payload":         row[4] or {},
                "confidence":      float(row[5]) if row[5] is not None else None,
                "created_by_agent":row[6],
                "storage_path":    row[7],
                "is_locked":       row[8],
                "created_at":      row[9].isoformat(),
            }
            for row in rows
        ]

    def latest_graph_state(self, run_id: str) -> dict[str, Any] | None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT payload_json
                    FROM research.run_artifacts
                    WHERE run_id = %s
                      AND artifact_type = 'run_log_json'
                      AND section_key = 'graph_state_snapshot'
                    ORDER BY version DESC, created_at DESC
                    LIMIT 1
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        return row[0] if row else None

    def mark_artifacts_stale(self, run_id: str, section_keys: list[str], reason: str) -> int:
        if not section_keys:
            return 0
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE research.run_artifacts
                    SET payload_json = COALESCE(payload_json, '{}'::jsonb) || %s::jsonb,
                        is_locked    = FALSE
                    WHERE run_id = %s
                      AND section_key = ANY(%s)
                    """,
                    (
                        Json({"stale": True, "stale_reason": reason, "stale_at": datetime.now(UTC).isoformat()}),
                        run_id,
                        section_keys,
                    ),
                )
                return int(cur.rowcount)

    def lock_artifacts(self, run_id: str, section_keys: list[str]) -> int:
        if not section_keys:
            return 0
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE research.run_artifacts
                    SET is_locked = TRUE
                    WHERE run_id = %s
                      AND section_key = ANY(%s)
                    """,
                    (run_id, section_keys),
                )
                return int(cur.rowcount)

    def add_approval(
        self,
        run_id: str,
        stage: str,
        decision: str,
        reviewer: str,
        feedback_patch: dict[str, Any],
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.run_approvals
                    (run_id, approval_stage, decision, reviewer, feedback_patch_json)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (run_id, stage, decision, reviewer, Json(feedback_patch)),
                )

    def add_budget_entry(
        self,
        run_id: str,
        step_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        budget_policy: str,
        fallback_model: str | None = None,
        stop_reason: str | None = None,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.run_budget_ledger
                    (run_id, step_name, model_name, prompt_tokens, completion_tokens,
                     cost_usd, budget_policy, fallback_model, stop_reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        step_name,
                        model_name,
                        prompt_tokens,
                        completion_tokens,
                        cost_usd,
                        budget_policy,
                        fallback_model,
                        stop_reason,
                    ),
                )

    def run_cost_usd(self, run_id: str) -> float:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM research.run_budget_ledger WHERE run_id = %s",
                    (run_id,),
                )
                value = cur.fetchone()[0]
        return float(value)

    def add_audit_event(
        self,
        run_id: str,
        actor: str,
        action: str,
        payload: dict[str, Any] | None = None,
        rule_reason: str | None = None,
        policy_reason: str | None = None,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.run_audit_events
                    (run_id, actor, action, rule_reason, policy_reason, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, actor, action, rule_reason, policy_reason, Json(payload or {})),
                )
