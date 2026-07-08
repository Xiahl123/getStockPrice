from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from app.store import WatchStore

logger = logging.getLogger(__name__)

AlertSender = Callable[[str], None]


@dataclass
class QuoteSnapshot:
    code: str
    region: str
    last: float
    open_price: float
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: Optional[float] = None
    chp: Optional[float] = None
    timestamp_ms: Optional[int] = None

    @property
    def key(self) -> str:
        return f"{self.code.upper()}${self.region.upper()}"

    @property
    def open_change_percent(self) -> float:
        if self.open_price == 0:
            return 0.0
        return (self.last - self.open_price) / self.open_price * 100.0


class AlertEngine:
    """相对开盘价涨跌幅达到阈值时触发提醒，带冷却与日内重设。"""

    def __init__(
        self,
        store: WatchStore,
        send_alert: AlertSender,
        cooldown_seconds: int = 300,
    ) -> None:
        self.store = store
        self.send_alert = send_alert
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        # key -> {direction: "up"|"down", at: float, day: date}
        self._last_alerts: dict[str, dict] = {}

    def on_quote(self, quote: QuoteSnapshot) -> None:
        item = self.store.get(quote.code, quote.region)
        if item is None:
            return
        if quote.open_price <= 0 or quote.last <= 0:
            return

        pct = quote.open_change_percent
        threshold = abs(item.percent)
        if abs(pct) < threshold:
            return

        direction = "up" if pct >= 0 else "down"
        today = date.today()
        now = time.time()

        with self._lock:
            prev = self._last_alerts.get(quote.key)
            if prev:
                same_day = prev.get("day") == today
                same_dir = prev.get("direction") == direction
                cooled = now - float(prev.get("at", 0)) >= self.cooldown_seconds
                if same_day and same_dir and not cooled:
                    return
            self._last_alerts[quote.key] = {
                "direction": direction,
                "at": now,
                "day": today,
            }

        arrow = "↑" if direction == "up" else "↓"
        sign = "+" if pct >= 0 else ""
        lines = [
            f"【股价提醒】{quote.code.upper()}.{quote.region.upper()} {arrow}",
            f"最新价: {quote.last}",
            f"开盘价: {quote.open_price}",
            f"相对开盘: {sign}{pct:.2f}%（阈值 {threshold:g}%）",
        ]
        if quote.prev_close is not None:
            lines.append(f"昨收: {quote.prev_close}")
        if quote.chp is not None:
            lines.append(f"相对昨收: {quote.chp:+.2f}%")
        if quote.high is not None and quote.low is not None:
            lines.append(f"日内高低: {quote.high} / {quote.low}")

        text = "\n".join(lines)
        logger.info("触发告警: %s", text.replace("\n", " | "))
        try:
            self.send_alert(text)
        except Exception:
            logger.exception("发送告警失败")
