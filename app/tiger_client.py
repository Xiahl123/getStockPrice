from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Set

from tigeropen.push.push_client import PushClient
from tigeropen.push.pb.QuoteBasicData_pb2 import QuoteBasicData

from app.alert_engine import AlertEngine, QuoteSnapshot
from app.config import Settings
from app.store import WatchStore
from app.tiger_config import build_tiger_client_config

logger = logging.getLogger(__name__)


class TigerQuoteClient:
    """老虎证券 PushClient 行情订阅封装。"""

    def __init__(
        self,
        settings: Settings,
        store: WatchStore,
        alert_engine: AlertEngine,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.alert_engine = alert_engine
        self.on_status = on_status
        self._client_config = build_tiger_client_config(settings)
        protocol, host, port = self._client_config.socket_host_port
        self._push = PushClient(
            host,
            port,
            use_ssl=(protocol == "ssl"),
            use_protobuf=True,
            client_config=self._client_config,
        )
        self._subscribed: Set[str] = set()
        self._lock = threading.Lock()
        self._started = False

        self._push.quote_changed = self._on_quote_changed
        self._push.connect_callback = self._on_connected
        self._push.subscribe_callback = self._on_subscribe_result
        self._push.error_callback = self._on_error

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        logger.info("连接老虎证券行情推送...")
        self._push.connect(
            self._client_config.tiger_id,
            self._client_config.private_key,
        )

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        try:
            symbols = list(self._subscribed)
            if symbols:
                self._push.unsubscribe_quote(symbols)
            self._push.disconnect()
        except Exception:
            logger.exception("断开老虎行情连接失败")
        with self._lock:
            self._subscribed.clear()

    def reload_subscriptions(self) -> None:
        """监控列表变更后增量更新订阅。"""
        if not self._started:
            return
        with self._lock:
            new_symbols = set(self.store.tiger_symbols())
            to_remove = sorted(self._subscribed - new_symbols)
            to_add = sorted(new_symbols - self._subscribed)
            if not to_remove and not to_add:
                return
            try:
                if to_remove:
                    self._push.unsubscribe_quote(to_remove)
                    self._subscribed -= set(to_remove)
                    logger.info("已取消订阅: %s", ",".join(to_remove))
                if to_add:
                    self._push.subscribe_quote(to_add)
                    self._subscribed |= set(to_add)
                    logger.info("已新增订阅: %s", ",".join(to_add))
            except Exception:
                logger.exception("刷新老虎订阅失败")

    def _notify(self, text: str) -> None:
        logger.info(text)
        if self.on_status:
            try:
                self.on_status(text)
            except Exception:
                logger.exception("状态回调失败")

    def _on_connected(self, _frame) -> None:
        logger.info("老虎证券行情推送已连接，准备订阅")
        with self._lock:
            symbols = self.store.tiger_symbols()
            self._subscribed.clear()
            if not symbols:
                logger.warning("当前没有监控股票，跳过订阅")
                return
            try:
                self._push.subscribe_quote(symbols)
                self._subscribed = set(symbols)
                logger.info("已发送订阅: %s", ",".join(symbols))
            except Exception:
                logger.exception("连接后订阅失败")

    def _on_subscribe_result(self, frame) -> None:
        msg = getattr(frame, "msg", None) or str(frame)
        if "fail" in str(msg).lower() or "error" in str(msg).lower():
            self._notify(f"老虎订阅失败: {msg}")
        else:
            logger.info("老虎订阅确认: %s", msg)

    def _on_error(self, frame) -> None:
        self._notify(f"老虎行情错误: {frame}")

    def _on_quote_changed(self, frame: QuoteBasicData) -> None:
        symbol = str(frame.symbol or "").strip().upper()
        if not symbol:
            return

        item = self.store.get_by_tiger_symbol(symbol)
        if item is None:
            return

        last = _proto_float(frame, "latestPrice")
        open_price = _proto_float(frame, "open")
        if last is None or open_price is None or open_price <= 0 or last <= 0:
            return

        prev_close = _proto_float(frame, "preClose")
        chp = None
        if prev_close and prev_close > 0:
            chp = (last - prev_close) / prev_close * 100.0

        quote = QuoteSnapshot(
            code=item.code,
            region=item.region,
            last=last,
            open_price=open_price,
            high=_proto_float(frame, "high"),
            low=_proto_float(frame, "low"),
            prev_close=prev_close,
            chp=chp,
            timestamp_ms=int(frame.timestamp) if frame.timestamp else None,
        )
        self.alert_engine.on_quote(quote)


def _proto_float(frame: QuoteBasicData, field: str) -> Optional[float]:
    if not frame.HasField(field):
        return None
    value = getattr(frame, field)
    if value is None:
        return None
    return float(value)
