# LoginTools/OfficialServerLogin.py
import asyncio
import requests

from .models import RequestResultOfVerificationCode, RequestResultOfAuth, RequestResultOfAccountToken

class OfficialServerLogin:

    GET_CODE_URL = "https://as.hypergryph.com/general/v1/send_phone_code"
    GET_TOKEN_URL = "https://as.hypergryph.com/user/auth/v2/token_by_phone_code"
    GET_ACCOUNT_TOKEN_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
    GRANT_APP_CODE = "be36d44aa36bfb5b"

    REQUEST_TIMEOUT = 10
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

    def __init__(self):
        """初始化逻辑"""

    def _get_verification_code(
        self,
        phone: str | int
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
            response = requests.post(
                self.GET_CODE_URL,
                json    = payload,
                timeout = self.REQUEST_TIMEOUT,
                headers = headers
            )
            result = response.json()

            msg = result["msg"]
            status = result["status"]

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
        except requests.exceptions.Timeout:
            return RequestResultOfVerificationCode (
                status  = False,
                phone   = phone,
                message = "服务器未在 10000 ms 内返回数据，请求超时"
            )
        except ValueError:
            return RequestResultOfVerificationCode (
                status  = False,
                phone   = phone,
                message = "获取到非法 / 不被支持的返回数据"
            )
        except requests.exceptions.RequestException as exc:
            return RequestResultOfVerificationCode (
                status  = False,
                phone   = phone,
                message = f"请求失败，错误类型：{exc}"
            )

    async def aget_verification_code(
        self,
        phone: str | int
    ) -> RequestResultOfVerificationCode | None:
        """创建单独线程执行验证码获取逻辑，并将数据返回给 main.py"""
        return await asyncio.to_thread (
            self._get_verification_code,
            phone
        )

    def _get_auth_token(
        self,
        phone: str | int,
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
            response = requests.post(
                self.GET_TOKEN_URL,
                json    = payload,
                timeout = self.REQUEST_TIMEOUT,
                headers = headers
            )
            result = response.json()

            status = result["status"]
            if status == 0:
                token = result["data"]["token"]
                hgId = result["data"]["hgId"]
                msg = result["msg"]
                return RequestResultOfAuth (
                    status  = True,
                    phone   = phone,
                    token   = token,
                    hgId    = hgId,
                    message = msg
                )
            else:
                msg = result["msg"]
                return RequestResultOfAuth (
                    status  = False,
                    phone   = phone,
                    message = msg
                )
        except requests.exceptions.Timeout:
            return RequestResultOfAuth (
                status  = False,
                phone   = phone,
                message = "服务器未在 10000ms 内返回数据，请求超时"
            )
        except ValueError:
            return RequestResultOfAuth (
                status  = False,
                phone   = phone,
                message = "获取到非法 / 不被支持的数据"
            )
        except requests.exceptions.RequestException as exc:
            return RequestResultOfAuth (
                status  = False,
                phone   = phone,
                message = f"请求失败，错误类型：{exc}"
            )

    async def aget_auth_token(
        self,
        phone: str | int,
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
        phone: str | int
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
            response = requests.post(
                self.GET_ACCOUNT_TOKEN_URL,
                json    = payload,
                timeout = self.REQUEST_TIMEOUT,
                headers = headers
            )
            result = response.json()

            if not isinstance(result, dict):
                return RequestResultOfAccountToken (
                    status  = False,
                    phone   = phone,
                    message = "返回数据格式异常"
                )

            status = result.get("status")
            msg = result.get("msg") or result.get("message") or result.get("error")
            account_token = result.get("data", {}).get("token")

            if status == 0 and account_token:
                return RequestResultOfAccountToken (
                    status       = True,
                    phone        = phone,
                    accountToken = account_token,
                    message      = msg
                )

            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = msg or f"grant token 获取失败：status={status}, keys=[{', '.join(result.keys())}]"
            )
        except requests.exceptions.Timeout:
            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = "服务器未在 10000ms 内返回数据，请求超时"
            )
        except ValueError:
            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = "获取到非法 / 不被支持的数据"
            )
        except (KeyError, TypeError):
            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = "返回数据缺少账号凭证字段"
            )
        except requests.exceptions.RequestException as exc:
            return RequestResultOfAccountToken (
                status  = False,
                phone   = phone,
                message = f"请求失败，错误类型：{exc}"
            )

    async def aget_account_token(
        self,
        login_token: str,
        phone: str | int
    ) -> RequestResultOfAccountToken:
        """创建单独线程执行账号凭证获取逻辑，并将数据返回给 main.py"""
        return await asyncio.to_thread (
            self._get_account_token,
            login_token,
            phone
        )
