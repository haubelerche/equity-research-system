"""Direct report renderer: facts → analytics → HTML → PDF.

Bypasses the full 23-stage pipeline. Loads canonical facts from snapshot,
computes ratios/valuation in Python, and renders a diagnostic facts report.
Production reports must be generated through scripts/run_research.py and
published through Supabase Storage run artifacts.

Usage:
    python scripts/render_from_facts.py --ticker DHG
    python scripts/render_from_facts.py --ticker DHG --snapshot storage/runs/dhg_dq_after_snapshot_fix/facts_snapshot.json
"""
from __future__ import annotations

import argparse
import json
import tempfile
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.facts.normalizer import FactTable, FactEntry, compute_derived
from backend.analytics.ratios import compute_ratios


def _find_latest_snapshot(ticker: str) -> Path | None:
    runs_dir = ROOT / "storage" / "runs"
    if not runs_dir.exists():
        return None
    candidates = sorted(runs_dir.glob("*/facts_snapshot.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for c in candidates:
        data = json.loads(c.read_text(encoding="utf-8"))
        if data.get("ticker", "").upper() == ticker.upper():
            return c
    return None


def _load_fact_table(snapshot_path: Path) -> tuple[dict, FactTable]:
    raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    facts = raw.get("facts", {})
    table: FactTable = {}
    for metric_key, periods in facts.items():
        table[metric_key] = {}
        for period_key, entry in periods.items():
            table[metric_key][period_key] = FactEntry(
                value=entry["value"],
                fact_id=entry.get("fact_id", ""),
                source_id=entry.get("source_id", ""),
                source_uri=entry.get("source_uri", ""),
                source_title=entry.get("source_title", ""),
                source_tier=entry.get("source_tier", 3),
                confidence=entry.get("confidence", "0.98"),
            )
    return raw, table


def _fmt(value: float | None, fmt_type: str = "currency") -> str:
    if value is None:
        return "—"
    if fmt_type == "percent":
        return f"{value * 100:.1f}%"
    if fmt_type == "multiple":
        return f"{value:.2f}x"
    if fmt_type == "integer":
        return f"{value:,.0f}"
    # currency in VND bn
    return f"{value / 1e9:,.1f}"


def _get_val(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry.value if hasattr(entry, "value") else float(entry)


def _build_html(ticker: str, meta: dict, table: FactTable, ratios: dict) -> str:
    periods = sorted(meta.get("periods_available", []))
    css = (ROOT / "backend" / "reporting" / "templates" / "report.css").read_text(encoding="utf-8")
    now = datetime.now().strftime("%d/%m/%Y")

    # Key metrics for latest period
    latest = periods[-1] if periods else "2025FY"
    rev = _get_val(table, "revenue.net", latest)
    ni = _get_val(table, "net_income.parent", latest)
    gp = _get_val(table, "gross_profit.total", latest)
    eps = _get_val(table, "eps.basic", latest)
    equity = _get_val(table, "equity.parent", latest)
    assets = _get_val(table, "total_assets.ending", latest)
    ocf = _get_val(table, "operating_cash_flow.total", latest)
    capex = _get_val(table, "capex.total", latest)
    fcf = (_get_val(table, "free_cash_flow.total", latest)
           or (ocf + capex if ocf is not None and capex is not None else None))

    # Ratio helpers
    def _r(key: str, period: str) -> float | None:
        return ratios.get(key, {}).get(period)

    # ── Financial summary table rows ──
    def _fin_row(label: str, key: str, fmt: str = "currency") -> str:
        cells = "".join(
            f'<td class="numeric">{_fmt(_get_val(table, key, p), fmt)}</td>'
            for p in periods
        )
        return f"<tr><td>{label}</td>{cells}</tr>"

    def _ratio_row(label: str, key: str, fmt: str = "percent") -> str:
        cells = "".join(
            f'<td class="numeric">{_fmt(_r(key, p), fmt)}</td>'
            for p in periods
        )
        return f"<tr><td>{label}</td>{cells}</tr>"

    def _derived_row(label: str, key: str, fmt: str = "currency") -> str:
        cells = "".join(
            f'<td class="numeric">{_fmt(_get_val(table, key, p), fmt)}</td>'
            for p in periods
        )
        return f"<tr><td>{label}</td>{cells}</tr>"

    period_headers = "".join(f"<th>{p}</th>" for p in periods)

    # Revenue growth YoY
    rev_vals = [_get_val(table, "revenue.net", p) for p in periods]
    rev_growth = []
    for i, p in enumerate(periods):
        if i == 0:
            rev_growth.append("—")
        elif rev_vals[i] is not None and rev_vals[i-1] is not None and rev_vals[i-1] != 0:
            g = (rev_vals[i] - rev_vals[i-1]) / abs(rev_vals[i-1])
            rev_growth.append(f"{g*100:.1f}%")
        else:
            rev_growth.append("—")

    rev_growth_cells = "".join(f'<td class="numeric">{g}</td>' for g in rev_growth)

    # Net income growth YoY
    ni_vals = [_get_val(table, "net_income.parent", p) for p in periods]
    ni_growth = []
    for i, p in enumerate(periods):
        if i == 0:
            ni_growth.append("—")
        elif ni_vals[i] is not None and ni_vals[i-1] is not None and ni_vals[i-1] != 0:
            g = (ni_vals[i] - ni_vals[i-1]) / abs(ni_vals[i-1])
            ni_growth.append(f"{g*100:.1f}%")
        else:
            ni_growth.append("—")
    ni_growth_cells = "".join(f'<td class="numeric">{g}</td>' for g in ni_growth)

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ticker} — Báo cáo phân tích cổ phiếu</title>
<style>
{css}
</style>
</head>
<body>

<!-- ── Cover Page ──────────────────────────────────────── -->
<div class="report-section chapter-break">
  <h1>{ticker} — Báo cáo phân tích cổ phiếu</h1>
  <p><strong>Ngày báo cáo:</strong> {now}</p>
  <p><strong>Ngành:</strong> Dược phẩm</p>
  <p><strong>Sàn:</strong> HOSE</p>
  <p><strong>Kỳ phân tích:</strong> {', '.join(periods)}</p>
  <p><strong>Nguồn dữ liệu:</strong> BCTC kiểm toán, VNStock VCI</p>
</div>

<!-- ── Executive Summary ──────────────────────────────── -->
<div class="report-section chapter-break">
  <h2>Tóm tắt đầu tư</h2>
  <p>Doanh thu {latest}: <strong>{_fmt(rev)} tỷ VND</strong>
  &nbsp;|&nbsp; LNST: <strong>{_fmt(ni)} tỷ VND</strong>
  &nbsp;|&nbsp; EPS: <strong>{_fmt(eps, 'integer')} VND</strong></p>
  <p>Biên lợi nhuận gộp: <strong>{_fmt(_r('gross_margin', latest), 'percent')}</strong>
  &nbsp;|&nbsp; Biên lợi nhuận ròng: <strong>{_fmt(_r('net_margin', latest), 'percent')}</strong>
  &nbsp;|&nbsp; ROE: <strong>{_fmt(_r('roe', latest), 'percent')}</strong></p>
  <p>Dòng tiền tự do (FCF): <strong>{_fmt(fcf)} tỷ VND</strong></p>
</div>

<!-- ── Income Statement Summary ──────────────────────── -->
<div class="report-section">
  <h2>Kết quả kinh doanh</h2>
  <div class="model-table-block">
    <table class="financial-model-table">
      <thead><tr><th>Chỉ tiêu (tỷ VND)</th>{period_headers}</tr></thead>
      <tbody>
        {_fin_row("Doanh thu thuần", "revenue.net")}
        <tr><td>Tăng trưởng doanh thu</td>{rev_growth_cells}</tr>
        {_fin_row("Giá vốn hàng bán", "cogs.total")}
        {_fin_row("Lợi nhuận gộp", "gross_profit.total")}
        {_ratio_row("Biên lợi nhuận gộp", "gross_margin")}
        {_fin_row("Chi phí lãi vay", "interest_expense.total")}
        {_fin_row("LNTT", "profit_before_tax.total")}
        {_fin_row("Thuế TNDN", "tax_expense.total")}
        {_fin_row("LNST CĐCTM", "net_income.parent")}
        <tr><td>Tăng trưởng LNST</td>{ni_growth_cells}</tr>
        {_ratio_row("Biên lợi nhuận ròng", "net_margin")}
        {_fin_row("EPS (VND)", "eps.basic", "integer")}
      </tbody>
    </table>
    <div class="table-source-note">Nguồn: BCTC kiểm toán; Đơn vị: tỷ VND (trừ EPS)</div>
  </div>
</div>

<!-- ── Balance Sheet Highlights ───────────────────────── -->
<div class="report-section">
  <h2>Bảng cân đối kế toán</h2>
  <div class="model-table-block">
    <table class="financial-model-table">
      <thead><tr><th>Chỉ tiêu (tỷ VND)</th>{period_headers}</tr></thead>
      <tbody>
        {_fin_row("Tổng tài sản", "total_assets.ending")}
        {_fin_row("VCSH (công ty mẹ)", "equity.parent")}
        {_fin_row("Nợ vay ngắn hạn", "short_term_debt.ending")}
        {_derived_row("Tổng nợ vay", "total_debt.ending")}
        {_fin_row("Tiền & tương đương tiền", "cash_and_equivalents.ending")}
        {_ratio_row("Nợ / VCSH", "debt_to_equity", "multiple")}
      </tbody>
    </table>
    <div class="table-source-note">Nguồn: BCTC kiểm toán</div>
  </div>
</div>

<!-- ── Cash Flow ──────────────────────────────────────── -->
<div class="report-section">
  <h2>Dòng tiền</h2>
  <div class="model-table-block">
    <table class="financial-model-table">
      <thead><tr><th>Chỉ tiêu (tỷ VND)</th>{period_headers}</tr></thead>
      <tbody>
        {_fin_row("Dòng tiền hoạt động", "operating_cash_flow.total")}
        {_fin_row("CAPEX", "capex.total")}
        {_derived_row("Free Cash Flow", "free_cash_flow.total")}
        {_fin_row("Khấu hao", "depreciation.total")}
      </tbody>
    </table>
    <div class="table-source-note">Nguồn: BCTC kiểm toán</div>
  </div>
</div>

<!-- ── Key Ratios ─────────────────────────────────────── -->
<div class="report-section">
  <h2>Các chỉ số tài chính chính</h2>
  <div class="model-table-block">
    <table class="financial-model-table">
      <thead><tr><th>Chỉ tiêu</th>{period_headers}</tr></thead>
      <tbody>
        {_ratio_row("Biên lợi nhuận gộp", "gross_margin")}
        {_ratio_row("Biên lợi nhuận ròng", "net_margin")}
        {_ratio_row("ROE", "roe")}
        {_ratio_row("ROA", "roa")}
        {_ratio_row("Nợ / VCSH", "debt_to_equity", "multiple")}
        {_ratio_row("Nợ / Tổng tài sản", "debt_to_assets", "multiple")}
      </tbody>
    </table>
  </div>
</div>

<!-- ── Analysis ───────────────────────────────────────── -->
<div class="report-section chapter-break">
  <h2>Nhận xét phân tích</h2>
  <h3>Doanh thu</h3>
  <p>{ticker} ghi nhận doanh thu thuần {latest} đạt {_fmt(rev)} tỷ VND{(', tăng trưởng ' + rev_growth[-1] + ' so với năm trước') if rev_growth[-1] != '—' else ''}.</p>

  <h3>Lợi nhuận</h3>
  <p>LNST thuộc CĐCTM đạt {_fmt(ni)} tỷ VND, tương ứng biên lợi nhuận ròng {_fmt(_r('net_margin', latest), 'percent')}.</p>

  <h3>Cấu trúc tài chính</h3>
  <p>Tỷ lệ nợ/VCSH ở mức {_fmt(_r('debt_to_equity', latest), 'multiple')}, cho thấy {
    'cấu trúc tài chính rất lành mạnh với gần như không sử dụng đòn bẩy' if (_r('debt_to_equity', latest) or 0) < 0.1
    else 'cấu trúc tài chính ở mức an toàn' if (_r('debt_to_equity', latest) or 0) < 0.5
    else 'đòn bẩy tài chính ở mức trung bình'
  }.</p>

  <h3>Dòng tiền</h3>
  <p>Dòng tiền tự do {latest} đạt {_fmt(fcf)} tỷ VND, {'cho thấy khả năng tạo tiền mặt tốt từ hoạt động kinh doanh' if (fcf or 0) > 0 else 'phản ánh áp lực dòng tiền trong kỳ'}.</p>
</div>

<!-- ── Disclaimer ─────────────────────────────────────── -->
<div class="report-section">
  <h2>Tuyên bố miễn trừ trách nhiệm</h2>
  <p style="font-size: 7.5pt; color: #666;">Báo cáo này được tạo tự động từ dữ liệu BCTC kiểm toán và dữ liệu thị trường.
  Các số liệu được tính toán bằng mô hình Python xác định (deterministic). Báo cáo chỉ mang tính chất tham khảo,
  không phải khuyến nghị đầu tư. Nhà đầu tư cần tự đánh giá và chịu trách nhiệm với quyết định đầu tư của mình.</p>
  <p style="font-size: 7pt; color: #999;">Dữ liệu: VNStock VCI, BCTC kiểm toán | Xử lý: Python analytics engine | Ngày: {now}</p>
</div>

</body>
</html>"""
    return html


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Direct facts → PDF renderer")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--snapshot", help="Path to facts_snapshot.json (auto-detected if omitted)")
    parser.add_argument(
        "--run-id",
        default="",
        help="Upload facts_report.html/pdf to Supabase Storage runs/{run_id}.",
    )
    parser.add_argument(
        "--local-output-dir",
        default="",
        help="Debug-only local output directory. Omit to use an OS temp directory outside the repo.",
    )
    args = parser.parse_args(argv)

    ticker = args.ticker.upper()

    # Find snapshot
    if args.snapshot:
        snapshot_path = Path(args.snapshot)
    else:
        snapshot_path = _find_latest_snapshot(ticker)
    if snapshot_path is None or not snapshot_path.exists():
        print(f"[ERROR] No facts_snapshot.json found for {ticker}")
        sys.exit(1)

    print(f"[render] Loading facts from {snapshot_path}")
    meta, fact_table = _load_fact_table(snapshot_path)
    print(f"[render] {len(fact_table)} metrics, periods: {meta.get('periods_available', [])}")

    # Compute derived metrics + ratios
    compute_derived(fact_table)
    ratios = compute_ratios(fact_table)
    print(f"[render] Computed {len(ratios)} ratio categories")

    # Build HTML
    html_content = _build_html(ticker, meta, fact_table, ratios)

    if not args.run_id:
        print(
            "[render] WARNING: render_from_facts.py is a dev diagnostic path, "
            "not the production multi-agent report path."
        )

    cleanup: tempfile.TemporaryDirectory[str] | None = None
    if args.local_output_dir:
        work_dir = Path(args.local_output_dir)
    else:
        cleanup = tempfile.TemporaryDirectory(prefix=f"{ticker.lower()}-facts-report-")
        work_dir = Path(cleanup.name)
    html_dir = work_dir / "html"
    pdf_dir = work_dir / "pdf"
    html_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    html_path = html_dir / f"{ticker}_facts_report.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"[render] HTML: {html_path}")

    # Render PDF
    from backend.reporting.pdf_renderer import PDFRenderer
    pdf_renderer = PDFRenderer()
    try:
        pdf_path = pdf_renderer.render(
            html_path,
            output_dir=pdf_dir,
            run_id="",
            allow_stub=True,
        )
        print(f"[render] PDF: {pdf_path}")
        if args.run_id:
            from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key

            adapter = SupabaseStorageAdapter()
            uploads = (
                ("facts_report.html", html_path, "text/html; charset=utf-8"),
                ("facts_report.pdf", pdf_path, "application/pdf"),
            )
            for artifact_name, local_path, content_type in uploads:
                storage_path = run_artifact_key(args.run_id, artifact_name)
                checksum = adapter.checksum_file(local_path)
                if adapter.exists(RUNS_BUCKET, storage_path):
                    if not adapter.validate_checksum(RUNS_BUCKET, storage_path, checksum):
                        adapter.upload_file(RUNS_BUCKET, storage_path, local_path, content_type, upsert=True)
                else:
                    adapter.upload_file(RUNS_BUCKET, storage_path, local_path, content_type)
                if not adapter.validate_checksum(RUNS_BUCKET, storage_path, checksum):
                    raise RuntimeError(f"Checksum validation failed: {RUNS_BUCKET}/{storage_path}")
                print(f"[render] uploaded: supabase://{RUNS_BUCKET}/{storage_path}")
    except Exception as e:
        print(f"[render] PDF rendering failed: {e}")
        if cleanup is None:
            print(f"[render] HTML report is still available at: {html_path}")
        else:
            print("[render] HTML was written only to a temporary directory; pass --local-output-dir to retain it.")
    finally:
        if cleanup is not None:
            cleanup.cleanup()


if __name__ == "__main__":
    main()
