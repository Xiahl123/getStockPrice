from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量: {name}，请参考 .env.example 配置 .env")
    return value


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    itick_token: str
    itick_ws_url: str
    itick_max_subscriptions: int
    feishu_app_id: str
    feishu_app_secret: str
    feishu_alert_chat_id: str
    feishu_alert_receive_id_type: str
    feishu_webhook_url: str
    default_alert_percent: float
    alert_cooldown_seconds: int
    data_file: Path
    log_level: str


def load_settings() -> Settings:
    data_file = Path(os.getenv("DATA_FILE", "./data/watches.json"))
    if not data_file.is_absolute():
        data_file = ROOT_DIR / data_file

    return Settings(
        itick_token=_require("ITICK_TOKEN"),
        itick_ws_url=os.getenv("ITICK_WS_URL", "wss://api-free.itick.org/stock").strip(),
        itick_max_subscriptions=_int("ITICK_MAX_SUBSCRIPTIONS", 3),
        feishu_app_id=_require("FEISHU_APP_ID"),
        feishu_app_secret=_require("FEISHU_APP_SECRET"),
        feishu_alert_chat_id=os.getenv("FEISHU_ALERT_CHAT_ID", "").strip(),
        feishu_alert_receive_id_type=os.getenv(
            "FEISHU_ALERT_RECEIVE_ID_TYPE", "chat_id"
        ).strip(),
        feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL", "").strip(),
        default_alert_percent=_float("DEFAULT_ALERT_PERCENT", 2.0),
        alert_cooldown_seconds=_int("ALERT_COOLDOWN_SECONDS", 300),
        data_file=data_file,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
