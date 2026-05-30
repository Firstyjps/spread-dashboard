# Monitor Page — Implementation Plan

> Multi-exchange, multi-pair spread monitor สำหรับ Gold perp arbitrage
> เป้าหมาย: ดู executable spread ของทุกคู่ exchange ในหน้าเดียว แบบ real-time
> อัปเดตล่าสุด: 30 พ.ค. 2026

---

## 1. Concept

### ปัญหาที่แก้
ตอนนี้ Overview page แสดง spread แค่ Bybit vs Lighter คู่เดียว และแสดง 3 เส้น (mid/long/short) ซึ่งซับซ้อนเกินไปสำหรับการ scan หา opportunity

### สิ่งที่ต้องการ
- หน้า **Monitor** ใหม่ แสดง chart เส้นเดียวต่อคู่ (executable spread in bps)
- รองรับหลาย pair พร้อมกัน
- เตรียม architecture รองรับ exchange ใหม่: **Binance**, **OKX**, **Hyperliquid**, **GRVT**, **Aster**

### Spread Formula — Lighter-Centric

เนื่องจากเรามอง Lighter เป็นหลัก:
- **"Buy"** = Buy Lighter (Long) + Short อีกฝั่ง
- **"Sell"** = Sell Lighter (Short) + Long อีกฝั่ง

**Buy Spread (ซื้อ Lighter, ขายอีกฝั่ง):**
```
buy_spread = (other_bid - lighter_ask) / lighter_ask × 10000 bps

ค่าบวก = กำไร (กดได้)
ค่าลบ  = ขาดทุน (อย่ากด)
```

**Sell Spread (ขาย Lighter, ซื้ออีกฝั่ง):**
```
sell_spread = (lighter_bid - other_ask) / other_ask × 10000 bps

ค่าบวก = กำไร (กดได้)
ค่าลบ  = ขาดทุน (อย่ากด)
```

**สำหรับคู่ที่ไม่มี Lighter (เช่น Binance↔Hyperliquid):**
```
spread = (bid_A - ask_B) / ask_B × 10000 bps
(แสดงทั้งสองทิศ: A→B และ B→A)
```

**Toggle options (frontend):**
| Mode | สูตร | ใช้เมื่อ |
|------|------|---------|
| Executable | ตามสูตรข้างบน | ดู opportunity จริง (default) |
| Mid | `(mid_A - mid_B) / mid_B` | ดูภาพรวม |
| Net | executable − fees_A − fees_B | ดูกำไรหลังหัก fee |

---

## 2. Exchange & Pair Matrix

### Exchanges ที่รองรับ (เรียงตาม priority)

| # | Exchange | Type | Gold Symbols | Leverage | Fee (maker/taker) | API | Priority |
|---|----------|------|-------------|----------|-------------------|-----|----------|
| 1 | **Bybit** | CEX | XAUTUSDT | 10x | 0.02%/0.055% | pybit (มีอยู่แล้ว) | ✅ มีแล้ว |
| 2 | **Lighter** | DEX | XAU | 25x | 0%/0% | มีอยู่แล้ว | ✅ มีแล้ว |
| 3 | **Binance** | CEX | XAUTUSDT | 50x | 0.02%/0.05% | REST+WS (fapi) | 🟢 Tier 1 |
| 4 | **Hyperliquid** | DEX | XAU | 50x | 0.015%/0.045% | REST+WS | 🟢 Tier 1 |
| 5 | **OKX** | CEX | XAUTUSDT | 50x | 0.02%/0.05% | REST+WS | 🟢 Tier 1 |
| 6 | **GRVT** | DEX | XAU, PAXG | 25x/50x | ~0%/0.05% | REST+WS | 🟡 Tier 2 |
| 7 | **Aster** | DEX | XAUUSDT, PAXGUSDT | 100x/50x | TBD | REST | 🟡 Tier 2 |
| 8 | **KuCoin** | CEX | XAUTUSDT | 50x | 0.02%/0.06% | REST+WS | 🟡 Tier 2 |
| 9 | **MEXC** | CEX | XAUTUSDT | 50x | 0%/0.01% (promo) | REST+WS | 🟡 Tier 2 |

### Pair Matrix — Tier 1 (ทำก่อน, spread กว้าง + volume ดี)

