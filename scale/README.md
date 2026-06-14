# Scale Planning Index

## Context

Thu muc nay chua cac ke hoach mo rong pipeline equity research tu pilot DHG sang 52 ticker con lai trong universe y duoc/y te Viet Nam. Pham vi hien tai duoc lay tu `config/dataset/universe/pharma_vn_universe.csv`, gom 53 ticker, trong do DHG la pilot hien huu va 52 ticker con lai can duoc mo rong co kiem soat.

## Problem Statement

Muc tieu khong phai la chay batch 52 ticker cang nhanh cang tot. Muc tieu dung la xay dung mot research factory co kha nang mo rong theo ticker nhung van giu duoc ky luat report-quality: du lieu co provenance, forecast co driver, valuation co bridge, report co citation theo claim, va export chi dien ra khi cac gate khong con loi blocking.

## Technical Deep-Dive

| Tai lieu | Vai tro | Doc khi nao |
|---|---|---|
| `00_rollout_master_plan.md` | Ke hoach tong the theo wave, exit criteria va thu tu uu tien | Doc dau tien de nam chien luoc scale |
| `01_ticker_readiness_matrix.md` | Khung danh gia readiness cho tung ticker va danh sach 52 ticker can mo rong | Dung truoc khi submit bat ky batch lon nao |
| `02_batch_execution_plan.md` | Ke hoach nang cap batch runner, cost cap, retry, concurrency va observability | Dung khi sua `backend/batch.py` hoac API batch |
| `03_archetype_model_plan.md` | Thiet ke research pack, forecast va valuation theo tung archetype doanh nghiep | Dung truoc khi mo rong ngoai pharma manufacturer |
| `04_report_quality_gate_and_publication_plan.md` | Chinh sach gate, artifact lifecycle va publish control khi scale | Dung truoc khi cho phep export PDF |
| `05_execution_backlog.md` | Backlog trien khai theo thu tu P0/P1/P2 | Dung de chuyen ke hoach thanh task ky thuat |

## Strategic Recommendations

Khong mo rong truc tiep sang 52 ticker bang mot lenh batch duy nhat. Thu tu de xuat la:

1. Khoa chat governance va export lifecycle tren DHG.
2. Chay pilot them 4 ticker MVP cung nhom pharma: IMP, DMC, TRA, DBD.
3. Tao readiness matrix cho 52 ticker con lai.
4. Mo rong pharma theo wave dua tren data availability.
5. Chi sau do moi mo rong sang healthcare services, medical equipment va medical distribution bang archetype rieng.
