from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.harness.agent_registry import AgentConfig
from backend.harness.state import ServiceNodeResult


ToolCallable = Callable[..., ServiceNodeResult]


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    implementation: ToolCallable
    owner_agent_ids: tuple[str, ...]
    input_schema: dict
    output_schema: str
    permission_level: str
    timeout_seconds: int
    blocking_semantics: str
    artifact_producer_key: str
    retry_policy: str = "no_retry"
    required_source_refs: bool = False
    cost_policy: str = "metered"


class ToolRegistry:
    def __init__(self) -> None:
        from backend.harness import tools
        self._tools: dict[str, ToolSpec] = {
            "auto_ingest": ToolSpec(
                tool_id="auto_ingest",
                implementation=tools.auto_ingest_tool,
                owner_agent_ids=("data_evidence",),
                input_schema={"ticker": "str", "from_year": "int", "to_year": "int", "ocr": "bool"},
                output_schema="ServiceNodeResult",
                permission_level="read_write_artifact",
                timeout_seconds=300,
                blocking_semantics="non-blocking acquisition; downstream source gates block unverified facts",
                artifact_producer_key="AUTO_INGEST",
            ),
            "build_facts": ToolSpec(
                tool_id="build_facts",
                implementation=tools.build_facts_tool,
                owner_agent_ids=("data_evidence",),
                input_schema={
                    "ticker": "str",
                    "from_year": "int",
                    "to_year": "int",
                    "auto_approve_assumptions": "bool",
                },
                output_schema="ServiceNodeResult",
                permission_level="read_write_artifact",
                timeout_seconds=300,
                blocking_semantics="blocks downstream DATA_QUALITY_GATE on validation failure",
                artifact_producer_key="BUILD_FACTS",
            ),
            "build_index": ToolSpec(
                tool_id="build_index",
                implementation=tools.build_index_tool,
                owner_agent_ids=("data_evidence",),
                input_schema={"ticker": "str", "from_year": "int", "to_year": "int"},
                output_schema="ServiceNodeResult",
                permission_level="read_write_artifact",
                timeout_seconds=300,
                blocking_semantics="supports final citation coverage",
                artifact_producer_key="BUILD_INDEX",
            ),
            "read_snapshot": ToolSpec(
                tool_id="read_snapshot",
                implementation=tools.read_snapshot_tool,
                owner_agent_ids=("financial_analysis",),
                input_schema={"ticker": "str", "snapshot_id": "str"},
                output_schema="ServiceNodeResult",
                permission_level="read_only",
                timeout_seconds=60,
                blocking_semantics="blocks financial analyst review when snapshot is unavailable",
                artifact_producer_key="READ_SNAPSHOT",
            ),
            "read_ratio_artifact": ToolSpec(
                tool_id="read_ratio_artifact",
                implementation=tools.read_ratio_artifact_tool,
                owner_agent_ids=("financial_analysis",),
                input_schema={"ticker": "str", "snapshot_id": "str"},
                output_schema="ServiceNodeResult",
                permission_level="read_only",
                timeout_seconds=60,
                blocking_semantics="blocks financial analyst review when ratio artifact is unavailable",
                artifact_producer_key="READ_RATIO_ARTIFACT",
            ),
            "run_valuation": ToolSpec(
                tool_id="run_valuation",
                implementation=tools.run_valuation_tool,
                owner_agent_ids=("forecast_valuation",),
                input_schema={"ticker": "str", "from_year": "int", "to_year": "int"},
                output_schema="ServiceNodeResult",
                permission_level="read_write_artifact",
                timeout_seconds=300,
                blocking_semantics="blocks VALUATION_GATE on missing valuation components",
                artifact_producer_key="VALUATION_RUN",
            ),
            "run_forecast": ToolSpec(
                tool_id="run_forecast",
                implementation=tools.run_forecast_tool,
                owner_agent_ids=("forecast_valuation",),
                input_schema={"ticker": "str", "snapshot_id": "str", "from_year": "int", "to_year": "int"},
                output_schema="ServiceNodeResult",
                permission_level="read_write_artifact",
                timeout_seconds=300,
                blocking_semantics="blocks FORECAST_QUALITY_GATE on missing deterministic forecast components",
                artifact_producer_key="FORECAST_RUN",
            ),
            "read_valuation_artifact": ToolSpec(
                tool_id="read_valuation_artifact",
                implementation=tools.read_valuation_artifact_tool,
                owner_agent_ids=("forecast_valuation",),
                input_schema={"artifact_path": "str"},
                output_schema="ServiceNodeResult",
                permission_level="read_only",
                timeout_seconds=60,
                blocking_semantics="blocks valuation review when artifact cannot be read",
                artifact_producer_key="READ_VALUATION_ARTIFACT",
            ),
            "evaluate_report_quality": ToolSpec(
                tool_id="evaluate_report_quality",
                implementation=tools.evaluate_quality_tool,
                owner_agent_ids=("senior_critic",),
                input_schema={"ticker": "str", "report_path": "str", "valuation_path": "str"},
                output_schema="ServiceNodeResult",
                permission_level="read_only",
                timeout_seconds=120,
                blocking_semantics="blocks EXPORT_GATE on critical quality failure",
                artifact_producer_key="QUALITY_EVALUATION",
            ),
        }

    def get_tool(self, tool_id: str) -> ToolSpec:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown harness tool_id: {tool_id}") from exc

    def validate_agent_tool_policy(self, agent_configs: dict[str, AgentConfig]) -> None:
        missing = sorted({
            tool_id
            for config in agent_configs.values()
            for tool_id in config.allowed_tools
            if tool_id not in self._tools
        })
        if missing:
            raise ValueError(f"Agent config references unimplemented tools: {missing}")

        violations: list[str] = []
        for agent_id, config in agent_configs.items():
            for tool_id in config.allowed_tools:
                spec = self.get_tool(tool_id)
                if agent_id not in spec.owner_agent_ids:
                    violations.append(f"{agent_id}:{tool_id}")
        if violations:
            raise ValueError(f"Agent config assigns tools to non-owner agents: {violations}")


def get_tool(tool_id: str) -> ToolSpec:
    return ToolRegistry().get_tool(tool_id)


def validate_agent_tool_policy(agent_configs: dict[str, AgentConfig]) -> None:
    ToolRegistry().validate_agent_tool_policy(agent_configs)
