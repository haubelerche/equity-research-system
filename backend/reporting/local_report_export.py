"""Local filesystem layout for report export previews."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPORT_ROOT = ROOT / "output" / "report_exports"


def prepare_local_report_export_dir(
    ticker: str,
    run_id: str,
    *,
    base_dir: Path | str | None = None,
) -> Path:
    """Return a clean latest export directory and archive the previous latest."""
    ticker_key = ticker.upper()
    root = Path(base_dir) if base_dir is not None else DEFAULT_EXPORT_ROOT
    ticker_root = root / ticker_key
    latest = ticker_root / "latest"
    archive_root = ticker_root / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)

    if latest.exists() and any(latest.iterdir()):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = archive_root / f"{stamp}_{run_id}"
        suffix = 1
        while archive_dir.exists():
            suffix += 1
            archive_dir = archive_root / f"{stamp}_{run_id}_{suffix}"
        shutil.move(str(latest), str(archive_dir))

    latest.mkdir(parents=True, exist_ok=True)
    metadata = {
        "ticker": ticker_key,
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "latest contains the most recent local export; older exports are archived.",
    }
    (latest / "EXPORT_METADATA.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return latest
