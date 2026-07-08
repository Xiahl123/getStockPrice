from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class WatchItem:
    code: str
    region: str
    percent: float

    @property
    def key(self) -> str:
        return f"{self.code.upper()}${self.region.upper()}"

    @property
    def display(self) -> str:
        return f"{self.code.upper()}.{self.region.upper()}"


class WatchStore:
    """线程安全的本地 JSON 监控列表。"""

    def __init__(self, path: Path, default_percent: float, max_items: int) -> None:
        self.path = path
        self.default_percent = default_percent
        self.max_items = max_items
        self._lock = threading.RLock()
        self._items: Dict[str, WatchItem] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._items = {}
                self.save()
                return
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            items: Dict[str, WatchItem] = {}
            for row in raw:
                item = WatchItem(
                    code=str(row["code"]).upper(),
                    region=str(row["region"]).upper(),
                    percent=float(row["percent"]),
                )
                items[item.key] = item
            self._items = items

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [asdict(item) for item in self._items.values()]
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def list(self) -> List[WatchItem]:
        with self._lock:
            return list(self._items.values())

    def get(self, code: str, region: str) -> Optional[WatchItem]:
        key = f"{code.upper()}${region.upper()}"
        with self._lock:
            return self._items.get(key)

    def add(self, code: str, region: str, percent: Optional[float] = None) -> WatchItem:
        with self._lock:
            item = WatchItem(
                code=code.upper(),
                region=region.upper(),
                percent=float(percent if percent is not None else self.default_percent),
            )
            if item.key not in self._items and len(self._items) >= self.max_items:
                raise ValueError(
                    f"已达到订阅上限 {self.max_items}（iTick 免费版限制）。"
                    "请先 /del 删除其他股票，或升级套餐并提高 ITICK_MAX_SUBSCRIPTIONS。"
                )
            self._items[item.key] = item
            self.save()
            return item

    def remove(self, code: str, region: str) -> bool:
        key = f"{code.upper()}${region.upper()}"
        with self._lock:
            existed = self._items.pop(key, None) is not None
            if existed:
                self.save()
            return existed

    def set_percent(self, code: str, region: str, percent: float) -> WatchItem:
        with self._lock:
            key = f"{code.upper()}${region.upper()}"
            item = self._items.get(key)
            if item is None:
                raise KeyError(f"未监控 {code.upper()}.{region.upper()}，请先 /add")
            item.percent = float(percent)
            self.save()
            return item

    def subscribe_params(self) -> str:
        with self._lock:
            return ",".join(item.key for item in self._items.values())
