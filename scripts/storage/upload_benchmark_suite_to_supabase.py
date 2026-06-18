"""Upload benchmark dashboard artifacts to Supabase Storage.

Production API containers should not carry generated ``output/`` payloads.
This script publishes the small root-level benchmark dashboard JSON artifacts
to the private ``runs`` bucket under ``<run_id>/<artifact_name>`` so
``backend.evaluation.project_evaluator`` can serve them through the normal API.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key
from scripts.storage.common import FileAction, ROOT, adapter_for, checksum_file, write_audit

DEFAULT_SOURCE = ROOT / "output" / "evaluation" / "eval_result" / "benchmark_suite"
DEFAULT_RUN_ID = "benchmark-suite-latest"
ARTIFACT_NAMES = (
    "benchmark_suite.json",
    "evaluation_packet.json",
    "data_quality.json",
    "retrieval_eval.json",
    "financial_eval.json",
    "citation_eval.json",
    "agent_eval.json",
    "report_eval.json",
    "publication_readiness.json",
    "observability_eval.json",
)


def _upload_json(
    adapter: SupabaseStorageAdapter | None,
    source: Path,
    run_id: str,
    *,
    dry_run: bool,
    upsert: bool,
) -> FileAction:
    target = run_artifact_key(run_id, source.name)
    checksum = checksum_file(source)
    if dry_run:
        return FileAction(
            str(source),
            RUNS_BUCKET,
            target,
            "would_upload",
            checksum,
            source.stat().st_size,
            "application/json",
            False,
        )
    assert adapter is not None
    adapter.upload_file(RUNS_BUCKET, target, source, "application/json", upsert=upsert)
    validated = adapter.validate_checksum(RUNS_BUCKET, target, checksum)
    return FileAction(
        str(source),
        RUNS_BUCKET,
        target,
        "uploaded",
        checksum,
        source.stat().st_size,
        "application/json",
        validated,
        None if validated else "checksum_validation_failed",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--upsert", action="store_true")
    parser.add_argument("--audit-name", default="benchmark_suite_storage_upload")
    args = parser.parse_args()

    source_dir = args.source_dir if args.source_dir.is_absolute() else ROOT / args.source_dir
    sources = [source_dir / name for name in ARTIFACT_NAMES if (source_dir / name).is_file()]
    missing = [name for name in ARTIFACT_NAMES if not (source_dir / name).is_file()]
    adapter = adapter_for(args.dry_run)
    actions = [
        _upload_json(adapter, source, args.run_id, dry_run=args.dry_run, upsert=args.upsert)
        for source in sources
    ]
    audit = write_audit(args.audit_name, actions, len(ARTIFACT_NAMES), len(sources), args.dry_run)
    print(
        f"run_id={args.run_id} uploaded={len(actions)} missing={missing} "
        f"dry_run={args.dry_run} audit={audit}"
    )


if __name__ == "__main__":
    main()
