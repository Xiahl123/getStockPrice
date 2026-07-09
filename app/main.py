from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from app.alert_engine import AlertEngine
from app.config import load_settings
from app.feishu_bot import FeishuBot
from app.store import WatchStore
from app.tiger_client import TigerQuoteClient

logger = logging.getLogger("main")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    store = WatchStore(
        path=settings.data_file,
        default_percent=settings.default_alert_percent,
        max_items=settings.max_watches,
    )

    quote_holder: dict[str, TigerQuoteClient | None] = {"client": None}

    bot = FeishuBot(
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret,
        store=store,
        alert_chat_id=settings.feishu_alert_chat_id,
        alert_receive_id_type=settings.feishu_alert_receive_id_type,
        webhook_url=settings.feishu_webhook_url,
        get_quote_client=lambda: quote_holder["client"],
    )

    engine = AlertEngine(
        store=store,
        send_alert=bot.send_alert,
        cooldown_seconds=settings.alert_cooldown_seconds,
    )

    tiger = TigerQuoteClient(
        settings=settings,
        store=store,
        alert_engine=engine,
    )
    quote_holder["client"] = tiger

    stop_event = threading.Event()

    def _shutdown(signum, _frame) -> None:
        logger.info("收到信号 %s，准备退出...", signum)
        stop_event.set()
        tiger.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info(
        "服务启动 | 监控 %s 只 | 默认阈值 %s%% | 上限 %s",
        len(store.list()),
        settings.default_alert_percent,
        settings.max_watches,
    )
    if not settings.feishu_alert_chat_id and not settings.feishu_webhook_url:
        logger.warning(
            "未配置 FEISHU_ALERT_CHAT_ID / FEISHU_WEBHOOK_URL。"
            "请先在飞书给机器人发 /chatid，再写入 .env。"
        )

    bot.start()
    tiger.start()

    while not stop_event.is_set():
        time.sleep(0.5)

    logger.info("服务已停止")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        sys.exit(1)
