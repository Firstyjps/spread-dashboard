from __future__ import annotations

from app.risk.database import get_kill_switch_state, set_kill_switch_state
from app.risk.models import now_ms


class KillSwitch:
    def __init__(self) -> None:
        self.active = False
        self.reason = ""
        self.activation_ts = 0.0

    async def load(self) -> None:
        state = await get_kill_switch_state()
        if not state:
            return
        self.active = bool(state["active"])
        self.reason = str(state["reason"] or "")
        self.activation_ts = float(state["activation_ts"] or 0.0)

    async def activate(self, reason: str) -> None:
        self.active = True
        self.reason = reason
        self.activation_ts = now_ms()
        await set_kill_switch_state(True, reason, self.activation_ts)

    async def reset(self) -> None:
        self.active = False
        self.reason = ""
        self.activation_ts = 0.0
        await set_kill_switch_state(False, "", 0.0)

    def status(self) -> dict[str, object]:
        return {
            "active": self.active,
            "reason": self.reason,
            "activation_ts": self.activation_ts,
        }
