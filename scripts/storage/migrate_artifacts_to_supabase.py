"""Upload inferable run artifacts to runs and approved reports to exports."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.storage import EXPORTS_BUCKET, RUNS_BUCKET, approved_export_key, run_artifact_key, run_chart_key
from scripts.storage.common import ROOT, adapter_for, add_common_args, files_under, infer_run_id, register_run_artifact, upload_no_overwrite, write_audit

ARTIFACT_ROOT = ROOT / "artifacts"
NAME_MAP = {
    "manifest.json": "manifest.json", "facts_snapshot.json": "facts_snapshot.json",
    "valuation.json": "valuation.json", "evidence_pack.json": "evidence_pack.json",
    "review_packet.json": "review_packet.json", "quality_gate.json": "quality_gate.json",
    "report.md": "report.md", "report.html": "report.html", "report.pdf": "report.pdf",
}


def target(source: Path) -> tuple[str, str] | None:
    run_id = infer_run_id(source)
    if not run_id:
        return None
    name = source.name.lower()
    ticker = next((part.upper() for part in source.parts if part.isalpha() and 2 <= len(part) <= 10), "UNKNOWN")
    if "approved" in source.as_posix().lower() and name in {"report.pdf", "report.html", "report.md"}:
        return EXPORTS_BUCKET, approved_export_key(ticker, run_id, name)
    if source.suffix.lower() == ".png" and "chart" in source.as_posix().lower():
        return RUNS_BUCKET, run_chart_key(run_id, source.stem)
    artifact_name = next((value for key, value in NAME_MAP.items() if name == key or name.endswith("_" + key)), None)
    if artifact_name:
        return RUNS_BUCKET, run_artifact_key(run_id, artifact_name)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    args = parser.parse_args()
    sources = files_under((ARTIFACT_ROOT,))
    adapter = adapter_for(args.dry_run)
    actions = []
    for source in sources:
        destination = target(source)
        if destination:
            action = upload_no_overwrite(adapter, source, *destination, dry_run=args.dry_run)
            actions.append(action)
            run_id = infer_run_id(source)
            if not args.dry_run and destination[0] == RUNS_BUCKET and run_id:
                register_run_artifact(run_id, action)
    audit = write_audit(args.audit_name or "run_artifacts", actions, len(sources), len(sources), args.dry_run)
    print(f"before={len(sources)} after={len(sources)} actions={len(actions)} audit={audit}")


if __name__ == "__main__":
    main()
