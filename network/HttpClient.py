# network/HttpClient.py
import requests

# Any 表示任意类型。即一个变量可以接受任何 python 类型的值
from typing import Any

from .exceptions import (
    InvalidResponseError,
    NetworkRequestError,
    RequestTimeoutError
)

class HttpClient:

    DEFAULT_TIMEOUT = 10
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        reuse_connections: bool = False,
    ):
        """初始化统一 HTTP 客户端的超时时间和 User-Agent"""
        self.timeout = timeout
        self.user_agent = user_agent
        """
        request.Session()
        带状态的请求客户端对象，实现 cookie 映射与存储、TCP 连接池（复用 TCP 连接）、共享配置与自动处理重定向等功能
        可以理解成一个含有多个标签页的浏览器实例，共享同一个连接池与配置，各自独立存储 cookie
        """
        self.session = requests.Session() if reuse_connections else None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any
    ) -> requests.Response:
        """发送 HTTP 请求，并将 requests 异常转换为项目统一异常"""
        request_headers = {
            "User-Agent": self.user_agent,
            **(headers or {}),
        }
        request_method = (
            self.session.request
            if self.session is not None
            else requests.request
        )

        try:
            response = request_method(
                method  = method,
                url     = url,
                headers = request_headers,
                timeout = self.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout as exc:
            raise RequestTimeoutError (
                f"服务器未在 {1000 * self.timeout}ms 内返回数据，请求超时"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise NetworkRequestError (
                f"HTTP 请求失败：{type(exc).__name__}"
            ) from exc
        
    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any
    ) -> dict:
        """发送 HTTP 请求并校验响应内容是否为 JSON 对象"""
        response = self.request(
            method,
            url,
            headers = headers,
            **kwargs
        )

        try:
            result = response.json()
        except ValueError as exc:
            raise InvalidResponseError (
                "服务器返回非法 / 不被支持的数据"
            ) from exc
        
        if not isinstance(result, dict):
            raise InvalidResponseError (
                "服务器返回的 json 不是对象"
            )
        
        return result

    def close(self) -> None:
        """关闭 Session 及其连接池。"""
        if self.session is not None:
            self.session.close()

    def temporary_session(self) -> "HttpClient":
        """创建继承当前配置、由调用方及时关闭的临时连接池客户端。"""
        return HttpClient(
            timeout             =   self.timeout,
            user_agent          =   self.user_agent,
            reuse_connections   =   True,
        )

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
