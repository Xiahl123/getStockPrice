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


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    tiger_id: str
    tiger_account: str
    tiger_license: str
    tiger_private_key: str
    tiger_private_key_path: Path | None
    tiger_props_path: Path | None
    tiger_secret_key: str
    tiger_sandbox: bool
    max_watches: int
    feishu_app_id: str
    feishu_app_secret: str
    feishu_alert_chat_id: str
    feishu_alert_receive_id_type: str
    feishu_webhook_url: str
    default_alert_percent: float
    alert_cooldown_seconds: int
    data_file: Path
    log_level: str
    host: str
    port: int


def load_settings() -> Settings:
    data_file = Path(os.getenv("DATA_FILE", "./data/watches.json"))
    if not data_file.is_absolute():
        data_file = ROOT_DIR / data_file

    props_raw = os.getenv("TIGER_PROPS_PATH", "").strip()
    props_path = None
    if props_raw:
        props_path = Path(props_raw)
        if not props_path.is_absolute():
            props_path = ROOT_DIR / props_path

    key_path_raw = os.getenv("TIGER_PRIVATE_KEY_PATH", "").strip()
    key_path = None
    if key_path_raw:
        key_path = Path(key_path_raw)
        if not key_path.is_absolute():
            key_path = ROOT_DIR / key_path

    if not props_path and not (key_path or os.getenv("TIGER_PRIVATE_KEY", "").strip()):
        raise RuntimeError(
            "请配置老虎证券凭证：TIGER_PROPS_PATH，或 TIGER_PRIVATE_KEY_PATH / TIGER_PRIVATE_KEY"
        )

    if not props_path:
        _require("TIGER_ID")
        _require("TIGER_ACCOUNT")

    return Settings(
        root_dir=ROOT_DIR,
        tiger_id=os.getenv("TIGER_ID", "").strip(),
        tiger_account=os.getenv("TIGER_ACCOUNT", "").strip(),
        tiger_license=os.getenv("TIGER_LICENSE", "").strip(),
        tiger_private_key=os.getenv("TIGER_PRIVATE_KEY", "").strip(),
        tiger_private_key_path=key_path,
        tiger_props_path=props_path,
        tiger_secret_key=os.getenv("TIGER_SECRET_KEY", "").strip(),
        tiger_sandbox=_bool("TIGER_SANDBOX", False),
        max_watches=_int("MAX_WATCHES", 30),
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
        host=os.getenv("HOST", "0.0.0.0").strip(),
        port=_int("PORT", 8080),
    )
