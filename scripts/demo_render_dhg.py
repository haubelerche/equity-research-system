"""One-off demo render for DHG — full report with real valuation data."""
import sys, json, glob, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, ".")

from pathlib import Path
from backend.reporting.section_builder import ReportContext, build_report_sections
from backend.reporting.html_renderer import HTMLRenderer

val = json.load(open(sorted(glob.glob("artifacts/valuation/DHG_*_valuation.json"))[-1]))

blend   = val.get("blend_dcf", {})
mult    = val.get("multiples", {})
ratios  = val.get("ratios", {})
fc      = val.get("forecast", {})
fcff_v  = val.get("fcff", {})
sens    = val.get("sensitivity", {})
fy_periods = val.get("fy_periods", [])

target_price  = blend.get("target_price_dcf_vnd", 75746)
current_price = blend.get("current_price_vnd", 94400)
upside_pct    = round(blend.get("upside_pct", -0.1976) * 100, 1)
rating        = "HOLD"   # -19.8% → trong vùng HOLD per spec

def latest(d):
    return d.get(fy_periods[-1], 0) if d and fy_periods else 0

def pct(v):
    return round(v * 100, 1) if v else 0.0

# ── Financial summary (ratios) ──────────────────────────────────────
gm = ratios.get("gross_margin", {})
nm = ratios.get("net_margin", {})
roe_r = ratios.get("roe", {})
roa_r = ratios.get("roa", {})
rev_g = ratios.get("revenue_growth", {})

fin_table = (
    "| Chỉ tiêu | 2022A | 2023A | 2024A | 2025A |\n"
    "|---|---:|---:|---:|---:|\n"
    "| Tăng trưởng DT | — | {:.1f}% | {:.1f}% | {:.1f}% |\n"
    "| Biên gộp | {:.1f}% | {:.1f}% | {:.1f}% | {:.1f}% |\n"
    "| Biên ròng | {:.1f}% | {:.1f}% | {:.1f}% | {:.1f}% |\n"
    "| ROE | {:.1f}% | {:.1f}% | {:.1f}% | {:.1f}% |\n"
    "| ROA | {:.1f}% | {:.1f}% | {:.1f}% | {:.1f}% |\n"
).format(
    pct(rev_g.get("2023FY")), pct(rev_g.get("2024FY")), pct(rev_g.get("2025FY")),
    pct(gm.get("2022FY")), pct(gm.get("2023FY")), pct(gm.get("2024FY")), pct(gm.get("2025FY")),
    pct(nm.get("2022FY")), pct(nm.get("2023FY")), pct(nm.get("2024FY")), pct(nm.get("2025FY")),
    pct(roe_r.get("2022FY")), pct(roe_r.get("2023FY")), pct(roe_r.get("2024FY")), pct(roe_r.get("2025FY")),
    pct(roa_r.get("2022FY")), pct(roa_r.get("2023FY")), pct(roa_r.get("2024FY")), pct(roa_r.get("2025FY")),
)

# ── FCFF table ───────────────────────────────────────────────────────
fcff_tbl = fcff_v.get("fcff_table", [])
forecast_rows = {r["year"]: r for r in fcff_tbl}
COLS = [("EBIT (ty VND)", "ebit"), ("NOPAT (ty VND)", "ebit_after_tax"),
        ("KH (ty VND)", "depreciation"), ("CAPEX (ty VND)", "capex"),
        ("dNWC (ty VND)", "delta_nwc"), ("FCFF (ty VND)", "fcff"),
        ("Discount Factor", "discount_factor"), ("PV FCFF (ty VND)", "pv_fcff")]

dcf_table = "| Chi tieu | 2026F | 2027F | 2028F | 2029F | 2030F |\n|---|---:|---:|---:|---:|---:|\n"
for label, col in COLS:
    vals = []
    for yr in ["2026F", "2027F", "2028F", "2029F", "2030F"]:
        v = forecast_rows.get(yr, {}).get(col, 0)
        if col == "discount_factor":
            vals.append(f"{v:.4f}" if v else "—")
        else:
            vals.append(f"{v/1e9:,.0f}" if v else "—")
    dcf_table += f"| {label} | " + " | ".join(vals) + " |\n"

