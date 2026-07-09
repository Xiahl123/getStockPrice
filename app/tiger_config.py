from __future__ import annotations

from pathlib import Path

from tigeropen.common.consts import Language
from tigeropen.common.util.signature_utils import read_private_key
from tigeropen.tiger_open_config import TigerOpenClientConfig

from app.config import Settings


def build_tiger_client_config(settings: Settings) -> TigerOpenClientConfig:
    """根据 .env 或配置文件目录构建老虎 SDK ClientConfig。"""
    if settings.tiger_props_path:
        props = settings.tiger_props_path
        if not props.is_absolute():
            props = settings.root_dir / props
        return TigerOpenClientConfig(
            props_path=str(props),
            sandbox_debug=settings.tiger_sandbox,
        )

    if not settings.tiger_id or not settings.tiger_account:
        raise RuntimeError("请配置 TIGER_ID 与 TIGER_ACCOUNT，或使用 TIGER_PROPS_PATH")

    private_key = _load_private_key(settings)
    config = TigerOpenClientConfig(sandbox_debug=settings.tiger_sandbox)
    config.tiger_id = settings.tiger_id
    config.account = settings.tiger_account
    config.private_key = private_key
    if settings.tiger_license:
        config.license = settings.tiger_license
    if settings.tiger_secret_key:
        config.secret_key = settings.tiger_secret_key
    config.language = Language.zh_CN
    return config


def _load_private_key(settings: Settings) -> str:
    if settings.tiger_private_key:
        key = settings.tiger_private_key.strip()
        if key:
            return key

    if settings.tiger_private_key_path:
        path = settings.tiger_private_key_path
        if not path.is_absolute():
            path = settings.root_dir / path
        if not path.exists():
            raise RuntimeError(f"私钥文件不存在: {path}")
        return read_private_key(str(path))

    raise RuntimeError(
        "请配置 TIGER_PRIVATE_KEY_PATH 或 TIGER_PRIVATE_KEY，"
        "或将 tiger_openapi_config.properties 放入 TIGER_PROPS_PATH"
    )
