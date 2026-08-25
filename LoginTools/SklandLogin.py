# LoginTools/SklandLogin.py
import asyncio

from ..network.exceptions import HttpClientError
from ..network.HttpClient import HttpClient
from ..network.validation import (
    require_dict,
    require_int,
    require_optional_str,
    require_str,
)
from .models import (
    RefreshResultOfSklandToken,
    RequestResultOfSklandCred,
    RequestResultOfSklandGrantCode,
)


def _response_message(result: dict, default: str) -> str:
    for field in ("msg", "message", "error"):
        message = require_optional_str(result.get(field), field)
        if message:
            return message
    return default


class SklandLoginHandler:

    GET_GRANT_CODE_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
    GET_CRED_URL = "https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code"
    REFRESH_TOKEN_URL = "https://zonai.skland.com/api/v1/auth/refresh"
    SKLAND_APP_CODE = "4ca99fa6b56cc2ba"

    REQUEST_TIMEOUT = 10
    USER_AGENT = "Skland/1.32.1 (com.hypergryph.skland; build:103201004; Android 33; ) Okhttp/4.11.0"

    def __init__(
        self,
        http_client: HttpClient
    ):
        """初始化类方法"""
        self.http_client = http_client

    # region grant_code 获取逻辑

    def _get_grant_code(
        self,
        login_token: str,
        phone: str
    ) -> RequestResultOfSklandGrantCode:
        """通过 login_token 换取森空岛 grant_code"""
        if not login_token or not phone:
            return RequestResultOfSklandGrantCode (
                status      = False,
                phone       = phone,
                message     = "手机号或 login_token 均不能为空"
            )

        payload = {
            "appCode": self.SKLAND_APP_CODE,
            "token": login_token,
            "type": 0
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT
        }

        try:
            result = self.http_client.request_json(
                "POST",
                self.GET_GRANT_CODE_URL,
                json    = payload,
                headers = headers
            )

            status = require_int(result.get("status"), "status")
            msg = _response_message(result, "grant code 获取成功")
            if status == 0:
                data = require_dict(result.get("data"), "data")
                code = require_str(data.get("code"), "data.code")
                return RequestResultOfSklandGrantCode (
                    status      = True,
                    phone       = phone,
                    grant_code  = code,
                    message     = msg
                )
            else:
                return RequestResultOfSklandGrantCode (
                    status      = False,
                    phone       = phone,
                    message     = _response_message(
                        result,
                        f"grant code 获取失败：status = {status}"
                    )
                )
        except HttpClientError as exc:
            return RequestResultOfSklandGrantCode (
                status  = False,
                phone   = phone,
                message = str(exc)
            )

    async def aget_grant_code(
        self,
        login_token: str,
        phone: str
    ) -> RequestResultOfSklandGrantCode:
        """
        通过 login_token 换取森空岛 grant_code
        grant_code 是短期、一次性 token，只用于下一步森空岛凭据生成
        """
        return await asyncio.to_thread (
            self._get_grant_code,
            login_token,
            phone
        )

    # endregion

    # region cred 获取逻辑

    def _get_cred_by_grant_code(
        self,
        phone: str,
        grant_code: str
    ) -> RequestResultOfSklandCred:
        """
        grant_code 换取森空岛长期凭据
        成功响应通常包含以下结构
        {
            "code": 0,
            "message": "OK",
            "data": {
                "cred": "森空岛长期凭据",
                "token": "森空岛签名 token"
            }
        }
        """
        if not grant_code or not phone:
            return RequestResultOfSklandCred (
                status  = False,
                phone   = phone,
                message = "grant_code 与 phone 不能为空"
            )

        payload = {
            "code": grant_code,
            "kind": 1
        }
        headers = {
            "Content-type": "application/json",
            "User-Agent": self.USER_AGENT
        }

        try:
            result = self.http_client.request_json(
                "POST",
                self.GET_CRED_URL,
                json    = payload,
                headers = headers
            )

            code = require_int(result.get("code"), "code")
            msg = _response_message(result, "cred 获取成功")
            if code == 0:
                data = require_dict(result.get("data"), "data")
                cred = require_str(data.get("cred"), "data.cred")
                token = require_str(data.get("token"), "data.token")
                return RequestResultOfSklandCred (
                    status  = True,
                    phone   = phone,
                    cred    = cred,
                    token   = token,
                    message = msg
                )
            else:
                return RequestResultOfSklandCred (
                    status  = False,
                    phone   = phone,
                    message = _response_message(
                        result,
                        f"cred 获取失败：status={code}"
                    )
                )
        except HttpClientError as exc:
            return RequestResultOfSklandCred (
                status  = False,
                phone   = phone,
                message = str(exc)
            )


    async def aget_cred_by_grant_code(
        self,
        phone: str,
        grant_code: str
    ) -> RequestResultOfSklandCred:
        """
        使用 grant_code 换取森空岛长期凭据与签名 token
        返回数据中 cred 字段即为长期凭据，已加密存储在本地
        """
        return await asyncio.to_thread (
            self._get_cred_by_grant_code,
            phone,
            grant_code
        )

    # endregion

    # region token 刷新逻辑

    def _refresh_token_by_cred(
        self,
        cred: str
    ) -> RefreshResultOfSklandToken:
        """
        发送 cred 以更新 token
        请求数据时需要用 token 计算签名
        每次更新角色信息的时候都需要调用一次，以免数据请求失败
        """
        if not cred:
            return RefreshResultOfSklandToken (
                status  = False,
                cred    = cred,
                message = "cred 不能为空"
            )

        headers = {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
            "cred": cred
        }

        try:
            result = self.http_client.request_json(
                "GET",
                self.REFRESH_TOKEN_URL,
                headers = headers
            )

            code = require_int(result.get("code"), "code")
            if code == 0:
                data = require_dict(result.get("data"), "data")
                token = require_str(data.get("token"), "data.token")
                msg = _response_message(result, "token 刷新成功")
                return RefreshResultOfSklandToken (
                    status  = True,
                    cred    = cred,
                    token   = token,
                    message = msg
                )
            else:
                return RefreshResultOfSklandToken (
                    status  = False,
                    cred    = cred,
                    message = _response_message(
                        result,
                        f"token 刷新失败：code = {code}"
                    )
                )
        except HttpClientError as exc:
            return  RefreshResultOfSklandToken (
                status  = False,
                cred    = cred,
                message = str(exc)
            )

    async def arefresh_token_by_cred(
        self,
        cred: str
    ) -> RefreshResultOfSklandToken:
        """通过 cred 刷新本地保存的 token 签名"""
        return await asyncio.to_thread(
            self._refresh_token_by_cred,
            cred
        )

    # endregion
