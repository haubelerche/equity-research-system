# Master Rollout Plan For 52 Remaining Tickers

## Context

Universe hien tai co 53 ticker: 44 pharma, 3 healthcare services, 3 medical equipment va 3 medical distribution. DHG da dong vai tro pilot dau tien, nen pham vi scale con lai la 52 ticker. Pipeline da co cac thanh phan cot loi nhu run-scoped artifacts, report-quality evaluator, export gates, `publishable_final_report_model`, va fast render path chi nen dung lai artifact da duoc phe duyet.

## Problem Statement

Neu mo rong ngay sang 52 ticker, he thong se khuếch dai bon nhom rui ro: thieu data readiness, sai archetype, sai forecast/valuation, va chi phi debug tang phi tuyen. Do do, scale plan phai duoc thiet ke nhu mot quy trinh san xuat co gate, khong phai mot script lap qua danh sach ticker.

## Technical Deep-Dive

### Rollout Waves

| Wave | Pham vi | Ticker | Muc tieu | Dieu kien thoat wave |
|---|---|---|---|---|
| 0 | Governance regression | DHG | Xac nhan DHG that bai khi thieu gate va chi export khi co approval dung | Fast render khong bypass gate; report-quality diagnostic on dinh |
| 1 | MVP pharma pilot | IMP, DMC, TRA, DBD | Kiem tra kha nang lap lai pipeline tren cac cong ty duoc lon hon, du lieu kha hon | It nhat 3/4 ticker tao duoc draft co valuation bridge va gate reasons ro rang |
| 2 | Liquid pharma expansion | OPC, PME, MKP, DHT, DCL, SPM, VMD, BVP | Mo rong sang pharma co thanh khoan/du lieu kha hon HOSE/HNX/UPCOM lon | Readiness score >= 80% truoc report writing |
| 3 | Remaining pharma | DVN, LDP, PPP, DP3, DP1, TW3, MED, PMC, VHE, VDP, DNM, DBT, DPP, DRP, DTP, VMC, P29, BID, PDT, BCR, VNP, YT1, CPC, HDA, TMP, DRG, LNT, HGP, PVD, CON, TNT | Xu ly long tail, UPCOM va cong ty nho | Moi ticker co status: publishable, draft_only, hoac data_blocked |
| 4 | Non-pharma archetypes | TNH, T32, NDT, JVC, AMV, DDS, YTC, HBH, DGW | Kiem tra model rieng cho dich vu y te, thiet bi y te va phan phoi | Khong con dung template pharma cho ticker non-pharma |

### Iron Triangle Assessment

| Axis | Yeu cau khi scale | Thiet ke de xuat |
|---|---|---|
| Scalability | Chay nhieu ticker ma khong no chi phi agent hoac DB contention | Batch queue, concurrency limit, cost cap theo ngay, resume failed runs |
| Reliability | Khong tao report publishable tu du lieu thieu hoac artifact stale | Ticker readiness manifest, snapshot consistency, artifact locking |
| Latency | Hoan thanh wave nho trong khung thoi gian co the debug | Tach data refresh, research pack, valuation, report va export thanh stage rieng |

## Strategic Recommendations

### Phase 0: Freeze Ungoverned Expansion

Khong submit full universe cho den khi co ba bao ve:

1. `generate_fast_report` chi render run co `publishable_final_report_model` locked.
2. `REPORT_QUALITY_GATE` bat buoc chay truoc export.
3. Batch runner co kha nang gioi han ticker, segment, concurrency va cost.

### Phase 1: Run MVP Pilot Beyond DHG

Chay IMP, DMC, TRA va DBD theo che do draft-first. Muc tieu cua phase nay khong phai tao report dep, ma la do xem pipeline loi o dau: ingestion, research pack, forecast, valuation, citation hay renderer.

### Phase 2: Build Readiness-First Scale Loop

Voi moi ticker:

```text
universe ticker
-> data readiness scan
-> archetype assignment
-> company research pack
-> deterministic forecast and valuation
-> report candidate
-> review and report-quality evaluation
-> publishable final only if score >= 85 and no failed blocking gate
```

### Phase 3: Controlled Production Expansion

Chi chay 10-15 ticker moi wave. Moi wave phai co bao cao tong ket:

| Metric | Target |
|---|---:|
| Data blocked rate | < 30% sau Wave 2 |
| Draft generated rate | > 70% cho pharma liquid universe |
| Report-quality allow-export rate | Ban dau co the thap; muc tieu > 50% sau model hardening |
| Average failed gates per ticker | Giam qua moi wave |
| Cost per draft report | Duoc ghi trong cost ledger |
