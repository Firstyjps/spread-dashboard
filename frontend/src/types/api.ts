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

/** Monitor Types */
export interface MonitorPair {
  id: string;
  exchange_a: string;
  symbol_a: string;
  price_a: { bid: number; ask: number; mid: number };
  exchange_b: string;
  symbol_b: string;
  price_b: { bid: number; ask: number; mid: number };
  executable_spread_bps: number;
  mid_spread_bps: number;
  direction: string;
}

export interface MonitorSpreadsResponse {
  group: string;
  ts: number;
  pairs: MonitorPair[];
}

/** A single row from /monitor/history — mirrors the spreads payload plus ts. */
export interface MonitorHistoryRow {
  id?: string;
  ts: number;
  buy_spread_bps?: number;
  sell_spread_bps?: number;
  mid_spread_bps?: number;
  net_buy_bps?: number;
  net_sell_bps?: number;
  best_spread_bps?: number;
  executable_spread_bps?: number;
  [key: string]: unknown;
}

/** GET /api/v1/monitor/history */
export interface MonitorHistoryResponse {
  pair: string;
  minutes: number;
  timeframe: string;
  history: MonitorHistoryRow[];
  count: number;
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

export interface NormalizedBalance {
  exchange: string;
  currency: string;
  total_equity: number | null;
  available: number | null;
  used_margin: number | null;
  unrealized_pnl: number | null;
}

export interface NormalizedPosition {
  exchange: string;
  symbol: string;
  side: string;
  qty: number;
  entry_price: number | null;
  mark_price: number | null;
  unrealized_pnl: number | null;
  leverage: number | null;
  liq_price: number | null;
}

export interface ExchangeSnapshot {
  exchange: string;
  balances: NormalizedBalance[];
  positions: NormalizedPosition[];
  errors: string[];
}

export interface PortfolioData {
  snapshots: ExchangeSnapshot[];
  totals: {
    currency?: string;
    total_equity?: number;
    available?: number;
    used_margin?: number;
    unrealized_pnl?: number;
  };
}

export interface PortfolioHistoryRecord {
  id: number;
  ts: number;
  account: string;
  total_equity: number | null;
  available: number | null;
  used_margin: number | null;
  unrealized_pnl: number | null;
}

export interface PositionData {
  amount: number;
  is_long: boolean;
  entry_price: number;
  pnl: number;
  mark_price?: number;
  liq_price?: number;
  leverage?: number;
  funding_paid?: number;
  realized_pnl?: number;
}

export interface ArbFundingData {
  bybit_rate: number | null;
  lighter_rate: number | null;
  lighter_8h: number | null;
  net_8h_rate: number | null;
}

export interface TheoreticalData {
  entry_bps: number | null;
  current_bps: number | null;
  diff_bps: number | null;
  pnl_usd: number | null;
}

export interface PositionsResponse {
  bybit: PositionData | null;
  lighter: PositionData | null;
  funding?: ArbFundingData | null;
  theoretical?: TheoreticalData | null;
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
  type: 'update' | 'snapshot' | 'pong' | 'monitor_update';
  data?: any;
  ts?: number;
}
