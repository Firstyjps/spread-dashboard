# Stability Optimization Plan

จากการวิเคราะห์ Codebase ทั้งหมด พบ 33 จุดที่ต้องปรับปรุง จัดกลุ่มเป็น 6 Phase ตามลำดับ Impact สูง → ต่ำ

---

## Phase 1: Database — Connection Pool + WAL Mode (CRITICAL)

**ปัญหา:** ทุก DB operation เปิด connection ใหม่ทุกครั้ง (insert_tick ถูกเรียก 2x/symbol ทุก 2 วินาที) — ไม่มี WAL mode ทำให้ read/write ชนกัน → "database is malformed"

**ไฟล์:** `backend/app/storage/database.py`

**แก้:**
- สร้าง Singleton connection pool (1 connection + WAL mode + busy_timeout=5000ms)
- `init_db()` → เปิด WAL, journal_size_limit, synchronous=NORMAL
- ทุกฟังก์ชัน (`insert_tick`, `insert_spread`, `get_recent_spreads` ฯลฯ) ใช้ connection จาก pool แทน `aiosqlite.connect()` ใหม่ทุกครั้ง
- เพิ่ม `close_db()` สำหรับ shutdown
- Batch insert: รวม insert_tick + insert_spread ในรอบเดียวแทนแยกคนละ commit

---

## Phase 2: WebSocket Heartbeat + Smart Reconnect (CRITICAL)

**ปัญหา:** Frontend reconnect ทุก 3 วิ ไม่มี limit, ไม่มี backoff, ไม่มี heartbeat → connection ตายแบบเงียบ แสดงข้อมูลเก่า

**ไฟล์:** `frontend/src/hooks/useWebSocket.ts`

**แก้:**
- เพิ่ม Heartbeat: ส่ง "ping" ทุก 15 วิ, ถ้าไม่ได้ "pong" ภายใน 5 วิ → ถือว่า dead → reconnect
- Exponential backoff reconnect: 1s → 2s → 4s → 8s → max 30s
- Max retry counter (30 ครั้ง) แล้ว stop + แสดง error
- Reset retry counter เมื่อเชื่อมต่อสำเร็จ
- เพิ่ม `connectionState`: 'connecting' | 'connected' | 'reconnecting' | 'disconnected'

---

## Phase 3: Poll Loop Resilience + Task Supervision (HIGH)

**ปัญหา:** `asyncio.create_task(poll_loop())` ไม่มีคนดูแล — ถ้า crash ก็จบ ไม่มี restart, ไม่มี timeout ต่อ cycle, sleep ไม่คำนวณเวลาที่เหลือ

**ไฟล์:** `backend/app/main.py`

**แก้:**
- เพิ่ม Task Supervisor: ถ้า poll_loop crash → log + auto-restart หลัง 2 วิ
- `asyncio.wait_for(asyncio.gather(*tasks), timeout=10)` เพื่อป้องกัน hang
- คำนวณ sleep ที่เหลือ: `elapsed = time.time() - t0; sleep = max(0.1, interval - elapsed)`
- เพิ่ม per-symbol error isolation: ถ้า symbol หนึ่ง error ไม่กระทบ symbol อื่น
- เพิ่ม consecutive error counter → log warning ถ้า error ติดกัน 5 ครั้ง

---

## Phase 4: HTTP Client Session Stability (HIGH)

**ปัญหา:**
1. `LighterClient.get_position()` สร้าง `aiohttp.ClientSession()` ใหม่ทุกครั้ง
2. `BybitClient` ทุก method ใช้ `asyncio.to_thread()` ไม่มี timeout → thread hang ได้
3. Lighter rate limit state ไม่ thread-safe

**ไฟล์:**
- `backend/app/collectors/lighter_client.py` — ใช้ persistent session
- `backend/app/collectors/bybit_client.py` — ครอบ `asyncio.wait_for()` timeout 10s
- `backend/app/collectors/lighter_collector.py` — เพิ่ม asyncio.Lock สำหรับ rate limit state

**แก้ lighter_client.py:**
- `get_position()` ใช้ persistent `aiohttp.ClientSession` แทนสร้างใหม่
- เพิ่ม `timeout=aiohttp.ClientTimeout(total=10)` ให้ชัดเจน

**แก้ bybit_client.py:**
- ทุก method: ครอบ `asyncio.wait_for(..., timeout=10)` รอบ `asyncio.to_thread()`
- ป้องกัน thread pool hang → ถ้า timeout → raise TimeoutError

**แก้ lighter_collector.py:**
- เพิ่ม `_rate_lock = asyncio.Lock()` ครอบ `_rate_limited_until` / `_429_count`
- `_refresh_funding_cache()` → update `_funding_cache_ts` even on error (ป้องกัน stale forever)

---

## Phase 5: Executor Resource Management (MEDIUM)

**ปัญหา:** `ArbitrageExecutor` สร้าง client ใหม่ทุกครั้ง, `_cleanup()` เรียกเฉพาะ finally ของ `run_arb()`, route อื่นไม่ cleanup

**ไฟล์:** `backend/app/services/executor.py` + `backend/app/api/routes.py`

**แก้:**
- ทำ `ArbitrageExecutor` เป็น async context manager (`__aenter__`/`__aexit__`)
- routes.py ใช้ `async with ArbitrageExecutor(settings) as executor:` ทุก endpoint
- Maker engine: ครอบ `cancel_order()` ด้วย timeout 5s ป้องกัน hang ตอน cleanup

---

## Phase 6: Spread Engine + Minor Fixes (MEDIUM)

**ปัญหา:**
- `compute_spread()` และ `get_all_current_data()` อ่าน `latest_ticks` ไม่ผ่าน lock
- Frontend `api.ts` ไม่มี timeout

**ไฟล์:**
- `backend/app/analytics/spread_engine.py` — ทำ `compute_spread()` + `get_all_current_data()` ให้ thread-safe
- `frontend/src/services/api.ts` — เพิ่ม fetch timeout (AbortController 15s)

**แก้ spread_engine.py:**
- `get_latest_tick()` → ใช้ copy ของ dict แทนอ่านตรง
- `compute_spread()` → อ่านจาก snapshot
- `get_all_current_data()` → ใช้ `dict(latest_ticks)` snapshot ก่อนวน loop

**แก้ api.ts:**
- เพิ่ม AbortController + setTimeout 15s ใน `fetchJSON` / `postJSON`

---

## Summary

| Phase | ไฟล์ | Impact | ความซับซ้อน |
|-------|------|--------|-------------|
| 1. DB Pool + WAL | database.py | CRITICAL | กลาง |
| 2. WS Heartbeat | useWebSocket.ts | CRITICAL | กลาง |
| 3. Poll Loop | main.py | HIGH | ต่ำ |
| 4. HTTP Clients | lighter_client/bybit_client/lighter_collector | HIGH | กลาง |
| 5. Executor | executor.py + routes.py | MEDIUM | ต่ำ |
| 6. Spread + API | spread_engine.py + api.ts | MEDIUM | ต่ำ |

แก้ทั้งหมด 9 ไฟล์ — ไม่เปลี่ยน API, ไม่เปลี่ยน WS protocol, backward compatible 100%
