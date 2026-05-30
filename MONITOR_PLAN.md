# Monitor Page — Implementation Plan

> Multi-exchange, multi-pair spread monitor สำหรับ Gold perp arbitrage
> เป้าหมาย: ดู executable spread ของทุกคู่ exchange ในหน้าเดียว แบบ real-time

---

## 1. Concept

### ปัญหาที่แก้
ตอนนี้ Overview page แสดง spread แค่ Bybit vs Lighter คู่เดียว และแสดง 3 เส้น (mid/long/short) ซึ่งซับซ้อนเกินไปสำหรับการ scan หา opportunity

### สิ่งที่ต้องการ
- หน้า **Monitor** ใหม่ แสดง chart เส้นเดียวต่อคู่ (executable spread in bps)
- รองรับหลาย pair พร้อมกัน (เช่น Bybit↔Lighter, Bybit↔Binance, Lighter↔GRVT ฯลฯ)
- เตรียม architecture รองรับ exchange ใหม่: **Binance**, **Aster**, **GRVT**

### Spread Formula (เส้นเดียว)

**Default: Executable Spread (bps)**
```
executable_spread = (bid_A - ask_B) / ask_B × 10000

โดย:
- A = exchange ที่จะขาย (ได้ bid)
- B = exchange ที่จะซื้อ (จ่าย ask)
- ค่าบวก = มี arb opportunity (ขาย A ซื้อ B ได้กำไร)
- ค่าลบ = ไม่มี opportunity
```

**Toggle options (frontend):**
| Mode | สูตร | ใช้เมื่อ |
|------|------|---------|
| Executable | `(bid_A - ask_B) / ask_B` | ดู opportunity จริง |
| Mid | `(mid_A - mid_B) / mid_B` | ดูภาพรวม |
| Net | executable − fees_A − fees_B | ดูกำไรหลังหัก fee |

---

## 2. Exchange & Pair Matrix

### Exchanges ที่รองรับ

| Exchange | Type | Gold Symbols | API |
|----------|------|-------------|-----|
| Bybit | CEX | XAUTUSDT | pybit (มีอยู่แล้ว) |
| Binance | CEX | XAUTUSDT | REST + WS |
| Lighter | DEX | XAU (= XAUUSDT) | มีอยู่แล้ว |
| GRVT | DEX | XAU, PAXG | REST + WS |
| Aster | DEX | XAUUSDT, PAXGUSDT | REST + WS |

### Pair Matrix (Gold)

ทุกคู่ที่เป็นไปได้ (directional — A sells, B buys):

```
Bybit XAUT  ↔  Lighter XAU
Bybit XAUT  ↔  Binance XAUT
Bybit XAUT  ↔  GRVT XAU
Bybit XAUT  ↔  GRVT PAXG
Bybit XAUT  ↔  Aster XAU
Bybit XAUT  ↔  Aster PAXG
Binance XAUT ↔  Lighter XAU
Binance XAUT ↔  GRVT XAU
Binance XAUT ↔  Aster XAU
Lighter XAU  ↔  GRVT XAU
Lighter XAU  ↔  Aster XAU
GRVT XAU    ↔  Aster XAU
... (+ reverse directions)
```

> Note: PAXG ≠ XAU ตรงๆ (PAXG = tokenized gold, XAU = gold index) แต่ราคาใกล้กันพอ arb ได้ ให้ user เลือกเปิด/ปิดคู่ cross-asset

---

## 3. Architecture

### 3.1 Backend — Exchange Adapter Pattern

```
backend/app/collectors/
├── base.py              ← NEW: abstract ExchangeAdapter
├── bybit_collector.py   ← existing (refactor to implement adapter)
├── lighter_collector.py ← existing (refactor to implement adapter)
├── binance_collector.py ← NEW
├── grvt_collector.py    ← NEW
├── aster_collector.py   ← NEW
└── registry.py          ← NEW: exchange registry + pair resolver
```

