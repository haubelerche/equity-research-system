from __future__ import annotations

import json
from pathlib import Path
import statistics

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def p95(vals):
    vals = sorted(vals)
    if not vals:
        return 0
    return vals[int(round((len(vals)-1)*0.95))]


def main():
    thresholds = yaml.safe_load((ROOT/'shared/acceptance_thresholds.yaml').read_text(encoding='utf-8'))
    facts = pd.read_csv(ROOT/'shared/golden_financials/all_benchmark10_plus_recommended_facts.csv')
    coverage = facts.groupby('ticker').agg(rows=('ticker','size'), years=('fiscal_year','nunique'), keys=('canonical_key','nunique'), min_conf=('confidence','min')).reset_index()
    data_pass = bool((coverage['years'] >= 4).all() and (coverage['keys'] >= 25).all() and (coverage['min_conf'] >= 0.70).all())

    ragas_rows = [json.loads(line) for line in (ROOT/'02_ragas_retrieval/ragas/ragas_samples.jsonl').read_text(encoding='utf-8').splitlines()]
    answerable = [r for r in ragas_rows if not r.get('metadata',{}).get('unanswerable')]
    rag_pass = len(answerable) >= 10 * 4 * 6 and all(r.get('contexts') for r in answerable)

    valuation_rows = [json.loads(line) for line in (ROOT/'03_financial_benchmarks/golden_valuation/valuation_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    fin_pass = all(r['inputs']['wacc'] > r['inputs']['terminal_growth'] and r['inputs']['shares_outstanding'] > 0 for r in valuation_rows)

    agent_rows = [json.loads(line) for line in (ROOT/'04_deepeval_agent/deepeval_cases/agent_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    agent_pass = len(agent_rows) >= 70 and any(r.get('input',{}).get('seeded_issue') for r in agent_rows)

    traces = pd.read_csv(ROOT/'05_ops_cost_latency/golden_run_traces.csv')
    ops_t = thresholds['05_ops_cost_latency']
    ops_pass = bool(
        p95(traces[traces.run_type=='warm'].total_duration_seconds.tolist()) <= ops_t['warm_full_report_p95_seconds_max'] and
        p95(traces[traces.run_type=='cold'].total_duration_seconds.tolist()) <= ops_t['cold_full_report_p95_seconds_max'] and
        traces.estimated_cost_usd.max() <= ops_t['cost_per_full_report_usd_soft_max'] and
        traces.artifact_upload_failures.sum() <= ops_t['artifact_upload_failures_max'] and
        traces.pdf_render_failures.sum() <= ops_t['pdf_render_failures_max']
    )
    score = 25*data_pass + 20*rag_pass + 25*fin_pass + 20*agent_pass + 10*ops_pass
    report = {
        'suite': 'vn_pharma_benchmark_suite_20260615',
        'score': score,
        'status': 'PASS' if score >= 90 and all([data_pass, rag_pass, fin_pass, agent_pass, ops_pass]) else 'WARN_OR_FAIL',
        'checks': {
            '01_pandera_data_quality': data_pass,
            '02_ragas_retrieval_dataset_shape': rag_pass,
            '03_financial_cases': fin_pass,
            '04_deepeval_case_inventory': agent_pass,
            '05_ops_cost_latency': ops_pass,
        },
        'coverage_by_ticker': coverage.to_dict(orient='records'),
        'counts': {'facts': len(facts), 'ragas_samples': len(ragas_rows), 'valuation_cases': len(valuation_rows), 'agent_cases': len(agent_rows), 'run_traces': len(traces)},
    }
    out = ROOT/'shared/scorecards/benchmark_scorecard.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

if __name__ == '__main__':
    main()
