from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from threading import RLock
from typing import Any

import requests


class PrtsImageCache:
    """统一缓存渲染器使用的 PRTS PNG 图片"""

    REQUEST_TIMEOUT = 10
    MAX_IMAGE_SIZE = 5 * 1024 * 1024
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    def __init__(self, cache_dir: str | Path, logger: Any | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger
        self._lock = RLock()

    def get_png(
        self,
        cache_key: str,
        remote_url: str,
        *,
        resource_name: str = "PRTS 图片",
    ) -> str:
        """优先返回缓存 PNG 的 data URL，获取失败时保留远程 URL"""
        cache_path = self._cache_path(cache_key)
        try:
            with self._lock:
                if cache_path.is_file():
                    content = cache_path.read_bytes()
                    if content.startswith(self.PNG_SIGNATURE):
                        return self._data_url(content)

            response = requests.get(remote_url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("Content-Type", "").lower()
            if (
                not content.startswith(self.PNG_SIGNATURE)
                or len(content) > self.MAX_IMAGE_SIZE
                or (content_type and not content_type.startswith("image/"))
            ):
                return remote_url

            with self._lock:
                temporary_path = cache_path.with_suffix(".tmp")
                temporary_path.write_bytes(content)
                temporary_path.replace(cache_path)
            return self._data_url(content)
        except (OSError, requests.RequestException) as exc:
            self._log("warning", f"{resource_name}获取失败：{exc}")
            return remote_url

    def _cache_path(self, cache_key: str) -> Path:
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.png"

    @staticmethod
    def _data_url(content: bytes) -> str:
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _log(self, level: str, message: str) -> None:
        method = getattr(self.logger, level, None)
        if callable(method):
            method(message)
