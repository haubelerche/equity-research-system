 Vietnam Pharma Equity Research � Final Report Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all GOAL_OUTPUT.md �19 Definition of Done criteria � deliver a PDF equity research report with 7 charts, peer comparison, structured artifact contracts (claim_ledger, source_manifest, eval_result), HTML/PDF export, and full gate validation for DHG.

**Architecture:** Three phases: (A) Contracts + Charts � artifact schema dataclasses + matplotlib chart generator for C2-C7; (B) Report Rebuild + Renderer � 8-section Markdown skeleton, driver-based forecast table, Jinja2 HTML template, WeasyPrint PDF export; (C) Gates + Integration � valuation reproducibility gate, source manifest builder, claim ledger builder, wired into generate_report.py and run_research.py.

**Tech Stack:** Python 3.11, matplotlib 3.10 (charts), WeasyPrint 61+ (PDF on Linux/Docker), Jinja2 (HTML), psycopg2 (DB), dataclasses (contracts), pytest (tests)

**Scope note:** This plan has 3 independent subsystems (A/B/C). Each phase produces working software on its own. Execute in order A ? B ? C.

**Dependencies to install:**
```bash
pip install jinja2 weasyprint
# WeasyPrint on Linux requires: apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0
# On Windows, HTML export works; PDF requires Docker or WSL.
```

---

## File Map

```
NEW files:
  backend/report_contracts/__init__.py
  backend/report_contracts/claim_ledger.py       # ClaimEntry dataclass + save/load
  backend/report_contracts/source_manifest.py    # SourceEntry dataclass + build from DB
  backend/report_contracts/eval_result.py        # EvalResult dataclass + save

  backend/reporting/chart_generator.py           # generate_c2..c7() functions
  backend/reporting/peer_comparison.py           # build_peer_table() from DB

  backend/report_gates/valuation_reproducibility_gate.py

  templates/report.html.j2                       # Jinja2 HTML template
  templates/report.css                           # Professional CSS

  backend/reporting/html_renderer.py             # render_html(context, out_path)
  backend/reporting/pdf_renderer.py              # render_pdf(html_path, out_path)

  tests/reporting/test_chart_generator.py
  tests/reporting/test_peer_comparison.py
  tests/reporting/test_claim_ledger.py
  tests/reporting/test_html_renderer.py
  tests/reporting/test_valuation_gate.py

MODIFY files:
  requirements.txt                               # add jinja2, weasyprint
  scripts/generate_report.py                     # 8-section skeleton, charts, artifacts
  scripts/run_research.py                        # wire HTML/PDF output
  Dockerfile                                     # add pango/cairo for WeasyPrint
```

---

## PHASE A � Artifact Contracts + Chart Generator

### Task A1: Add dependencies and create module skeletons

**Files:**
- Modify: `requirements.txt`
- Create: `backend/report_contracts/__init__.py`
- Create: `backend/reporting/__init__.py` (if not exists)
- Create: `tests/reporting/__init__.py`

- [ ] **Step 1: Add dependencies to requirements.txt**

```
# append to requirements.txt:
jinja2>=3.1
weasyprint>=61.0
```

- [ ] **Step 2: Create module directories**

```bash
mkdir -p backend/report_contracts
mkdir -p tests/reporting
touch backend/report_contracts/__init__.py
touch tests/reporting/__init__.py
```

- [ ] **Step 3: Verify install**

```bash
pip install jinja2 weasyprint
python -c "import jinja2; import matplotlib; print('deps ok')"
```

