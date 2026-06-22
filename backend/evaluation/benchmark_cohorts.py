"""Benchmark cohort selection for evaluation scripts.

The cohort layer keeps benchmark runs from collapsing onto a single ticker
proxy. It lets scripts resolve a diverse, reproducible basket of tickers from
repository config instead of hard-coding one symbol such as DBD.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml

from backend.dataset.config_io import load_universe_tickers
from backend.evaluation.benchmark_paths import BENCHMARK_COHORTS_PATH, GOLDEN_FINANCIALS_DIR

DEFAULT_BENCHMARK_COHORT = "full_universe"


def _normalize_tickers(tickers: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for ticker in tickers:
        value = str(ticker or "").strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _tickers_with_golden_financials(root: Path = GOLDEN_FINANCIALS_DIR) -> set[str]:
    if not root.exists():
        return set()
    return {
        path.stem.upper()
        for path in root.glob("*.csv")
        if path.is_file() and not path.stem.lower().startswith("all_")
    }


def _apply_cohort_filters(tickers: list[str], payload: dict[str, Any]) -> list[str]:
    if payload.get("requires_golden_financials"):
        ready = _tickers_with_golden_financials()
        return [ticker for ticker in tickers if ticker in ready]
    return tickers


def load_benchmark_cohort_config(path: Path = BENCHMARK_COHORTS_PATH) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError):
        return {
            "version": "benchmark_cohorts_v1",
            "default_cohort": DEFAULT_BENCHMARK_COHORT,
            "cohorts": {},
        }
    return payload if isinstance(payload, dict) else {
        "version": "benchmark_cohorts_v1",
        "default_cohort": DEFAULT_BENCHMARK_COHORT,
        "cohorts": {},
    }


def available_benchmark_cohorts(path: Path = BENCHMARK_COHORTS_PATH) -> dict[str, list[str]]:
    config = load_benchmark_cohort_config(path)
    cohorts = config.get("cohorts") or {}
    if not isinstance(cohorts, dict):
        return {}
    result: dict[str, list[str]] = {}
    for name, payload in cohorts.items():
        if not isinstance(payload, dict):
            continue
        if payload.get("source") == "universe":
            result[str(name)] = _apply_cohort_filters(
                _normalize_tickers(load_universe_tickers()),
                payload,
            )
        else:
            result[str(name)] = _normalize_tickers(payload.get("tickers") or [])
    return result


def resolve_benchmark_tickers(
    *,
    cohort: str | None = None,
    tickers: Iterable[str] | None = None,
    path: Path = BENCHMARK_COHORTS_PATH,
    validate_against_universe: bool = True,
) -> list[str]:
    if tickers is not None:
        resolved = _normalize_tickers(tickers)
    else:
        config = load_benchmark_cohort_config(path)
        cohorts = config.get("cohorts") or {}
        cohort_name = cohort or str(config.get("default_cohort") or DEFAULT_BENCHMARK_COHORT)
        cohort_payload = cohorts.get(cohort_name) if isinstance(cohorts, dict) else None
        if not isinstance(cohort_payload, dict):
            available = ", ".join(sorted(str(name) for name in cohorts)) or "<none>"
            raise KeyError(f"unknown benchmark cohort {cohort_name!r}; available: {available}")
        if cohort_payload.get("source") == "universe":
            resolved = _apply_cohort_filters(
                _normalize_tickers(load_universe_tickers()),
                cohort_payload,
            )
        else:
            resolved = _normalize_tickers(cohort_payload.get("tickers") or [])

    if not validate_against_universe:
        return resolved

    universe = set(load_universe_tickers())
    missing = [ticker for ticker in resolved if ticker not in universe]
    if missing:
        raise ValueError(
            "benchmark cohort contains tickers outside the configured universe: "
            + ", ".join(missing)
        )
    return resolved