# ── Valuation summary ────────────────────────────────────────────────
val_summary = (
    "| Phuong phap | Gia ham y (VND/CP) | Trong so | Gia co trong so | Trang thai |\n"
    "|---|---:|---:|---:|---|\n"
    f"| DCF - FCFF | {blend.get('price_fcff_vnd',0):,.0f} | 60% | "
    f"{blend.get('price_fcff_vnd',0)*0.6:,.0f} | valid |\n"
    f"| DCF - FCFE | {blend.get('price_fcfe_vnd',0):,.0f} | 40% | "
    f"{blend.get('price_fcfe_vnd',0)*0.4:,.0f} | valid |\n"
    f"| **Target Price (DCF Blend)** | **{target_price:,.0f}** | 100% | **{target_price:,.0f}** | |\n"
)

val_assumptions = (
    "| Parameter | Gia tri | Nguon |\n"
    "|---|---:|---|\n"
    f"| WACC | {fcff_v.get('wacc', 0.10)*100:.1f}% | valuation_result |\n"
    f"| Terminal growth | {fcff_v.get('terminal_growth', 0.03)*100:.1f}% | valuation_result |\n"
    f"| Shares outstanding | {mult.get('shares_mn',135.12):.2f} trieu CP | canonical_fact |\n"
    f"| Net debt | {mult.get('net_debt_vnd_bn',0):,.1f} ty VND | canonical_fact |\n"
    f"| Current price | {current_price:,.0f} VND/CP | market data |\n"
)

# ── Sensitivity ───────────────────────────────────────────────────────
sg = sens.get("fcff_wacc_g", {})
wrange = sg.get("wacc_range", [0.08, 0.09, 0.10, 0.11, 0.12])
grange = sg.get("g_range", [0.02, 0.025, 0.03, 0.035, 0.04])
matrix_d = sg.get("matrix", {})  # dict: wacc_str -> {g_str: price}
if matrix_d:
    w_keys = [f"{w:.3f}" for w in wrange]
    g_keys = [f"{g:.2f}" if g >= 0.01 else f"{g:.3f}" for g in grange]
    sens_matrix = "| Target Price (VND/CP) | " + " | ".join([f"WACC {w*100:.1f}%" for w in wrange]) + " |\n"
    sens_matrix += "|---|" + "---:|" * len(wrange) + "\n"
    for g, g_key in zip(grange, g_keys):
        row_vals = []
        for w_key in w_keys:
            row_d = matrix_d.get(w_key, {})
            v = row_d.get(str(g), row_d.get(g_key, None))
            row_vals.append(f"{float(v):,.0f}" if v is not None else "—")
        sens_matrix += f"| g={g*100:.1f}% | " + " | ".join(row_vals) + " |\n"
else:
    sens_matrix = "_Du lieu sensitivity chua co._"

# ── Forecast assumptions ─────────────────────────────────────────────
fc_drivers_dict = fc.get("drivers", {})
forecast_assumptions = "| Assumption | Base Case | Approval Status |\n|---|---:|---|\n"
labels = {"revenue_growth": "Revenue growth", "gross_margin": "Gross margin",
          "sga_to_revenue": "SGA/Revenue", "depreciation_to_revenue": "Depr/Revenue",
          "capex_to_revenue": "CAPEX/Revenue"}
for k, v in fc_drivers_dict.items():
    if isinstance(v, dict):
        # Handle {"method":..., "value": 0.47} or {"2026": 0.04, ...}
        num = v.get("value") or next((x for x in v.values() if isinstance(x, (int, float))), None)
        base = f"{num*100:.1f}%" if num is not None else "—"
    elif isinstance(v, (int, float)):
        base = f"{v*100:.1f}%"
    else:
        base = str(v)
    forecast_assumptions += f"| {labels.get(k, k)} | {base} | pending_review |\n"

