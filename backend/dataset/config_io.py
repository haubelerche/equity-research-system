from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DATASET_CONFIG_DIR = ROOT / "config" / "dataset"
UNIVERSE_FILE = DATASET_CONFIG_DIR / "universe" / "pharma_vn_universe.csv"
FIN_TAXONOMY_FILE = DATASET_CONFIG_DIR / "taxonomy" / "financial_taxonomy_vn_pharma.yaml"
CATALYST_TAXONOMY_FILE = DATASET_CONFIG_DIR / "taxonomy" / "catalyst_taxonomy_vn_pharma.yaml"


def load_universe_rows() -> list[dict[str, str]]:
    with UNIVERSE_FILE.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_universe_tickers() -> list[str]:
    return [row["ticker"].strip().upper() for row in load_universe_rows() if row.get("ticker")]


def load_financial_taxonomy() -> dict[str, Any]:
    with FIN_TAXONOMY_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_catalyst_taxonomy() -> dict[str, Any]:
    with CATALYST_TAXONOMY_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