| # | Pair | ทิศ Buy (ซื้อ B ขาย A) | Spread โดยประมาณ | เหตุผล |
|---|------|----------------------|-----------------|--------|
| 1 | Lighter XAU ↔ Bybit XAUT | Buy Lighter, Short Bybit | ~60 bps | มีอยู่แล้ว, spread กว้าง |
| 2 | Lighter XAU ↔ Binance XAUT | Buy Lighter, Short Binance | ~60 bps | CEX ใหญ่สุด |
| 3 | Lighter XAU ↔ OKX XAUT | Buy Lighter, Short OKX | ~55 bps | CEX ใหม่ volume สูง |
| 4 | Hyperliquid XAU ↔ Bybit XAUT | Buy HL, Short Bybit | ~50 bps | DEX ใหญ่สุด |
| 5 | Hyperliquid XAU ↔ Binance XAUT | Buy HL, Short Binance | ~50 bps | DEX vs CEX |
| 6 | Lighter XAU ↔ Hyperliquid XAU | Buy Lighter, Short HL | ~5 bps | DEX vs DEX (แคบ) |

### Pair Matrix — Tier 2 (ทำทีหลัง)

| # | Pair | Spread โดยประมาณ | เหตุผล |
|---|------|-----------------|--------|
| 7 | GRVT XAU ↔ Bybit XAUT | ~55 bps | GRVT ราคาใกล้ Lighter |
| 8 | Aster XAU ↔ Bybit XAUT | ~55 bps | Aster ราคาใกล้ Lighter |
| 9 | GRVT XAU ↔ GRVT PAXG | ~26 bps | **intra-exchange** cross-asset |
| 10 | Aster XAU ↔ Aster PAXG | ~18 bps | intra-exchange cross-asset |
| 11 | Lighter XAU ↔ GRVT PAXG | ~30 bps | cross-exchange + cross-asset |
| 12 | KuCoin XAUT ↔ Lighter XAU | ~58 bps | CEX เพิ่มเติม |
| 13 | MEXC XAUT ↔ Lighter XAU | ~60 bps | zero-fee promo |

### ทำไม DEX ราคาสูงกว่า CEX?

จากข้อมูลจริง: Lighter/GRVT/Aster ราคา ~4,540+ vs Bybit/Binance ~4,516 (ต่างกัน ~$27 = ~60 bps)
สาเหตุ: DEX มี funding mechanism ต่างกัน, liquidity ต่ำกว่า, ไม่มี market maker ใหญ่ arbitrage ให้ราคาเท่ากัน → **โอกาสของเรา**

---

## 3. Architecture

### 3.1 Backend — Exchange Adapter Pattern

```
backend/app/collectors/
├── base.py                ← NEW: abstract ExchangeAdapter
├── registry.py            ← NEW: exchange registry + pair resolver
├── bybit_collector.py     ← existing (refactor to implement adapter)
├── lighter_collector.py   ← existing (refactor to implement adapter)
├── binance_collector.py   ← NEW (Tier 1)
├── hyperliquid_collector.py ← NEW (Tier 1)
├── okx_collector.py       ← NEW (Tier 1)
├── grvt_collector.py      ← NEW (Tier 2)
├── aster_collector.py     ← NEW (Tier 2)
└── bybit_client.py        ← existing (unchanged)
```

**ExchangeAdapter interface:**
```python
# backend/app/collectors/base.py
from abc import ABC, abstractmethod
from app.models import NormalizedTick

class ExchangeAdapter(ABC):
    name: str  # "bybit", "binance", "lighter", "hyperliquid", "okx", "grvt", "aster"
    
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
    
    @property
    def fee_maker(self) -> float:
        """Maker fee rate (e.g. 0.0002 = 0.02%)"""
        return 0.0
    
    @property
    def fee_taker(self) -> float:
        """Taker fee rate (e.g. 0.0005 = 0.05%)"""
        return 0.0
```

