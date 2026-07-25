# OperatorInfo/client.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

from .exceptions import (
    OperatorNotFoundError,
    OperatorResponseError,
    OperatorValidationError,
)


class JsonHttpClient(Protocol):
    def request_json(self, method: str, url: str, **kwargs: Any) -> dict:
        """发送请求并返回 JSON 对象"""
        ...

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """发送请求并返回原始响应对象"""
        ...


@dataclass(slots=True, frozen=True)
class PrtsPage:
    title: str
    html: str
    revision_id: int | None
    images: tuple[str, ...]             # 可变长元组，类型必须为 str，但不限制数量
    source_url: str


class PrtsWikiClient:
    API_URL = "https://prts.wiki/api.php"
    PAGE_URL = "https://prts.wiki/w/"
    USER_AGENT = (
        "AstrBot-Arknights/1.0 "
        "(+https://github.com/Bricks0411/astrbot_plugin_for_Arknights)"
    )

    def __init__(
        self,
        http_client: JsonHttpClient,
        *,
        logger: Any | None = None,
        bypass_environment_proxy: bool = True,
    ):
        """初始化类方法"""
        self.http_client = http_client
        self.logger = logger
        self.bypass_environment_proxy = bypass_environment_proxy

    def get_operator_page(self, name: str) -> PrtsPage:
        """向 prts.wiki 获取原始页面 html 化信息"""
        normalized = " ".join(name.strip().split())
        # 审查问题是通用 ValueError 会越过调用方仅针对 OperatorInfoError 的异常处理
        # 这里改为模块专用校验异常，让同步入口和直接使用客户端的调用方都能统一捕获
        if not normalized or len(normalized) > 64:
            raise OperatorValidationError("干员名不能为空且不能超过 64 个字符")

        payload = self._request_json(
            "GET",
            self.API_URL,
            params={
                "action": "parse",
                "page": normalized,
                "prop": "text|images|revid",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
                "origin": "*",
            },
        )
        error = payload.get("error")
        if error:
            code = str(error.get("code", ""))
            if code in {"missingtitle", "invalidtitle"}:
                raise OperatorNotFoundError(f"PRTS 中不存在页面：{normalized}")
            raise OperatorResponseError(error.get("info") or f"MediaWiki API 错误：{code}")

        parsed = payload.get("parse")
        if not isinstance(parsed, dict) or not isinstance(parsed.get("text"), str):
            raise OperatorResponseError("PRTS 响应缺少 parse.text")

        title = str(parsed.get("title") or normalized)
        images = tuple(str(item) for item in parsed.get("images", []) if isinstance(item, str))
        return PrtsPage (
            title       = title,
            html        = parsed["text"],
            revision_id = parsed.get("revid") if isinstance(parsed.get("revid"), int) else None,
            images      = images,
            source_url  = self.PAGE_URL + quote(title.replace(" ", "_"), safe=""),
        )

    def resolve_portrait_url(self, operator_name: str, images: tuple[str, ...]) -> str | None:
        """
        不同干员可能存在的立绘种类数不同，低星干员的立绘数小于高星干员
        例如 3 星干员最高精英一，仅两张立绘；6 星干员最高精英二，对应三张立绘
        """
        candidates = [name for name in images if "立绘" in name and operator_name in name]
        guessed = [f"立绘_{operator_name}_2.png", f"立绘_{operator_name}_1.png"]
        candidates = guessed + [name for name in candidates if name not in guessed]

        return self._resolve_image_url(candidates)

    def resolve_avatar_url(self, operator_name: str, images: tuple[str, ...]) -> str | None:
        """获取头像 URL，详情见 avatar.md，文件未上传至 github"""
        candidates = [
            name
            for name in images
            if ("头像" in name or "半身像" in name) and operator_name in name
        ]
        guessed = [
            f"头像_{operator_name}.png",
            f"半身像_{operator_name}_1.png",
            f"半身像_{operator_name}_2.png",
        ]
        candidates = guessed + [name for name in candidates if name not in guessed]
        return self._resolve_image_url(candidates)

    def _resolve_image_url(self, candidates: list[str]) -> str | None:
        """按候选文件名顺序查询并返回首个可用的图片 URL。"""
        for filename in candidates:
            payload = self._request_json(
                "GET",
                self.API_URL,
                params={
                    "action": "query",
                    "prop": "imageinfo",
                    "titles": f"文件:{filename}",
                    "iiprop": "url|mime|size",
                    "format": "json",
                    "formatversion": "2",
                    "redirects": "1",
                    "origin": "*",
                },
            )
            pages = payload.get("query", {}).get("pages", [])
            if not isinstance(pages, list) or not pages:
                continue
            info = pages[0].get("imageinfo") if isinstance(pages[0], dict) else None
            if isinstance(info, list) and info and isinstance(info[0].get("url"), str):
                return info[0]["url"]
        return None

    def download_image(self, url: str) -> tuple[bytes, str]:
        """封装图片下载逻辑"""
        try:
            response = self._request_with_proxy_fallback(
                self.http_client.request,
                "GET",
                url,
                allow_redirects=True,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Accept": "image/*",
                },
            )
        except Exception as exc:
            host = urlsplit(url).netloc or "unknown-host"
            raise OperatorResponseError(
                f"PRTS 图片下载失败（host={host}）：{type(exc).__name__}: {exc}"
            ) from exc
        content = response.content
        content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise OperatorResponseError(f"响应内容不是图片：{content_type}")
        if len(content) > 15 * 1024 * 1024:
            raise OperatorResponseError("图片文件超过 15 MiB 限制")
        return content, content_type

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict:
        """封装 GET json 逻辑"""
        request_headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
            **kwargs.pop("headers", {}),
        }
        try:
            return self._request_with_proxy_fallback(
                self.http_client.request_json,
                method,
                url,
                headers=request_headers,
                **kwargs,
            )
        except OperatorResponseError:
            raise
        except Exception as exc:
            params = kwargs.get("params")
            operation = "unknown"
            target = ""
            if isinstance(params, dict):
                operation = str(params.get("action") or operation)
                if params.get("page"):
                    target = f", page={params['page']!r}"
                elif params.get("titles"):
                    target = f", titles={params['titles']!r}"
            host = urlsplit(url).netloc or "unknown-host"
            raise OperatorResponseError(
                "PRTS API 请求失败"
                f"（method={method}, host={host}, action={operation}{target}）："
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _request_with_proxy_fallback(
        self,
        request_method: Any,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """
        PRTS 在部分环境代理下会提前关闭 TLS 连接。

        默认先直连，直连失败时再按 HTTP 客户端原配置（包括环境代理）重试一次。
        显式传入 proxies 时尊重调用方配置，不自动切换。
        """
        if not self.bypass_environment_proxy or "proxies" in kwargs:
            return request_method(method, url, **kwargs)

        direct_kwargs = dict(kwargs)
        direct_kwargs["proxies"] = {"http": "", "https": ""}
        try:
            return request_method(method, url, **direct_kwargs)
        except Exception as direct_exc:
            self._log_retry(
                "PRTS 直连请求失败，将按 HTTP 客户端代理配置重试"
                f"（method={method}, host={urlsplit(url).netloc or 'unknown-host'}）",
                direct_exc,
            )
            return request_method(method, url, **kwargs)

    def _log_retry(self, message: str, exc: Exception) -> None:
        """记录已进入恢复分支的异常 traceback。"""
        if self.logger is None:
            return
        warning_method = getattr(self.logger, "warning", None)
        if not callable(warning_method):
            warning_method = getattr(self.logger, "warn", None)
        if callable(warning_method):
            warning_method(
                f"{message}：{type(exc).__name__}: {exc}",
                exc_info=True,
            )
