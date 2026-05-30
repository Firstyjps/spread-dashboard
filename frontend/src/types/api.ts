/**
 * Shared TypeScript interfaces for API data.
 *
 * These types mirror the backend's data models and are used across
 * frontend components to replace `any` with compile-time type safety.
 */

/** A single spread metric row from the database. */
export interface SpreadRow {
  id: number;
  ts: number;
  symbol: string;
  bybit_mid: number;
  lighter_mid: number;
  bybit_bid: number;
  bybit_ask: number;
  lighter_bid: number;
  lighter_ask: number;
  exchange_spread_mid: number;
  long_spread: number;
  short_spread: number;
  bid_ask_spread_bybit: number;
  bid_ask_spread_lighter: number;
  basis_bybit: number | null;
  basis_bybit_bps: number | null;
  funding_diff: number | null;
  received_at: number;
}

/** An alert from the alerts table. */
export interface Alert {
  id: number;
  ts: number;
  alert_type: string;
  symbol: string | null;
  severity: string;
  message: string;
  value: number | null;
  threshold: number | null;
  acknowledged: number;
}

/** Persisted execution journal row. */
export interface TradeRecord {
  id: number;
  ts: number;
  symbol: string;
  strategy: string;
  side: string;
  qty_requested: number;
  qty_filled: number;
  bybit_side: string;
  bybit_fill_price: number | null;
  bybit_fee: number | null;
  lighter_fill_price: number | null;
  lighter_fee: number | null;
  spread_bps_at_entry: number | null;
  net_pnl_usd: number | null;
  duration_ms: number | null;
  status: string;
  detail: string | null;
}

/** Tick data for a single exchange feed. */
export interface TickData {
  mid: number;
  bid: number;
  ask: number;
  bid_size?: number;
  ask_size?: number;
  last_price?: number;
  mark_price?: number;
  index_price?: number;
  volume_24h?: number;
  open_interest?: number;
  received_at: number;
}

/** Per-symbol data from the WebSocket update/snapshot. */
export interface SymbolData {
  bybit?: TickData;
  lighter?: TickData;
  spread?: {
    exchange_spread_mid: number;
    long_spread: number;
    short_spread: number;
    bid_ask_spread_bybit: number;
    bid_ask_spread_lighter: number;
    basis_bybit?: number | null;
    basis_bybit_bps?: number | null;
    funding_diff?: number | null;
  };
  zscore?: number | null;
  imbalance_bybit?: number | null;
  imbalance_lighter?: number | null;
  latency_bybit?: number | null;
  latency_lighter?: number | null;
  net_pnl_bps?: number | null;
}

/** Map of symbol → data, as returned by WebSocket and REST endpoints. */
export type SymbolDataMap = Record<string, SymbolData>;

/** Recharts-compatible data point for the spread chart. */
export interface ChartPoint {
  time: string;
  mid_spread: number;
  long_spread: number;
  short_spread: number;
}

// ─── API Response Types ─────────────────────────────────────────

/** GET /api/v1/health */
export interface ExchangeHealth {
  status: string;
  latency_ms?: number;
  error?: string;
}

export interface HealthResponse {
  status: string;
  exchanges: {
    bybit: ExchangeHealth;
    lighter: ExchangeHealth;
  };
  symbols: string[];
}

/** GET /api/v1/prices — returns SymbolDataMap directly */
export type PricesResponse = SymbolDataMap;

/** GET /api/v1/funding */
export interface FundingEntry {
  ts: number;
  exchange: string;
  symbol: string;
  funding_rate: number;
  predicted_rate: number | null;
  next_funding_time: number | null;
  funding_interval_hours: number | null;
  annualized_rate: number | null;
}

export type FundingResponse = Record<string, {
  bybit: FundingEntry | null;
  lighter: FundingEntry | null;
  funding_diff: number | null;
}>;

/** GET /api/v1/spreads */
export interface SpreadsResponse {
  symbol: string;
  current: SpreadRow | null;
  zscore: number | null;
  net_pnl_bps: number | null;
  cost_breakdown: Record<string, number> | null;
  history: SpreadRow[];
  count: number;
  stats: {
    n: number;
    mean: number | null;
    std: number | null;
    p10: number | null;
    p50: number | null;
    p90: number | null;
    min: number | null;
    max: number | null;
  };
}

/** GET /api/v1/spreads/history */
export interface SpreadsHistoryResponse {
  symbol: string;
  days: number;
  history: SpreadHistoryPoint[];
  count: number;
  stats: SpreadsResponse['stats'];
}

/** Slim spread point returned by /spreads/history (only 4 columns). */
export interface SpreadHistoryPoint {
  ts: number;
  exchange_spread_mid: number;
  long_spread: number;
  short_spread: number;
}

/** GET /api/v1/config */
export interface ConfigResponse {
  symbols: string[];
  poll_interval_ms: number;
  spread_alert_bps: number;
  stale_feed_timeout_s: number;
  latency_warning_ms: number;
}

/** GET /api/v1/portfolio */
export interface PositionEntry {
  exchange: string;
  symbol: string;
  side: string;
  amount: number;
  entry_price: number;
  mark_price?: number;
  unrealised_pnl?: number;
  leverage?: number;
}

export interface PortfolioResponse {
  positions: PositionEntry[];
  total_unrealised_pnl?: number;
}

/** POST /api/v1/execute response */
export interface ExecuteResponse {
  status: string;
  detail: string;
  bybit?: Record<string, unknown>;
  lighter?: string;
  matched_qty?: string;
}

/** GET /api/v1/auto-hedge/status */
export interface AutoHedgeStatus {
  running: boolean;
  symbol: string | null;
  poll_interval_s: number | null;
  min_delta: number | null;
  last_check_ts: number | null;
  last_hedge_ts: number | null;
  hedge_count: number;
}

/** GET /api/v1/sl-tp/status */
export interface SlTpStatus {
  running: boolean;
  symbol: string | null;
  sl_delta: number | null;
  tp_delta: number | null;
  triggered: boolean;
  trigger_type: string | null;
  trigger_ts: number | null;
}

/** WebSocket message envelope */
export interface WsMessage {
  type: 'update' | 'snapshot' | 'pong';
  data?: SymbolDataMap;
  ts?: number;
}
