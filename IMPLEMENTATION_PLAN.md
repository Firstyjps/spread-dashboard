# Implementation Plan — Spread Dashboard Refactor & Cleanup

> เอกสารนี้เป็น execution plan สำหรับ Codex ทำตามทีละ task
> **กติกา:** Codex = ลงมือเขียน/แก้โค้ด | Kiro = อัปเดต status, รีวิว, เช็คว่า build/test ผ่าน
> แต่ละ task มี **acceptance criteria** + **verification command** ที่ต้องผ่านก่อนปิด task

**Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Progress Summary

| Phase | หัวข้อ | สถานะ |
|-------|--------|-------|
| Phase 1 (partial) | เคลียร์ dead code execution layer | ✅ DONE |
| Phase 0 | กู้ build frontend (deritrade code + scratch files) | ✅ DONE — verified by Kiro |
| Phase 1 (rest) | ปิด dead config ใน executor | ⬜ TODO — **ทำต่อ** |
| Phase 2 | Type safety frontend (เลิกใช้ `any`) | ⬜ TODO |
| Phase 3 | ต่อฟีเจอร์ค้าง + จัดโครงสร้าง | ⬜ TODO |
| Phase 4 | เอกสาร + DX (linter/CI) | ⬜ TODO |

**Global rules สำหรับทุก task:**
- ห้ามเปลี่ยน REST API path / WebSocket protocol โดยไม่ระบุไว้ใน task
- ทุก task ที่แตะ backend ต้องผ่าน `python -c "import app.main"` (import ต้องสะอาด)
- ทุก task ที่แตะ frontend ต้องผ่าน `npm run build` ใน `frontend/`
- commit แยกต่อ task พร้อม message ตามที่ระบุ

---

## ✅ Phase 1 (partial) — DONE: เคลียร์ dead code Execution layer

> ทำเสร็จแล้ว บันทึกไว้เป็นหลักฐาน ไม่ต้องทำซ้ำ

- [x] ลบ `backend/app/execution/linear_limit_slicer.py`
- [x] ลบ `backend/app/execution/maker_slicer_linear.py`
- [x] ลบ `backend/app/execution/bybit_linear_client.py`
- [x] ลบ package `backend/app/exchanges/bybit_linear/` ทั้งหมด
- [x] ลบ `backend/tests/test_linear_slicer.py`, `backend/tests/test_maker_slicer.py`
- [x] ลบ `backend/tools/linear_slice.py`, `backend/tools/maker_slice.py`
- [x] ตัด router `/execute` ที่ซ้ำใน `backend/app/execution/__init__.py` (เก็บ `TradeRequest` + iceberg/rate-limiter exports)
- [x] verify: import สะอาด, executor/cost_model tests 21 passed

**ผลลัพธ์:** execution เหลือเส้นทางเดียว → `routes.py /execute` → `ArbitrageExecutor` → `maker_engine` + `LighterClient`; Bybit client เหลือตัวเดียว (`collectors/bybit_client.py`)

---

## 🔴 Phase 0 — กู้ build frontend (CRITICAL, ทำก่อน)

> ปัญหา: มีโค้ดต่างโปรเจค "deritrade" ปนใน frontend ที่ import `node:fs`, `ioredis`, `next`, `@deritrade/db`
> ทำให้ `tsc && vite build` พัง และยังไม่ได้ commit (อยู่ใน git `??`)
> ยืนยันแล้ว: `App.tsx` ไม่ได้ import หน้า campaign/api-keys เลย → เป็น dead code ทั้งหมด

### TASK-0.1 — ลบไฟล์ scratch ที่ root/backend/frontend
- [x] **status** — ✅ verified (ไฟล์ทั้ง 5 หายแล้ว, commit ec136c5)
- **ลบ:**
  - `frontend/extract.mjs`
  - `frontend/extract_template.mjs`
  - `frontend/extracted_app.jsx`
  - `frontend/extracted_design.jsx`
  - `backend/mock_trades.py`
