from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.orchestrator import Supervisor
from backend.runtime_store import RuntimeStore
from backend.settings import settings


def run_eval(run_id: str, out_dir: Path) -> Path:
    store = RuntimeStore(dsn=settings.database_url)
    supervisor = Supervisor(store=store)
    result = supervisor.run_offline_evaluation(run_id=run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}_offline_eval.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline evaluation for a research run.")
    parser.add_argument("--run-id", required=True, help="Research run id.")
    parser.add_argument(
        "--out-dir",
        default="dataset/evaluations",
        help="Directory to store evaluation output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = run_eval(run_id=args.run_id, out_dir=Path(args.out_dir))
    print(f"Offline evaluation written to: {out}")


if __name__ == "__main__":
    main()

