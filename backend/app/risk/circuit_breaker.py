from __future__ import annotations

from app.risk.models import now_ms


class RiskCircuitBreaker:
    def __init__(self) -> None:
        self.tripped = False
        self.reason = ""
        self.tripped_ts = 0.0
        self.cooldown_until_ts = 0.0

    def trip(self, reason: str, cooldown_minutes: float) -> None:
        self.tripped = True
        self.reason = reason
        self.tripped_ts = now_ms()
        self.cooldown_until_ts = self.tripped_ts + cooldown_minutes * 60_000

    def reset(self) -> None:
        self.tripped = False
        self.reason = ""
        self.tripped_ts = 0.0
        self.cooldown_until_ts = 0.0

    def is_cooldown_active(self) -> bool:
        return now_ms() < self.cooldown_until_ts

    def cooldown_remaining_s(self) -> float:
        return max(0.0, (self.cooldown_until_ts - now_ms()) / 1000)

    def status(self) -> dict[str, object]:
        return {
            "tripped": self.tripped,
            "reason": self.reason,
            "tripped_ts": self.tripped_ts,
            "cooldown_active": self.is_cooldown_active(),
            "cooldown_remaining_s": self.cooldown_remaining_s(),
        }
