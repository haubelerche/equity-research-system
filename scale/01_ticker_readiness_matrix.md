# Ticker Readiness Matrix

## Context

Readiness matrix la lop kiem soat truoc batch. No quyet dinh ticker nao duoc chay full report, ticker nao chi duoc refresh data, va ticker nao phai bi chan vi thieu bang chung hoac sai archetype.

## Problem Statement

Pipeline research co the that bai mot cach ton kem neu dua ticker chua san sang vao full agent workflow. Mot ticker thieu bao cao tai chinh, gia thi truong, source official, peer set hoac archetype model se tao report draft yeu, lam tang chi phi LLM va lam nhieu failure kho phan loai.

## Technical Deep-Dive

### Initial Universe Split

| Segment | Remaining Count | Tickers |
|---|---:|---|
| Pharma | 43 | IMP, DMC, TRA, DBD, OPC, PME, MKP, DVN, DHT, LDP, PPP, DP3, DP1, TW3, MED, PMC, VHE, VDP, DCL, SPM, VMD, BVP, DNM, DBT, DPP, DRP, DTP, VMC, P29, BID, PDT, BCR, VNP, YT1, CPC, HDA, TMP, DRG, LNT, HGP, PVD, CON, TNT |
| Healthcare services | 3 | TNH, T32, NDT |
| Medical equipment | 3 | JVC, AMV, DDS |
| Medical distribution | 3 | YTC, HBH, DGW |

### Readiness Schema

Moi ticker nen co mot record readiness rieng:

```yaml
ticker_readiness:
  ticker:
  segment:
  archetype:
  exchange:
  data_status:
    financial_statements:
      annual_periods_available:
      quarterly_periods_available:
      latest_period:
      source_tier:
      blocking_gaps:
    market_data:
      latest_price_date:
      liquidity_available:
      market_cap_available:
    official_documents:
      annual_reports:
      quarterly_reports:
      disclosures:
      ocr_required:
    research_evidence:
      company_profile:
      business_segments:
      revenue_mix:
      product_or_service_mix:
      catalysts:
      risks:
    valuation_inputs:
      shares:
      cash:
      debt:
      working_capital:
      capex:
      tax_rate:
      wacc_inputs:
    peer_set:
      peers:
      peer_metrics_available:
  readiness_score:
  decision: ready_for_full_report | refresh_required | draft_only | data_blocked
  blocking_reasons:
```

### Scoring Model

| Component | Weight | Pass Condition |
|---|---:|---|
| Financial statements completeness | 25 | Co du P&L, balance sheet, cash flow cho lich su can thiet |
| Market data freshness | 10 | Co gia, market cap va ngay gia moi |
| Official source coverage | 15 | Co annual/quarterly report hoac disclosure co provenance |
| Company-specific research | 15 | Co segment, product/service, catalyst va risk rieng |
| Forecast input availability | 15 | Co driver inputs phu hop archetype |
| Valuation input availability | 15 | Co cash, debt, shares, WACC assumptions, working capital |
| Peer set availability | 5 | Co peer cung archetype hoac ly do thieu peer |

### Decision Policy

| Readiness Score | Decision | Action |
|---:|---|---|
| >= 85 | `ready_for_full_report` | Cho phep full report pipeline |
| 70-84 | `draft_only` | Cho phep draft noi bo, khong export client-final |
| 50-69 | `refresh_required` | Chi chay data refresh, ingestion, OCR, evidence collection |
| < 50 | `data_blocked` | Khong chay report; tao task thu thap data |

## Strategic Recommendations

1. Tao `scale/ticker_readiness.csv` hoac artifact tu dong trong `research` schema sau khi co implementation.
2. Bat buoc readiness scan truoc `backend.batch.submit_universe_runs`.
3. Neu ticker non-pharma chua co archetype model rieng, mac dinh decision phai la `draft_only` hoac `data_blocked`, khong duoc `ready_for_full_report`.
4. Dung readiness matrix de uu tien wave, khong uu tien theo thu tu CSV.

