from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from backend.settings import settings

REQUIRED_PROMPT_SECTIONS = [
    "# Objective",
    "# Allowed Inputs",
    "# Forbidden Actions",
    "# Output JSON Schema",
    "# Uncertainty Language",
    "# Source And Citation Discipline",
    "# Escalation Conditions",
    "# Project Disclaimer Boundary",
]

VALID_AGENT_ROLES = {
    "SupervisorAgent",
    "DataRetrievalAgent",
    "FinancialAnalystAgent",
    "ValuationAgent",
    "ReportWriterCriticAgent",
}

VALID_AGENT_TOOLS = {
    "build_facts",
    "build_index",
    "read_snapshot",
    "read_ratio_artifact",
    "run_valuation",
    "read_valuation_artifact",
    "generate_report",
    "evaluate_report_quality",
}

MODEL_ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)(?::-(.+))?\}$")


class AgentConfig(BaseModel):
    agent_id: str
    role: str
    model: str
    temperature: float = 0.0
    prompt_path: str
    prompt: str
    allowed_tools: list[str] = Field(default_factory=list)
    output_schema: str = "AgentResult"
    budget_class: str = "reasoning"
    timeout_seconds: int = 60
    retry_policy: str = "no_retry"


class AgentRegistry:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path("config/agents/agents.yml")
        self.base_dir = self.config_path.parent
        self._configs: dict[str, AgentConfig] | None = None

    def load(self) -> dict[str, AgentConfig]:
        if self._configs is not None:
            return self._configs
        if not self.config_path.exists():
            raise FileNotFoundError(f"Agent config not found: {self.config_path}")
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        agents = raw.get("agents")
        if not isinstance(agents, dict) or not agents:
            raise ValueError("Agent config must contain a non-empty 'agents' mapping")

        configs: dict[str, AgentConfig] = {}
        for agent_id, spec in agents.items():
            if spec.get("role") not in VALID_AGENT_ROLES:
                raise ValueError(f"Unsupported role for {agent_id}: {spec.get('role')}")
            unsupported_tools = sorted(set(spec.get("allowed_tools") or []) - VALID_AGENT_TOOLS)
            if unsupported_tools:
                raise ValueError(f"Unsupported tools for {agent_id}: {unsupported_tools}")
            prompt_path = self.base_dir / spec["prompt_path"]
            if not prompt_path.exists():
                raise FileNotFoundError(f"Prompt file not found for {agent_id}: {prompt_path}")
            prompt = prompt_path.read_text(encoding="utf-8")
            missing = [section for section in REQUIRED_PROMPT_SECTIONS if section not in prompt]
            if missing:
                raise ValueError(f"Prompt {prompt_path} missing required sections: {missing}")
            resolved_spec = dict(spec)
            resolved_spec["model"] = self._resolve_model(str(spec.get("model") or "default"))
            configs[agent_id] = AgentConfig(agent_id=agent_id, prompt=prompt, **resolved_spec)
        self._configs = configs
        return configs

    def validate(self) -> None:
        self.load()

    def get_agent_config(self, agent_id: str) -> AgentConfig:
        configs = self.load()
        if agent_id not in configs:
            raise KeyError(f"Unknown agent_id: {agent_id}")
        return configs[agent_id]

    @staticmethod
    def _resolve_model(model: str) -> str:
        if model in {"default", "${DEFAULT_MODEL_NAME}", "${DEFAULT_MODEL}"}:
            return settings.default_model_name
        match = MODEL_ENV_PATTERN.match(model)
        if not match:
            return model
        env_name, fallback = match.groups()
        resolved = os.getenv(env_name) or fallback
        if not resolved:
            raise ValueError(f"Model environment variable is not set: {env_name}")
        return resolved
