"""Categorise why live RAG metrics are low: per query, show retrieved chunk relevance,
whether the expected value appears in any retrieved chunk, and the RAGAS per-sample scores."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def main(suite_dir: str, tickers: list[str]) -> int:
    base = ROOT / suite_dir
    for ticker in tickers:
        rj = _load(base / ticker / "retrieval_eval.json")
        if not rj:
            print(f"{ticker}: no retrieval_eval.json")
            continue
        print(f"\n===== {ticker} =====")

        def walk(o, key):
            out = []
            stack = [o]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    if key in cur and isinstance(cur[key], list):
                        out.extend(cur[key])
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
            return out

        queries = walk(rj, "queries")
        miss = [q for q in queries if q.get("hit") is False and q.get("material") is True]
        print(f"queries={len(queries)} material_misses={len(miss)}")
        for q in miss[:8]:
            tiers = [c.get("reliability_tier") for c in q.get("top_5", [])]
            print(f"  MISS {q.get('id')}: retrieved_tiers={tiers} first_rank={q.get('first_rank')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "output/evaluation/_live_test",
                  sys.argv[2:] or ["DHG"]))
