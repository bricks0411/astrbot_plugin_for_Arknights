# OperatorInfo/service.py
from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import time

from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from .client import PrtsWikiClient
from .exceptions import OperatorValidationError
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
        logger: Any | None = None,
    ):
        """初始化干员百科服务、缓存策略和并发查询锁"""
        self.client = client
        self.parser = PrtsOperatorParser()
        self.cache_dir = Path(cache_dir)
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)
        self.download_portrait = download_portrait
        self.logger = logger
        # 弱引用字典：若某个协程任务正持有 / 等待某把锁，则该锁将一直存在
        # 所有协程均释放该锁后，对应锁自动消失
        self._locks: WeakValueDictionary[str, asyncio.Lock] = (
            WeakValueDictionary()
        )

    async def get_operator(self, name: str, *, force_refresh: bool = False) -> OperatorData:
        """异步查询干员数据，并合并同名并发请求以复用缓存"""
        key = self._normalize_name(name)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if not force_refresh:
                cached = self._load_cache(key)
                if cached is not None:
                    self._log("debug", f"PRTS 缓存命中（operator={key!r}）")
                    return cached
            self._log(
                "info",
                f"PRTS 数据抓取开始（operator={key!r}, force_refresh={force_refresh}）",
            )
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
        """查询干员数据并通过 AstrBot html_render() 直接生成图片"""
        operator = await self.get_operator(name, force_refresh=force_refresh)
        return await render_operator_card(
            renderer,
            operator,
            return_url=return_url,
            options=render_options,
        )

    def get_operator_sync(self, name: str, *, force_refresh: bool = False) -> OperatorData:
        """同步查询干员数据，并按需读取或刷新缓存"""
        key = self._normalize_name(name)
        if not force_refresh:
            cached = self._load_cache(key)
            if cached is not None:
                return cached
        return self._fetch_and_cache(key)

    def get_cached_operator(
        self,
        name: str,
        *,
        allow_expired: bool = False,
    ) -> OperatorData | None:
        """读取 PRTS 本地缓存；请求失败后的文本兜底可显式允许过期数据。"""
        key = self._normalize_name(name)
        return self._load_cache(key, allow_expired=allow_expired)

    def _fetch_and_cache(self, name: str) -> OperatorData:
        """
        获取 html 页面、干员立绘和头像，并执行缓存逻辑
        """
        started_at = time.monotonic()
        # 根据干员名获取 html 页面
        page = self.client.get_operator_page(name)
        self._log(
            "debug",
            "PRTS 页面获取成功"
            f"（operator={name!r}, title={page.title!r}, revision_id={page.revision_id}, "
            f"images={len(page.images)}）",
        )
        # 初始化立绘、头像 URL
        portrait_url: str | None = None
        avatar_url: str | None = None
        # 审查指出原变量名只表达立绘告警，但实际还会收集头像解析告警
        # 改为图片资源告警后，变量语义与其承载的两类错误保持一致
        image_warning: str | None = None
        # 获取立绘 URL
        try:
            portrait_url = self.client.resolve_portrait_url(page.title, page.images)
        except Exception as exc:
            self._log_exception(
                f"PRTS 立绘地址解析失败（operator={page.title!r}）",
                exc,
            )
            image_warning = f"立绘地址解析失败：{type(exc).__name__}"

        # 获取头像 URL
        try:
            avatar_url = self.client.resolve_avatar_url(page.title, page.images)
        except Exception as exc:
            self._log_exception(
                f"PRTS 头像地址解析失败（operator={page.title!r}）",
                exc,
            )
            image_warning = self._join_warning(
                image_warning,
                f"头像地址解析失败：{type(exc).__name__}",
            )

        # 解析并获取以 OperatorInfo 组织的干员数据
        operator = self.parser.parse(page, portrait_url, avatar_url)
        # 立绘缓存
        if image_warning:
            operator.warnings.append(image_warning)
        if portrait_url and self.download_portrait:
            try:
                content, mime = self.client.download_image(portrait_url)
                operator.portrait_path = str(self._save_portrait(operator.name, content, mime))
            except Exception as exc:
                self._log_exception(
                    f"PRTS 立绘下载或缓存失败（operator={operator.name!r}）",
                    exc,
                )
                # 审查问题是下载失败后仍保留同一个远程地址，渲染器会再次请求已确认不可用的资源
                # 下载失败时清除远程地址，确保渲染器直接进入无立绘降级路径并避免重复失败
                operator.portrait_url = None
                operator.warnings.append(f"立绘缓存失败：{type(exc).__name__}")
        elif not portrait_url:
            operator.warnings.append("未找到干员立绘")

        # 头像缓存
        if avatar_url and self.download_portrait:
            try:
                content, mime = self.client.download_image(avatar_url)
                operator.avatar_path = str(self._save_image(operator.name, "avatars", content, mime))
            except Exception as exc:
                self._log_exception(
                    f"PRTS 头像下载或缓存失败（operator={operator.name!r}）",
                    exc,
                )
                # 头像与立绘使用相同的本地优先渲染规则，下载失败时也不能保留已失效的远程回退
                # 清除地址后仍保留百科文本数据和告警信息，不让非关键图片阻断整次查询
                operator.avatar_url = None
                operator.warnings.append(f"头像缓存失败：{type(exc).__name__}")
        elif not avatar_url:
            operator.warnings.append("未找到干员头像")

        self._save_cache(name, operator)
        canonical_key = self._normalize_name(operator.name)
        if canonical_key != name:
            self._save_cache(canonical_key, operator)
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        self._log(
            "info",
            f"PRTS 数据抓取完成（operator={operator.name!r}, elapsed_ms={elapsed_ms}, "
            f"warnings={len(operator.warnings)}）",
        )
        return operator

    def _log(self, level: str, message: str) -> None:
        """仅为 PRTS 请求链提供可选日志，不强制模块依赖 AstrBot。"""
        if self.logger is None:
            return
        log_method = getattr(self.logger, level, None)
        if callable(log_method):
            log_method(message)

    def _log_exception(self, message: str, exc: Exception) -> None:
        """记录当前异常的完整 traceback，并兼容没有 exception() 的日志器。"""
        if self.logger is None:
            return
        exception_method = getattr(self.logger, "exception", None)
        if callable(exception_method):
            exception_method(f"{message}：{type(exc).__name__}: {exc}")
            return
        error_method = getattr(self.logger, "error", None)
        if callable(error_method):
            error_method(
                f"{message}：{type(exc).__name__}: {exc}",
                exc_info=True,
            )

    def _load_cache(
        self,
        name: str,
        *,
        allow_expired: bool = False,
    ) -> OperatorData | None:
        """加载缓存"""
        path = self._data_cache_path(name)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("cache_version") != self.CACHE_VERSION:
                return None
            if (
                not allow_expired
                and time.time() - float(payload["cached_at"]) > self.cache_ttl_seconds
            ):
                return None
            return OperatorData.from_dict(payload["operator"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_cache(self, name: str, operator: OperatorData) -> None:
        """创建干员信息缓存"""
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
        """保存立绘"""
        return self._save_image(name, "portraits", content, mime)

    def _save_image(self, name: str, folder: str, content: bytes, mime: str) -> Path:
        """保存图片"""
        suffix = mimetypes.guess_extension(mime) or ".img"
        if suffix == ".jpe":
            suffix = ".jpg"
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        path = self.cache_dir / folder / f"{digest}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path.resolve()

    def _data_cache_path(self, name: str) -> Path:
        """构造干员数据缓存"""
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        return self.cache_dir / "operators" / f"{digest}.json"

    @staticmethod
    def _normalize_name(name: str) -> str:
        """静态方法：正则化干员名"""
        normalized = " ".join(name.strip().split())
        # 审查问题是 ValueError 不属于 OperatorInfoError 异常体系，LLM 工具调用方可能漏接异常
        # 使用模块专用校验异常后，query_and_render 及 main.py 的统一异常分支可以稳定处理非法名称
        if not normalized or len(normalized) > 64:
            raise OperatorValidationError("干员名不能为空且不能超过 64 个字符")
        return normalized

    @staticmethod
    def _join_warning(current: str | None, extra: str) -> str:
        """合并已有警告和新增警告文本。"""
        return f"{current}；{extra}" if current else extra
