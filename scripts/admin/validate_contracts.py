from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]

JSON_SCHEMAS = [
    "config/dataset/contracts/source_version.schema.json",
    "config/dataset/contracts/financial_fact.schema.json",
    "config/dataset/contracts/catalyst_event.schema.json",
    "config/dataset/contracts/document_chunk.schema.json",
    "config/dataset/contracts/citation.schema.json",
    "config/dataset/contracts/agent_message.schema.json",
    "config/dataset/contracts/tool_call.schema.json",
]

YAML_FILES = [
    "config/dataset/sources/source_catalog.yaml",
    "config/dataset/taxonomy/financial_taxonomy_vn_pharma.yaml",
    "config/dataset/taxonomy/catalyst_taxonomy_vn_pharma.yaml",
]


def main() -> None:
    for rel_path in JSON_SCHEMAS:
        path = ROOT / rel_path
        with path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
        if schema.get("type") != "object":
            raise ValueError(f"{rel_path} must be an object schema")

    for rel_path in YAML_FILES:
        path = ROOT / rel_path
        with path.open("r", encoding="utf-8") as f:
            _ = yaml.safe_load(f)

    print("Contract and taxonomy validation passed")


if __name__ == "__main__":
    main()
