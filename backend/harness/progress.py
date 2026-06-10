from __future__ import annotations

import sys
import time
from typing import IO, Any


class ProgressReporter:
    """Real-time console progress reporter for the research harness."""

    def __init__(self, stream: IO[str] | None = None, quiet: bool = False) -> None:
        self._stream = stream or sys.stderr
        self._quiet = quiet
        self._stage_start_time: float | None = None

    def _write(self, msg: str) -> None:
        if self._quiet:
            return
        self._stream.write(msg + "\n")
        self._stream.flush()

    def run_start(self, run_id: str, ticker: str, run_type: str) -> None:
        self._write(f"\n{'='*70}")
        self._write(f"  RESEARCH RUN: {ticker} | {run_type}")
        self._write(f"  Run ID: {run_id}")
        self._write(f"{'='*70}\n")

    def stage_start(self, stage: str, stage_index: int, total_stages: int) -> None:
        self._stage_start_time = time.monotonic()
        self._write(f"  [{stage_index + 1}/{total_stages}] {stage} ...")

    def stage_end(self, stage: str, elapsed_sec: float, status: str) -> None:
        icon = "OK" if status == "completed" else "!!"
        self._write(f"        {icon} {stage} done in {elapsed_sec:.1f}s [{status}]")

    def gate_result(self, gate_name: str, passed: bool, issues: list[str]) -> None:
        label = "PASS" if passed else "FAIL"
        self._write(f"        GATE {gate_name}: {label}")
        if not passed and issues:
            for issue in issues[:5]:
                self._write(f"             - {issue}")

    def agent_start(self, agent_id: str, task: str) -> None:
        short_task = task[:80] + "..." if len(task) > 80 else task
        self._write(f"        AGENT [{agent_id}] {short_task}")

    def agent_end(self, agent_id: str, status: str, confidence: float | None = None, latency_ms: int | None = None) -> None:
        parts = [f"        AGENT [{agent_id}] -> {status}"]
        if confidence is not None:
            parts.append(f"confidence={confidence:.2f}")
        if latency_ms is not None:
            parts.append(f"{latency_ms / 1000:.1f}s")
        self._write(" | ".join(parts))

    def tool_start(self, tool_id: str, agent_id: str) -> None:
        self._write(f"        TOOL  [{agent_id}/{tool_id}] running...")

    def tool_end(self, tool_id: str, status: str, blocking_reason: str | None = None) -> None:
        msg = f"        TOOL  [{tool_id}] -> {status}"
        if blocking_reason:
            msg += f" | BLOCKED: {blocking_reason}"
        self._write(msg)

    def blocking(self, stage: str, reason: str) -> None:
        self._write(f"\n  *** BLOCKED at {stage}: {reason}\n")

    def error(self, stage: str, error_msg: str) -> None:
        self._write(f"  *** ERROR at {stage}: {error_msg}")

    def run_summary(
        self,
        run_id: str,
        ticker: str,
        final_status: str,
        total_elapsed_sec: float,
        stages_completed: int,
        stages_total: int,
        gate_results: dict[str, bool],
        output_path: str | None,
        errors: list[str],
    ) -> None:
        self._write(f"\n{'='*70}")
        self._write(f"  RUN COMPLETE: {ticker} | {final_status} | {total_elapsed_sec:.1f}s")
        self._write(f"  Stages: {stages_completed}/{stages_total}")

        passed = sum(1 for v in gate_results.values() if v)
        failed = sum(1 for v in gate_results.values() if not v)
        self._write(f"  Gates: {passed} passed, {failed} failed")

        if errors:
            self._write(f"  Errors ({len(errors)}):")
            for err in errors[:10]:
                self._write(f"    - {err[:120]}")

        if output_path:
            self._write(f"  Output: {output_path}")
        else:
            self._write("  Output: NO PDF GENERATED")

        self._write(f"{'='*70}\n")
