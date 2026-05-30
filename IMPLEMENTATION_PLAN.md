# Implementation Plan — Spread Dashboard Refactor & Cleanup

> เอกสารนี้เป็น execution plan สำหรับ refactor/cleanup ของโปรเจค
> อัปเดตล่าสุด: 30 พ.ค. 2026

**Status legend:** `[ ]` not started · `[x]` done

---

## Progress Summary

| Phase | หัวข้อ | สถานะ |
|-------|--------|-------|
| Phase 0 | กู้ build frontend (deritrade code + scratch files) | ✅ DONE |
| Phase 1 | เคลียร์ dead code execution layer + ปิด dead config | ✅ DONE |
| Phase 2 | Type safety frontend (เลิกใช้ `any`) | ✅ DONE |
| Phase 3 | ต่อฟีเจอร์ค้าง + จัดโครงสร้าง | ✅ DONE |
| Phase 4 | เอกสาร + DX (linter/CI) | ✅ DONE (partial — eslint/prettier frontend ยังไม่ได้เพิ่ม) |

---

## ✅ Phase 0 — DONE

- [x] TASK-0.1 — ลบไฟล์ scratch (commit `ec136c5`)
- [x] TASK-0.2 — ลบโค้ด deritrade จาก frontend (commit `02a6778`)
- [x] TASK-0.3 — กู้ frontend build ให้ผ่าน (commit `c12c1b3`)
- [x] TASK-0.4 — commit งานค้าง UI shell (commit `87e9aaf`)

---

## ✅ Phase 1 — DONE

- [x] ลบ dead execution modules: linear_limit_slicer, maker_slicer_linear, bybit_linear_client, exchanges/bybit_linear (commit `c02e91b`, -3,162 LOC)
- [x] ตัด router `/execute` ที่ซ้ำใน execution/__init__.py
- [x] TASK-1.1 — clarify maker-only arb config (commit `ee4694b`)

---

## ✅ Phase 2 — DONE

- [x] TASK-2.1 — นิยาม type สำหรับ API response ใน `types/api.ts`
- [x] TASK-2.2 — เปลี่ยน `api.ts` จาก `any` เป็น typed (ยกเว้น 4 endpoints ที่ component มี local type)
- [x] TASK-2.3 — แก้ `useState<any>` ใน App.tsx → `SymbolDataMap | null`
- (commit `c07e8ba`)

**Note:** endpoints ที่ยังเป็น `any`: health, portfolio, positions, execute, sl-tp, auto-hedge — เพราะ component เหล่านั้นมี local type definition ของตัวเองที่ไม่ตรงกับ backend response shape พอดี ถ้าจะแก้ต้อง refactor component ด้วย (scope ใหญ่กว่า)

---

## ✅ Phase 3 — DONE

- [x] TASK-3.1 — ต่อ Settings page เข้า routing (commit `8017fda`)
- [x] TASK-3.2 — ปิด auth gate เพราะเป็น single-user หลัง Cloudflare (commit `dcc9a6e`)
- [x] TASK-3.3 — consolidate data dir, ลบ root `data/`, เพิ่ม gitignore (commit `724bc39`)
- [x] TASK-3.4 — drop unused funding_snapshots table จาก schema (commit `724bc39`)

---

## ✅ Phase 4 — DONE (partial)

- [x] TASK-4.1 — อัปเดต DESIGN.md base URL (commit `dfd7677`)
- [x] TASK-4.2 — archive plan.md → docs/archive/ (commit `dfd7677`)
- [x] TASK-4.3 — เพิ่ม ruff linter config สำหรับ backend (commit `74ba146`)
- [ ] TASK-4.4 (optional) — pre-commit hook
- [ ] eslint/prettier สำหรับ frontend (optional)

---

## 🟢 Optional / Future Work

| หัวข้อ | รายละเอียด |
|--------|-----------|
| TASK-2.4 | เปิด `noUnusedLocals`/`noUnusedParameters` ใน tsconfig |
| eslint + prettier | เพิ่ม linter ฝั่ง frontend |
| pre-commit hook | รัน `tsc --noEmit` + `ruff` ก่อน commit |
| Refactor component types | ทำให้ PortfolioPage, HealthPage, ExecutionPanel ใช้ shared types แทน local `any` |
| Risk framework | เพิ่ม dry-run mode, position/notional limit ตาม DESIGN.md Section D.6 |

---

## Commit History (refactor session)

```
74ba146 chore: add ruff linter config for backend
dcc9a6e fix: disable auth gate (single-user behind Cloudflare)
8017fda feat: wire settings page into navigation
c07e8ba refactor: type API client and WS data flow (remove most any)
5dc61c4 docs: add implementation plan for ongoing refactor
dfd7677 docs: update DESIGN.md base URL, archive completed stability plan
724bc39 chore: consolidate data dir, drop unused funding_snapshots table
ee4694b docs: clarify maker-only arb config vs market fallback
c02e91b chore: remove dead execution/exchanges modules and duplicate /execute route
87e9aaf feat: institutional UI shell + settings forms
c12c1b3 fix: restore clean frontend build
02a6778 chore: remove orphaned deritrade code from frontend
ec136c5 chore: remove scratch/extraction files
```
