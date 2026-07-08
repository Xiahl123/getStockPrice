from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Optional

import websocket

from app.alert_engine import AlertEngine, QuoteSnapshot
from app.store import WatchStore

logger = logging.getLogger(__name__)


class ITickClient:
    """iTick 股票行情 WebSocket 客户端（单连接，适合免费版）。"""

    def __init__(
        self,
        token: str,
        ws_url: str,
        store: WatchStore,
        alert_engine: AlertEngine,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.token = token
        self.ws_url = ws_url
        self.store = store
        self.alert_engine = alert_engine
        self.on_status = on_status
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._ping_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_forever, name="itick-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reload.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def reload_subscriptions(self) -> None:
        """监控列表变更后，关闭当前连接以触发重连并重新订阅。"""
        logger.info("准备重载 iTick 订阅")
        self._reload.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _notify(self, text: str) -> None:
        logger.info(text)
        if self.on_status:
            try:
                self.on_status(text)
            except Exception:
                logger.exception("状态回调失败")

    def _run_forever(self) -> None:
        while not self._stop.is_set():
            self._reload.clear()
            self._connect_once()
            if self._stop.is_set():
                break
            # 被 reload 触发的关闭立即重连；异常关闭稍等再重试
            wait = 1.0 if self._reload.is_set() else 5.0
            logger.info("%.0f 秒后重连 iTick...", wait)
            self._stop.wait(wait)

    def _connect_once(self) -> None:
        headers = [f"token: {self.token}"]

        def on_open(ws: websocket.WebSocketApp) -> None:
            logger.info("iTick WebSocket 已连接")
            self._start_ping(ws)
            self._subscribe(ws)

        def on_message(_ws: websocket.WebSocketApp, message: str) -> None:
            self._handle_message(message)

        def on_error(_ws: websocket.WebSocketApp, error: Exception) -> None:
            logger.error("iTick WebSocket 错误: %s", error)

        def on_close(_ws: websocket.WebSocketApp, status: int, msg: str) -> None:
            logger.warning("iTick WebSocket 关闭: %s %s", status, msg)

        ws = websocket.WebSocketApp(
            self.ws_url,
            header=headers,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        with self._lock:
            self._ws = ws

        try:
            ws.run_forever(ping_interval=0)
        finally:
            with self._lock:
                if self._ws is ws:
                    self._ws = None

    def _start_ping(self, ws: websocket.WebSocketApp) -> None:
        def loop() -> None:
            while not self._stop.is_set() and self._ws is ws:
                try:
                    payload = {"ac": "ping", "params": str(int(time.time() * 1000))}
                    ws.send(json.dumps(payload))
                except Exception:
                    break
                if self._stop.wait(30):
                    break

        self._ping_thread = threading.Thread(target=loop, name="itick-ping", daemon=True)
        self._ping_thread.start()

    def _subscribe(self, ws: websocket.WebSocketApp) -> None:
        params = self.store.subscribe_params()
        if not params:
            logger.warning("当前没有监控股票，跳过订阅")
            return
        msg = {"ac": "subscribe", "params": params, "types": "quote"}
        ws.send(json.dumps(msg))
        logger.info("已发送订阅: %s", params)

    def _handle_message(self, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("无法解析消息: %s", message)
            return

        res_ac = data.get("resAc")
        if res_ac == "auth":
            if data.get("code") == 1:
                logger.info("iTick 鉴权成功")
            else:
                self._notify(f"iTick 鉴权失败: {data.get('msg')}")
            return

        if res_ac == "subscribe":
            if data.get("code") == 1:
                logger.info("iTick 订阅成功")
            else:
                self._notify(f"iTick 订阅失败: {data.get('msg')}")
            return

        if res_ac == "pong":
            return

        payload = data.get("data")
        if not isinstance(payload, dict):
            return
        if payload.get("type") != "quote":
            return

        code = str(payload.get("s") or "").upper()
        region = str(payload.get("r") or "").upper()
        last = payload.get("ld")
        open_price = payload.get("o")
        if not code or not region or last is None or open_price is None:
            return

        quote = QuoteSnapshot(
            code=code,
            region=region,
            last=float(last),
            open_price=float(open_price),
            high=float(payload["h"]) if payload.get("h") is not None else None,
            low=float(payload["l"]) if payload.get("l") is not None else None,
            prev_close=float(payload["p"]) if payload.get("p") is not None else None,
            chp=float(payload["chp"]) if payload.get("chp") is not None else None,
            timestamp_ms=int(payload["t"]) if payload.get("t") is not None else None,
        )
        self.alert_engine.on_quote(quote)
