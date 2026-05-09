from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json


class RuntimeStore:
    """Persistence layer for orchestration/runtime metadata."""

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

    def ensure_schema(self) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                migrations_dir = Path(__file__).resolve().parents[1] / "scripts" / "db" / "migrations"
                for name in ("001_initial_schema.sql", "002_backend_runtime.sql", "003_lineage_enhancements.sql"):
                    sql = (migrations_dir / name).read_text(encoding="utf-8")
                    cur.execute(sql)

    def create_run(
        self,
        run_id: str,
        ticker: str,
        run_type: str,
        objective: str,
        flags: dict[str, Any],
        policy: dict[str, Any],
        org_id: str | None = None,
        requested_by: str | None = None,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_runs
                    (run_id, ticker, run_type, objective, status, current_state, org_id, requested_by, flags_json, policy_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        ticker,
                        run_type,
                        objective,
                        "INIT",
                        "INIT",
                        org_id,
                        requested_by,
                        Json(flags),
                        Json(policy),
                    ),
                )

    def update_run_state(
        self,
        run_id: str,
        status: str,
        state: str,
        flags: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE research_runs
                    SET status = %s,
                        current_state = %s,
                        flags_json = COALESCE(%s, flags_json),
                        updated_at = NOW(),
                        finished_at = CASE WHEN %s THEN NOW() ELSE finished_at END
                    WHERE run_id = %s
                    """,
                    (status, state, Json(flags) if flags is not None else None, finished, run_id),
                )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, ticker, run_type, status, current_state, flags_json, created_at, updated_at, finished_at, policy_json
                    FROM research_runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "ticker": row[1],
            "run_type": row[2],
            "status": row[3],
            "current_state": row[4],
            "flags_json": row[5] or {},
            "created_at": row[6].isoformat(),
            "updated_at": row[7].isoformat(),
            "finished_at": row[8].isoformat() if row[8] else None,
            "policy_json": row[9] or {},
        }

    def add_step(
        self,
        run_id: str,
        step_name: str,
        agent_name: str,
        status: str,
        policy_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO run_steps (run_id, step_name, agent_name, status, policy_reason, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (run_id, step_name, agent_name, status, policy_reason, Json(metadata or {})),
                )
                step_id = cur.fetchone()[0]
        return int(step_id)

    def close_step(self, step_id: int, status: str, metadata: dict[str, Any] | None = None) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE run_steps
                    SET status = %s,
                        ended_at = NOW(),
                        duration_ms = CAST(EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000 AS BIGINT),
                        metadata_json = COALESCE(metadata_json, '{}'::jsonb) || %s
                    WHERE id = %s
                    """,
                    (status, Json(metadata or {}), step_id),
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
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO run_artifacts
                    (artifact_id, run_id, artifact_type, section_key, payload_json, evidence_refs_json, confidence, created_by_agent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (artifact_id) DO UPDATE
                    SET payload_json = EXCLUDED.payload_json,
                        evidence_refs_json = EXCLUDED.evidence_refs_json,
                        confidence = EXCLUDED.confidence,
                        created_by_agent = EXCLUDED.created_by_agent
                    """,
                    (
                        artifact_id,
                        run_id,
                        artifact_type,
                        section_key,
                        Json(payload),
                        Json(evidence_refs or []),
                        confidence,
                        created_by_agent,
                    ),
                )

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT artifact_id, artifact_type, section_key, payload_json, confidence, created_by_agent, created_at
                    FROM run_artifacts
                    WHERE run_id = %s
                    ORDER BY created_at
                    """,
                    (run_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "artifact_id": row[0],
                "artifact_type": row[1],
                "section_key": row[2],
                "payload": row[3] or {},
                "confidence": float(row[4]) if row[4] is not None else None,
                "created_by_agent": row[5],
                "created_at": row[6].isoformat(),
            }
            for row in rows
        ]

    def add_approval(self, run_id: str, stage: str, decision: str, reviewer: str, feedback_patch: dict[str, Any]) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO run_approvals (run_id, approval_stage, decision, reviewer, feedback_patch_json)
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
                    INSERT INTO run_budget_ledger
                    (run_id, step_name, model_name, prompt_tokens, completion_tokens, cost_usd, budget_policy, fallback_model, stop_reason)
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
                cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM run_budget_ledger WHERE run_id = %s", (run_id,))
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
                    INSERT INTO run_audit_events (run_id, actor, action, rule_reason, policy_reason, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, actor, action, rule_reason, policy_reason, Json(payload or {})),
                )