**ExchangeAdapter interface:**
```python
# backend/app/collectors/base.py
from abc import ABC, abstractmethod
from app.models import NormalizedTick

class ExchangeAdapter(ABC):
    name: str  # "bybit", "binance", "lighter", "grvt", "aster"
    
    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> NormalizedTick | None:
        """Fetch current bid/ask/mid for a symbol."""
        ...
    
    @abstractmethod
    async def health_check(self) -> dict:
        ...
    
    @abstractmethod
    async def close(self):
        ...
    
    @property
    @abstractmethod
    def supported_symbols(self) -> list[str]:
        """Return list of symbols this exchange supports."""
        ...
```

**Registry:**
```python
# backend/app/collectors/registry.py
from typing import Dict, List, Tuple

class ExchangeRegistry:
    adapters: Dict[str, ExchangeAdapter] = {}
    
    def register(self, adapter: ExchangeAdapter):
        self.adapters[adapter.name] = adapter
    
    def get_pairs(self, asset_group: str = "gold") -> List[Tuple[str, str, str, str]]:
        """Return all possible (exchange_a, symbol_a, exchange_b, symbol_b) pairs."""
        ...
    
    def compute_executable_spread(self, tick_a: NormalizedTick, tick_b: NormalizedTick) -> float:
        """(bid_a - ask_b) / ask_b in bps"""
        return (tick_a.bid - tick_b.ask) / tick_b.ask * 10000
```

### 3.2 Config — Symbol Groups

```python
# backend/app/config/settings.py (เพิ่ม)

# Monitor: asset groups for multi-exchange spread tracking
# Format: "GROUP_NAME:EXCHANGE:SYMBOL,EXCHANGE:SYMBOL,..."
monitor_groups: str = "gold:bybit:XAUTUSDT,binance:XAUTUSDT,lighter:XAUUSDT,grvt:XAU,grvt:PAXG,aster:XAUUSDT,aster:PAXGUSDT"
```

### 3.3 New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/monitor/pairs` | รายการ pair ทั้งหมดที่ active |
| GET | `/api/v1/monitor/spreads?group=gold` | Current executable spread ทุกคู่ |
| GET | `/api/v1/monitor/history?pair=bybit:XAUTUSDT-lighter:XAU&minutes=60` | Spread history ของคู่ที่เลือก |
| WS | `/ws` (extend existing) | เพิ่ม message type `monitor_update` |

**Response shape `/api/v1/monitor/spreads`:**
```json
{
  "group": "gold",
  "ts": 1717070400000,
  "pairs": [
    {
      "id": "bybit:XAUTUSDT-lighter:XAU",
      "exchange_a": "bybit",
      "symbol_a": "XAUTUSDT",
      "price_a": { "bid": 4516.80, "ask": 4517.00, "mid": 4516.90 },
      "exchange_b": "lighter",
      "symbol_b": "XAU",
      "price_b": { "bid": 4543.50, "ask": 4544.00, "mid": 4543.75 },
      "executable_spread_bps": -5.98,
      "mid_spread_bps": -5.94,
      "direction": "buy_a_sell_b"
    },
    ...
  ]
}
```

### 3.4 Frontend — Monitor Page

```
frontend/src/components/monitor/
├── MonitorPage.tsx        ← main page (grid of mini-charts)
├── PairCard.tsx           ← single pair: label + sparkline chart
├── SpreadMiniChart.tsx    ← lightweight single-line chart (recharts)
├── PairSelector.tsx       ← toggle which pairs to show
└── SpreadModeToggle.tsx   ← switch executable/mid/net
```