**Registry + Spread Calculator:**
```python
# backend/app/collectors/registry.py

class ExchangeRegistry:
    adapters: Dict[str, ExchangeAdapter] = {}
    
    def register(self, adapter: ExchangeAdapter):
        self.adapters[adapter.name] = adapter
    
    def get_pairs(self, group: str = "gold") -> List[PairConfig]:
        """Return all configured pairs for a group."""
        ...
    
    def compute_buy_spread(self, lighter_tick, other_tick) -> float:
        """Buy Lighter, Sell Other: (other_bid - lighter_ask) / lighter_ask × 10000"""
        if lighter_tick.ask <= 0:
            return 0.0
        return (other_tick.bid - lighter_tick.ask) / lighter_tick.ask * 10000
    
    def compute_sell_spread(self, lighter_tick, other_tick) -> float:
        """Sell Lighter, Buy Other: (lighter_bid - other_ask) / other_ask × 10000"""
        if other_tick.ask <= 0:
            return 0.0
        return (lighter_tick.bid - other_tick.ask) / other_tick.ask * 10000
    
    def compute_net_spread(self, spread_bps, fee_a, fee_b) -> float:
        """Spread after fees: spread - (fee_a + fee_b) in bps"""
        return spread_bps - (fee_a + fee_b) * 10000
```

### 3.2 New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/monitor/pairs` | รายการ pair ทั้งหมดที่ active |
| GET | `/api/v1/monitor/spreads?group=gold` | Current spread ทุกคู่ |
| GET | `/api/v1/monitor/history?pair=lighter:XAU-bybit:XAUTUSDT&minutes=60` | History ของคู่ที่เลือก |
| WS | `/ws` (extend) | เพิ่ม message type `monitor_update` |

**Response shape `/api/v1/monitor/spreads`:**
```json
{
  "group": "gold",
  "ts": 1717070400000,
  "pairs": [
    {
      "id": "lighter:XAU-bybit:XAUTUSDT",
      "exchange_a": "lighter",
      "symbol_a": "XAU",
      "price_a": { "bid": 4543.50, "ask": 4544.00, "mid": 4543.75 },
      "exchange_b": "bybit",
      "symbol_b": "XAUTUSDT",
      "price_b": { "bid": 4516.80, "ask": 4517.00, "mid": 4516.90 },
      "buy_spread_bps": -59.9,
      "sell_spread_bps": 58.7,
      "net_buy_bps": -59.9,
      "net_sell_bps": 57.6,
      "best_direction": "sell",
      "best_spread_bps": 58.7
    }
  ]
}
```

### 3.3 Frontend — Monitor Page

```
frontend/src/components/monitor/
├── MonitorPage.tsx        ← main page (grid of pair cards)
├── PairCard.tsx           ← single pair: label + spread + sparkline
├── SpreadMiniChart.tsx    ← lightweight single-line recharts
├── PairSelector.tsx       ← toggle which pairs to show
└── SpreadModeToggle.tsx   ← switch executable/mid/net
```

**UI Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  Monitor        [Executable ▾]  [Gold ▾]  [5m ▾]           │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────────────┐  ┌────────────────────┐            │
│  │ Lighter ↔ Bybit    │  │ Lighter ↔ Binance  │            │
│  │ XAU      XAUTUSDT  │  │ XAU      XAUTUSDT  │            │
│  │ SELL +58.7 bps  🟢 │  │ SELL +57.2 bps  🟢 │            │
│  │ [═══════════════]   │  │ [═══════════════]   │            │
│  └────────────────────┘  └────────────────────┘            │
│  ┌────────────────────┐  ┌────────────────────┐            │
│  │ Lighter ↔ OKX      │  │ Hyperliquid ↔ Bybit│            │
│  │ XAU      XAUTUSDT  │  │ XAU      XAUTUSDT  │            │
│  │ SELL +55.1 bps  🟢 │  │ SELL +50.3 bps  🟢 │            │
│  │ [═══════════════]   │  │ [═══════════════]   │            │
│  └────────────────────┘  └────────────────────┘            │
│  ┌────────────────────┐  ┌────────────────────┐            │
│  │ GRVT XAU ↔ PAXG   │  │ Lighter ↔ GRVT     │            │
│  │ intra-exchange      │  │ XAU      XAU       │            │
│  │ SELL +26.1 bps  🟡 │  │ BUY  +3.2 bps  🟡  │            │
│  │ [═══════════════]   │  │ [═══════════════]   │            │
│  └────────────────────┘  └────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

