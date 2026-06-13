from dataclasses import dataclass

from backend.harness.tools import _official_facts_ready


@dataclass
class _Result:
    ingest_status: str
    promoted: int


def test_official_ready_requires_promoted_fact():
    results = [_Result(ingest_status="OFFICIAL_FACTS_READY", promoted=0)]
    assert _official_facts_ready(results) is False


def test_official_ready_accepts_promoted_official_fact():
    results = [_Result(ingest_status="OFFICIAL_FACTS_READY", promoted=2)]
    assert _official_facts_ready(results) is True


def test_promoted_tier2_fact_is_not_official_ready():
    results = [_Result(ingest_status="TIER2_ONLY", promoted=2)]
    assert _official_facts_ready(results) is False
