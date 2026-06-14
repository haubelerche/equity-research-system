from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, UTC
from typing import Any

import psycopg2
from psycopg2.extras import Json

from backend.database.config import connect_with_retry, require_database_url

REQUIRED_SCHEMA_VERSION = "035_runs_status_auto_exported"

DB_TO_PUBLIC_STATUS = {
    "initialized": "INIT",
    "running": "ANALYZING",
    "data_ready": "ANALYZING",
    "analysis_ready": "ANALYZING",
    "valuation_ready": "VALUATING",
    "report_ready": "SYNTHESIZING",
    "blocked": "BLOCKED",
    "approved": "PUBLISHED",
    "auto_exported": "PUBLISHED_DRAFT",
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
    "PUBLISHED": "approved",
    "PUBLISHED_DRAFT": "auto_exported",
    "BLOCKED": "blocked",
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
        self.dsn = require_database_url(dsn)

    @contextmanager
    def conn(self):
        connection = connect_with_retry(self.dsn)
        try:
            # Verify the connection is alive (Supabase pooler may close idle ones)
            try:
                connection.cursor().execute("SELECT 1")
            except Exception:
                try:
                    connection.close()
                except Exception:
                    pass
                connection = connect_with_retry(self.dsn)
            yield connection
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def _write(self, fn, *, retries: int = 2):
        """Run fn(connection) in a fresh connection, retrying transient pooler disconnects."""
        last_exc = None
        for attempt in range(retries + 1):
            try:
                with self.conn() as connection:
                    return fn(connection)
            except psycopg2.OperationalError as exc:
                last_exc = exc
                if attempt == retries:
                    raise
                time.sleep(0.5 * (2 ** attempt))
        raise last_exc  # pragma: no cover

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

    def ensure_company_reference(
        self,
        *,
        ticker: str,
        company_name_vi: str,
        company_name_en: str | None,
        exchange: str | None,
        sector: str,
        subsector: str | None,
        peer_group_id: str,
        peer_group_name: str,
    ) -> None:
        """Register a company and universe membership before run creation.

        research.runs has a strict FK to ref.companies. This method turns the
        configured universe CSV into canonical reference rows so non-MVP
        tickers can enter the harness without weakening referential integrity.
        """
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ref.companies
                    (ticker, company_name_vi, company_name_en, exchange, sector, subsector)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE
                    SET company_name_vi = COALESCE(EXCLUDED.company_name_vi, ref.companies.company_name_vi),
                        company_name_en = COALESCE(EXCLUDED.company_name_en, ref.companies.company_name_en),
                        exchange        = COALESCE(EXCLUDED.exchange,        ref.companies.exchange),
                        sector          = COALESCE(EXCLUDED.sector,          ref.companies.sector),
                        subsector       = COALESCE(EXCLUDED.subsector,       ref.companies.subsector),
                        updated_at      = NOW()
                    """,
                    (ticker, company_name_vi, company_name_en, exchange, sector, subsector),
                )
                cur.execute(
                    """
                    INSERT INTO ref.peer_groups (peer_group_id, peer_group_name)
                    VALUES (%s, %s)
                    ON CONFLICT (peer_group_id) DO UPDATE
                    SET peer_group_name = EXCLUDED.peer_group_name
                    """,
                    (peer_group_id, peer_group_name),
                )
                cur.execute(
                    """
                    INSERT INTO ref.peer_group_members (peer_group_id, ticker)
                    VALUES (%s, %s)
                    ON CONFLICT (peer_group_id, ticker) DO NOTHING
                    """,
                    (peer_group_id, ticker),
                )

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
        def _work(connection):
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
        return self._write(_work)

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

    def get_latest_approval(
        self,
        run_id: str,
        approval_stage: str,
    ) -> dict[str, Any] | None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT approval_stage, decision, reviewer, feedback_patch_json,
                           created_at, approved_at
                    FROM research.run_approvals
                    WHERE run_id = %s AND approval_stage = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (run_id, approval_stage),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "approval_stage": row[0],
            "decision": row[1],
            "reviewer": row[2],
            "feedback_patch_json": row[3] or {},
            "created_at": row[4].isoformat(),
            "approved_at": row[5].isoformat() if row[5] else None,
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
        def _work(connection):
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
                return int(cur.fetchone()[0])
        return self._write(_work)

    def close_step(
        self,
        step_id: int,
        status: str,
        output_hash: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        def _work(connection):
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
        return self._write(_work)

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
        storage_bucket: str | None = None,
        checksum: str | None = None,
        content_type: str | None = None,
        file_size_bytes: int | None = None,
        is_locked: bool = False,
    ) -> None:
        def _work(connection):
            nonlocal artifact_id
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT artifact_id
                    FROM research.run_artifacts
                    WHERE run_id = %s
                      AND artifact_type = %s
                      AND COALESCE(section_key, '') = COALESCE(%s, '')
                      AND version = %s
                    LIMIT 1
                    """,
                    (run_id, artifact_type, section_key, version),
                )
                existing = cur.fetchone()
                if existing:
                    artifact_id = existing[0]
                cur.execute(
                    """
                    INSERT INTO research.run_artifacts
                    (artifact_id, run_id, artifact_type, section_key, version,
                     payload_json, evidence_refs_json, confidence, created_by_agent,
                     storage_bucket, storage_path, checksum, content_type, file_size_bytes, is_locked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (artifact_id) DO UPDATE
                    SET payload_json       = EXCLUDED.payload_json,
                        evidence_refs_json = EXCLUDED.evidence_refs_json,
                        confidence         = EXCLUDED.confidence,
                        created_by_agent   = EXCLUDED.created_by_agent,
                        storage_path       = EXCLUDED.storage_path,
                        storage_bucket     = EXCLUDED.storage_bucket,
                        checksum           = EXCLUDED.checksum,
                        content_type       = EXCLUDED.content_type,
                        file_size_bytes    = EXCLUDED.file_size_bytes,
                        is_locked          = EXCLUDED.is_locked
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
                        storage_bucket,
                        storage_path,
                        checksum,
                        content_type,
                        file_size_bytes,
                        is_locked,
                    ),
                )
        return self._write(_work)

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT artifact_id, artifact_type, section_key, version,
                           payload_json, confidence, created_by_agent, storage_bucket,
                           storage_path, checksum, content_type, file_size_bytes, is_locked, created_at
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
                "storage_bucket":  row[7],
                "storage_path":    row[8],
                "checksum":        row[9],
                "content_type":    row[10],
                "file_size_bytes": row[11],
                "is_locked":       row[12],
                "created_at":      row[13].isoformat(),
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
        def _work(connection):
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit.cost_ledger
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
        return self._write(_work)

    def run_cost_usd(self, run_id: str) -> float:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM audit.cost_ledger WHERE run_id = %s",
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
        def _work(connection):
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.run_audit_events
                    (run_id, actor, action, rule_reason, policy_reason, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, actor, action, rule_reason, policy_reason, Json(payload or {})),
                )
        return self._write(_work)
