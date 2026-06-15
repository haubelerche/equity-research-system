from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = ROOT / "config" / "benchmarks"


def test_interface_benchmark_dataset_folders_exist() -> None:
    expected = {
        "01_pandera_data_quality": "01_pandera_data_quality",
        "02_ragas_retrieval": "02_ragas_retrieval",
        "03_financial_benchmarks": "03_financial_benchmarks",
        "04_deepeval_agent": "04_deepeval_agent",
        "05_ops_cost_latency": "05_ops_cost_latency",
    }

    for folder, benchmark_id in expected.items():
        manifest_path = BENCHMARK_ROOT / folder / "dataset_manifest.yaml"
        assert manifest_path.is_file(), f"{folder} is missing dataset_manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

        assert manifest["benchmark"]["id"] == benchmark_id
        assert manifest["datasets"], f"{folder} must declare at least one dataset"


def test_manifest_required_datasets_resolve_to_existing_roots() -> None:
    for manifest_path in sorted(BENCHMARK_ROOT.glob("*/dataset_manifest.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        datasets = manifest["datasets"]
        dataset_items = (
            datasets.items()
            if isinstance(datasets, dict)
            else ((str(index), dataset) for index, dataset in enumerate(datasets, start=1))
        )
        for dataset_id, dataset in dataset_items:
            raw_path = str(dataset)
            root_path = raw_path.split("*", 1)[0].rstrip("/\\")
            assert (manifest_path.parent / root_path).exists(), (
                f"{manifest_path.parent.name}:{dataset_id} points to missing "
                f"required dataset root {raw_path}"
            )