- **Acceptance:** ไฟล์เหล่านี้หายจาก working tree
- **Verify:** `git status --short` ไม่แสดงไฟล์เหล่านี้แล้ว
- **Commit:** `chore: remove scratch/extraction files`

### TASK-0.2 — ลบโค้ด deritrade ที่ไม่ได้ใช้ออกจาก frontend
- [x] **status** — ✅ verified (campaign/api-keys ลบแล้ว, lib/ เหลือแค่ cn.ts+format.ts ที่ chrome ใช้, ไม่มี import @deritrade/ioredis/next/node เหลือ, commit 02a6778)
- **เงื่อนไขก่อนเริ่ม:** ยืนยันว่าไม่มีอะไรใน `App.tsx` หรือหน้าที่ใช้งานจริง import จากโฟลเดอร์เหล่านี้ (grep `@/lib/`, `components/campaign`, `components/api-keys` ในไฟล์ที่ App.tsx อ้างถึง)
- **ลบทั้งโฟลเดอร์:**
  - `frontend/src/lib/` (ยกเว้นไฟล์ที่ component live ใช้ — ดู note ด้านล่าง)
  - `frontend/src/components/campaign/`
  - `frontend/src/components/api-keys/`
- **⚠️ NOTE สำคัญ — ก่อนลบ `lib/` ทั้งหมด ต้องตรวจ:** มีบางไฟล์ใน `lib/` ที่ component ที่ใช้งานจริงต้องใช้ เช่น:
  - `lib/cn.ts` (ใช้โดย `components/chrome/*`)
  - `lib/format.ts` (ใช้โดย `chrome/TopNav.tsx`)
  - ไฟล์ใดที่ chrome/ หรือ overview/ หรือหน้า live อื่นๆ import → **ห้ามลบ ให้ย้ายไปไว้ที่ปลอดภัย**
  - วิธี: grep หา import ของแต่ละไฟล์ใน `lib/` จากเฉพาะ component ที่อยู่ในเส้นทาง render จริง (App.tsx → chrome, overview, health, history, portfolio, trades, settings, common, symbol, auth)
  - ลบเฉพาะไฟล์ที่ "ไม่มี live component ใช้" (botSpawner, redis, accountExchangeClient, campaignRadar, campaignDiscovery, multiAccount, userSettings, withdrawalValidation, adminAccess, bots, botLifecycle, env, sourceRegistry, strategyOptions, symbols (เวอร์ชัน deritrade), currentUser, auth (เวอร์ชัน deritrade), hash, dedupe, rateLimit, tokenPrices, types/campaignTypes/time ที่ผูกกับ campaign ฯลฯ)
- **ลบ test ที่ผูกกับโค้ด deritrade:**
  - `frontend/src/lib/__tests__/` ทั้งโฟลเดอร์ (ถ้ายังเหลือ)
- **Acceptance:** ไม่มีไฟล์ใน frontend ที่ import `@deritrade/*`, `ioredis`, `next/*`, `node:*` เหลืออยู่
- **Verify:**
  ```
  cd frontend
  npx grep-like: ค้นหาว่าไม่มี import "@deritrade", "ioredis", "next/", "node:" เหลือใน src/
  ```
  (หรือใช้ ripgrep: `rg "@deritrade|ioredis|next/|node:" src/` ต้องได้ 0 matches ในไฟล์ที่เหลือ)
- **Commit:** `chore: remove orphaned deritrade code from frontend`

### TASK-0.3 — ทำให้ `npm run build` ผ่าน
- [x] **status** — ✅ verified (npm run build exit 0, dist/ สร้างใน 8.73s, commit c12c1b3)
- **depends on:** TASK-0.2
- **ทำ:**
  - รัน `cd frontend && npm run build`
  - แก้ทุก type error / import error ที่เหลือ (ควรเหลือน้อยมากหลังลบ deritrade)
  - ถ้ามี component live ที่ยัง import ไฟล์ที่เผลอลบ → ย้าย/สร้างไฟล์ helper เล็กๆ กลับมา (เช่น `cn.ts`, `format.ts`)
