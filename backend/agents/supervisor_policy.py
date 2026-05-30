from __future__ import annotations

from typing import Any


class SupervisorPolicy:
    """Small policy object for graph routing decisions."""

    @staticmethod
    def should_stop_for_review(state: dict[str, Any]) -> bool:
        return bool(state.get("requires_human") or state.get("blocking_reason"))

    @staticmethod
    def final_approval_present(state: dict[str, Any]) -> bool:
        approvals = state.get("approvals") or {}
        return approvals.get("final_report") == "approved"