**Card features:**
- แสดง best direction (Buy/Sell) + spread bps
- สีเขียว = spread > 20 bps (opportunity), สีเหลือง = 5-20 bps, สีแดง = < 5 bps
- Mini sparkline chart เส้นเดียว (best spread ของคู่นั้น)
- Click → expand full chart

---

## 4. Implementation Tasks

### Phase A — Backend: Exchange Adapters + API (Codex)

```
TASK-M.1: สร้าง ExchangeAdapter base class + registry
  Files: backend/app/collectors/base.py, backend/app/collectors/registry.py
  Verify: python -c "from app.collectors.base import ExchangeAdapter; from app.collectors.registry import ExchangeRegistry"

TASK-M.2: Binance collector (Tier 1)
  Files: backend/app/collectors/binance_collector.py
  API: GET https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=XAUTUSDT
  Returns: { "symbol", "bidPrice", "bidQty", "askPrice", "askQty", "time" }
  WS: wss://fstream.binance.com/ws/xautusdt@bookTicker
  Verify: python -c "from app.collectors.binance_collector import BinanceCollector"

TASK-M.3: Hyperliquid collector (Tier 1)
  Files: backend/app/collectors/hyperliquid_collector.py
  API: POST https://api.hyperliquid.xyz/info (body: {"type": "l2Book", "coin": "XAU"})
  Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
  Fee: maker 0.015%, taker 0.045%
  Verify: python -c "from app.collectors.hyperliquid_collector import HyperliquidCollector"

TASK-M.4: OKX collector (Tier 1)
  Files: backend/app/collectors/okx_collector.py
  API: GET https://www.okx.com/api/v5/market/ticker?instId=XAUT-USDT-SWAP
  WS: wss://ws.okx.com:8443/ws/v5/public (subscribe: {"op":"subscribe","args":[{"channel":"tickers","instId":"XAUT-USDT-SWAP"}]})
  Fee: maker 0.02%, taker 0.05%
  Verify: python -c "from app.collectors.okx_collector import OkxCollector"

TASK-M.5: GRVT collector (Tier 2 — stub OK)
  Files: backend/app/collectors/grvt_collector.py
  API: https://trades.grvt.io (research needed)
  Docs: https://docs.grvt.io
  Symbols: XAU, PAXG
  Verify: python -c "from app.collectors.grvt_collector import GrvtCollector"

TASK-M.6: Aster collector (Tier 2 — stub OK)
  Files: backend/app/collectors/aster_collector.py
  API: https://www.asterdex.com (research needed)
  Symbols: XAUUSDT, PAXGUSDT
  Verify: python -c "from app.collectors.aster_collector import AsterCollector"

TASK-M.7: Monitor API endpoints + poll loop
  Files: backend/app/api/monitor_routes.py, backend/app/main.py (extend)
  Endpoints: /monitor/pairs, /monitor/spreads, /monitor/history
  WS: extend existing /ws with type "monitor_update"
  Verify: python -c "import app.main" + curl localhost:8000/api/v1/monitor/pairs
```

### Phase B — Frontend: Monitor Page (Antigravity)

```
TASK-M.8: MonitorPage + routing
  - สร้าง MonitorPage.tsx, เพิ่ม 'monitor' ใน App.tsx Page type
  - Lazy import + route
  - Verify: npm run build

TASK-M.9: PairCard + SpreadMiniChart
  - PairCard: pair name + best direction + bps + color coding
  - SpreadMiniChart: recharts LineChart เส้นเดียว
  - Verify: npm run build

TASK-M.10: SpreadModeToggle + PairSelector
  - Dropdown: Executable/Mid/Net
  - Toggle: เลือกคู่ที่จะแสดง
  - Verify: npm run build

TASK-M.11: Connect to API + WS
  - เพิ่ม api.monitorPairs(), api.monitorSpreads() ใน api.ts
  - Subscribe WS "monitor_update"
  - Verify: npm run build

TASK-M.12: เพิ่ม Monitor เข้า SideNav
  - Icon: BarChart3 หรือ Activity
  - Verify: npm run build
```

### Phase C — Config & Polish

```
TASK-M.13: Config (monitor_groups, fees per exchange)
TASK-M.14: Alert integration (Telegram when spread > threshold)
TASK-M.15: Timeframe selector (1m/5m/15m/1h/4h)
```