- **Acceptance:** `npm run build` exit 0, ได้ `dist/`
- **Verify:** `cd frontend && npm run build` → ต้องเห็น "built in ..." ไม่มี error
- **Commit:** `fix: restore clean frontend build`

### TASK-0.4 — commit งานที่ค้างใน git ที่ตั้งใจเก็บ
- [x] **status** — ✅ verified (commit 87e9aaf; เหลือ backend dead-code deletions ยังไม่ commit — ดู note ล่าง)
- **depends on:** TASK-0.3
- **ทำ:** stage + commit เฉพาะไฟล์ที่เป็นของจริง (chrome/, settings forms, auth, public/, ฯลฯ) ที่ผ่าน build แล้ว
- **Acceptance:** `git status` สะอาด (เหลือเฉพาะของที่ตั้งใจไม่ commit)
- **Verify:** `git status --short`
- **Commit:** `feat: institutional UI shell + settings forms` (หรือแยกตามกลุ่มที่เหมาะสม)

---

## 🟠 Phase 1 (rest) — ปิด dead config ใน executor

### TASK-1.1 — ลบ/ทำ `maker_allow_market_fallback` ให้มีผลจริง หรือ document ว่า arb เป็น maker-only เสมอ
- [ ] **status**
- **ปัญหา:** `ArbitrageExecutor` บังคับ `force_maker_only=self.maker_only` (default True) → `maker_allow_market_fallback` ในเส้นทาง arb เป็น dead config (ใช้แค่ใน `/execute/maker_test`)
- **ตัวเลือก (เลือก 1):**
  - (A) เพิ่ม comment ใน `settings.py` ระบุชัดว่า `maker_allow_market_fallback` ใช้เฉพาะ maker_test ไม่ใช้ใน arb (เพราะ arb คุมด้วย `arb_maker_only`)
  - (B) ทำให้ `arb_maker_only=False` แล้วเคารพ `maker_allow_market_fallback` ได้จริง (ถ้าต้องการ market fallback ใน arb)
- **แนะนำ:** (A) — ปลอดภัยกว่า ไม่เปลี่ยน behavior การเทรด
- **Files:** `backend/app/config/settings.py`, `backend/app/services/executor.py` (เพิ่ม comment)
- **Acceptance:** อ่านโค้ดแล้วเข้าใจชัดว่า flag ไหนคุมอะไร ไม่มี config กำกวม
- **Verify:** `python -c "import app.main"` + `python -m pytest tests/test_executor.py -q`
- **Commit:** `docs: clarify maker-only arb config`

---

## 🟡 Phase 2 — Type safety frontend

### TASK-2.1 — นิยาม type สำหรับ API response ใน `types/api.ts`
- [ ] **status**
- **ทำ:** เติม interface สำหรับ: `PricesResponse`, `SpreadPoint`, `FundingResponse`, `PositionsResponse`, `TradeRecord`, `PortfolioResponse`, `HealthResponse`, `ConfigResponse`
- **อ้างอิง shape จริงจาก:** `backend/app/api/routes.py` (response ของแต่ละ endpoint) + `backend/app/models/`
- **Files:** `frontend/src/types/api.ts`
- **Acceptance:** type ครอบทุก endpoint ที่ `api.ts` เรียก
- **Verify:** `cd frontend && npx tsc --noEmit`
- **Commit:** `feat: add typed API response models`

### TASK-2.2 — เปลี่ยน `api.ts` จาก `any` เป็น generic ที่ถูกต้อง
- [ ] **status**
- **depends on:** TASK-2.1
- **ทำ:** แทน `fetchJSON<any>` / `postJSON<any>` ด้วย type จาก TASK-2.1
- **Files:** `frontend/src/services/api.ts`
- **Acceptance:** ไม่มี `<any>` เหลือใน `api.ts`
- **Verify:** `cd frontend && npm run build`
- **Commit:** `refactor: type the API client`

