from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SMOKE_TARGETS = (
    "tests/api/test_evaluation_endpoints.py",
    "tests/api/test_reports_endpoints.py",
    "tests/unit/test_borrowing_alias_map.py",
    "tests/unit/test_vnstock_ar_alias.py",
    "tests/unit/test_vnstock_finance_dedup.py",
    "tests/unit/test_chart_generator.py",
)


def main() -> int:
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    command = [sys.executable, "-m", "pytest", "-q", *SMOKE_TARGETS]
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
