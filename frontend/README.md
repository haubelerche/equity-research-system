# Pharma Equity Research — Frontend

Giao diện web (100% tiếng Việt) gồm 2 trang, đặt trên backend FastAPI sẵn có:

1. **Báo cáo** (`/reports`) — duyệt universe ticker dược/y tế đang cấu hình, xem trước (ảnh trang PDF), tải `report.pdf` +
   `explanation.pdf`, và yêu cầu sinh báo cáo cho ticker chưa có.
2. **Khung đánh giá** (`/eval`) — dashboard 8 lớp đánh giá fail-closed (data → RAG → financial →
   citation → agent → FPTS → observability → rollout/CI), với metrics, ngưỡng P0/P1/P2, trạng thái
   pass/fail/measured-only, sơ đồ pipeline, ma trận CI và bảng ngưỡng theo độ chín. Hiện chạy bằng
   dữ liệu mock đúng schema artifact thật; khi có eval thật chỉ cần đổi nguồn dữ liệu.

## Tech

Vite + React 18 + TypeScript + React Router + Vitest. Font **Open Sans** (hỗ trợ dấu tiếng Việt,
self-host qua `@fontsource/open-sans`), cỡ chữ gốc 17px, số dùng monospace.

## Yêu cầu

- Node 18+ và npm.
- Backend FastAPI chạy ở `http://localhost:8000` (để gọi `/reports`, `/research`).

## Lệnh

```bash
cd frontend
npm install          # cài dependencies
npm run dev          # dev server tại http://localhost:5173 (proxy /reports + /research -> :8000)
npm run test         # chạy toàn bộ test (Vitest)
npm run build        # type-check + build production -> frontend/dist/
```

## Quy ước gọi API

Client gọi thẳng đường dẫn backend — **không có tiền tố `/api`**:
`/reports`, `/reports/{ticker}/file/{kind}`, `/reports/{ticker}/preview/{page}`,
`/research/start`, `/research/{id}/status`.

- **Dev:** `vite.config.ts` proxy `/reports` và `/research` sang `http://localhost:8000` (không
  rewrite path).
- **Prod:** chạy `npm run build` rồi khởi động FastAPI; backend tự phục vụ `frontend/dist/` (SPA
  fallback, các route API được ưu tiên trước catch-all). Cùng origin nên không cần proxy.
- **Vercel:** đặt `Root Directory` = `frontend/`, để `frontend/vercel.json` điều khiển `npm ci`,
  `npm run build`, `dist/`, và SPA rewrite.
  Đặt `VITE_API_BASE` trên Vercel bằng public URL của Railway backend, ví dụ
  `https://your-railway-backend.up.railway.app`.

## Cấu trúc

```
src/
  api/          client.ts (fetch typed), types.ts, runStatus.ts (map RunStatus enum thật)
  data/         universe.ts (active configured universe), evalFramework.ts (8 lớp × metrics × ngưỡng)
  lib/          reportFilter.ts, evalStatus.ts (logic thuần, có test)
  mock/         8 file JSON artifact + index.ts (loader giá trị mock cho dashboard)
  components/   reports/* (row, filters, preview, generate), eval/* (pill, metric row, layer card, pipeline, toggle)
  pages/        ReportsPage.tsx, EvalDashboardPage.tsx
  styles/       tokens.css, global.css (design system)
```
