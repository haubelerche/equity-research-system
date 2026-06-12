"""v2 DAL: audit.events â€” immutable governance log.

Append-only. No updates, no deletes. Every significant event must be logged here.
"""
from __future__ import annotations

import json
from typing import Any

from backend.database.canonical.connection import get_conn


def log_event(
    event_type: str,
    actor: str,
    run_id: str | None = None,
    target_table: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    """Append one audit event. Returns the inserted id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.events
                    (event_type, actor, run_id, target_table, target_id, payload_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    event_type,
                    actor,
                    run_id,
                    target_table,
                    target_id,
                    json.dumps(payload or {}),
                ),
            )
            row = cur.fetchone()
            return row[0] if row else -1


def log_cost(
    step_name: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    run_id: str | None = None,
    budget_policy: str | None = None,
    fallback_model: str | None = None,
    stop_reason: str | None = None,
) -> None:
    """Append one cost ledger entry."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.cost_ledger
                    (run_id, step_name, model_name, prompt_tokens, completion_tokens,
                     cost_usd, budget_policy, fallback_model, stop_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id, step_name, model_name, prompt_tokens, completion_tokens,
                    cost_usd, budget_policy, fallback_model, stop_reason,
                ),
            )

