from __future__ import annotations

import json
import logging
import re
import threading
from typing import TYPE_CHECKING, Callable, Optional

import lark_oapi as lark
import requests
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

from app.store import WatchStore

if TYPE_CHECKING:
    from app.itick_client import ITickClient

logger = logging.getLogger(__name__)

HELP_TEXT = """股票监控机器人命令：

/add <代码> <市场> [百分比]
  添加监控。例: /add AAPL US 2.5
  市场: US / HK / CN
  百分比省略则用默认值（相对开盘价）

/del <代码> <市场>
  删除监控。例: /del AAPL US

/set <代码> <市场> <百分比>
  修改阈值。例: /set 700 HK 3

/list
  查看当前监控列表

/chatid
  显示当前会话 ID（填到 .env 的 FEISHU_ALERT_CHAT_ID）

/help
  显示本帮助

说明：
· 提醒条件：相对当日开盘价涨跌绝对值 ≥ 设定百分比
· iTick 免费版最多同时监控 3 只股票"""


class FeishuBot:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        store: WatchStore,
        alert_chat_id: str = "",
        alert_receive_id_type: str = "chat_id",
        webhook_url: str = "",
        get_itick: Optional[Callable[[], Optional["ITickClient"]]] = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.store = store
        self.alert_chat_id = alert_chat_id
        self.alert_receive_id_type = alert_receive_id_type
        self.webhook_url = webhook_url
        self.get_itick = get_itick
        self._api = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )
        self._ws_client: Optional[lark.ws.Client] = None
        self._thread: Optional[threading.Thread] = None
        # 记住最近一次发命令的会话，便于告警回落到同一会话
        self._last_command_chat_id: Optional[str] = None
        self._last_command_receive_type = "chat_id"

    def start(self) -> None:
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        self._ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
        )
        self._thread = threading.Thread(
            target=self._ws_client.start,
            name="feishu-ws",
            daemon=True,
        )
        self._thread.start()
        logger.info("飞书长连接线程已启动")

    def send_alert(self, text: str) -> None:
        sent = False
        target_id = self.alert_chat_id or self._last_command_chat_id
        receive_type = (
            self.alert_receive_id_type
            if self.alert_chat_id
            else self._last_command_receive_type
        )
        if target_id:
            self.send_text(receive_type, target_id, text)
            sent = True
        if self.webhook_url:
            self._send_webhook(text)
            sent = True
        if not sent:
            logger.error(
                "无法发送告警：请配置 FEISHU_ALERT_CHAT_ID 或 FEISHU_WEBHOOK_URL，"
                "或先在飞书里给机器人发一条 /help"
            )

    def send_text(self, receive_id_type: str, receive_id: str, text: str) -> None:
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self._api.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                f"飞书发消息失败 code={response.code} msg={response.msg} "
                f"log_id={response.get_log_id()}"
            )

    def _send_webhook(self, text: str) -> None:
        resp = requests.post(
            self.webhook_url,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code", 0) != 0 and body.get("StatusCode", 0) != 0:
            # 飞书 webhook 成功时通常 StatusCode=0 或无 code
            if body.get("code") not in (None, 0):
                raise RuntimeError(f"Webhook 发送失败: {body}")

    def _on_message(self, data: P2ImMessageReceiveV1) -> None:
        try:
            event = data.event
            message = event.message
            if message.message_type != "text":
                self._reply(message, "目前只支持文本命令，发送 /help 查看用法")
                return

            content = json.loads(message.content or "{}")
            text = str(content.get("text", "")).strip()
            # 去掉群里的 @机器人 片段
            text = re.sub(r"@_user_\d+\s*", "", text).strip()
            if not text:
                return

            chat_id = message.chat_id
            chat_type = message.chat_type  # p2p / group
            if chat_id:
                self._last_command_chat_id = chat_id
                self._last_command_receive_type = "chat_id"

            reply = self._handle_command(text, chat_id=chat_id, chat_type=chat_type)
            if reply:
                self._reply(message, reply)
        except Exception:
            logger.exception("处理飞书消息失败")

    def _reply(self, message, text: str) -> None:
        chat_id = message.chat_id
        if not chat_id:
            return
        self.send_text("chat_id", chat_id, text)

    def _reload_itick(self) -> None:
        if not self.get_itick:
            return
        client = self.get_itick()
        if client is not None:
            client.reload_subscriptions()

    def _handle_command(
        self, text: str, chat_id: Optional[str], chat_type: Optional[str]
    ) -> str:
        parts = text.split()
        cmd = parts[0].lower()

        if cmd in {"/help", "help", "帮助"}:
            return HELP_TEXT

        if cmd in {"/chatid", "chatid"}:
            return (
                f"当前会话 chat_id:\n{chat_id}\n"
                f"chat_type: {chat_type}\n"
                "请把它填到 .env 的 FEISHU_ALERT_CHAT_ID，然后重启服务。"
            )

        if cmd in {"/list", "list"}:
            items = self.store.list()
            if not items:
                return "当前没有监控股票。用 /add AAPL US 2 添加。"
            lines = ["当前监控列表:"]
            for item in items:
                lines.append(f"· {item.display}  阈值 {item.percent:g}%（相对开盘）")
            lines.append(f"上限: {self.store.max_items} 只")
            return "\n".join(lines)

        if cmd in {"/add", "add"}:
            if len(parts) < 3:
                return "用法: /add <代码> <市场> [百分比]\n例: /add AAPL US 2.5"
            code, region = parts[1], parts[2]
            percent = float(parts[3]) if len(parts) >= 4 else None
            try:
                item = self.store.add(code, region, percent)
            except ValueError as exc:
                return str(exc)
            self._reload_itick()
            return (
                f"已添加 {item.display}，阈值 {item.percent:g}%（相对开盘）。\n"
                "订阅已刷新。"
            )

        if cmd in {"/del", "del", "/remove", "remove"}:
            if len(parts) < 3:
                return "用法: /del <代码> <市场>\n例: /del AAPL US"
            code, region = parts[1], parts[2]
            ok = self.store.remove(code, region)
            if not ok:
                return f"未找到 {code.upper()}.{region.upper()}"
            self._reload_itick()
            return f"已删除 {code.upper()}.{region.upper()}，订阅已刷新。"

        if cmd in {"/set", "set"}:
            if len(parts) < 4:
                return "用法: /set <代码> <市场> <百分比>\n例: /set 700 HK 3"
            code, region, percent_raw = parts[1], parts[2], parts[3]
            try:
                item = self.store.set_percent(code, region, float(percent_raw))
            except KeyError as exc:
                return str(exc)
            return f"已更新 {item.display} 阈值为 {item.percent:g}%"

        return f"未知命令: {cmd}\n发送 /help 查看用法"
