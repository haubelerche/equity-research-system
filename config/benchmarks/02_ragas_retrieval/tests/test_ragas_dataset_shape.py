from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def test_ragas_samples_have_ground_truth_and_context_policy():
    path = ROOT / "02_ragas_retrieval" / "ragas" / "ragas_samples.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) >= 300
    assert any(r["metadata"].get("unanswerable") for r in rows)
    answerable = [r for r in rows if not r["metadata"].get("unanswerable")]
    assert all(r["contexts"] for r in answerable)
