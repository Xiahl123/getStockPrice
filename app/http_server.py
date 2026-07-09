from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    status_provider: Optional[Callable[[], dict]] = None

    def do_GET(self) -> None:
        if self.path not in {"/", "/health"}:
            self._send_json(404, {"error": "not found"})
            return
        payload = {"status": "ok"}
        if self.status_provider:
            try:
                payload.update(self.status_provider())
            except Exception:
                logger.exception("生成健康检查状态失败")
                self._send_json(500, {"status": "error"})
                return
        self._send_json(200, payload)

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        logger.debug("HTTP %s - %s", self.address_string(), format % args)


class HttpServer:
    def __init__(
        self,
        host: str,
        port: int,
        status_provider: Optional[Callable[[], dict]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self._status_provider = status_provider
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        handler = type(
            "BoundHealthHandler",
            (_HealthHandler,),
            {"status_provider": self._status_provider},
        )
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="http-server",
            daemon=True,
        )
        self._thread.start()
        logger.info("HTTP 服务已启动: http://%s:%s", self.host, self.port)

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        logger.info("HTTP 服务已停止")
