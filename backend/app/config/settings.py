# file: backend/app/config/settings.py
from pydantic_settings import BaseSettings
from typing import List
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

    @property
    def symbol_list(self) -> List[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    @property
    def poll_interval_seconds(self) -> float:
        return self.poll_interval_ms / 1000.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