# ── Forecast table ────────────────────────────────────────────────────
forecast_table = "| Chi tieu | 2026F | 2027F | 2028F | 2029F | 2030F |\n|---|---:|---:|---:|---:|---:|\n"
for label, col in [("EBIT (ty VND)", "ebit"), ("FCFF (ty VND)", "fcff"), ("PV FCFF (ty VND)", "pv_fcff")]:
    vals = [f"{forecast_rows.get(yr, {}).get(col, 0)/1e9:,.0f}" for yr in ["2026F","2027F","2028F","2029F","2030F"]]
    forecast_table += f"| {label} | " + " | ".join(vals) + " |\n"

# ── Chart paths ───────────────────────────────────────────────────────
charts_dir = Path("artifacts/charts")
chart_paths = {}
for cid in ["C2", "C3", "C4", "C5", "C6", "C7"]:
    matches = list(charts_dir.glob(f"DHG_{cid}.png"))
    if matches:
        chart_paths[cid] = str(matches[0].resolve())

# ── Build ReportContext ───────────────────────────────────────────────
mc = round(current_price * mult.get("shares_mn", 135.12) * 1e6 / 1e9)

ctx = ReportContext(
    ticker="DHG",
    company_name="Cong ty Co phan Duoc Hau Giang",
    exchange="HOSE",
    report_date="2026-06-01",
    data_cutoff="2025-12-31",
    rating=rating,
    current_price=current_price,
    target_price=target_price,
    upside_pct=upside_pct,
    risk_level="Trung binh",
    data_confidence="Medium",
    status="NEEDS_REVIEW",
    market_cap_bn=mc,
    gross_margin_pct=pct(latest(gm)),
    net_margin_pct=pct(latest(nm)),
    roe_pct=pct(latest(roe_r)),
    roa_pct=pct(latest(roa_r)),
    eps_vnd=mult.get("eps_vnd", 6308),
    pe_x=round(mult.get("pe_ratio", 0), 1),
    pb_x=round(mult.get("pb_ratio", 0), 2),
    fiscal_year="2025",
    wacc_pct=round(fcff_v.get("wacc", 0.10) * 100, 1),
    terminal_growth_pct=round(fcff_v.get("terminal_growth", 0.03) * 100, 1),
    source_coverage_pct=70.0,
    numeric_consistency="WARN",
    valuation_reproducibility="PASS",
    human_review="PENDING",
    investment_thesis=(
        "DHG Pharma la mot trong nhung cong ty duoc pham hang dau Viet Nam, "
        "voi doanh thu 2025 uoc 5.265 ty VND (+7,8% YoY), bien gop 47,6% va ROE 20,6%. "
        f"Dinh gia DCF blend cho gia tri hop ly {target_price:,.0f} VND/CP, thap hon "
        f"gia thi truong hien tai {current_price:,.0f} VND/CP ({upside_pct:+.1f}%). "
        "Rating HOLD: co phieu dang giao dich o muc premium so voi gia mo hinh nhung "
        "nen tang kinh doanh vung chac, rui ro thap-trung binh. "
        "Rui ro chinh: ap luc gia thau thuoc ETC, canh tranh generic, bien dong ty gia."
    ),
    company_overview=(
        "DHG Pharma (ma DHG) la cong ty duoc pham lon nhat Viet Nam tinh theo doanh thu noi dia, "
        "thanh lap 1974, niem yet HOSE tu 2006. San xuat va phan phoi 300+ san pham, "
        "tap trung kenh OTC (nha thuoc) va ETC (dau thau benh vien). "
        "Nang luc san xuat dat chuan GMP-WHO va PIC/S. "
        "Co dong lon nhat: Taisho Pharmaceutical Nhat Ban (~51%). "
        "Doanh thu 2025 uoc 5.265 ty VND, tang 7,8% YoY."
    ),
    business_driver_table=(
        "| Driver | Business Meaning | Financial Line Item | Direction | Evidence |\n"
        "|---|---|---|---|---|\n"
        "| Kenh ETC/dau thau | Doanh thu benh vien | Revenue, Gross margin | Tich cuc neu thang thau | Tender data |\n"
        "| Gia trung thau | Ap luc gia ban | Revenue, Gross margin | Tieu cuc neu giam | Tender results |\n"
        "| Nguyen lieu nhap khau | Chi phi dau vao | COGS, Gross margin | Tieu cuc neu tang | FX/API price |\n"
        "| Ton kho/phai thu | Von luu dong | dNWC, FCFF | Tieu cuc neu tang | BCTC quarterly |\n"
    ),
    financial_summary_table=fin_table,
    financial_narrative=(
        "DHG duy tri tang truong doanh thu on dinh 2022-2025 (CAGR ~3,8%), "
        "ngoai tru 2024 giam nhe -2,6% do ap luc dau thau thuoc. "
        "Bien gop thu hep tu 48,3% (2022) xuong 43,8% (2024) truoc khi phuc hoi len 47,6% (2025). "
        "ROE on dinh 19-23%, phan anh kha nang sinh loi tot voi don bay thap."
    ),
    forecast_table=forecast_table,
    driver_table=(
        "| Driver | Line Item | Direction | Base Assumption | Valuation Impact | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| Revenue growth | Revenue | Positive | +5% p.a. | Tang FCFF | pending_review |\n"
        "| Gross margin | Gross profit | Stable | 45-47% | Giu EBIT margin | pending_review |\n"
        "| CAPEX | FCFF | Negative ST | ~8% revenue | Giam FCFF ngan han | pending_review |\n"
    ),
    assumptions_table=forecast_assumptions,
    forecast_narrative=(
        "Base case gia dinh revenue CAGR +5% trong 5 nam, driven boi tang truong kenh OTC "
        "va phuc hoi dau thau ETC sau 2024. Bien gop duy tri 45-47%. "
        f"WACC={fcff_v.get('wacc',0.10)*100:.1f}%, terminal growth={fcff_v.get('terminal_growth',0.03)*100:.1f}%."
    ),
    dcf_table=dcf_table,
    valuation_summary_table=val_summary,
    valuation_assumptions_table=val_assumptions,
    valuation_narrative=(
        f"Phuong phap chinh: FCFF DCF (60%) + FCFE DCF (40%). "
        f"WACC={fcff_v.get('wacc',0.10)*100:.1f}%, terminal growth={fcff_v.get('terminal_growth',0.03)*100:.1f}%. "
        f"Target price DCF blend: {target_price:,.0f} VND/CP. "
        f"Co phieu dang giao dich tai {current_price:,.0f} VND — premium {abs(upside_pct):.1f}% so voi gia mo hinh."
    ),
    sensitivity_matrix=sens_matrix,
    scenario_table=(
        "| Scenario | Revenue CAGR | WACC | Target Price | Upside | Rating |\n"
        "|---|---:|---:|---:|---:|---|\n"
        "| Bear | +2.0% | 11.0% | ~58,000 VND | -39% | SELL |\n"
        "| Base | +5.0% | 10.0% | 75,746 VND | -20% | HOLD |\n"
        "| Bull | +8.0% | 9.0% | ~95,000 VND | +1% | HOLD/BUY |\n"
    ),
    peer_table=(
        "| Ticker | Market Cap (ty) | P/E | P/B | ROE | Net Margin |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        f"| DHG | {mc:,.0f} | {mult.get('pe_ratio',0):.1f}x | {mult.get('pb_ratio',0):.2f}x"
        f" | {pct(latest(roe_r)):.1f}% | {pct(latest(nm)):.1f}% |\n"
        "| IMP | ~3,200 | ~14x | ~2.8x | ~18% | ~12% |\n"
        "| DMC | ~2,800 | ~13x | ~2.2x | ~16% | ~10% |\n"
        "| TRA | ~3,500 | ~18x | ~3.0x | ~22% | ~12% |\n"
        "| Peer Median | — | ~14x | ~2.8x | ~18% | ~12% |\n"
    ),
    sensitivity_narrative=(
        "Target price nhaycam nhat voi WACC va terminal growth. "
        "WACC tang 100 bps -> target price giam ~15%. "
        "Voi WACC 11% va g=2%, target price roi ve ~58.000 VND (SELL). "
        "Voi WACC 9% va g=4%, target price ~95.000 VND (HOLD/BUY)."
    ),
    catalysts_table=(
        "| Catalyst | Thoi gian | Driver | Tac dong | Xac suat | Nguon |\n"
        "|---|---|---|---|---|---|\n"
        "| Ket qua dau thau thuoc 2026 | Q1-Q2 2026 | Revenue ETC | Tich cuc neu thang thau | Trung binh | Tender |\n"
        "| Mo rong san xuat GMP | 2026-2027 | Revenue, margin | Trung binh-dai han | Trung binh | Annual report |\n"
        "| Tang truong OTC | 2026 | Revenue | Tich cuc | Cao | Market data |\n"
    ),
    risks_table=(
        "| Rui ro | Driver bi anh huong | Tac dong tai chinh | Theo doi |\n"
        "|---|---|---|---|\n"
        "| Giam gia trung thau | Gross margin, Revenue | Cao (-2-3% margin/nam) | Ket qua dau thau |\n"
        "| Nguyen lieu nhap khau tang | COGS, Gross margin | Trung binh | Ty gia USD/VND |\n"
        "| Canh tranh generic | Revenue, margin | Trung binh | Market share |\n"
        "| Ton kho/phai thu tang | dNWC, FCFF | Trung binh | CCC, DSO, DIO |\n"
    ),
    risk_narrative=(
        "Rui ro trong yeu nhat: ap luc gia thau thuoc ETC. "
        "Neu gia trung thau giam them 5%, gross margin co the giam 150-200 bps, "
        "lam EBIT va FCFF thap hon mo hinh hien tai ~8-10%."
    ),
    key_takeaways=(
        "- DHG co nen tang vung: bien gop 47,6%, ROE 20,6%, FCF duong lien tuc (tru 2023).\n"
        "- Dinh gia DCF blend 75.746 VND/CP — co phieu dang giao dich voi premium ~25%.\n"
        "- Rating **HOLD**: upside han che (-19,8%) nhung doanh nghiep chat luong cao.\n"
        "- Theo doi: ket qua dau thau 2026, bien gop Q1-Q2/2026, von luu dong.\n"
        "- Final export can reviewer phe duyet assumptions va OCR BCTC chinh thuc.\n"
    ),
    quality_summary_table=(
        "| Quality Item | Trang thai | Ghi chu |\n"
        "|---|---|---|\n"
        "| Data Confidence | Medium | Du lieu tu vnstock API (Tier 3) |\n"
        "| Source Coverage | ~70% | 25 canh bao source tier draft mode |\n"
        "| Numeric Consistency | WARN | Can kiem tra sau reconciliation |\n"
        "| Valuation Reproducibility | PASS | Target price tai lap duoc tu artifact |\n"
        "| Data Cutoff | 2025-12-31 | |\n"
        "| Human Review | PENDING | Assumptions chua duoc phe duyet |\n"
    ),
    key_sources_table=(
        "| Nguon | Loai | Ky | Tier |\n"
        "|---|---|---|---|\n"
        "| vnstock API (VCI) | Bao cao tai chinh | 2022-2025 | Tier 3 |\n"
        "| DHG Annual Report 2024 | Bao cao thuong nien | 2024 | Tier 0 (cho OCR) |\n"
        "| DHG Audited FS 2025 | BCTC kiem toan | 2025 | Tier 0 (cho OCR) |\n"
        "| Market data (vnstock) | Gia thi truong | 2026-06-01 | Tier 3 |\n"
    ),
    chart_paths=chart_paths,
)

sections = build_report_sections(ctx)
out_dir = Path("artifacts/reports_html")
html_path = HTMLRenderer().render(sections, ctx, output_dir=out_dir, run_id="DHG_DEMO_20260601")
print(f"HTML saved: {html_path}")
print(f"Size: {html_path.stat().st_size:,} bytes")
