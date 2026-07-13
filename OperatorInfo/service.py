# OperatorInfo/service.py
from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import time
from pathlib import Path

from .client import PrtsWikiClient
from .models import OperatorData
from .parser import PrtsOperatorParser
from .renderer import HtmlRenderer, render_operator_card


class OperatorEncyclopedia:
    CACHE_VERSION = 2

    def __init__(
        self,
        client: PrtsWikiClient,
        cache_dir: str | Path,
        *,
        cache_ttl_seconds: int = 24 * 60 * 60,
        download_portrait: bool = True,
    ):
        self.client = client
        self.parser = PrtsOperatorParser()
        self.cache_dir = Path(cache_dir)
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)
        self.download_portrait = download_portrait
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_operator(self, name: str, *, force_refresh: bool = False) -> OperatorData:
        key = self._normalize_name(name)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if not force_refresh:
                cached = self._load_cache(key)
                if cached is not None:
                    return cached
            return await asyncio.to_thread(self._fetch_and_cache, key)

    async def query_and_render(
        self,
        renderer: HtmlRenderer,
        name: str,
        *,
        force_refresh: bool = False,
        return_url: bool = True,
        render_options: dict | None = None,
    ) -> str:
        """查询干员数据并通过 AstrBot html_render() 直接生成图片。"""
        operator = await self.get_operator(name, force_refresh=force_refresh)
        return await render_operator_card(
            renderer,
            operator,
            return_url=return_url,
            options=render_options,
        )

    def get_operator_sync(self, name: str, *, force_refresh: bool = False) -> OperatorData:
        key = self._normalize_name(name)
        if not force_refresh:
            cached = self._load_cache(key)
            if cached is not None:
                return cached
        return self._fetch_and_cache(key)

    def _fetch_and_cache(self, name: str) -> OperatorData:
        page = self.client.get_operator_page(name)
        portrait_url: str | None = None
        avatar_url: str | None = None
        portrait_warning: str | None = None
        try:
            portrait_url = self.client.resolve_portrait_url(page.title, page.images)
        except Exception as exc:
            portrait_warning = f"立绘地址解析失败：{type(exc).__name__}"

        try:
            avatar_url = self.client.resolve_avatar_url(page.title, page.images)
        except Exception as exc:
            portrait_warning = self._join_warning(
                portrait_warning,
                f"头像地址解析失败：{type(exc).__name__}",
            )

        operator = self.parser.parse(page, portrait_url, avatar_url)
        if portrait_warning:
            operator.warnings.append(portrait_warning)
        if portrait_url and self.download_portrait:
            try:
                content, mime = self.client.download_image(portrait_url)
                operator.portrait_path = str(self._save_portrait(operator.name, content, mime))
            except Exception as exc:
                operator.warnings.append(f"立绘缓存失败：{type(exc).__name__}")
        elif not portrait_url:
            operator.warnings.append("未找到干员立绘")

        if avatar_url and self.download_portrait:
            try:
                content, mime = self.client.download_image(avatar_url)
                operator.avatar_path = str(self._save_image(operator.name, "avatars", content, mime))
            except Exception as exc:
                operator.warnings.append(f"头像缓存失败：{type(exc).__name__}")
        elif not avatar_url:
            operator.warnings.append("未找到干员头像")

        self._save_cache(name, operator)
        canonical_key = self._normalize_name(operator.name)
        if canonical_key != name:
            self._save_cache(canonical_key, operator)
        return operator

    def _load_cache(self, name: str) -> OperatorData | None:
        path = self._data_cache_path(name)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("cache_version") != self.CACHE_VERSION:
                return None
            if time.time() - float(payload["cached_at"]) > self.cache_ttl_seconds:
                return None
            return OperatorData.from_dict(payload["operator"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_cache(self, name: str, operator: OperatorData) -> None:
        path = self._data_cache_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "cache_version": self.CACHE_VERSION,
                    "cached_at": time.time(),
                    "operator": operator.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _save_portrait(self, name: str, content: bytes, mime: str) -> Path:
        return self._save_image(name, "portraits", content, mime)

    def _save_image(self, name: str, folder: str, content: bytes, mime: str) -> Path:
        suffix = mimetypes.guess_extension(mime) or ".img"
        if suffix == ".jpe":
            suffix = ".jpg"
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        path = self.cache_dir / folder / f"{digest}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path.resolve()

    def _data_cache_path(self, name: str) -> Path:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        return self.cache_dir / "operators" / f"{digest}.json"

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = " ".join(name.strip().split())
        if not normalized or len(normalized) > 64:
            raise ValueError("干员名不能为空且不能超过 64 个字符")
        return normalized

    @staticmethod
    def _join_warning(current: str | None, extra: str) -> str:
        return f"{current}；{extra}" if current else extra