---

## 5. API Research Summary

### Binance Futures ✅
- Book ticker: `GET https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=XAUTUSDT`
- WS: `wss://fstream.binance.com/ws/xautusdt@bookTicker`
- Rate limit: 2400 req/min

### Hyperliquid ✅
- L2 Book: `POST https://api.hyperliquid.xyz/info` body `{"type":"l2Book","coin":"XAU"}`
- All mids: `POST https://api.hyperliquid.xyz/info` body `{"type":"allMids"}`
- WS: `wss://api.hyperliquid.xyz/ws` subscribe `{"method":"subscribe","subscription":{"type":"l2Book","coin":"XAU"}}`
- Fee: maker 0.015%, taker 0.045%
- Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api

### OKX ✅
- Ticker: `GET https://www.okx.com/api/v5/market/ticker?instId=XAUT-USDT-SWAP`
- Book: `GET https://www.okx.com/api/v5/market/books?instId=XAUT-USDT-SWAP&sz=1`
- WS: `wss://ws.okx.com:8443/ws/v5/public`
- Fee: maker 0.02%, taker 0.05%

### GRVT ⚠️ (ต้อง research เพิ่ม)
- Base: https://trades.grvt.io
- Docs: https://docs.grvt.io
- Markets: XAU (25x), PAXG (50x)

### Aster ⚠️ (ต้อง research เพิ่ม)
- Base: https://www.asterdex.com
- Markets: XAUUSDT (100x), PAXGUSDT (50x)

---

## 6. Execution Order

```
Tier 1 (ทำก่อน):
  Backend:  M.1 → M.2 (Binance) → M.3 (Hyperliquid) → M.4 (OKX) → M.7 (API+poll)
  Frontend: M.8 → M.9 → M.10 → M.11 → M.12

Tier 2 (ทำทีหลัง):
  Backend:  M.5 (GRVT) → M.6 (Aster)
  Config:   M.13 → M.14 → M.15

Backend กับ Frontend ทำ parallel ได้ (frontend mock data ก่อน)
```

---

## 7. Codex Prompt (Phase A)

```
อ่านไฟล์ MONITOR_PLAN.md ใน root ของโปรเจคนี้ทั้งหมด

ทำ Phase A Tier 1 (TASK-M.1 → M.4 → M.7) ตามลำดับ ข้าม M.5, M.6 ไปก่อน

กฎ:
- ทำตาม architecture ใน Section 3 อย่างเคร่งครัด
- ใช้ Lighter-centric spread formula (Section 1)
- ห้ามเปลี่ยน API path / WS protocol ที่มีอยู่เดิม (เพิ่มใหม่ได้)
- รัน Verify command ของแต่ละ task ให้ผ่านก่อนขึ้น task ถัดไป
- ถ้า task ไหน verify ไม่ผ่าน ให้หยุดแล้วรายงาน
- commit แยกต่อ task: "feat: [task description]"
- ทำเสร็จแล้วรัน: python -c "import app.main" ให้ผ่าน
- สรุปสิ่งที่ทำ + ผล verify ทุก task กลับมา

อย่ารัน pytest ทั้ง suite (บาง test ต่อ network แล้วค้าง)
```

## 8. Antigravity Prompt (Phase B)

```
อ่านไฟล์ MONITOR_PLAN.md ใน root ของโปรเจคนี้ทั้งหมด

ทำ Phase B ทั้งหมด (TASK-M.8 → M.12) ตามลำดับ

กฎ:
- ทำตาม UI layout ใน Section 3.3
- ใช้ recharts สำหรับ chart (มีอยู่แล้วใน dependencies)
- ใช้ Tailwind + component style เดียวกับ components/chrome/
- แต่ละ PairCard แสดง: best direction (Buy/Sell) + spread bps + สี (เขียว >20, เหลือง 5-20, แดง <5)
- Backend API ยังไม่พร้อม — ใช้ mock data ก่อน พร้อม TODO comment
- ห้ามแก้ไฟล์ใน backend/
- รัน npm run build ให้ผ่านหลังทำแต่ละ task
- commit แยกต่อ task
- สรุปสิ่งที่ทำ + ผล npm run build กลับมา
```