### TASK-2.3 — แก้ `useState<any>` ใน `App.tsx` + components ที่รับ data
- [ ] **status**
- **depends on:** TASK-2.2
- **ทำ:** `wsData`, `priceData` ใช้ type จริง; ปรับ prop type ของ `OverviewPage` ฯลฯ ตามจำเป็น
- **Files:** `frontend/src/App.tsx` + components ที่ consume `data`
- **Acceptance:** ลด `any` ในเส้นทาง data flow หลัก
- **Verify:** `cd frontend && npm run build`
- **Commit:** `refactor: type WS/price data flow`

### TASK-2.4 (optional) — เปิด `noUnusedLocals` / `noUnusedParameters` กลับ
- [ ] **status**
- **depends on:** Phase 0 เสร็จ (dead code หมดแล้ว)
- **Files:** `frontend/tsconfig.json`
- **Acceptance:** เปิด flag แล้ว `npm run build` ยังผ่าน
- **Verify:** `cd frontend && npm run build`
- **Commit:** `chore: enable stricter tsconfig`

---

## 🟡 Phase 3 — ต่อฟีเจอร์ค้าง + จัดโครงสร้าง

### TASK-3.1 — ต่อ Settings page เข้า routing (เลิก placeholder)
- [ ] **status**
- **ปัญหา:** `App.tsx` มี `page === 'settings'` แสดง "Settings Page placeholder" แต่มี `SettingsPage`, `RiskSettingsForm`, `TelegramSettingsForm`, `SettingsDefaultsForm` ครบแล้ว
- **ทำ:** lazy-import `SettingsPage` แล้ว render แทน placeholder; เพิ่ม `'settings'` เข้า type `Page`
- **Files:** `frontend/src/App.tsx`
- **Acceptance:** กดเมนู Settings แล้วเห็นฟอร์มจริง
- **Verify:** `cd frontend && npm run build` + เปิดดูหน้า settings
- **Commit:** `feat: wire settings page into navigation`

### TASK-3.2 — ยืนยัน auth flow ทำงาน (login → เข้าระบบได้)
- [ ] **status**
- **ปัญหา:** `App.tsx` เปิด `if (!isAuthenticated) return <LoginPage/>` แล้ว — ต้องเช็คว่า `AuthContext` + `LoginPage` ทำงานครบ (login, persist token, logout)
- **ทำ:** ทดสอบ flow; ถ้า single-user หลัง Cloudflare ไม่ต้องการ auth → ตัดสินใจปิดและลบให้สะอาด
- **Files:** `frontend/src/components/auth/AuthContext.tsx`, `LoginPage.tsx`, `App.tsx`
- **Acceptance:** login ได้จริง หรือ ตัด auth ออกอย่างสะอาด (ไม่มี import ค้าง)
- **Verify:** `cd frontend && npm run build` + ทดสอบ login
- **Commit:** `fix: verify/finalize auth flow`

### TASK-3.3 — รวม data directory ให้เหลือที่เดียว
- [ ] **status**
- **ปัญหา:** มี `data/` (root) และ `backend/data/` — `settings.db_path = ./data/spread_dashboard.db` (relative ต่อ cwd ของ backend)
- **ทำ:** ยืนยันว่า DB จริงอยู่ `backend/data/`; ลบ/gitignore `data/` ที่ root ถ้าไม่ใช้; อัปเดต DEPLOY.md ให้ตรง
- **Files:** `.gitignore`, `README.md`/`DEPLOY.md`, (อาจ) `backend/app/config/settings.py`
- **Acceptance:** มี data dir ที่เดียวชัดเจน ไม่สับสน
- **Verify:** start backend แล้ว DB ถูกสร้าง/อ่านจากที่เดียว
- **Commit:** `chore: consolidate data directory`

