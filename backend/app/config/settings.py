# file: backend/app/config/settings.py
from pydantic_settings import BaseSettings
from typing import Dict, List, Tuple
import os


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Bybit
    bybit_base_url: str = "https://api.bytick.com"
    bybit_ws_public_linear: str = "wss://stream.bytick.com/v5/public/linear"
    bybit_ws_public_spot: str = "wss://stream.bytick.com/v5/public/spot"
    bybit_api_key: str = ""
    bybit_api_secret: str = ""

    # Lighter
    lighter_base_url: str = "https://mainnet.zklighter.elliot.ai"
    lighter_ws_url: str = "wss://mainnet.zklighter.elliot.ai/stream"
    lighter_private_key: str = ""
    lighter_api_key_index: int = 0
    lighter_account_index: int = 0

    # Database
    db_path: str = "./data/spread_dashboard.db"

    # Symbols
    symbols: str = "BTCUSDT,ETHUSDT"

    # Alert thresholds
    spread_alert_bps: float = 5.0
    stale_feed_timeout_s: int = 10
    latency_warning_ms: int = 500

    # Polling
    poll_interval_ms: int = 2000

    # Telegram Alerts
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_alert_cooldown_s: int = 60
    alert_upper_bps: float = 60.0
    alert_lower_bps: float = 30.0

    # CORS (comma-separated origins, default: localhost dev servers)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Maker Engine (Bybit PostOnly LIMIT execution)
    maker_max_time_s: float = 90.0
    maker_reprice_interval_ms: int = 2000
    maker_max_reprices: int = 60
    maker_aggressiveness: str = "BALANCED"
    maker_allow_market_fallback: bool = True
    maker_fee_rate: float = 0.0002
    taker_fee_rate: float = 0.00055
    maker_spread_guard_ticks: int = 1
    maker_vol_window: int = 20
    maker_vol_limit_ticks: int = 10
    maker_max_deviation_ticks: int = 50

    # Arbitrage execution (sequential Bybit-first mode)
    arb_maker_only: bool = True        # Disable market fallback — maker fees only
    arb_min_fill_pct: float = 10.0     # Minimum Bybit fill % before executing Lighter

    # Iceberg Executor (Bybit GTC LIMIT synthetic iceberg)
    iceberg_child_qty: float = 0.001
    iceberg_max_active_children: int = 1
    iceberg_price_policy: str = "PASSIVE"           # PASSIVE | MID | CHASE
    iceberg_urgency: str = "normal"                  # passive | normal | aggressive
    iceberg_poll_interval_ms: int = 500
    iceberg_cooldown_ms: int = 1500
    iceberg_max_runtime_s: float = 120.0
    iceberg_reprice_threshold_bps: int = 5
    iceberg_max_cancels: int = 30
    iceberg_max_slippage_bps: int = 50
    iceberg_max_retries: int = 3

    # Rate limiter (shared across execution strategies)
    rate_limit_max_tokens: int = 10
    rate_limit_refill_rate: float = 10.0

    # LIMIT Slicer (Bybit LINEAR — LIMIT-only sliced execution)
    bybit_testnet: bool = False                # use Bybit testnet API
    exec_slice_default: int = 5                # default number of slices
    exec_slice_poll_s: float = 1.0             # fill polling interval (seconds)
    exec_slice_timeout_s: float = 60.0         # max execution time (seconds)
    exec_slice_price_offset_bps: int = 0       # extra price aggressiveness (bps)

    # Per-symbol alert threshold overrides (format: "SYMBOL:UPPER:LOWER,...")
    # Symbols not listed here use global alert_upper_bps / alert_lower_bps
    # e.g., "XAUTUSDT:75:45" means XAUT alerts at 75 bps upper, 45 bps lower
    alert_overrides: str = ""

    # Cross-exchange symbol aliases (format: "DASHBOARD_SYM:LIGHTER_SYM,...")
    # When symbols differ between exchanges, map dashboard symbol to Lighter symbol
    # e.g., "XAUTUSDT:XAUUSDT" means: dashboard uses XAUTUSDT, Lighter uses XAUUSDT (market: XAU)
    lighter_symbol_map: str = "XAUTUSDT:XAUUSDT"

    @property
    def symbol_list(self) -> List[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    @property
    def poll_interval_seconds(self) -> float:
        return self.poll_interval_ms / 1000.0

    def get_alert_thresholds(self, symbol: str) -> Tuple[float, float]:
        """Return (upper_bps, lower_bps) for a symbol.

        Checks alert_overrides first; falls back to global defaults.
        Format: "SYMBOL:UPPER:LOWER,..."
        """
        if self.alert_overrides:
            for entry in self.alert_overrides.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                parts = entry.split(":")
                if len(parts) == 3 and parts[0].strip() == symbol:
                    try:
                        return float(parts[1].strip()), float(parts[2].strip())
                    except ValueError:
                        continue
        return self.alert_upper_bps, self.alert_lower_bps

    @property
    def lighter_aliases(self) -> Dict[str, str]:
        """Parse LIGHTER_SYMBOL_MAP into dict: {dashboard_sym: lighter_sym}."""
        result = {}
        if not self.lighter_symbol_map:
            return result
        for pair in self.lighter_symbol_map.split(","):
            pair = pair.strip()
            if ":" in pair:
                dashboard_sym, lighter_sym = pair.split(":", 1)
                result[dashboard_sym.strip()] = lighter_sym.strip()
        return result

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