**UI Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  Monitor          [Executable ▾]  [Gold ▾]  [5m ▾]     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │ Bybit ↔ Lighter  │  │ Bybit ↔ Binance  │            │
│  │ XAUT    XAU      │  │ XAUT    XAUT     │            │
│  │ +27.3 bps        │  │ +0.8 bps         │            │
│  │ [═══════════════] │  │ [═══════════════] │            │
│  └──────────────────┘  └──────────────────┘            │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │ Bybit ↔ GRVT     │  │ Lighter ↔ GRVT   │            │
│  │ XAUT    XAU      │  │ XAU      XAU     │            │
│  │ +25.1 bps        │  │ -0.3 bps         │            │
│  │ [═══════════════] │  │ [═══════════════] │            │
│  └──────────────────┘  └──────────────────┘            │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │ Bybit ↔ Aster    │  │ Binance ↔ Lighter│            │
│  │ XAUT    XAU      │  │ XAUT     XAU     │            │
│  │ +24.8 bps        │  │ +26.5 bps        │            │
│  │ [═══════════════] │  │ [═══════════════] │            │
│  └──────────────────┘  └──────────────────┘            │
└─────────────────────────────────────────────────────────┘
```

**Features:**
- Grid layout responsive (2 col desktop, 1 col mobile)
- แต่ละ card แสดง: pair name, current spread (bps), mini sparkline chart (เส้นเดียว)
- สีเขียว = spread บวก (มี opportunity), สีแดง = spread ลบ
- Click card → expand เป็น full chart
- Dropdown เลือก mode: Executable / Mid / Net
- Dropdown เลือก timeframe: 1m / 5m / 15m / 1h / 4h

---

## 4. Implementation Tasks (สำหรับ Codex)

### Phase A — Backend: Exchange Adapter + Registry

```
TASK-M.1: สร้าง ExchangeAdapter base class
  - สร้าง backend/app/collectors/base.py
  - Define abstract interface: fetch_ticker, health_check, close, supported_symbols
  - Verify: python -c "from app.collectors.base import ExchangeAdapter"

TASK-M.2: สร้าง ExchangeRegistry + pair resolver
  - สร้าง backend/app/collectors/registry.py
  - Implement: register, get_pairs, compute_executable_spread
  - Config: parse monitor_groups from settings
  - Verify: python -c "from app.collectors.registry import ExchangeRegistry"

TASK-M.3: Binance collector
  - สร้าง backend/app/collectors/binance_collector.py
  - Implement ExchangeAdapter for Binance Futures
  - API: GET /fapi/v1/ticker/bookTicker?symbol=XAUTUSDT
  - Verify: python -c "from app.collectors.binance_collector import BinanceCollector"

TASK-M.4: GRVT collector
  - สร้าง backend/app/collectors/grvt_collector.py
  - Implement ExchangeAdapter for GRVT
  - API: ต้อง research GRVT API docs (REST + WS)
  - Verify: python -c "from app.collectors.grvt_collector import GrvtCollector"

TASK-M.5: Aster collector
  - สร้าง backend/app/collectors/aster_collector.py
  - Implement ExchangeAdapter for Aster DEX
  - API: ต้อง research Aster API docs
  - Verify: python -c "from app.collectors.aster_collector import AsterCollector"

TASK-M.6: Monitor API endpoints
  - สร้าง backend/app/api/monitor_routes.py
  - Implement: /monitor/pairs, /monitor/spreads, /monitor/history
  - Register router ใน main.py
  - Verify: python -c "import app.main" + curl /api/v1/monitor/pairs

TASK-M.7: Monitor poll loop
  - เพิ่ม monitor_poll_loop ใน main.py (แยกจาก poll_loop เดิม)
  - Poll ทุก exchange ใน registry ทุก 2s
  - Store spread data ใน memory (ring buffer) + optional SQLite
  - Extend WS broadcast: เพิ่ม type "monitor_update"
  - Verify: start backend, WS ส่ง monitor_update
```

### Phase B — Frontend: Monitor Page

```
TASK-M.8: สร้าง MonitorPage + routing
  - สร้าง frontend/src/components/monitor/MonitorPage.tsx
  - เพิ่ม 'monitor' เข้า Page type ใน App.tsx
  - Lazy import + route
  - Verify: npm run build

