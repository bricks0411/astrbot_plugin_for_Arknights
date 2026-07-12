# network/HttpClient.py
import requests

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
        user_agent: str = DEFAULT_USER_AGENT
    ):
        self.timeout = timeout
        self.user_agent = user_agent

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any
    ) -> requests.Response:
        request_headers = {
            "User-Agent": self.user_agent,
            **(headers or {})
        }

        try:
            response = requests.request(
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
