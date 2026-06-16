from pathlib import Path
import sys
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "shared" / "golden_financials" / "all_benchmark10_plus_recommended_facts.csv"
NEG = ROOT / "01_pandera_data_quality" / "negative_fixtures"

pytest.importorskip("pandera", reason="pandera is optional in package-level structural tests")
sys.path.insert(0, str(ROOT / "01_pandera_data_quality"))
from pandera_schema import validate_facts  # noqa: E402


def test_golden_facts_schema_valid():
    df = pd.read_csv(FACTS)
    validated = validate_facts(df)
    assert len(validated) >= 10 * 100


def test_negative_fixtures_fail():
    for path in NEG.glob("*.csv"):
        if path.name == "baseline_valid_sample.csv":
            continue
        df = pd.read_csv(path)
        with pytest.raises(Exception):
            validate_facts(df)
