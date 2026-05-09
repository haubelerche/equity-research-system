from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]

JSON_SCHEMAS = [
    "dataset/contracts/source_version.schema.json",
    "dataset/contracts/financial_fact.schema.json",
    "dataset/contracts/catalyst_event.schema.json",
    "dataset/contracts/document_chunk.schema.json",
    "dataset/contracts/citation.schema.json",
    "dataset/contracts/agent_message.schema.json",
    "dataset/contracts/tool_call.schema.json",
]

YAML_FILES = [
    "dataset/sources/source_catalog.yaml",
    "dataset/taxonomy/financial_taxonomy_vn_pharma.yaml",
    "dataset/taxonomy/catalyst_taxonomy_vn_pharma.yaml",
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
