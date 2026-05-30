export type RiskDecisionType = 'approve' | 'reject' | 'simulate';

export type RiskOrder = {
  symbol: string;
  side: 'Buy' | 'Sell';
  qty: number;
  price: number | null;
  exchange: string;
  order_type: string;
  source: string;
  timestamp_ms: number;
  reduce_only: boolean;
};

export type RiskConfig = {
  dry_run_enabled: boolean;
  max_position_per_symbol: number;
  position_limits_override: Record<string, number>;
  max_notional_exposure_usd: number;
  max_order_rate_per_minute: number;
  rate_limit_queue_timeout_s: number;
  price_sanity_band_pct: number;
  price_data_max_age_s: number;
  kill_switch_loss_threshold_usd: number;
  kill_switch_consecutive_failures: number;
  kill_switch_feed_stale_s: number;
  kill_switch_spread_inversion_pct: number;
  kill_switch_spread_inversion_duration_s: number;
  cooldown_minutes: number;
  audit_retention_days: number;
};

export type RiskRateStatus = {
  used: number;
  remaining: number;
  limit: number;
  window_s: number;
  queued: boolean;
};

export type RiskDecision = {
  decision: RiskDecisionType;
  reason: string;
  order: RiskOrder;
  dry_run_mode: boolean;
  kill_switch_active: boolean;
  circuit_breaker_tripped: boolean;
  cooldown_active: boolean;
  positions: Record<string, number>;
  notional_exposure_usd: number;
  order_rates: Record<string, RiskRateStatus>;
  timestamp_ms: number;
};

export type RiskStatus = {
  dry_run_mode: boolean;
  kill_switch_active: boolean;
  kill_switch_reason: string;
  circuit_breaker_tripped: boolean;
  cooldown_active: boolean;
  cooldown_remaining_s: number;
  positions: Record<string, number>;
  position_limits: Record<string, number>;
  notional_exposure_usd: number;
  notional_cap_usd: number;
  order_rates: Record<string, RiskRateStatus>;
  config: RiskConfig;
  last_decision: RiskDecision | null;
  updated_ts: number;
};

export type RiskConfigResponse = {
  config: RiskConfig;
  ranges: Record<string, [number, number]>;
};

export type RiskConfigPatch = Partial<RiskConfig> & {
  confirm_live?: boolean;
};

export type RiskAuditItem = {
  id: number;
  timestamp_ms: number;
  decision_type: RiskDecisionType;
  symbol: string;
  side: string;
  qty: number;
  price: number | null;
  exchange: string;
  order_type: string;
  source: string;
  reason: string;
  dry_run_mode: boolean;
  kill_switch_active: boolean;
  circuit_breaker_tripped: boolean;
  cooldown_active: boolean;
  positions: Record<string, number>;
  notional_exposure_usd: number;
  order_rates: Record<string, RiskRateStatus>;
  created_at: number;
};

export type RiskAuditResponse = {
  items: RiskAuditItem[];
  page: number;
  page_size: number;
  total: number;
};
