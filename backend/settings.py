from __future__ import annotations

import os
from dataclasses import dataclass


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


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
    report_output_dir: str = os.getenv("REPORT_OUTPUT_DIR", "output")
    report_universe_csv: str = os.getenv(
        "REPORT_UNIVERSE_CSV",
        "config/dataset/universe/pharma_vn_universe.csv",
    )
    storage_inventory_timeout_sec: float = float(os.getenv("STORAGE_INVENTORY_TIMEOUT_SEC", "2.5"))
    storage_file_timeout_sec: float = float(os.getenv("STORAGE_FILE_TIMEOUT_SEC", "15.0"))
    storage_api_max_attempts: int = int(os.getenv("STORAGE_API_MAX_ATTEMPTS", "1"))
    cors_allow_origins: tuple[str, ...] = _csv_env(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:4173,https://multi-agent-equity-research.vercel.app",
    )
    cors_allow_origin_regex: str = os.getenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"https://.*\.vercel\.app",
    )


settings = Settings()
