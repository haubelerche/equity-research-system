from __future__ import annotations
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def count_csv_rows(path: Path) -> int:
    with path.open(encoding='utf-8') as f:
        return max(0, sum(1 for _ in f) - 1)


def main():
    metric_registry = (ROOT / 'shared/metric_registry_v3.yaml').read_text(encoding='utf-8')
    counts = {
        'metric_registry_entries': metric_registry.count('metric_id:'),
        'v3_financial_facts': count_csv_rows(ROOT / 'shared/golden_financials/all_benchmark_facts_v3.csv'),
        'rag_v3_queries': count_csv_rows(ROOT / '02_ragas_retrieval/golden_queries/golden_query_index_v3.csv'),
        'rag_v3_chunks': len(read_jsonl(ROOT / '02_ragas_retrieval/golden_chunks/official_like_chunks_v3.jsonl')),
        'finance_v3_cases': len(read_jsonl(ROOT / '03_financial_benchmarks/golden_valuation/finance_cases_v3.jsonl')),
        'agent_v3_trace_cases': len(read_jsonl(ROOT / '04_deepeval_agent/deepeval_cases/agent_trace_cases_v3.jsonl')),
        'ops_v3_traces': count_csv_rows(ROOT / '05_ops_cost_latency/golden_run_traces_v3.csv'),
        'citation_claim_cases': len(read_jsonl(ROOT / '06_citation_provenance/claim_ledger_cases.jsonl')),
        'report_quality_cases': len(read_jsonl(ROOT / '07_report_quality/report_quality_cases.jsonl')),
        'publication_cases': len(read_jsonl(ROOT / '08_publication_readiness/publication_readiness_cases.jsonl')),
    }
    checks = {
        'has_8_domains': all((ROOT / d).exists() for d in ['01_pandera_data_quality','02_ragas_retrieval','03_financial_benchmarks','04_deepeval_agent','05_ops_cost_latency','06_citation_provenance','07_report_quality','08_publication_readiness']),
        'has_metric_registry': counts['metric_registry_entries'] >= 60,
        'has_v3_fact_lineage': counts['v3_financial_facts'] >= 1000,
        'has_citation_report_publication': counts['citation_claim_cases'] >= 80 and counts['report_quality_cases'] >= 10 and counts['publication_cases'] >= 20,
        'has_artifact_schemas': len(list((ROOT/'shared/evaluation_artifact_schemas').glob('*.schema.json'))) >= 8,
        'has_docs_reference': len(list((ROOT/'docs_reference').glob('*.md'))) >= 20,
    }
    score = sum(100/len(checks) for v in checks.values() if v)
    status = 'PASS' if all(checks.values()) else 'WARN_OR_FAIL'
    report = {'suite':'vn_pharma_benchmark_suite_20260615_v3','score':round(score,2),'status':status,'checks':checks,'counts':counts}
    out = ROOT / 'shared/scorecards/benchmark_scorecard_v3.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
