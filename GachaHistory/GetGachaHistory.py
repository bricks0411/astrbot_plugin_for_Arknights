# GachaHistory/GetGachaHistory.py
import asyncio

from ..GetDoctorInfo.models import RequestResultOfDoctorInfo
from .models import RequestResultOfPoolList, RequestResultOfGachaHistory
from ..network.HttpClient import HttpClient
from ..network.exceptions import (
    HttpClientError,
    InvalidResponseError,
    RequestTimeoutError
)

class OfficialGetGachaHistory:

    BASE_REQUEST_POOL_URL = "https://ak.hypergryph.com/user/api/inquiry/gacha/cate"
    BASE_REQUEST_GACHA_HISTORY_URL = "https://ak.hypergryph.com/user/api/inquiry/gacha/history"
    BASE_REQUEST_U8_TOKEN_URL = "https://binding-api-account-prod.hypergryph.com/account/binding/v1/u8_token_by_uid"
    BASE_REQUEST_ROLE_LOGIN_URL = "https://ak.hypergryph.com/user/api/role/login"
    REQUEST_TIMEOUT = 10
    GACHA_PAGE_SIZE = 50
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

    def __init__(self, http_client: HttpClient):
        """初始化官方抽卡记录客户端。"""
        self.http_client = http_client

    def _base_headers(self) -> dict[str, str]:
        """构造访问明日方舟用户中心接口的基础请求头。"""
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://ak.hypergryph.com/user/headhunting",
            "User-Agent": self.USER_AGENT,
        }


    def _authorized_headers(self, u8_token: str) -> dict[str, str]:
        """卡池信息和抽卡记录接口：共用请求头"""
        return {
            **self._base_headers(),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "x-role-token": u8_token,
        }


    def _get_u8_token(self, grant_token: str, uid: str) -> str | None:
        """使用授权令牌和 UID 换取角色 U8 Token。"""
        headers = {
            **self._base_headers(),
            "Content-Type": "application/json",
            "Origin": "https://ak.hypergryph.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        payload = {
            "token": grant_token,
            "uid": uid,
        }
        result = self.http_client.request_json(
            "POST",
            self.BASE_REQUEST_U8_TOKEN_URL,
            json=payload,
            headers=headers
        )
        return result.get("data", {}).get("token")


    def _get_role_cookie(self, u8_token: str) -> str | None:
        """登录指定角色并返回用户中心会话 Cookie。"""
        headers = {
            **self._base_headers(),
            "Content-Type": "application/json",
            "Origin": "https://ak.hypergryph.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        payload = {
            "token": u8_token,
            "source_from": "",
            "share_type": "",
            "share_by": "",
        }
        response = self.http_client.request(
            "POST",
            self.BASE_REQUEST_ROLE_LOGIN_URL,
            json=payload,
            headers=headers
        )
        return response.cookies.get("ak-user-center")


    def _get_pool_list(
        self,
        user_info: RequestResultOfDoctorInfo
    ) -> RequestResultOfPoolList:
        """卡池列表获取逻辑"""
        if not user_info:
            return RequestResultOfPoolList (
                status  = False,
                message = "用户信息不能为空"
            )

        uid = user_info.uid
        grant_token = user_info.token

        try:
            u8_token = self._get_u8_token(grant_token, uid)
            if not u8_token:
                return RequestResultOfPoolList (
                    status  = False,
                    message = "获取角色 token 失败"
                )

            role_cookie = self._get_role_cookie(u8_token)
            if not role_cookie:
                return RequestResultOfPoolList (
                    status  = False,
                    message = "角色登录失败，请稍后再试"
                )

            headers = self._authorized_headers(u8_token)
            cookies = {
                "ak-user-center": role_cookie
            }

            result = self.http_client.request_json(
                "GET",
                self.BASE_REQUEST_POOL_URL,
                params={
                    "uid": uid
                },
                headers=headers,
                cookies=cookies
            )

            code = result.get("code")
            if code is None:
                return RequestResultOfPoolList (
                    status  = False,
                    message = result.get("message") or result.get("msg") or "请求失败"
                )

            if code != 0:
                return RequestResultOfPoolList (
                    status  = False,
                    code    = code,
                    message = result.get("msg") or result.get("message") or "请求失败"
                )

            pool_list = result.get("data")
            if not isinstance(pool_list, list):
                return RequestResultOfPoolList (
                    status  = False,
                    code    = code,
                    message = "卡池列表返回格式异常"
                )

            return RequestResultOfPoolList (
                status      = True,
                message     = result.get("msg") or result.get("message") or "请求成功",
                code        = code,
                pool_list   = pool_list
            )
        except RequestTimeoutError as exc:
            return RequestResultOfPoolList (
                status  = False,
                message = "服务器没有在 10000ms 内返回数据，请求超时"
            )
        except InvalidResponseError as exc:
            return RequestResultOfPoolList (
                status  = False,
                message = "获取到非法 / 不被支持的数据"
            )
        except (KeyError, TypeError, IndexError):
            return RequestResultOfPoolList (
                status  = False,
                message = "返回数据缺少必要字段"
            )
        except HttpClientError as exc:
            return RequestResultOfPoolList (
                status  = False,
                message = f"请求失败！错误类型 {exc}"
            )


    async def aget_pool_list(
        self,
        user_info: RequestResultOfDoctorInfo
    ) -> RequestResultOfPoolList:
        """创建单独线程执行卡池列表获取逻辑，并将数据返回给 main.py"""
        return await asyncio.to_thread(
            self._get_pool_list,
            user_info
        )


    def _get_gacha_history_by_pool(
        self,
        user_info : RequestResultOfDoctorInfo,
        pool_type: str,
        u8_token: str,
        role_cookie: str
    ) -> RequestResultOfGachaHistory:
        """按照卡池种类分页获取全部抽卡记录。"""
        uid = user_info.uid
        try:
            headers = self._authorized_headers(u8_token)
            cookies = {
                "ak-user-center": role_cookie
            }
            gacha_history = []
            cursor = None
            seen_cursors = set()

            while True:
                params = {
                    "uid": uid,
                    "category": pool_type,
                    "size": self.GACHA_PAGE_SIZE,
                }
                if cursor is not None:
                    params["pos"], params["gachaTs"] = cursor

                result = self.http_client.request_json(
                    "GET",
                    self.BASE_REQUEST_GACHA_HISTORY_URL,
                    params=params,
                    headers=headers,
                    cookies=cookies
                )

                code = result.get("code")
                if code is None:
                    return RequestResultOfGachaHistory (
                        status  = False,
                        message = result.get("msg") or result.get("message") or "请求失败"
                    )

                if code != 0:
                    return RequestResultOfGachaHistory (
                        status  = False,
                        code    = code,
                        message = result.get("msg") or result.get("message") or "请求失败"
                    )

                data = result.get("data")
                page_records = data.get("list") if isinstance(data, dict) else None
                if not isinstance(page_records, list) or not isinstance(data.get("hasMore"), bool):
                    return RequestResultOfGachaHistory (
                        status  = False,
                        code    = code,
                        message = "抽卡记录返回格式异常"
                    )

                gacha_history.extend(page_records)
                if not data["hasMore"]:
                    break

                cursor_record = next(
                    (
                        record
                        for record in reversed(page_records)
                        if isinstance(record, dict) and record.get("pos") == 0
                    ),
                    None,
                )
                if cursor_record is None or cursor_record.get("gachaTs") is None:
                    return RequestResultOfGachaHistory (
                        status  = False,
                        code    = code,
                        message = "抽卡记录缺少下一页游标"
                    )

                cursor = (cursor_record["pos"], cursor_record["gachaTs"])
                if cursor in seen_cursors:
                    return RequestResultOfGachaHistory (
                        status  = False,
                        code    = code,
                        message = "抽卡记录分页游标重复"
                    )
                seen_cursors.add(cursor)

            return RequestResultOfGachaHistory (
                status          = True,
                message         = result.get("msg") or result.get("message") or "请求成功",
                code            = code,
                gacha_history   = gacha_history
            )
        except RequestTimeoutError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = "服务器没有在 10000ms 内返回数据，请求超时"
            )
        except InvalidResponseError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = "获取到非法 / 不被支持的数据"
            )
        except (KeyError, TypeError, IndexError):
            return RequestResultOfGachaHistory (
                status  = False,
                message = "返回数据缺少必要字段"
            )
        except HttpClientError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = f"请求失败！错误类型 {exc}"
            )


    def _get_gacha_history(
        self,
        user_info: RequestResultOfDoctorInfo,
        pool_list: list[dict]
    ) -> RequestResultOfGachaHistory:
        """抽卡记录获取逻辑"""
        if not user_info:
            return RequestResultOfGachaHistory (
                status  = False,
                message = "用户信息不能为空"
            )

        if not pool_list:
            return RequestResultOfGachaHistory (
                status  = False,
                message = "没有获取到卡池列表"
            )

        uid = user_info.uid
        grant_token = user_info.token
        try:
            u8_token = self._get_u8_token(grant_token, uid)
            if not u8_token:
                return RequestResultOfGachaHistory (
                    status  = False,
                    message = "获取角色 token 失败"
                )
            role_cookie = self._get_role_cookie(u8_token)
            if not role_cookie:
                return RequestResultOfGachaHistory (
                    status  = False,
                    message = "角色登录失败，请稍后再试"
                )
        except RequestTimeoutError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = "服务器没有在 10000ms 内返回数据，请求超时"
            )
        except (InvalidResponseError, TypeError) as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = "认证接口返回了无效数据"
            )
        except HttpClientError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = f"请求失败！错误类型 {exc}"
            )

        gacha_history = []
        success_message = "请求成功"

        for pool in pool_list:
            if not isinstance(pool, dict) or not pool.get("id"):
                return RequestResultOfGachaHistory (
                    status  = False,
                    message = "卡池信息缺少必要字段"
                )
            result = self._get_gacha_history_by_pool(
                user_info,
                pool.get("id"),
                u8_token,
                role_cookie
            )
            if result.status is False:
                return RequestResultOfGachaHistory (
                    status  = False,
                    message = result.message
                )
            if result.code != 0:
                return RequestResultOfGachaHistory (
                    status  = False,
                    code    = result.code,
                    message = result.message
                )

            # 审查问题是最终返回值直接读取循环变量 result，代码依赖最后一次循环一定执行且成功
            # 每轮成功后显式保存消息，使聚合结果的数据来源清楚并避免循环变量泄漏到返回阶段
            if result.message:
                success_message = result.message

            for record in result.gacha_history or []:
                if isinstance(record, dict):
                    record["category"] = pool["id"]
                    gacha_history.append(record)

        return RequestResultOfGachaHistory (
            status          = True,
            message         = success_message,
            code            = 0,
            gacha_history   = gacha_history
        )


    async def aget_gacha_history(
        self,
        user_info: RequestResultOfDoctorInfo,
        pool_list: list[dict]
    ) -> RequestResultOfGachaHistory:
        """创建单独线程执行抽卡逻辑，并将数据返回给 main.py"""
        return await asyncio.to_thread(
            self._get_gacha_history,
            user_info,
            pool_list
        )
