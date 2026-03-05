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
