from __future__ import annotations

import pytest

from backend.harness.model_adapter import (
    CHEAP_MODEL,
    MAIN_MODEL,
    PRODUCTION_MODELS,
    OpenAIModelAdapter,
    create_model_adapter,
    select_model_for_task,
    validate_production_model,
)


class TestSelectModelForTask:
    def test_lightweight_tasks_use_cheap_model(self) -> None:
        for task_type in ("route", "classify", "extract_json", "detect_ticker",
                          "detect_period", "detect_unit", "normalize_format"):
            assert select_model_for_task(task_type) == CHEAP_MODEL

    def test_reasoning_tasks_use_main_model(self) -> None:
        for task_type in ("research_plan", "financial_analysis", "report_draft",
                          "critic_review", "valuation", "evidence_summary"):
            assert select_model_for_task(task_type) == MAIN_MODEL

    def test_unknown_task_defaults_to_main_model(self) -> None:
        assert select_model_for_task("something_new") == MAIN_MODEL


class TestValidateProductionModel:
    def test_main_model_allowed(self) -> None:
        validate_production_model(MAIN_MODEL)

    def test_cheap_model_allowed(self) -> None:
        validate_production_model(CHEAP_MODEL)

    def test_claude_rejected(self) -> None:
        with pytest.raises(ValueError, match="not allowed in production"):
            validate_production_model("claude-sonnet-4-6")

    def test_gpt4o_rejected(self) -> None:
        with pytest.raises(ValueError, match="not allowed in production"):
            validate_production_model("gpt-4o")

    def test_gpt41_rejected(self) -> None:
        with pytest.raises(ValueError, match="not allowed in production"):
            validate_production_model("gpt-4.1")

    def test_gpt55_rejected(self) -> None:
        with pytest.raises(ValueError, match="not allowed in production"):
            validate_production_model("gpt-5.5")

    def test_gpt54_full_rejected(self) -> None:
        with pytest.raises(ValueError, match="not allowed in production"):
            validate_production_model("gpt-5.4")


class TestCreateModelAdapter:
    def test_returns_openai_adapter_for_main_model(self) -> None:
        adapter = create_model_adapter(MAIN_MODEL)
        assert isinstance(adapter, OpenAIModelAdapter)

    def test_returns_openai_adapter_for_cheap_model(self) -> None:
        adapter = create_model_adapter(CHEAP_MODEL)
        assert isinstance(adapter, OpenAIModelAdapter)

    def test_defaults_to_main_model(self) -> None:
        adapter = create_model_adapter()
        assert isinstance(adapter, OpenAIModelAdapter)

    def test_rejects_non_production_model(self) -> None:
        with pytest.raises(ValueError, match="not allowed in production"):
            create_model_adapter("claude-sonnet-4-6")


class TestCostEstimation:
    def test_main_model_cost(self) -> None:
        cost = OpenAIModelAdapter._estimate_cost(MAIN_MODEL, 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.75 + 4.50)

    def test_cheap_model_cost(self) -> None:
        cost = OpenAIModelAdapter._estimate_cost(CHEAP_MODEL, 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.20 + 1.25)

    def test_zero_tokens(self) -> None:
        cost = OpenAIModelAdapter._estimate_cost(MAIN_MODEL, 0, 0)
        assert cost == 0.0


class TestProductionModelsConsistency:
    def test_main_and_cheap_are_in_production_set(self) -> None:
        assert MAIN_MODEL in PRODUCTION_MODELS
        assert CHEAP_MODEL in PRODUCTION_MODELS

    def test_exactly_two_production_models(self) -> None:
        assert len(PRODUCTION_MODELS) == 2
