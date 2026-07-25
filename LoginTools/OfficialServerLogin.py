# LoginTools/OfficialServerLogin.py
import asyncio

from .models import RequestResultOfVerificationCode, RequestResultOfAuth, RequestResultOfAccountToken
from ..network.HttpClient import HttpClient
from ..network.exceptions import (
    HttpClientError
)
from ..network.validation import (
    require_dict,
    require_int,
    require_optional_str,
    require_str,
)


def _response_message(result: dict, default: str) -> str:
    for field in ("msg", "message", "error"):
        message = require_optional_str(result.get(field), field)
        if message:
            return message
    return default

class OfficialServerLogin:

    GET_CODE_URL = "https://as.hypergryph.com/general/v1/send_phone_code"
    GET_TOKEN_URL = "https://as.hypergryph.com/user/auth/v2/token_by_phone_code"
    GET_ACCOUNT_TOKEN_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
    GRANT_APP_CODE = "be36d44aa36bfb5b"

    REQUEST_TIMEOUT = 10
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

    def __init__(
        self,
        http_client: HttpClient
    ):
        """初始化类方法"""
        self.http_client = http_client

    def _get_verification_code(
        self,
        phone: str
    ) -> RequestResultOfVerificationCode:
        """验证码获取逻辑"""
        if not phone:
            return RequestResultOfVerificationCode (
                status  = False,
                phone   = phone,
                message = "手机号不能为空"
            )

        payload = {
            "phone": phone,
            "type": 2
        }
        headers = {
            "Content-Type": "application/json"
        }

        try:
            result = self.http_client.request_json(
                "POST",
                self.GET_CODE_URL,
                json    = payload,
                headers = headers
            )

            status = require_int(result.get("status"), "status")
            msg = _response_message(
                result,
                "验证码发送成功" if status == 0 else "验证码发送失败",
            )

            if status == 0:
                return RequestResultOfVerificationCode (
                    status  = True,
                    phone   = phone,
                    message = msg
                )
            else:
                return RequestResultOfVerificationCode (
                    status  = False,
                    phone   = phone,
                    message = msg
                )
        except HttpClientError as exc:
            return RequestResultOfVerificationCode (
                status  = False,
                phone   = phone,
                message = str(exc),
            )

    async def aget_verification_code(
        self,
        phone: str
    ) -> RequestResultOfVerificationCode | None:
        """创建单独线程执行验证码获取逻辑，并将数据返回给 main.py"""
        return await asyncio.to_thread (
            self._get_verification_code,
            phone
        )

    def _get_auth_token(
        self,
        phone: str,
        verification_code: str | int
    ) -> RequestResultOfAuth:
        """通过验证码登录"""
        if not phone or not verification_code:
            return RequestResultOfAuth (
                status  = False,
                phone   = phone,
                message = "验证码或手机号不能为空"
            )

        payload = {
            "phone": phone,
            "code": verification_code
        }
        headers = {
            "Content-Type": "application/json"
        }
        try:
            result = self.http_client.request_json(
                "POST",
                self.GET_TOKEN_URL,
                json    = payload,
                headers = headers
            )

            status = require_int(result.get("status"), "status")
            if status == 0:
                data = require_dict(result.get("data"), "data")
                token = require_str(data.get("token"), "data.token")
                hgId = require_str(data.get("hgId"), "data.hgId")
                msg = require_str(result.get("msg"), "msg")
                return RequestResultOfAuth (
                    status  = True,
                    phone   = phone,
                    token   = token,
                    hgId    = hgId,
                    message = msg
                )
            else:
                msg = require_str(result.get("msg"), "msg")
                return RequestResultOfAuth (
                    status  = False,
                    phone   = phone,
                    message = msg
                )
        except HttpClientError as exc:
            return RequestResultOfAuth (
                status  = False,
                phone   = phone,
                message = str(exc)
            )

    async def aget_auth_token(
        self,
        phone: str,
        verification_code: str | int
    ) -> RequestResultOfAuth:
        """创建单独线程执行验证码登录逻辑，并将数据返回给 main.py"""
        return await asyncio.to_thread (
            self._get_auth_token,
            phone,
            verification_code
        )

    def _get_account_token(
        self,
        login_token: str,
        phone: str
    ) -> RequestResultOfAccountToken:
        """使用验证码登录 token 换取账号系统凭证"""
        if not login_token:
            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = "登录 token 不能为空"
            )

        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "Origin": "https://ak.hypergryph.com",
            "Pragma": "no-cache",
            "Referer": "https://ak.hypergryph.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": self.USER_AGENT,
        }
        payload = {
            "token": login_token,
            "appCode": self.GRANT_APP_CODE,
            "type": 1,
        }

        try:
            result = self.http_client.request_json(
                "POST",
                self.GET_ACCOUNT_TOKEN_URL,
                json    = payload,
                headers = headers
            )

            status = require_int(result.get("status"), "status")
            if status == 0:
                data = require_dict(result.get("data"), "data")
                account_token = require_str(data.get("token"), "data.token")
                return RequestResultOfAccountToken (
                    status       = True,
                    phone        = phone,
                    accountToken = account_token,
                    message      = _response_message(result, "账号凭证获取成功")
                )

            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = _response_message(
                    result,
                    f"grant token 获取失败：status={status}",
                )
            )
        except HttpClientError as exc:
            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = str(exc)
            )

    async def aget_account_token(
        self,
        login_token: str,
        phone: str
    ) -> RequestResultOfAccountToken:
        """创建单独线程执行账号凭证获取逻辑，并将数据返回给 main.py"""
        return await asyncio.to_thread (
            self._get_account_token,
            login_token,
            phone
        )
