from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume a persisted harness graph state.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage", required=True)
    return parser.parse_args()


def main() -> None:
    _load_dotenv()
    args = parse_args()

    from backend.harness.runner import ResearchGraphRunner
    from backend.harness.state import ResearchGraphState
    from backend.runtime_store import RuntimeStore
    from backend.settings import settings

    store = RuntimeStore(dsn=settings.database_url)
    latest = store.latest_graph_state(args.run_id)
    if latest is None:
        raise SystemExit(f"graph state not found: {args.run_id}")

    state = ResearchGraphState(**latest)
    state.status = "running"
    state.requires_human = False
    state.blocking_reason = None
    state.errors = []
    store.update_run_state(args.run_id, "analysis_ready", args.stage)

    result = ResearchGraphRunner(store=store).run_until_pause(state, start_stage=args.stage)
    print(f"RESUME_RESULT status={result.status} stage={result.current_stage} blocking={result.blocking_reason}")
    if result.status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
