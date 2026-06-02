from __future__ import annotations

from unittest.mock import MagicMock


def test_run_research_cli_exposes_only_canonical_harness_args() -> None:
    from scripts.run_research import parse_args

    args = parse_args(["--ticker", "dhg", "--from-year", "2022", "--to-year", "2025", "--ocr"])

    assert args.ticker == "dhg"
    assert args.from_year == 2022
    assert args.to_year == 2025
    assert args.ocr is True
    assert not hasattr(args, "legacy_pipeline")
    assert not hasattr(args, "skip_ingest")


def test_runner_execute_preserves_period_scope_and_ocr_flag(monkeypatch) -> None:
    from backend.harness.runner import ResearchGraphRunner
    from backend.orchestrator import RunContext

    captured = {}

    def fake_run_until_pause(self, state, start_stage="PREFLIGHT"):
        captured["from_year"] = state.from_year
        captured["to_year"] = state.to_year
        captured["ocr"] = state.ocr
        return state

    monkeypatch.setattr(ResearchGraphRunner, "run_until_pause", fake_run_until_pause)

    runner = ResearchGraphRunner(store=MagicMock())
    runner.execute(
        RunContext(
            run_id="run_scope_test",
            ticker="DHG",
            run_type="full_report",
            objective="scope test",
            policy={},
            flags={},
            from_year=2022,
            to_year=2024,
            ocr=True,
        )
    )

    assert captured == {"from_year": 2022, "to_year": 2024, "ocr": True}
