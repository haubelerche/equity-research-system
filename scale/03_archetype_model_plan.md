# Archetype Model Plan

## Context

Universe hien tai khong dong nhat. Da so la pharma, nhung con co healthcare services, medical equipment va medical distribution. Mot template duy nhat ve API, EU-GMP, ETC/OTC va tender thuoc se sai khi ap dung cho benh vien, thiet bi y te hoac doanh nghiep phan phoi.

## Problem Statement

Khi scale 52 ticker, loi nghiem trong nhat ve san pham khong phai la report thieu dep, ma la report dung sai mo hinh kinh doanh. Sai archetype lam forecast driver sai, peer set sai, valuation assumption sai, va narrative trong report tro nen chung chung hoac misleading.

## Technical Deep-Dive

### Required Archetypes

| Archetype | Applicable Tickers | Research Pack Required Evidence | Forecast Drivers | Valuation Focus |
|---|---|---|---|---|
| Branded/generic pharma manufacturer | DHG, IMP, DMC, DBD, PME, DCL, DHT, etc. | Product groups, ETC/OTC mix, factory status, GMP, API exposure, tender results | Channel revenue, product mix, API/FX, gross margin, SG&A, capex | FCFF/FCFE if debt and payout data are reliable |
| Traditional medicine / herbal pharma | TRA, OPC, VHE, PMC, possible long-tail pharma | Brand strength, herbal material supply, OTC channel, product concentration | OTC growth, raw material cost, distribution expansion, brand spend | FCFF with margin and working capital sensitivity |
| Tender-focused pharma | DBD, DMC, IMP, selected manufacturers | Tender value, win rate, hospital channel, product registration, reimbursement | ETC volume, tender price, payment cycle, receivable days | FCFF with working capital and receivables stress |
| Medical distribution | YTC, HBH, DGW | Distribution contracts, inventory cycle, customer concentration, gross spread | Sales volume, gross spread, inventory days, receivable days | Lower-margin DCF, working capital critical |
| Medical equipment | JVC, AMV, DDS | Product category, import exposure, hospital capex/tender, FX, warranty/service | Tender cycle, imported cost, FX, capex demand | Scenario-based valuation; high governance around revenue quality |
| Healthcare services | TNH, T32, NDT | Beds/clinics, utilization, patient volume, ARPU, payer mix, expansion capex | Patient visits, bed utilization, ARPU, payer mix, staffing cost | DCF with capex, depreciation and utilization scenarios |

### Archetype Assignment Contract

Moi ticker phai co:

```yaml
archetype_assignment:
  ticker:
  primary_archetype:
  secondary_archetype:
  confidence:
  evidence_refs:
  forbidden_templates:
  required_driver_model:
  peer_selection_rule:
```

### Model-Specific Gate Examples

| Archetype | Blocking Condition |
|---|---|
| Pharma manufacturer | Report nhac API/GMP/ETC nhung research pack khong co source-specific evidence |
| Traditional medicine | Forecast dua tren tender hospital neu doanh nghiep chu yeu OTC/herbal ma khong co evidence |
| Distributor | Valuation bo qua working capital days hoac inventory cycle |
| Medical equipment | Gross margin forecast khong co FX/import cost sensitivity |
| Healthcare services | Revenue forecast khong co utilization, ARPU hoac capacity assumption |

## Strategic Recommendations

1. Khong nen scale non-pharma truoc khi co archetype-specific gate.
2. `company_research_pack` nen co schema linh hoat theo archetype, khong bat moi ticker co API/GMP.
3. Peer engine phai chon peer theo archetype va margin profile, khong chi theo sector label.
4. Report writer chi duoc nhan section evidence pack da duoc archetype filter, de tranh noi dung pharma ro ri sang non-pharma.

