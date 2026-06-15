from __future__ import annotations
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def test_required_v3_domains_exist():
    for d in [
        '01_pandera_data_quality','02_ragas_retrieval','03_financial_benchmarks','04_deepeval_agent',
        '05_ops_cost_latency','06_citation_provenance','07_report_quality','08_publication_readiness'
    ]:
        assert (ROOT / d).exists(), d


def test_metric_registry_covers_all_categories():
    text = (ROOT / 'shared/metric_registry_v3.yaml').read_text(encoding='utf-8')
    for category in ['data_quality','rag','financial_model','citation','agent_llm','report_quality','operations','publication_readiness']:
        assert f'category: {category}' in text
    assert text.count('metric_id:') >= 60


def test_common_metric_schema_has_governance_fields():
    schema = json.loads((ROOT / 'shared/schemas/metric_result.schema.json').read_text(encoding='utf-8'))
    req = set(schema['required'])
    for field in ['metric_id','category','layer','metric_type','scope','severity','blocks_publish','threshold_operator','sample_size','failed_examples','remediation_hint']:
        assert field in req


def test_v3_fact_dataset_has_lineage_columns():
    with (ROOT / 'shared/golden_financials/all_benchmark_facts_v3.csv').open(encoding='utf-8') as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
    for col in ['snapshot_id','fact_id','source_doc_id','source_tier','reconciliation_status','freshness_status','promotion_status','ocr_status','materiality']:
        assert col in cols


def test_citation_report_publication_datasets_are_non_empty():
    assert len(read_jsonl(ROOT / '06_citation_provenance/claim_ledger_cases.jsonl')) >= 80
    assert len(read_jsonl(ROOT / '07_report_quality/report_quality_cases.jsonl')) >= 10
    assert len(read_jsonl(ROOT / '08_publication_readiness/publication_readiness_cases.jsonl')) >= 20


def test_evaluation_artifact_examples_have_metrics():
    examples = list((ROOT / 'shared/evaluation_artifact_examples').glob('*.json'))
    examples += list((ROOT / '01_pandera_data_quality/artifact_examples').glob('*.json'))
    examples += list((ROOT / '03_financial_benchmarks/artifact_examples').glob('*.json'))
    examples += list((ROOT / '06_citation_provenance/artifact_examples').glob('*.json'))
    examples += list((ROOT / '07_report_quality/artifact_examples').glob('*.json'))
    examples += list((ROOT / '08_publication_readiness/artifact_examples').glob('*.json'))
    assert examples
    for p in examples:
        obj = json.loads(p.read_text(encoding='utf-8'))
        assert obj['schema_version'] == '20260615_v3'
        assert isinstance(obj.get('metrics'), list) and obj['metrics']