### TASK-3.4 — จัดการ `funding_snapshots` table ที่ไม่มี producer
- [ ] **status**
- **ปัญหา:** ตาราง `funding_snapshots` ถูก CREATE แต่ไม่เคยมีใคร INSERT (`/api/v1/funding` ดึง live ทุกครั้ง)
- **ตัวเลือก (เลือก 1):**
  - (A) ลบ table ออกจาก `init_db()` schema (ลด schema ที่ไม่ใช้)
  - (B) ต่อ producer ให้เขียน snapshot จริง (ถ้าต้องการ history funding)
- **แนะนำ:** (A) เว้นแต่ต้องการ funding history
- **Files:** `backend/app/storage/database.py`
- **Acceptance:** schema ตรงกับการใช้งานจริง
- **Verify:** `python -c "import app.main"` + start backend ไม่ error
- **Commit:** `chore: drop unused funding_snapshots table` (หรือ `feat: persist funding snapshots`)

---

## 🟢 Phase 4 — เอกสาร + DX

### TASK-4.1 — อัปเดต DESIGN.md / README ให้ตรงกับโค้ดจริง
- [ ] **status**
- **ทำ:** แก้ base URL ใน DESIGN.md (`api.bybit.com` → `api.bytick.com`), อัปเดตสถานะ checkpoint, ระบุว่า execution ใช้ sequential Bybit-first
- **Files:** `docs/DESIGN.md`, `README.md`
- **Acceptance:** เอกสารตรงกับ implementation
- **Commit:** `docs: sync design docs with implementation`

### TASK-4.2 — archive `plan.md` (stability plan ที่ทำเสร็จแล้ว)
- [ ] **status**
- **ทำ:** ย้าย `plan.md` → `docs/archive/stability-plan-DONE.md` หรือเพิ่มหมายเหตุว่าเสร็จแล้ว
- **Files:** `plan.md`
- **Commit:** `docs: archive completed stability plan`

### TASK-4.3 — เพิ่ม linter/formatter
- [ ] **status**
- **ทำ:**
  - backend: เพิ่ม `ruff` (lint + format) ลง `requirements.txt` + config
  - frontend: เพิ่ม `eslint` + `prettier` config
- **Files:** `backend/requirements.txt`, `backend/pyproject.toml` (ใหม่), `frontend/package.json`, `.eslintrc`/`prettier` config
- **Acceptance:** `ruff check backend/app` + `npx eslint frontend/src` รันได้
- **Commit:** `chore: add linters and formatters`

### TASK-4.4 (optional) — pre-commit hook กัน scratch file / build พัง
- [ ] **status**
- **ทำ:** เพิ่ม pre-commit ที่รัน `tsc --noEmit` (frontend) + `ruff` (backend) ก่อน commit
- **Commit:** `chore: add pre-commit hooks`

---

## Verification Cheat-Sheet (ให้ Kiro เช็คหลัง Codex ทำแต่ละ task)

| ขอบเขต | คำสั่ง |
|--------|--------|
| Backend import | `cd backend && python -c "import app.main"` |
| Backend tests (เร็ว, ไม่ต่อ net) | `cd backend && python -m pytest tests/test_executor.py tests/test_cost_model.py tests/test_percentiles.py tests/test_portfolio.py -q` |
| Frontend type-check | `cd frontend && npx tsc --noEmit` |
| Frontend build | `cd frontend && npm run build` |
| งานค้าง git | `git status --short` |
| ไม่มีโค้ด deritrade เหลือ | `rg "@deritrade\|ioredis\|next/\|node:" frontend/src` → 0 matches |

> ⚠️ อย่ารัน `pytest` ทั้ง suite แบบไม่มี timeout — บาง test ต่อ network จริง (lighter/bybit) แล้วค้าง ให้รันเฉพาะไฟล์ที่ไม่ touch network