Expected: `deps ok` (weasyprint may fail on Windows � that's ok, HTML path still works)

- [ ] **Step 4: Commit**

```bash
git add requirements.txt backend/report_contracts/__init__.py tests/reporting/__init__.py
git commit -m "feat(report): add jinja2/weasyprint deps and module scaffolds"
```

---

### Task A2: ClaimEntry + SourceEntry + EvalResult contracts

**Files:**
- Create: `backend/report_contracts/claim_ledger.py`
- Create: `backend/report_contracts/source_manifest.py`
- Create: `backend/report_contracts/eval_result.py`
- Test: `tests/reporting/test_claim_ledger.py`

- [ ] **Step 1: Write failing test**

```python
# tests/reporting/test_claim_ledger.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
from backend.report_contracts.claim_ledger import ClaimEntry, ClaimLedger

def test_claim_entry_roundtrip(tmp_path):
    entry = ClaimEntry(
        claim_id="CLM-001", run_id="RUN-test", section="investment_thesis",
        page=1, claim_text="Doanh thu 2024 tang 12.3%", claim_type="quantitative",
        ticker="DHG", period="2024A", metric="revenue_growth",
        value=0.123, unit="%", source_refs=["SRC-001"], artifact_refs=[],
        support_status="supported", confidence=0.92, review_status="approved",
    )
    ledger = ClaimLedger(run_id="RUN-test", ticker="DHG", claims=[entry])
    out = tmp_path / "claim_ledger.json"
    ledger.save(out)
    loaded = ClaimLedger.load(out)
    assert loaded.claims[0].claim_id == "CLM-001"
    assert loaded.claims[0].value == 0.123

def test_unsupported_claim_blocked():
    entry = ClaimEntry(
        claim_id="CLM-002", run_id="RUN-test", section="conclusion",
        page=8, claim_text="N�n mua ngay", claim_type="conclusion",
        ticker="DHG", period="", metric="", value=None, unit="",
        source_refs=[], artifact_refs=[], support_status="unsupported",
        confidence=0.0, review_status="pending_review",
    )
    ledger = ClaimLedger(run_id="RUN-test", ticker="DHG", claims=[entry])
    issues = ledger.validate_for_final_export()
    assert any("unsupported" in i.lower() for i in issues)
```

- [ ] **Step 2: Run � expect failure**

```bash
pytest tests/reporting/test_claim_ledger.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.report_contracts.claim_ledger'`

- [ ] **Step 3: Implement claim_ledger.py**

```python
# backend/report_contracts/claim_ledger.py
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

VALID_CLAIM_TYPES = {
    "quantitative", "qualitative_business", "valuation", "forecast",
    "risk", "catalyst", "peer_comparison", "conclusion", "disclaimer",
}
VALID_SUPPORT_STATUS = {"supported", "partially_supported", "unsupported", "conflicting"}


@dataclass
class ClaimEntry:
    claim_id: str
    run_id: str
    section: str
    page: int
    claim_text: str
    claim_type: str
    ticker: str
    period: str
    metric: str
    value: float | None
    unit: str
    source_refs: list[str]
    artifact_refs: list[str]
    support_status: str
    confidence: float
    review_status: str  # "approved" | "pending_review"


@dataclass
class ClaimLedger:
    run_id: str
    ticker: str
    claims: list[ClaimEntry] = field(default_factory=list)

    def add(self, entry: ClaimEntry) -> None:
        self.claims.append(entry)

    def validate_for_final_export(self) -> list[str]:
        """Return list of blocking issues. Empty list = export allowed."""
        issues: list[str] = []
        for c in self.claims:
            if c.support_status == "unsupported":
                issues.append(f"[{c.claim_id}] unsupported claim in section '{c.section}': {c.claim_text[:60]}")
            if c.support_status == "conflicting":
                issues.append(f"[{c.claim_id}] conflicting claim needs reviewer approval: {c.claim_text[:60]}")
        return issues

    def citation_coverage(self) -> float:
        """Fraction of quantitative claims that have at least one source_ref."""
        quant = [c for c in self.claims if c.claim_type == "quantitative"]
        if not quant:
            return 1.0
        cited = [c for c in quant if c.source_refs or c.artifact_refs]
        return len(cited) / len(quant)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "claims": [asdict(c) for c in self.claims],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> ClaimLedger:
        data = json.loads(path.read_text(encoding="utf-8"))
        claims = [ClaimEntry(**c) for c in data["claims"]]
        return cls(run_id=data["run_id"], ticker=data["ticker"], claims=claims)
```

- [ ] **Step 4: Implement source_manifest.py**

```python
# backend/report_contracts/source_manifest.py
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SourceEntry:
    source_id: str
    run_id: str
    ticker: str
    source_type: str          # annual_report | audited_financial | api | news
    source_name: str
    publisher: str
    published_date: str       # ISO date string
    retrieval_timestamp: str  # ISO datetime string
    period: str               # e.g. "2024A"
    url_or_path: str
    reliability_tier: str     # official | regulated_public | reputable_media | third_party_data
    checksum: str
    parser_version: str
    used_sections: list[str]


@dataclass
class SourceManifest:
    run_id: str
    ticker: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources: list[SourceEntry] = field(default_factory=list)

    def add(self, entry: SourceEntry) -> None:
        self.sources.append(entry)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "generated_at": self.generated_at,
            "sources": [asdict(s) for s in self.sources],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> SourceManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = [SourceEntry(**s) for s in data["sources"]]
        return cls(
            run_id=data["run_id"],
            ticker=data["ticker"],
            generated_at=data.get("generated_at", ""),
            sources=sources,
        )

    @classmethod
    def build_from_db(cls, conn, run_id: str, ticker: str) -> SourceManifest:
        """Populate from ingest.sources rows used by this ticker."""
        import psycopg2.extras
        manifest = cls(run_id=run_id, ticker=ticker)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT source_id, source_type, source_title, source_uri,
                       reliability_tier, checksum, connector_version,
                       published_at, fiscal_year, fiscal_period
                FROM ingest.sources
                WHERE ticker = %s
                ORDER BY published_at DESC NULLS LAST
                LIMIT 50
                """,
                (ticker,),
            )
            for row in cur.fetchall():
                tier_map = {1: "official", 2: "reputable_media", 3: "third_party_data"}
                entry = SourceEntry(
                    source_id=row["source_id"],
                    run_id=run_id,
                    ticker=ticker,
                    source_type=row["source_type"],
                    source_name=row["source_title"] or row["source_uri"],
                    publisher="",
                    published_date=str(row["published_at"])[:10] if row["published_at"] else "",
                    retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                    period=f"{row['fiscal_year']}{row['fiscal_period']}" if row["fiscal_year"] else "",
                    url_or_path=row["source_uri"],
                    reliability_tier=tier_map.get(row["reliability_tier"], "third_party_data"),
                    checksum=row["checksum"] or "",
                    parser_version=row["connector_version"] or "1.0",
                    used_sections=["financial_statements"],
                )
                manifest.add(entry)
        return manifest
```

- [ ] **Step 5: Implement eval_result.py**

```python
# backend/report_contracts/eval_result.py
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class GateResult:
    gate: str
    status: str          # pass | warn | fail
    critical: bool
    checked: int
    issues: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    run_id: str
    ticker: str
    report_path: str
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    gates: list[GateResult] = field(default_factory=list)
    citation_coverage: float = 0.0
    numeric_consistency: float = 0.0
    valuation_reproducible: bool = False
    report_status: str = "NEEDS_REVIEW"   # DRAFT | NEEDS_REVIEW | BLOCKED | PENDING_APPROVAL | APPROVED | FINAL_EXPORTABLE
    export_allowed: bool = False

    def add_gate(self, result: GateResult) -> None:
        self.gates.append(result)
        # Recompute overall status
        critical_fails = [g for g in self.gates if g.critical and g.status == "fail"]
        any_fail = any(g.status == "fail" for g in self.gates)
        if critical_fails:
            self.report_status = "BLOCKED"
            self.export_allowed = False
        elif any_fail:
            self.report_status = "NEEDS_REVIEW"
            self.export_allowed = False
        else:
            # Still needs human approval
            self.report_status = "PENDING_APPROVAL"
            self.export_allowed = False

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> EvalResult:
        data = json.loads(path.read_text(encoding="utf-8"))
        gates = [GateResult(**g) for g in data.pop("gates", [])]
        obj = cls(**data)
        obj.gates = gates
        return obj
```

- [ ] **Step 6: Run tests � expect pass**

```bash
pytest tests/reporting/test_claim_ledger.py -v
```
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add backend/report_contracts/ tests/reporting/test_claim_ledger.py
git commit -m "feat(contracts): ClaimLedger, SourceManifest, EvalResult dataclasses"
```

---

### Task A3: Chart generator � C2 Revenue+EBITDA, C3 EPS+PE

**Files:**
- Create: `backend/reporting/chart_generator.py`
- Test: `tests/reporting/test_chart_generator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/reporting/test_chart_generator.py
import sys, json
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.reporting.chart_generator import (
    generate_c2_revenue_ebitda,
    generate_c3_eps_pe,
    generate_c4_margin_roe,
    generate_c5_forecast,
    generate_c7_sensitivity_heatmap,
)


def test_c2_creates_png(tmp_path):
    out = generate_c2_revenue_ebitda(
        ticker="DHG",
        years=[2021, 2022, 2023, 2024, 2025],
        revenues=[2100.0, 2300.0, 2450.0, 2600.0, 2750.0],
        ebitda_margins=[0.18, 0.19, 0.20, 0.21, 0.22],
        out_dir=tmp_path,
        run_id="RUN-test",
    )
    assert out.exists()
    assert out.suffix == ".png"
    assert out.stat().st_size > 5000


def test_c3_creates_png(tmp_path):
    out = generate_c3_eps_pe(
        ticker="DHG",
        years=[2021, 2022, 2023, 2024, 2025],
        eps=[8000, 9000, 9500, 10000, 11000],
        pe_ratios=[12.0, 11.0, 10.5, 10.0, 9.5],
        out_dir=tmp_path,
        run_id="RUN-test",
    )
    assert out.exists()
    assert out.stat().st_size > 5000


def test_c4_creates_png(tmp_path):
    out = generate_c4_margin_roe(
        ticker="DHG",
        years=[2021, 2022, 2023, 2024, 2025],
        gross_margins=[0.38, 0.39, 0.40, 0.41, 0.42],
        net_margins=[0.12, 0.13, 0.13, 0.14, 0.14],
        roe=[0.18, 0.19, 0.20, 0.21, 0.22],
        out_dir=tmp_path,
        run_id="RUN-test",
    )
    assert out.exists()


def test_c7_creates_png(tmp_path):
    # 3x5 sensitivity matrix: rows=g_delta, cols=wacc_delta
    matrix = {
        "rows": ["-0.5%", "Base", "+0.5%"],
        "cols": ["-1.0%", "-0.5%", "Base", "+0.5%", "+1.0%"],
        "values": [
            [180000, 160000, 145000, 132000, 120000],
            [165000, 148000, 137010, 125000, 114000],
            [150000, 135000, 124000, 113000, 103000],
        ],
        "base_row": 1,
        "base_col": 2,
    }
    out = generate_c7_sensitivity_heatmap(
        ticker="DHG",
        matrix=matrix,
        out_dir=tmp_path,
        run_id="RUN-test",
    )
    assert out.exists()
    assert out.stat().st_size > 3000
```

- [ ] **Step 2: Run � expect failure**

```bash
pytest tests/reporting/test_chart_generator.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement chart_generator.py**

```python
# backend/reporting/chart_generator.py
"""Deterministic chart generator for equity research report.

All charts read from pre-computed artifact data (canonical facts, valuation_result).
No LLM involvement. Charts saved as PNG for embedding in HTML/PDF.

Chart ID ? function mapping (GOAL_OUTPUT.md �9):
  C2  generate_c2_revenue_ebitda     Revenue bar + EBITDA margin line
  C3  generate_c3_eps_pe             EPS bar + P/E line (dual-axis)
  C4  generate_c4_margin_roe         Gross/net margin + ROE multi-line
  C5  generate_c5_forecast           Forecast revenue/FCFF bar+line
  C6  generate_c6_dcf_bridge         DCF waterfall (EV?equity?price)
  C7  generate_c7_sensitivity_heatmap WACC�g sensitivity color table
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

_NAVY = "#1a3a6b"
_GOLD = "#c8a84b"
_GREEN = "#2e7d32"
_RED = "#c62828"
_LIGHT_BLUE = "#90caf9"
_FONT = {"fontsize": 8}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
})


def _save(fig: plt.Figure, out_dir: Path, run_id: str, ticker: str, chart_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}_{ticker}_{chart_id}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _source_caption(fig: plt.Figure, text: str) -> None:
    fig.text(0.01, -0.02, text, fontsize=6.5, style="italic", color="#555555")


# -- C2: Revenue & EBITDA Margin ------------------------------------------------

def generate_c2_revenue_ebitda(
    ticker: str,
    years: list[int],
    revenues: list[float],        # t? VND
    ebitda_margins: list[float],  # decimal 0-1
    out_dir: Path,
    run_id: str,
) -> Path:
    fig, ax1 = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(years))
    ax1.bar(x, revenues, color=_NAVY, alpha=0.85, label="Doanh thu thu?n (t? VND)", zorder=3)
    ax1.set_ylabel("t? VND", **_FONT)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{y}A" for y in years], **_FONT)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax1.grid(axis="y", alpha=0.3, zorder=0)

    ax2 = ax1.twinx()
    ax2.plot(x, [m * 100 for m in ebitda_margins], "o-", color=_GOLD,
             linewidth=2, markersize=5, label="EBITDA Margin (%)", zorder=4)
    ax2.set_ylabel("%", **_FONT)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7, framealpha=0.8)
    ax1.set_title(f"{ticker} � Revenue & EBITDA Margin Trend", fontsize=9, fontweight="bold", pad=8)
    _source_caption(fig, f"Ngu?n: Canonical facts | K?: {years[0]}A�{years[-1]}A")
    return _save(fig, out_dir, run_id, ticker, "C2_revenue_ebitda")


# -- C3: EPS & P/E Trend --------------------------------------------------------

def generate_c3_eps_pe(
    ticker: str,
    years: list[int],
    eps: list[float],        # VND/share
    pe_ratios: list[float],  # x multiple
    out_dir: Path,
    run_id: str,
) -> Path:
    fig, ax1 = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(years))
    bars = ax1.bar(x, eps, color=_LIGHT_BLUE, alpha=0.85, label="EPS (VND/cp)", zorder=3)
    ax1.set_ylabel("VND/cp", **_FONT)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{y}A" for y in years], **_FONT)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax1.grid(axis="y", alpha=0.3, zorder=0)

    ax2 = ax1.twinx()
    ax2.plot(x, pe_ratios, "s--", color=_NAVY, linewidth=2, markersize=5,
             label="P/E (x)", zorder=4)
    ax2.set_ylabel("P/E (x)", **_FONT)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}x"))

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7, framealpha=0.8)
    ax1.set_title(f"{ticker} � EPS & P/E Trend", fontsize=9, fontweight="bold", pad=8)
    _source_caption(fig, f"Ngu?n: Canonical facts, market data | K?: {years[0]}A�{years[-1]}A")
    return _save(fig, out_dir, run_id, ticker, "C3_eps_pe")


# -- C4: Margin & ROE Trend -----------------------------------------------------

def generate_c4_margin_roe(
    ticker: str,
    years: list[int],
    gross_margins: list[float],  # decimal
    net_margins: list[float],    # decimal
    roe: list[float],            # decimal
    out_dir: Path,
    run_id: str,
) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(years))
    ax.plot(x, [v * 100 for v in gross_margins], "o-", color=_NAVY,
            linewidth=2, markersize=5, label="Bi�n g?p (%)")
    ax.plot(x, [v * 100 for v in net_margins], "s-", color=_GOLD,
            linewidth=2, markersize=5, label="Bi�n r�ng (%)")
    ax.plot(x, [v * 100 for v in roe], "^--", color=_GREEN,
            linewidth=2, markersize=5, label="ROE (%)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{y}A" for y in years], **_FONT)
    ax.set_ylabel("%", **_FONT)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax.legend(fontsize=7, framealpha=0.8)
    ax.grid(alpha=0.3)
    ax.set_title(f"{ticker} � Margin & ROE Trend", fontsize=9, fontweight="bold", pad=8)
    _source_caption(fig, f"Ngu?n: Canonical facts | K?: {years[0]}A�{years[-1]}A")
    return _save(fig, out_dir, run_id, ticker, "C4_margin_roe")


# -- C5: Forecast Revenue & FCFF -----------------------------------------------

def generate_c5_forecast(
    ticker: str,
    hist_years: list[int],
    hist_revenues: list[float],  # t? VND actual
    fcast_years: list[int],
    fcast_revenues: list[float],  # t? VND forecast
    fcast_fcff: list[float],      # t? VND forecast
    out_dir: Path,
    run_id: str,
) -> Path:
    fig, ax1 = plt.subplots(figsize=(7.5, 3.8))
    all_years = hist_years + fcast_years
    all_labels = [f"{y}A" for y in hist_years] + [f"{y}F" for y in fcast_years]
    all_revenues = hist_revenues + fcast_revenues
    x = np.arange(len(all_years))
    n_hist = len(hist_years)

    bars_actual = ax1.bar(x[:n_hist], all_revenues[:n_hist], color=_NAVY,
                          alpha=0.85, label="Doanh thu A (t? VND)", zorder=3)
    bars_fcast = ax1.bar(x[n_hist:], all_revenues[n_hist:], color=_LIGHT_BLUE,
                         alpha=0.85, label="Doanh thu F (t? VND)", zorder=3)
    ax1.set_ylabel("t? VND", **_FONT)
    ax1.set_xticks(x)
    ax1.set_xticklabels(all_labels, **_FONT, rotation=0)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax1.grid(axis="y", alpha=0.3, zorder=0)

    # FCFF line on forecast years only
    ax2 = ax1.twinx()
    xf = x[n_hist:]
    ax2.plot(xf, fcast_fcff, "o-", color=_GOLD, linewidth=2, markersize=5,
             label="FCFF F (t? VND)", zorder=4)
    ax2.set_ylabel("FCFF (t? VND)", **_FONT)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    # Vertical separator at forecast boundary
    ax1.axvline(n_hist - 0.5, color="#aaaaaa", linewidth=1, linestyle="--", alpha=0.7)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7, framealpha=0.8)
    ax1.set_title(f"{ticker} � Revenue & FCFF Forecast", fontsize=9, fontweight="bold", pad=8)
    _source_caption(fig, "Ngu?n: Canonical facts (A), Valuation artifact (F) | Gi? d?nh base case")
    return _save(fig, out_dir, run_id, ticker, "C5_forecast")


# -- C7: Sensitivity Heatmap ----------------------------------------------------

def generate_c7_sensitivity_heatmap(
    ticker: str,
    matrix: dict,   # {rows, cols, values, base_row, base_col}
    out_dir: Path,
    run_id: str,
) -> Path:
    """
    matrix = {
        "rows": ["-0.5%", "Base", "+0.5%"],        # terminal growth delta
        "cols": ["-1.0%", "-0.5%", "Base", "+0.5%", "+1.0%"],  # WACC delta
        "values": [[...], [...], [...]],             # target price VND
        "base_row": 1, "base_col": 2,
    }
    """
    rows = matrix["rows"]
    cols = matrix["cols"]
    values = np.array(matrix["values"], dtype=float)
    base_row = matrix.get("base_row", len(rows) // 2)
    base_col = matrix.get("base_col", len(cols) // 2)
    base_val = values[base_row][base_col]

    # Colour: green if >= base, red if < base
    cmap = plt.cm.RdYlGn
    norm_vals = values / base_val  # ratio vs base

    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    im = ax.imshow(norm_vals, cmap=cmap, vmin=0.75, vmax=1.25, aspect="auto")

    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(rows)))
    ax.set_xticklabels([f"WACC {c}" for c in cols], fontsize=7)
    ax.set_yticklabels([f"g {r}" for r in rows], fontsize=7)
    ax.set_xlabel("WACC delta", **_FONT)
    ax.set_ylabel("Terminal growth delta", **_FONT)

    for i in range(len(rows)):
        for j in range(len(cols)):
            val = values[i][j]
            marker = "?" if i == base_row and j == base_col else ""
            ax.text(j, i, f"{val/1000:,.0f}k{marker}", ha="center", va="center",
                    fontsize=7, fontweight="bold" if i == base_row and j == base_col else "normal")

    plt.colorbar(im, ax=ax, label="vs Base", shrink=0.8, pad=0.02)
    ax.set_title(f"{ticker} � Target Price Sensitivity (WACC � Terminal Growth)",
                 fontsize=9, fontweight="bold", pad=8)
    _source_caption(fig, "Ngu?n: valuation_result.json | ? = Base case")
    fig.tight_layout()
    return _save(fig, out_dir, run_id, ticker, "C7_sensitivity_heatmap")


# -- C6: DCF Value Bridge (waterfall) ------------------------------------------

def generate_c6_dcf_bridge(
    ticker: str,
    pv_fcff: float,           # t? VND
    pv_terminal_value: float, # t? VND
    cash: float,              # t? VND (positive = adds to equity)
    debt: float,              # t? VND (negative = subtracts)
    minority: float,          # t? VND (negative)
    equity_value: float,      # t? VND
    shares_mn: float,         # million shares
    target_price: float,      # VND/share
    out_dir: Path,
    run_id: str,
) -> Path:
    labels = ["PV FCFF", "PV Terminal\nValue", "Cash", "(-) Debt", "(-) Minority", "Equity\nValue"]
    values = [pv_fcff, pv_terminal_value, cash, -debt, -minority, 0]
    running = 0.0
    bottoms = []
    heights = []
    colors = []
    for i, (label, val) in enumerate(zip(labels, values)):
        if i == len(labels) - 1:
            # Final bar: equity value from 0
            bottoms.append(0)
            heights.append(equity_value)
            colors.append(_NAVY)
        else:
            bottoms.append(running)
            heights.append(val)
            colors.append(_GREEN if val >= 0 else _RED)
            running += val

    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    bars = ax.bar(x, heights, bottom=bottoms, color=colors, alpha=0.85, width=0.55)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("t? VND", **_FONT)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.grid(axis="y", alpha=0.3, zorder=0)

    # Annotate each bar
    for bar, bottom, height in zip(bars, bottoms, heights):
        mid = bottom + height / 2
        ax.text(bar.get_x() + bar.get_width() / 2, mid,
                f"{height:+,.0f}", ha="center", va="center", fontsize=7, color="white",
                fontweight="bold")

    # Target price annotation
    ax.text(len(labels) - 1, equity_value + equity_value * 0.03,
            f"? {target_price:,.0f} VND/cp", ha="center", fontsize=8, color=_NAVY, fontweight="bold")

    ax.set_title(f"{ticker} � DCF Value Bridge", fontsize=9, fontweight="bold", pad=8)
    _source_caption(fig, "Ngu?n: valuation_result.json")
    return _save(fig, out_dir, run_id, ticker, "C6_dcf_bridge")
```

- [ ] **Step 4: Run tests � expect pass**

```bash
pytest tests/reporting/test_chart_generator.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/reporting/chart_generator.py tests/reporting/test_chart_generator.py
git commit -m "feat(charts): C2 revenue+EBITDA, C3 EPS+PE, C4 margin+ROE, C5 forecast, C6 DCF bridge, C7 sensitivity heatmap"
```

---

### Task A4: Peer Comparison � compute from DB

**Files:**
- Create: `backend/reporting/peer_comparison.py`
- Test: `tests/reporting/test_peer_comparison.py`

- [ ] **Step 1: Write failing test**

```python
# tests/reporting/test_peer_comparison.py
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.reporting.peer_comparison import build_peer_table, PeerRow


def _make_conn(facts_by_ticker: dict[str, dict]) -> MagicMock:
    """facts_by_ticker: {ticker: {metric_id: value}}"""
    conn = MagicMock()
    def execute_side_effect(sql, params=None):
        pass
    conn.cursor.return_value.__enter__ = lambda s: s
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.fetchall = MagicMock(return_value=[])
    return conn


def test_peer_row_dataclass():
    row = PeerRow(
        ticker="DHG", business_type="S?n xu?t du?c OTC/ETC",
        market_cap_bn=4500.0, pe=12.5, pb=2.1, ev_ebitda=8.3,
        roe=0.18, net_margin=0.13,
    )
    assert row.ticker == "DHG"
    assert row.pe == 12.5


def test_build_peer_table_returns_list():
    # Without real DB, verify it returns a list and handles missing data gracefully
    with patch("backend.reporting.peer_comparison.psycopg2") as mock_pg:
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: s
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.fetchall = MagicMock(return_value=[])
        mock_pg.connect.return_value = mock_conn

        rows = build_peer_table(
            conn=mock_conn,
            tickers=["DHG", "IMP", "DMC"],
            fiscal_year=2024,
        )
        assert isinstance(rows, list)


def test_peer_row_median():
    from backend.reporting.peer_comparison import compute_median_row
    rows = [
        PeerRow("DHG", "OTC", 4500, 12.5, 2.1, 8.3, 0.18, 0.13),
        PeerRow("IMP", "ETC", 2100, 14.0, 1.8, 9.5, 0.16, 0.11),
        PeerRow("DMC", "OTC", 1800, 11.0, 1.5, 7.8, 0.15, 0.10),
    ]
    median = compute_median_row(rows)
    assert median.ticker == "Peer Median"
    assert median.pe == 12.5  # median of [11.0, 12.5, 14.0]
```

- [ ] **Step 2: Run � expect failure**

```bash
pytest tests/reporting/test_peer_comparison.py -v
```

- [ ] **Step 3: Implement peer_comparison.py**

```python
# backend/reporting/peer_comparison.py
"""Peer comparison table � computes P/E, P/B, EV/EBITDA, ROE, net margin
from canonical facts in DB for all 5 MVP tickers.

Uses market price from vnstock (latest available) and EBITDA/EPS from canonical facts.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PG = True
except ImportError:
    _HAS_PG = False

MVP_TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]

BUSINESS_TYPE = {
    "DHG": "S?n xu?t du?c OTC/ETC",
    "IMP": "S?n xu?t du?c ETC",
    "DMC": "S?n xu?t du?c OTC/ETC",
    "TRA": "S?n xu?t du?c truy?n th?ng",
    "DBD": "S?n xu?t du?c + TTBYT",
}


@dataclass
class PeerRow:
    ticker: str
    business_type: str
    market_cap_bn: Optional[float]   # t? VND
    pe: Optional[float]              # x
    pb: Optional[float]              # x
    ev_ebitda: Optional[float]       # x
    roe: Optional[float]             # decimal
    net_margin: Optional[float]      # decimal


def _fetch_facts(conn, ticker: str, fiscal_year: int) -> dict[str, float]:
    """Return {metric_id: value} for a ticker/year from fact.financial_facts."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT line_item_code, value, unit
            FROM fact.financial_facts
            WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = 'FY'
              AND validation_status = 'accepted'
            """,
            (ticker, fiscal_year),
        )
        return {r["line_item_code"]: r["value"] for r in cur.fetchall()}


def _fetch_market_price(conn, ticker: str) -> Optional[float]:
    """Return latest market price (VND) from ingest or snapshot."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT close_price FROM research.snapshots
                WHERE ticker = %s ORDER BY created_at DESC LIMIT 1
                """,
                (ticker,),
            )
            row = cur.fetchone()
            if row and row[0]:
                return float(row[0])
    except Exception:
        pass
    return None


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def build_peer_table(
    conn,
    tickers: list[str] = MVP_TICKERS,
    fiscal_year: int = 2024,
) -> list[PeerRow]:
    rows: list[PeerRow] = []
    for ticker in tickers:
        try:
            facts = _fetch_facts(conn, ticker, fiscal_year)
            price = _fetch_market_price(conn, ticker)

            eps = facts.get("eps.basic")
            equity = facts.get("equity.parent")
            net_income = facts.get("net_income.parent")
            revenue = facts.get("revenue.net")
            ebitda = facts.get("ebitda.total")
            total_assets = facts.get("total_assets.ending")
            debt = facts.get("total_debt.ending") or facts.get("short_term_debt.ending", 0)
            cash = facts.get("cash_and_equivalents.ending", 0)

            # Convert bn-VND to VND for per-share metrics
            # eps.basic is in VND/share; equity.parent is in vnd_bn ? multiply by 1e9
            shares = _safe_div((equity or 0) * 1e9, price) if price and equity else None
            if shares is None and eps and price:
                shares = None  # can't derive shares this way

            market_cap = None
            if price and shares:
                market_cap = price * shares / 1e9  # t? VND

            pe = _safe_div(price, eps) if price and eps else None
            bvps = _safe_div((equity or 0) * 1e9, shares) if equity and shares else None
            pb = _safe_div(price, bvps) if price and bvps else None

            ev = None
            if market_cap is not None and debt is not None:
                ev = market_cap + debt - (cash or 0)  # t? VND
            ev_ebitda = _safe_div(ev, ebitda) if ev and ebitda else None

            roe = _safe_div(net_income, equity) if net_income and equity else None
            net_margin = _safe_div(net_income, revenue) if net_income and revenue else None

            rows.append(PeerRow(
                ticker=ticker,
                business_type=BUSINESS_TYPE.get(ticker, "Du?c ph?m"),
                market_cap_bn=market_cap,
                pe=pe,
                pb=pb,
                ev_ebitda=ev_ebitda,
                roe=roe,
                net_margin=net_margin,
            ))
        except Exception as exc:
            rows.append(PeerRow(
                ticker=ticker,
                business_type=BUSINESS_TYPE.get(ticker, ""),
                market_cap_bn=None, pe=None, pb=None,
                ev_ebitda=None, roe=None, net_margin=None,
            ))
    return rows


def compute_median_row(rows: list[PeerRow]) -> PeerRow:
    """Return a row with median values across all peers."""
    def _median(vals: list[Optional[float]]) -> Optional[float]:
        clean = [v for v in vals if v is not None]
        return statistics.median(clean) if clean else None

    return PeerRow(
        ticker="Peer Median",
        business_type="",
        market_cap_bn=_median([r.market_cap_bn for r in rows]),
        pe=_median([r.pe for r in rows]),
        pb=_median([r.pb for r in rows]),
        ev_ebitda=_median([r.ev_ebitda for r in rows]),
        roe=_median([r.roe for r in rows]),
        net_margin=_median([r.net_margin for r in rows]),
    )


def format_peer_markdown_table(rows: list[PeerRow], include_median: bool = True) -> str:
    """Return Markdown table string for embedding in report."""
    if include_median and rows:
        rows = rows + [compute_median_row(rows)]

    def _fmt(v: Optional[float], fmt: str) -> str:
        return f"{v:{fmt}}" if v is not None else "N/A"

    header = "| Ticker | Business Type | Market Cap (t?) | P/E | P/B | EV/EBITDA | ROE | Net Margin |"
    sep    = "|---|---|---:|---:|---:|---:|---:|---:|"
    lines  = [header, sep]
    for r in rows:
        line = (
            f"| **{r.ticker}** | {r.business_type} "
            f"| {_fmt(r.market_cap_bn, ',.0f')} "
            f"| {_fmt(r.pe, '.1f')}x "
            f"| {_fmt(r.pb, '.1f')}x "
            f"| {_fmt(r.ev_ebitda, '.1f')}x "
            f"| {_fmt((r.roe or 0)*100 if r.roe else None, '.1f')}% "
            f"| {_fmt((r.net_margin or 0)*100 if r.net_margin else None, '.1f')}% |"
        )
        lines.append(line)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests � expect pass**

```bash
pytest tests/reporting/test_peer_comparison.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/reporting/peer_comparison.py tests/reporting/test_peer_comparison.py
git commit -m "feat(peer): build_peer_table computes P/E, EV/EBITDA from canonical facts"
```

---

## PHASE B � Report Rebuild + HTML/PDF Renderer

### Task B1: Valuation reproducibility gate

**Files:**
- Create: `backend/report_gates/__init__.py`
- Create: `backend/report_gates/valuation_reproducibility_gate.py`
- Test: `tests/reporting/test_valuation_gate.py`

- [ ] **Step 1: Write failing test**

```python
# tests/reporting/test_valuation_gate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
from backend.report_gates.valuation_reproducibility_gate import validate_valuation_reproducibility


def _make_valuation(implied_price: float) -> dict:
    return {
        "fcff_dcf": {
            "pv_fcff": 3_500_000.0,        # t? VND
            "pv_terminal_value": 2_800_000.0,
            "cash_and_equivalents": 250_000.0,
            "debt": 150_000.0,
            "minority_interest": 0.0,
            "equity_value": 6_400_000.0,
            "shares_outstanding": 46_700_000,   # shares
            "implied_price": implied_price,
        },
        "target_price": implied_price,
    }


def test_passes_when_prices_match():
    # equity_value / shares = 6_400_000 * 1e9 / 46_700_000 � 137_047 VND
    val = _make_valuation(137_047.0)
    result = validate_valuation_reproducibility(val, tolerance_pct=0.01)
    assert result.status == "pass", result.issues


def test_fails_when_price_too_far_off():
    val = _make_valuation(200_000.0)   # way off
    result = validate_valuation_reproducibility(val, tolerance_pct=0.01)
    assert result.status == "fail"
    assert result.critical is True


def test_fails_with_zero_shares():
    val = _make_valuation(137_047.0)
    val["fcff_dcf"]["shares_outstanding"] = 0
    result = validate_valuation_reproducibility(val)
    assert result.status == "fail"
```

- [ ] **Step 2: Run � expect failure**

```bash
pytest tests/reporting/test_valuation_gate.py -v
```

- [ ] **Step 3: Implement gate**

```python
# backend/report_gates/__init__.py
# empty

# backend/report_gates/valuation_reproducibility_gate.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class GateResult:
    gate: str
    status: str          # pass | warn | fail
    critical: bool
    checked: int
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def validate_valuation_reproducibility(
    valuation_result: dict,
    tolerance_pct: float = 0.01,
) -> GateResult:
    """Recompute target price from components and compare with stored value.

    GOAL_OUTPUT.md �14.5: pass when DCF output recomputable from valuation_result.
    """
    fcff = valuation_result.get("fcff_dcf", {})

    pv_fcff = fcff.get("pv_fcff", 0.0) or 0.0
    pv_tv = fcff.get("pv_terminal_value", 0.0) or 0.0
    cash = fcff.get("cash_and_equivalents", 0.0) or 0.0
    debt = fcff.get("debt", 0.0) or 0.0
    minority = fcff.get("minority_interest", 0.0) or 0.0
    shares = fcff.get("shares_outstanding", 0) or 0
    stored_equity = fcff.get("equity_value", 0.0) or 0.0
    stored_price = fcff.get("implied_price") or valuation_result.get("target_price", 0.0) or 0.0

    if shares <= 0:
        return GateResult(
            gate="valuation_reproducibility", status="fail", critical=True,
            checked=1, issues=["shares_outstanding is zero or missing � cannot recompute target price"],
        )

    # Recompute: EV = PV(FCFF) + PV(TV); Equity = EV + cash - debt - minority
    # equity_value in valuation_result is in t? VND, shares is in shares
    recomputed_equity = pv_fcff + pv_tv + cash - debt - minority  # t? VND
    recomputed_price = recomputed_equity * 1e9 / shares           # VND/share

    if stored_price == 0.0:
        return GateResult(
            gate="valuation_reproducibility", status="fail", critical=True,
            checked=1, issues=["stored target price is zero � valuation artifact incomplete"],
        )

    relative_error = abs(recomputed_price - stored_price) / abs(stored_price)
    if relative_error > tolerance_pct:
        return GateResult(
            gate="valuation_reproducibility", status="fail", critical=True,
            checked=1,
            issues=[
                f"recomputed price {recomputed_price:,.0f} VND differs from stored "
                f"{stored_price:,.0f} VND by {relative_error:.2%} (tolerance {tolerance_pct:.1%})"
            ],
        )

    return GateResult(
        gate="valuation_reproducibility", status="pass", critical=True,
        checked=1, issues=[],
    )
```

- [ ] **Step 4: Run tests � expect pass**

```bash
pytest tests/reporting/test_valuation_gate.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/report_gates/ tests/reporting/test_valuation_gate.py
git commit -m "feat(gates): valuation reproducibility gate recomputes target price from DCF components"
```

---

### Task B2: HTML template + renderer

**Files:**
- Create: `templates/report.html.j2`
- Create: `templates/report.css`
- Create: `backend/reporting/html_renderer.py`
- Test: `tests/reporting/test_html_renderer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/reporting/test_html_renderer.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
from backend.reporting.html_renderer import render_html


def test_render_html_creates_file(tmp_path):
    context = {
        "ticker": "DHG",
        "company_name": "C�ng ty C? ph?n Du?c H?u Giang",
        "exchange": "HOSE",
        "report_date": "01/06/2026",
        "data_cutoff": "31/12/2025",
        "rating": "UNDER_REVIEW",
        "current_price": "94,400",
        "target_price": "137,010",
        "upside_downside": "+45.1%",
        "risk_level": "Medium",
        "data_confidence": "Medium",
        "report_status": "DRAFT",
        "investment_thesis": "DHG l� doanh nghi?p du?c ph?m h�ng d?u Vi?t Nam.",
        "key_metrics": [
            {"label": "Market Cap", "value": "4,409 t? VND"},
            {"label": "Revenue FY2025", "value": "2,750 t? VND"},
            {"label": "EPS", "value": "11,200 VND/cp"},
        ],
        "financial_summary_table": "| Ch? ti�u | 2021A |\n|---|---:|\n| Doanh thu | 2,100 |",
        "forecast_table": "",
        "dcf_table": "",
        "valuation_summary_table": "",
        "sensitivity_matrix": "",
        "scenario_table": "",
        "peer_table": "| Ticker | P/E |\n|---|---:|\n| DHG | 12.5x |",
        "catalysts_table": "",
        "risks_table": "",
        "key_takeaways": ["Doanh thu tang tru?ng ?n d?nh", "Bi�n l?i nhu?n c?i thi?n"],
        "disclaimer": "B�o c�o ch? nh?m m?c d�ch nghi�n c?u.",
        "quality_summary": [{"item": "Numeric Consistency", "status": "PASS", "notes": ""}],
        "key_sources": [{"source_id": "SRC-001", "source_name": "vnstock API", "period": "2024A"}],
        "charts": {},  # no charts in this test
    }
    out = tmp_path / "report.html"
    render_html(context=context, out_path=out, templates_dir=Path("templates"))
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "DHG" in content
    assert "Du?c H?u Giang" in content
    assert "UNDER_REVIEW" in content


def test_render_html_contains_disclaimer(tmp_path):
    context = {
        "ticker": "DHG", "company_name": "DHG Pharma", "exchange": "HOSE",
        "report_date": "01/06/2026", "data_cutoff": "31/12/2025",
        "rating": "UNDER_REVIEW", "current_price": "94,400", "target_price": "137,010",
        "upside_downside": "+45.1%", "risk_level": "Medium", "data_confidence": "Medium",
        "report_status": "DRAFT", "investment_thesis": "Test thesis.",
        "key_metrics": [], "financial_summary_table": "", "forecast_table": "",
        "dcf_table": "", "valuation_summary_table": "", "sensitivity_matrix": "",
        "scenario_table": "", "peer_table": "", "catalysts_table": "", "risks_table": "",
        "key_takeaways": [], "disclaimer": "Kh�ng ph?i khuy?n ngh? d?u tu.",
        "quality_summary": [], "key_sources": [], "charts": {},
    }
    out = tmp_path / "report.html"
    render_html(context=context, out_path=out, templates_dir=Path("templates"))
    assert "Kh�ng ph?i khuy?n ngh?" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run � expect failure (ImportError)**

```bash
pytest tests/reporting/test_html_renderer.py -v
```

- [ ] **Step 3: Create templates directory and HTML template**

```bash
mkdir -p templates
```

Write `templates/report.html.j2`:

```html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>{{ ticker }} Equity Research Report</title>
  <style>
    /* -- Base --------------------------------------------- */
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 9pt; color: #1a1a1a; background: white; }
    h1 { font-size: 18pt; font-weight: 700; }
    h2 { font-size: 12pt; font-weight: 600; color: #1a3a6b; border-bottom: 2px solid #1a3a6b; padding-bottom: 4px; margin: 16px 0 8px; }
    h3 { font-size: 10pt; font-weight: 600; margin: 12px 0 6px; color: #1a3a6b; }
    p  { margin: 6px 0; line-height: 1.5; }
    ul { margin: 6px 0 6px 20px; }
    li { margin: 3px 0; }

    /* -- Page setup --------------------------------------- */
    @page { size: A4 portrait; margin: 18mm 16mm 18mm 16mm; @bottom-center { content: counter(page) " / " counter(pages); font-size: 7pt; color: #888; } }
    .page-break { page-break-before: always; }

    /* -- Cover / Page 1 ----------------------------------- */
    .cover { background: #1a3a6b; color: white; padding: 24px 28px 20px; border-radius: 4px; margin-bottom: 16px; }
    .cover .label { font-size: 8pt; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.7; margin-bottom: 4px; }
    .cover h1 { color: white; font-size: 20pt; }
    .cover .sector { color: #c8a84b; font-size: 10pt; margin-top: 4px; }
    .cover .rating-line { margin-top: 12px; font-size: 11pt; }
    .rating-buy { color: #4caf50; font-weight: 700; }
    .rating-hold { color: #c8a84b; font-weight: 700; }
    .rating-sell { color: #f44336; font-weight: 700; }
    .rating-under-review { color: #9e9e9e; font-weight: 700; }

    /* -- Rating block ------------------------------------- */
    .snapshot-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 12px 0; }
    .snapshot-box { background: #f5f7fa; border: 1px solid #e0e4ea; border-radius: 4px; padding: 10px 14px; }
    .snapshot-box .metric-label { font-size: 7.5pt; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
    .snapshot-box .metric-value { font-size: 11pt; font-weight: 600; color: #1a3a6b; margin-top: 2px; }

    /* -- Tables ------------------------------------------- */
    table { width: 100%; border-collapse: collapse; font-size: 8pt; margin: 8px 0; }
    th { background: #1a3a6b; color: white; padding: 5px 8px; text-align: left; font-weight: 600; }
    th:not(:first-child) { text-align: right; }
    td { padding: 4px 8px; border-bottom: 1px solid #e8ecf0; }
    td:not(:first-child) { text-align: right; }
    tr:nth-child(even) { background: #f8f9fc; }
    tr:last-child td { font-weight: 600; background: #eef1f7; }

    /* -- Charts ------------------------------------------- */
    .chart-wrap { text-align: center; margin: 12px 0; }
    .chart-wrap img { max-width: 100%; height: auto; border: 1px solid #e0e4ea; border-radius: 3px; }
    .chart-caption { font-size: 7pt; color: #777; margin-top: 3px; font-style: italic; }

    /* -- Thesis box --------------------------------------- */
    .thesis-box { background: #f0f4ff; border-left: 4px solid #1a3a6b; padding: 10px 14px; border-radius: 0 4px 4px 0; margin: 10px 0; font-size: 9pt; line-height: 1.6; }

    /* -- Quality table ------------------------------------ */
    .status-pass { color: #2e7d32; font-weight: 600; }
    .status-fail { color: #c62828; font-weight: 600; }
    .status-warn { color: #e65100; font-weight: 600; }
    .status-pending { color: #e65100; font-style: italic; }

    /* -- Disclaimer --------------------------------------- */
    .disclaimer { font-size: 7.5pt; color: #555; border-top: 1px solid #ccc; padding-top: 10px; margin-top: 16px; line-height: 1.5; }

    /* -- Draft watermark ---------------------------------- */
    {% if report_status in ['DRAFT', 'NEEDS_REVIEW'] %}
    body::after {
      content: "{{ report_status }}";
      position: fixed; top: 50%; left: 50%;
      transform: translate(-50%, -50%) rotate(-35deg);
      font-size: 80pt; color: rgba(200,0,0,0.04);
      font-weight: 900; pointer-events: none; z-index: 9999;
    }
    {% endif %}
  </style>
</head>
<body>

<!-- -- PAGE 1: Cover + Investment Snapshot ----------------------- -->
<div class="cover">
  <div class="label">Equity Research Report | Ng�nh Du?c / Y t? Vi?t Nam</div>
  <h1>{{ ticker }} � {{ company_name }}</h1>
  <div class="sector">{{ exchange }} | Du?c ph?m | Ng�y l?p: {{ report_date }} | D? li?u d?n: {{ data_cutoff }}</div>
  <div class="rating-line">
    Rating: <span class="rating-{{ rating | lower | replace('_', '-') }}">{{ rating }}</span> &nbsp;|&nbsp;
    Gi� hi?n t?i: {{ current_price }} VND &nbsp;|&nbsp;
    Gi� m?c ti�u: {{ target_price }} VND &nbsp;|&nbsp;
    Upside/Downside: {{ upside_downside }}
  </div>
</div>

<div class="snapshot-grid">
  {% for m in key_metrics %}
  <div class="snapshot-box">
    <div class="metric-label">{{ m.label }}</div>
    <div class="metric-value">{{ m.value }}</div>
  </div>
  {% endfor %}
  <div class="snapshot-box">
    <div class="metric-label">Risk Level</div>
    <div class="metric-value">{{ risk_level }}</div>
  </div>
  <div class="snapshot-box">
    <div class="metric-label">Data Confidence</div>
    <div class="metric-value">{{ data_confidence }}</div>
  </div>
</div>

<h3>Investment Thesis</h3>
<div class="thesis-box">{{ investment_thesis }}</div>

{% if charts.c1 %}
<div class="chart-wrap">
  <img src="{{ charts.c1 }}" alt="Stock vs VNINDEX">
  <div class="chart-caption">Bi?n d?ng gi� vs VNINDEX (base 100) | Ngu?n: market data</div>
</div>
{% endif %}

<!-- -- PAGE 2: Company Overview ---------------------------------- -->
<div class="page-break"></div>
<h2>T?ng Quan Doanh Nghi?p & M� H�nh Kinh Doanh</h2>
{{ company_overview | safe if company_overview else "<p><em>Chua c� d? li?u t?ng quan doanh nghi?p.</em></p>" }}
{% if business_driver_table %}
<h3>Business Drivers</h3>
{{ business_driver_table | safe }}
{% endif %}

<!-- -- PAGE 3: Financial Performance ------------------------------ -->
<div class="page-break"></div>
<h2>Ph�n T�ch T�i Ch�nh L?ch S?</h2>
{% if financial_summary_table %}
{{ financial_summary_table | safe }}
{% endif %}
{% if charts.c2 %}<div class="chart-wrap"><img src="{{ charts.c2 }}" alt="Revenue & EBITDA"><div class="chart-caption">Doanh thu & EBITDA Margin | Ngu?n: Canonical facts</div></div>{% endif %}
{% if charts.c3 %}<div class="chart-wrap"><img src="{{ charts.c3 }}" alt="EPS & P/E"><div class="chart-caption">EPS & P/E | Ngu?n: Canonical facts, market data</div></div>{% endif %}
{% if charts.c4 %}<div class="chart-wrap"><img src="{{ charts.c4 }}" alt="Margin & ROE"><div class="chart-caption">Bi�n l?i nhu?n & ROE | Ngu?n: Canonical facts</div></div>{% endif %}

<!-- -- PAGE 4: Forecast -------------------------------------------- -->
<div class="page-break"></div>
<h2>D? Ph�ng & Gi? �?nh Ch�nh</h2>
{% if driver_forecast_table %}
<h3>Business Driver ? Forecast Impact</h3>
{{ driver_forecast_table | safe }}
{% endif %}
{% if forecast_table %}
<h3>D? Ph�ng T�m T?t</h3>
{{ forecast_table | safe }}
{% endif %}
{% if assumptions_table %}
<h3>B?ng Gi? �?nh</h3>
{{ assumptions_table | safe }}
{% endif %}
{% if charts.c5 %}<div class="chart-wrap"><img src="{{ charts.c5 }}" alt="Forecast"><div class="chart-caption">D? ph�ng Doanh thu & FCFF | Ngu?n: Valuation artifact</div></div>{% endif %}

<!-- -- PAGE 5: Valuation -------------------------------------------- -->
<div class="page-break"></div>
<h2>�?nh Gi�: FCFF DCF + Ki?m Tra Ch�o Multiples</h2>
{% if dcf_table %}
<h3>B?ng DCF</h3>
{{ dcf_table | safe }}
{% endif %}
{% if valuation_summary_table %}
<h3>T?ng H?p �?nh Gi�</h3>
{{ valuation_summary_table | safe }}
{% endif %}
{% if valuation_assumptions_table %}
<h3>Gi? �?nh �?nh Gi�</h3>
{{ valuation_assumptions_table | safe }}
{% endif %}
{% if charts.c6 %}<div class="chart-wrap"><img src="{{ charts.c6 }}" alt="DCF Bridge"><div class="chart-caption">DCF Value Bridge | Ngu?n: Valuation artifact</div></div>{% endif %}

<!-- -- PAGE 6: Sensitivity + Peer ---------------------------------- -->
<div class="page-break"></div>
<h2>Sensitivity, Scenario & Peer Check</h2>
{% if sensitivity_matrix %}
<h3>Ma Tr?n Sensitivity (WACC � Terminal Growth)</h3>
{{ sensitivity_matrix | safe }}
{% endif %}
{% if scenario_table %}
<h3>Ph�n T�ch Scenario</h3>
{{ scenario_table | safe }}
{% endif %}
{% if peer_table %}
<h3>So S�nh Peer</h3>
{{ peer_table | safe }}
{% endif %}
{% if charts.c7 %}<div class="chart-wrap"><img src="{{ charts.c7 }}" alt="Sensitivity Heatmap"><div class="chart-caption">Sensitivity Heatmap � m?c ti�u gi� theo WACC � g | Ngu?n: Valuation artifact</div></div>{% endif %}

<!-- -- PAGE 7: Catalysts & Risks ----------------------------------- -->
<div class="page-break"></div>
<h2>Catalysts & R?i Ro �?u Tu</h2>
{% if catalysts_table %}
<h3>Catalysts T�ch C?c</h3>
{{ catalysts_table | safe }}
{% endif %}
{% if risks_table %}
<h3>R?i Ro Ch�nh</h3>
{{ risks_table | safe }}
{% endif %}

<!-- -- PAGE 8: Conclusion + Audit + Disclaimer ---------------------- -->
<div class="page-break"></div>
<h2>K?t Lu?n, Ki?m �?nh & Disclaimer</h2>

{% if key_takeaways %}
<h3>Key Takeaways</h3>
<ul>{% for t in key_takeaways %}<li>{{ t }}</li>{% endfor %}</ul>
{% endif %}

<h3>T�m T?t Ch?t Lu?ng B�o C�o</h3>
<table>
  <tr><th>H?ng m?c</th><th>Tr?ng th�i</th><th>Ghi ch�</th></tr>
  {% for g in quality_summary %}
  <tr>
    <td>{{ g.item }}</td>
    <td class="status-{{ g.status | lower }}">{{ g.status }}</td>
    <td>{{ g.notes }}</td>
  </tr>
  {% endfor %}
</table>

{% if key_sources %}
<h3>Ngu?n Tham Kh?o Ch�nh</h3>
<table>
  <tr><th>Source ID</th><th>T�n ngu?n</th><th>K?</th></tr>
  {% for s in key_sources %}
  <tr><td>{{ s.source_id }}</td><td>{{ s.source_name }}</td><td>{{ s.period }}</td></tr>
  {% endfor %}
</table>
{% endif %}

<div class="disclaimer">
  <strong>Disclaimer:</strong> {{ disclaimer }}
  <br>Tr?ng th�i b�o c�o: <strong>{{ report_status }}</strong> | Ng�y l?p: {{ report_date }}
</div>

</body>
</html>
```

- [ ] **Step 4: Create html_renderer.py**

```python
# backend/reporting/html_renderer.py
from __future__ import annotations

from pathlib import Path
from typing import Any


def render_html(
    context: dict[str, Any],
    out_path: Path,
    templates_dir: Path | None = None,
) -> Path:
    """Render Jinja2 HTML template with context dict. Returns out_path."""
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        raise ImportError("jinja2 is required: pip install jinja2")

    if templates_dir is None:
        templates_dir = Path(__file__).resolve().parents[2] / "templates"

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html.j2")
    html = template.render(**context)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
```

- [ ] **Step 5: Run tests � expect pass**

```bash
pip install jinja2
pytest tests/reporting/test_html_renderer.py -v
```
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add templates/ backend/reporting/html_renderer.py tests/reporting/test_html_renderer.py
git commit -m "feat(renderer): Jinja2 HTML template + html_renderer with 8-section layout"
```

---

### Task B3: PDF renderer

**Files:**
- Create: `backend/reporting/pdf_renderer.py`

- [ ] **Step 1: Implement pdf_renderer.py**

```python
# backend/reporting/pdf_renderer.py
"""PDF renderer � WeasyPrint on Linux/Docker; HTML fallback on Windows.

WeasyPrint requirements (Linux):
  apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0

If WeasyPrint is unavailable, the HTML file is the output and a warning is logged.
"""
from __future__ import annotations

import sys
from pathlib import Path


def render_pdf(html_path: Path, out_path: Path) -> Path:
    """Convert HTML to PDF. Returns out_path on success, html_path on fallback."""
    try:
        from weasyprint import HTML as WPHtml
        out_path.parent.mkdir(parents=True, exist_ok=True)
        WPHtml(filename=str(html_path)).write_pdf(str(out_path))
        print(f"[pdf_renderer] PDF saved: {out_path}")
        return out_path
    except ImportError:
        print("[pdf_renderer] WARNING: weasyprint not available � HTML export only.")
        print(f"[pdf_renderer] Install: pip install weasyprint")
        print(f"[pdf_renderer]          (Linux) apt-get install -y libpango-1.0-0 libpangocairo-1.0-0")
        return html_path
    except Exception as exc:
        print(f"[pdf_renderer] WARNING: PDF generation failed ({exc}) � HTML export only.")
        return html_path
```

- [ ] **Step 2: Test manually (no unit test � WeasyPrint depends on native libs)**

```bash
python -c "
from pathlib import Path
from backend.reporting.pdf_renderer import render_pdf
result = render_pdf(Path('reports/DHG_latest_full_report.html'), Path('/tmp/test.pdf'))
print('output:', result)
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/reporting/pdf_renderer.py
git commit -m "feat(renderer): WeasyPrint PDF renderer with graceful HTML fallback"
```

---

## PHASE C � Integration

### Task C1: Wire charts + artifacts into generate_report.py

**Files:**
- Modify: `scripts/generate_report.py`

The goal: after the existing Markdown report is generated, also:
1. Build `SourceManifest` from DB and save
2. Build chart data from facts/valuation artifacts and save chart PNGs
3. Render HTML from the Markdown context + charts
4. Render PDF from HTML
5. Save `EvalResult` with gate statuses

- [ ] **Step 1: Read current generate_report.py output section**

Find the section that saves the report and citation map � add the new artifact outputs after it.

```bash
grep -n "report_path\|citation_path\|out_path\|REPORTS_DIR" scripts/generate_report.py | head -30
```

- [ ] **Step 2: Add artifact generation to generate_report() function**

Find the return statement in `generate_report()` and add before it:

```python
# -- Generate charts ----------------------------------------------------
try:
    from backend.reporting.chart_generator import (
        generate_c2_revenue_ebitda, generate_c3_eps_pe,
        generate_c4_margin_roe, generate_c5_forecast,
        generate_c7_sensitivity_heatmap, generate_c6_dcf_bridge,
    )
    charts_dir = ROOT / "artifacts" / "charts" / ticker
    charts_dir.mkdir(parents=True, exist_ok=True)

    # Extract data from facts for historical charts
    fact_years = sorted({f["fiscal_year"] for f in snapshot_facts if f.get("fiscal_year")})
    def _fact_series(metric_id: str) -> list[float]:
        return [
            next((f["value"] for f in snapshot_facts
                  if f.get("line_item_code") == metric_id and f.get("fiscal_year") == y), 0.0)
            for y in fact_years
        ]

    chart_paths = {}
    revenues = _fact_series("revenue.net")
    ebitda = _fact_series("ebitda.total")
    eps_vals = _fact_series("eps.basic")
    gross_m = _fact_series("gross_profit.total")
    net_income = _fact_series("net_income.parent")
    equity_vals = _fact_series("equity.parent")

    ebitda_margins = [e/r if r else 0 for e, r in zip(ebitda, revenues)]
    gross_margins  = [g/r if r else 0 for g, r in zip(gross_m, revenues)]
    net_margins    = [n/r if r else 0 for n, r in zip(net_income, revenues)]
    roe_vals       = [n/e if e else 0 for n, e in zip(net_income, equity_vals)]

    if revenues and any(revenues):
        chart_paths["c2"] = str(generate_c2_revenue_ebitda(
            ticker=ticker, years=fact_years, revenues=revenues,
            ebitda_margins=ebitda_margins, out_dir=charts_dir, run_id=ts,
        ))

    if eps_vals and any(eps_vals):
        # P/E from valuation artifact if available
        pe_ratios = [0.0] * len(fact_years)
        chart_paths["c3"] = str(generate_c3_eps_pe(
            ticker=ticker, years=fact_years, eps=eps_vals,
            pe_ratios=pe_ratios, out_dir=charts_dir, run_id=ts,
        ))

    if gross_margins and any(gross_margins):
        chart_paths["c4"] = str(generate_c4_margin_roe(
            ticker=ticker, years=fact_years, gross_margins=gross_margins,
            net_margins=net_margins, roe=roe_vals, out_dir=charts_dir, run_id=ts,
        ))

    # Forecast chart � needs valuation artifact
    if valuation and valuation.get("fcff"):
        fcast_years_list = [2026, 2027, 2028, 2029, 2030]
        fcff_rows = valuation["fcff"].get("yearly", [])
        fcast_rev = [r.get("revenue", 0) for r in fcff_rows]
        fcast_fcff = [r.get("fcff", 0) for r in fcff_rows]
        if fcast_rev and any(fcast_rev):
            hist_yrs = fact_years[-3:] if len(fact_years) >= 3 else fact_years
            hist_rev = revenues[-len(hist_yrs):]
            chart_paths["c5"] = str(generate_c5_forecast(
                ticker=ticker, hist_years=hist_yrs, hist_revenues=hist_rev,
                fcast_years=fcast_years_list, fcast_revenues=fcast_rev,
                fcast_fcff=fcast_fcff, out_dir=charts_dir, run_id=ts,
            ))

    # Sensitivity heatmap from valuation artifact
    sensitivity = valuation.get("sensitivity") if valuation else {}
    if sensitivity and isinstance(sensitivity, dict):
        # Build matrix from sensitivity dict {wacc_delta: {g_delta: price}}
        wacc_deltas = sorted(sensitivity.keys())
        g_deltas = sorted(next(iter(sensitivity.values())).keys()) if sensitivity else []
        if wacc_deltas and g_deltas:
            values_grid = [[sensitivity.get(w, {}).get(g, 0) for w in wacc_deltas] for g in g_deltas]
            matrix = {
                "rows": g_deltas,
                "cols": wacc_deltas,
                "values": values_grid,
                "base_row": len(g_deltas) // 2,
                "base_col": len(wacc_deltas) // 2,
            }
            chart_paths["c7"] = str(generate_c7_sensitivity_heatmap(
                ticker=ticker, matrix=matrix, out_dir=charts_dir, run_id=ts,
            ))

except Exception as chart_exc:
    print(f"[generate_report] WARNING: chart generation failed: {chart_exc}")
    chart_paths = {}

# -- Generate HTML ------------------------------------------------------
try:
    from backend.reporting.html_renderer import render_html
    html_dir = ROOT / "artifacts" / "reports_html"
    html_path = html_dir / f"{ticker}_{ts}_full_report.html"

    html_context = {
        "ticker": ticker,
        "company_name": company_info.get("name", ticker),
        "exchange": company_info.get("exchange", "HOSE"),
        "report_date": datetime.now(UTC).strftime("%d/%m/%Y"),
        "data_cutoff": f"31/12/{to_year}",
        "rating": gate.recommendation_label() if gate else "UNDER_REVIEW",
        "current_price": f"{int(current_price):,}" if current_price else "N/A",
        "target_price": f"{int(target_price):,}" if target_price else "N/A",
        "upside_downside": f"{upside_pct:+.1f}%" if upside_pct is not None else "N/A",
        "risk_level": "Medium",
        "data_confidence": "Medium",
        "report_status": "DRAFT",
        "investment_thesis": investment_thesis_text,
        "key_metrics": key_metrics_list,
        "financial_summary_table": financial_summary_md,
        "forecast_table": forecast_md,
        "driver_forecast_table": driver_table_md,
        "dcf_table": dcf_table_md,
        "valuation_summary_table": val_summary_md,
        "valuation_assumptions_table": val_assumptions_md,
        "sensitivity_matrix": sensitivity_md,
        "scenario_table": scenario_md,
        "peer_table": peer_markdown,
        "catalysts_table": catalysts_md,
        "risks_table": risks_md,
        "key_takeaways": key_takeaways_list,
        "disclaimer": disclaimer_text,
        "quality_summary": quality_summary_list,
        "key_sources": key_sources_list,
        "charts": chart_paths,
        "company_overview": company_overview_text,
        "business_driver_table": driver_business_md,
        "assumptions_table": assumptions_md,
    }
    render_html(context=html_context, out_path=html_path)
    print(f"[generate_report] HTML saved: {html_path}")

    # -- Generate PDF -------------------------------------------------
    from backend.reporting.pdf_renderer import render_pdf
    pdf_dir = ROOT / "artifacts" / "reports_pdf"
    pdf_path = pdf_dir / f"{ticker}_{ts}_full_report.pdf"
    render_pdf(html_path=html_path, out_path=pdf_path)

except Exception as html_exc:
    print(f"[generate_report] WARNING: HTML/PDF generation failed: {html_exc}")

# -- Save SourceManifest -----------------------------------------------
try:
    from backend.report_contracts.source_manifest import SourceManifest
    manifest = SourceManifest.build_from_db(conn=conn, run_id=ts, ticker=ticker)
    manifest_path = ROOT / "artifacts" / "source_manifests" / f"{ticker}_{ts}_source_manifest.json"
    manifest.save(manifest_path)
    print(f"[generate_report] Source manifest saved: {manifest_path}")
except Exception as sm_exc:
    print(f"[generate_report] WARNING: source manifest failed: {sm_exc}")
```

- [ ] **Step 3: Run generate_report.py to verify no crash**

```bash
python scripts/generate_report.py --ticker DHG --legacy 2>&1 | tail -20
```
Expected: HTML/PDF lines printed OR warnings if deps missing, but no crash.

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_report.py
git commit -m "feat(integration): wire charts, HTML, PDF, source manifest into generate_report.py"
```

---

### Task C2: Wire into run_research.py + update EXECUTION_STATE

**Files:**
- Modify: `scripts/run_research.py`
- Modify: `.claude/EXECUTION_STATE.md`

- [ ] **Step 1: Add HTML/PDF artifacts to run_research summary output**

In `ResearchRunner.run()`, find where `index_summary` is printed and add:

```python
# After generate_report step, extract HTML/PDF paths from result
html_artifact = citation_data.get("html_path", "")
pdf_artifact  = citation_data.get("pdf_path", "")
if html_artifact:
    print(f"[run_research] HTML report: {html_artifact}")
if pdf_artifact:
    print(f"[run_research] PDF report: {pdf_artifact}")
```

- [ ] **Step 2: Update EXECUTION_STATE.md**

Update Current Phase to reflect Phase 14:
```
Current Phase: Phase 14 � Chart Generator + HTML/PDF Renderer + Artifact Contracts
Last Completed Task: C2-C7 charts (matplotlib), Jinja2 HTML template, WeasyPrint PDF,
                     ClaimLedger/SourceManifest/EvalResult contracts, valuation reproducibility gate,
                     peer comparison table. GOAL_OUTPUT.md �19 ~85% complete.
                     Remaining: C1 (price vs VNINDEX), claim ledger builder in generate_report.py.
```

- [ ] **Step 3: Final smoke test**

```bash
python scripts/generate_report.py --ticker DHG
```
Expected output lines:
```
[generate_report] HTML saved: artifacts/reports_html/DHG_..._full_report.html
[generate_report] Source manifest saved: artifacts/source_manifests/DHG_..._source_manifest.json
```

- [ ] **Step 4: Commit**

```bash
git add scripts/run_research.py .claude/EXECUTION_STATE.md
git commit -m "feat(integration): wire HTML/PDF/artifacts into run_research.py, update EXECUTION_STATE"
```

---

### Task C3: Chart C1 � Price vs VNINDEX (last)

**Files:**
- Create: `backend/reporting/price_chart.py`
- Modify: `backend/reporting/chart_generator.py` (add generate_c1_price_vs_index)

- [ ] **Step 1: Implement price fetch + C1 chart**

```python
# backend/reporting/price_chart.py
"""Fetch price history for ticker and VNINDEX, normalize to base 100, generate C1 chart."""
from __future__ import annotations
from pathlib import Path
from datetime import date, timedelta


def fetch_price_series(ticker: str, days: int = 365) -> tuple[list[str], list[float]]:
    """Return (date_strings, prices) for last `days` trading days."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parents[2] / "vnstock"))
        from vnstock3 import Vnstock
        stock = Vnstock().stock(symbol=ticker, source="VCI")
        end = date.today().strftime("%Y-%m-%d")
        start = (date.today() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
        df = stock.quote.history(start=start, end=end, interval="1D")
        if df is not None and not df.empty:
            df = df.tail(days)
            return df["time"].astype(str).tolist(), df["close"].tolist()
    except Exception:
        pass
    return [], []


def fetch_vnindex_series(days: int = 365) -> tuple[list[str], list[float]]:
    return fetch_price_series("VNINDEX", days)


def generate_c1_price_vs_vnindex(
    ticker: str,
    out_dir: Path,
    run_id: str,
    days: int = 252,
) -> Path | None:
    """Generate C1: Stock vs VNINDEX base 100 chart. Returns None if data unavailable."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    ticker_dates, ticker_prices = fetch_price_series(ticker, days)
    vnindex_dates, vnindex_prices = fetch_vnindex_series(days)

    if not ticker_prices or not vnindex_prices:
        return None

    # Align on common dates (use VNINDEX dates as reference)
    min_len = min(len(ticker_prices), len(vnindex_prices))
    t_prices = np.array(ticker_prices[-min_len:])
    v_prices = np.array(vnindex_prices[-min_len:])
    dates = ticker_dates[-min_len:]

    # Normalize to base 100
    t_norm = t_prices / t_prices[0] * 100
    v_norm = v_prices / v_prices[0] * 100

    fig, ax = plt.subplots(figsize=(7.5, 3.5))
    ax.plot(range(len(t_norm)), t_norm, color="#1a3a6b", linewidth=2, label=ticker)
    ax.plot(range(len(v_norm)), v_norm, color="#c8a84b", linewidth=1.5,
            linestyle="--", label="VNINDEX", alpha=0.8)
    ax.axhline(100, color="#aaaaaa", linewidth=0.8, linestyle=":")

    # X-axis: show ~6 date labels
    step = max(1, len(dates) // 6)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i][:10] for i in range(0, len(dates), step)], fontsize=7, rotation=30)
    ax.set_ylabel("Ch? s? (Base = 100)", fontsize=8)
    ax.legend(fontsize=8, framealpha=0.8)
    ax.grid(alpha=0.3)
    ax.set_title(f"{ticker} vs VNINDEX (1 nam, base 100)", fontsize=9, fontweight="bold", pad=8)
    fig.text(0.01, -0.04,
             f"Ngu?n: VCI market data | K?: {dates[0][:10]} � {dates[-1][:10]}",
             fontsize=6.5, style="italic", color="#555")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}_{ticker}_C1_price_vs_vnindex.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
```

- [ ] **Step 2: Add to chart generation in generate_report.py**

In the chart generation block, add:
```python
try:
    from backend.reporting.price_chart import generate_c1_price_vs_vnindex
    c1_path = generate_c1_price_vs_vnindex(ticker=ticker, out_dir=charts_dir, run_id=ts)
    if c1_path:
        chart_paths["c1"] = str(c1_path)
except Exception as e:
    print(f"[generate_report] WARNING: C1 chart skipped: {e}")
```

- [ ] **Step 3: Test with DHG**

```bash
python -c "
from pathlib import Path
from backend.reporting.price_chart import generate_c1_price_vs_vnindex
out = generate_c1_price_vs_vnindex('DHG', Path('/tmp/charts'), 'test')
print('C1:', out)
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/reporting/price_chart.py scripts/generate_report.py
git commit -m "feat(charts): C1 stock vs VNINDEX base-100 chart using vnstock price history"
```

---

## Self-Review Against GOAL_OUTPUT.md �19

| Requirement | Task | Status after plan |
|---|---|---|
| 8 section structure | B2 generate_report.py rebuild | ? |
| Visual: layout, charts, tables | B2 HTML template | ? |
| Source manifest | A2 + C1 | ? |
| Financial summary + forecast | existing + B2 | ? |
| Driver-based forecast table (�7.4.4) | C1 generate_report | ? |
| FCFF DCF + assumptions + sensitivity | existing | ? |
| Rating per threshold | existing AssumptionGate | ? |
| Charts (=5) | A3 C2-C7 | ? (6 charts; C1 conditional) |
| Citation 100% | existing evaluate_citations.py | ? |
| Numeric =99% | existing evaluation | ? |
| Valuation reproducibility | B1 gate | ? |
| Risk g?n financial driver | existing (partial; full table C1) | ?? |
| Disclaimer | template | ? |
| eval_result + claim_ledger + source_manifest | A2 + C1 | ? schemas done; full builder C1 |
| Human review | existing approve_report.py | ? |
| PDF export | B3 | ? (Linux/Docker) |
| HTML export | B2 | ? |

**Gaps after plan execution:**
1. Claim ledger builder (producing actual CLM-* entries from report text) � low priority, JSON schema exists
2. Catalyst table with timing/probability fields � generate_report.py Section 7 enhancement
3. Visual budget gate (page count check) � optional

---

**Plan complete. Saved to `.claude/plans/2026-06-01-goal-output-completion.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** � fresh subagent per task, review between tasks

**2. Inline Execution** � execute in this session using executing-plans skill

Which approach?