TASK-M.9: สร้าง PairCard + SpreadMiniChart
  - สร้าง PairCard.tsx: แสดง pair name + current bps + color
  - สร้าง SpreadMiniChart.tsx: recharts LineChart เส้นเดียว (lightweight)
  - Verify: npm run build

TASK-M.10: สร้าง SpreadModeToggle + PairSelector
  - SpreadModeToggle: dropdown เลือก executable/mid/net
  - PairSelector: toggle คู่ที่จะแสดง
  - Verify: npm run build

TASK-M.11: Connect to API + WS
  - เพิ่ม api.monitorPairs(), api.monitorSpreads() ใน api.ts
  - Subscribe WS type "monitor_update"
  - Wire data → PairCard grid
  - Verify: npm run build + ทดสอบกับ backend จริง

TASK-M.12: เพิ่ม Monitor เข้า SideNav
  - เพิ่มเมนู "Monitor" ใน SideNav.tsx
  - Icon: Activity หรือ BarChart3
  - Verify: npm run build
```

### Phase C — Config & Polish

```
TASK-M.13: เพิ่ม settings สำหรับ monitor
  - เพิ่ม monitor_groups, monitor_poll_interval_ms ใน settings.py
  - เพิ่ม .env.example
  - Verify: python -c "import app.main"

TASK-M.14: เพิ่ม fee config ต่อ exchange (สำหรับ Net mode)
  - Config: fee_rates per exchange (maker/taker)
  - ใช้ใน compute_net_spread
  - Verify: unit test

TASK-M.15: Alert integration
  - เพิ่ม alert threshold สำหรับ monitor pairs
  - ถ้า executable spread > threshold → Telegram alert
  - Verify: unit test
```

---

## 5. Execution Order (แนะนำ)

```
Phase A (backend):  M.1 → M.2 → M.3 → M.4 → M.5 → M.6 → M.7
Phase B (frontend): M.8 → M.9 → M.10 → M.11 → M.12
Phase C (config):   M.13 → M.14 → M.15

Phase A กับ B ทำ parallel ได้ (frontend mock data ก่อน)
```

---

## 6. Codex Prompt (copy-paste ได้เลย)

```
อ่านไฟล์ MONITOR_PLAN.md ใน root ของโปรเจคนี้

ทำเฉพาะ TASK-M.1 เท่านั้น ตามที่ระบุในไฟล์
- ทำตาม Acceptance criteria ให้ครบ
- ห้ามทำ task อื่นนอกเหนือจากที่สั่ง
- ห้ามเปลี่ยน REST API path หรือ WebSocket protocol ที่มีอยู่เดิม
- ทำเสร็จแล้วรัน Verify command ของ task นั้นให้ผ่านก่อน
- สรุปสิ่งที่แก้ไป + ผลของ Verify command กลับมา
```

เปลี่ยนเลข task (M.1 → M.2 → ...) ตามลำดับ

---

## 7. API Research Notes (สำหรับ Codex)

### Binance Futures
- Book ticker: `GET https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=XAUTUSDT`
- Returns: `{ "symbol", "bidPrice", "bidQty", "askPrice", "askQty", "time" }`
- WS: `wss://fstream.binance.com/ws/xautusdt@bookTicker`
- Rate limit: 2400 req/min (generous)

### GRVT
- Base: `https://trades.grvt.io` (ต้อง verify)
- Docs: https://docs.grvt.io
- Markets: XAU (25x), PAXG (50x)
- ต้อง research exact endpoint สำหรับ orderbook/ticker

### Aster (asterdex.com)
- Base: `https://www.asterdex.com` (ต้อง verify API base)
- Markets: XAUUSDT (100x), PAXGUSDT (50x)
- ต้อง research API docs

> ⚠️ สำหรับ GRVT และ Aster: ถ้า Codex หา API docs ไม่เจอ ให้สร้าง collector เป็น stub (raise NotImplementedError) แล้วใส่ TODO comment ไว้ ผมจะ research เพิ่มให้ทีหลัง
