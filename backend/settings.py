from __future__ import annotations

import os
from dataclasses import dataclass


def _env_first(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    worker_pool_size: int = int(os.getenv("WORKER_POOL_SIZE", "4"))
    default_budget_policy: str = os.getenv("DEFAULT_BUDGET_POLICY", "standard")
    default_model_name: str = _env_first("DEFAULT_MODEL_NAME", "DEFAULT_MODEL", default="gpt-5-mini")
    soft_budget_usd: float = float(os.getenv("SOFT_BUDGET_USD", "2.0"))
    hard_budget_usd: float = float(os.getenv("HARD_BUDGET_USD", "5.0"))
    fallback_model: str = os.getenv("FALLBACK_MODEL", "gpt-5-nano")
    enable_agentic_loops: bool = os.getenv("ENABLE_AGENTIC_LOOPS", "1") == "1"
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


settings = Settings()
