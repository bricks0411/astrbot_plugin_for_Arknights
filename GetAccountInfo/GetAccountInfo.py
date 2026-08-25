# GetAccountInfo/GetAccountInfo.py
import asyncio

from urllib.parse import urlencode
from .HeaderBuilder import build_sign_headers
from .model import RequestResultOfAccountInfo
from ..network.HttpClient import HttpClient
from ..network.exceptions import HttpClientError
from ..network.validation import (
    require_dict,
    require_int,
    require_optional_str,
)

def _response_message(result: dict, default: str) -> str:
    for field in ("msg", "message"):
        message = require_optional_str(result.get(field), field)
        if message:
            return message
    return default

class GetAccountInfo:

    BASE_ACCOUNT_INFO_URL = "https://zonai.skland.com/api/v1/game/player/info"

    REQUEST_TIMEOUT = 10
    USER_AGENT = "Skland/1.32.1 (com.hypergryph.skland; build:103201004; Android 33; ) Okhttp/4.11.0"

    def __init__(self, http_client: HttpClient):
        """初始化类方法"""
        self.http_client = http_client


    def _get_account_info(
        self,
        uid: str,
        cred: str,
        token: str
    ) -> RequestResultOfAccountInfo:
        """使用 http 请求获取传入的角色数据"""
        if not uid or not cred or not token:
            return RequestResultOfAccountInfo (
                status  = False,
                message = "cred、token 和 uid 均不能为空"
            )
        url = (
            f"{self.BASE_ACCOUNT_INFO_URL}?"
            f"{urlencode({'uid': uid})}"
        )
        headers = {
            **build_sign_headers(
                url,
                cred,
                token
            ),
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        code = None
        try:
            result = self.http_client.request_json(
                "GET",
                url,
                headers  = headers
            )

            code = require_int(result.get("code"), "code")
            if code == 0:
                data = require_dict(result.get("data"), "data")
                return RequestResultOfAccountInfo (
                    status  = True,
                    message = "角色信息获取成功",
                    code    = code,
                    data    = data
                )
            else:
                return RequestResultOfAccountInfo (
                    status  = False,
                    code    = code,
                    message = _response_message(
                        result, 
                        f"角色信息获取失败：code={code}"
                    )
                )
        except HttpClientError as exc:
            return RequestResultOfAccountInfo (
                status  = False,
                code    = code,
                message = str(exc)
            )


    async def aget_account_info(
        self,
        uid: str,
        cred: str,
        token: str
    ) -> RequestResultOfAccountInfo:
        """执行角色详细数据请求逻辑"""
        return await asyncio.to_thread (
            self._get_account_info,
            uid,
            cred,
            token
        )
