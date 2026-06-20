"""Dump the graded report-quality dimension distribution across benchmark tickers.

Run after the graded scorer lands to set thresholds empirically and to perform the
variation checkpoint (spec: stop and report honestly if reports are uniform).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.evaluation.runtime_evaluators import (
    REPORT_QUALITY_SCORE_KEYS,
    _pdf_stats,
    _report_pdf_path,
    _report_quality_subscores,
    _report_quality_total,
)

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "frontend" / "public" / "eval" / "framework.json"


def main() -> None:
    tickers = json.loads(FRAMEWORK.read_text(encoding="utf-8")).get("tickers", [])
    rows: dict[str, list[float]] = {key: [] for key in REPORT_QUALITY_SCORE_KEYS}
    totals: list[float] = []
    for ticker in tickers:
        report = _pdf_stats(_report_pdf_path(ROOT, ticker, "report"))
        explanation = _pdf_stats(_report_pdf_path(ROOT, ticker, "explanation"))
        scores = _report_quality_subscores(report, explanation)
        for key in REPORT_QUALITY_SCORE_KEYS:
            value = scores.get(key)
            if isinstance(value, (int, float)):
                rows[key].append(float(value))
        total = _report_quality_total(scores)
        if isinstance(total, (int, float)):
            totals.append(float(total))

    def summarize(values: list[float]) -> str:
        if not values:
            return "n=0"
        values = sorted(values)
        p10 = values[max(0, int(len(values) * 0.10) - 1)]
        return (
            f"n={len(values)} min={values[0]:.1f} p10={p10:.1f} "
            f"median={statistics.median(values):.1f} max={values[-1]:.1f}"
        )

    print(f"tickers={len(tickers)}")
    for key in REPORT_QUALITY_SCORE_KEYS:
        print(f"{key:42} {summarize(rows[key])}")
    print(f"{'quality_total':42} {summarize(totals)}")


if __name__ == "__main__":
    main()
