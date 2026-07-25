# GachaHistory/GetGachaHistory.py
import asyncio

from ..GetDoctorInfo.models import RequestResultOfDoctorInfo
from .models import RequestResultOfPoolList, RequestResultOfGachaHistory
from ..network.HttpClient import HttpClient
from ..network.exceptions import HttpClientError
from ..network.validation import (
    require_bool,
    require_dict,
    require_dict_list,
    require_int,
    require_optional_str,
    require_str,
)


def _response_message(result: dict, default: str) -> str:
    for field in ("msg", "message"):
        message = require_optional_str(result.get(field), field)
        if message:
            return message
    return default


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
            json    = payload,
            headers = headers
        )
        status = require_int(result.get("status"), "status")
        if status != 0:
            return None
        data = require_dict(result.get("data"), "data")
        return require_str(data.get("token"), "data.token")


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
            json    = payload,
            headers = headers
        )
        return require_optional_str(
            response.cookies.get("ak-user-center"),
            "cookies.ak-user-center",
        )


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
                params  = {
                    "uid": uid
                },
                headers = headers,
                cookies = cookies
            )

            code = require_int(result.get("code"), "code")

            if code != 0:
                return RequestResultOfPoolList (
                    status  = False,
                    code    = code,
                    message = _response_message(result, "请求失败")
                )

            pool_list = require_dict_list(result.get("data"), "data")
            for index, pool in enumerate(pool_list):
                require_str(pool.get("id"), f"data[{index}].id")

            return RequestResultOfPoolList (
                status      = True,
                message     = _response_message(result, "请求成功"),
                code        = code,
                pool_list   = pool_list
            )
        except HttpClientError as exc:
            return RequestResultOfPoolList (
                status  = False,
                message = str(exc)
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
        page_http_client = self.http_client.temporary_session()
        try:
            headers = self._authorized_headers(u8_token)
            cookies = {
                "ak-user-center": role_cookie
            }
            gacha_history = []
            # 抽卡记录查询游标：tuple(pos, gachaTs)；定位抽卡记录查询偏移量
            cursor = None
            seen_cursors = set()

            # 轮询式请求，维护请求游标，每次根据最后一条记录移动游标，当 hasMore 字段为 False 时跳出循环
            while True:
                params = {
                    "uid": uid,
                    "category": pool_type,
                    "size": self.GACHA_PAGE_SIZE,
                }
                if cursor is not None:
                    params["pos"], params["gachaTs"] = cursor

                # 获取抽卡记录，每一页 50 条记录
                result = page_http_client.request_json(
                    "GET",
                    self.BASE_REQUEST_GACHA_HISTORY_URL,
                    params  = params,
                    headers = headers,
                    cookies = cookies
                )

                code = require_int(result.get("code"), "code")

                # 调试：输出返回数据
                # print(result)

                if code != 0:
                    return RequestResultOfGachaHistory (
                        status  = False,
                        code    = code,
                        message = _response_message(result, "请求失败")
                    )

                data = require_dict(result.get("data"), "data")
                page_records = require_dict_list(data.get("list"), "data.list")
                has_more = require_bool(data.get("hasMore"), "data.hasMore")

                gacha_history.extend(page_records)
                if not has_more:
                    break

                cursor_record = None
                for index in range(len(page_records) - 1, -1, -1):
                    record = page_records[index]
                    position = require_int(
                        record.get("pos"),
                        f"data.list[{index}].pos",
                    )
                    if position == 0:
                        cursor_record = record
                        break

                if cursor_record is None:
                    return RequestResultOfGachaHistory (
                        status  = False,
                        code    = code,
                        message = "抽卡记录缺少下一页游标"
                    )

                # 维护下一游标位
                cursor = (
                    require_int(cursor_record.get("pos"), "data.list[].pos"),
                    require_str(
                        cursor_record.get("gachaTs"),
                        "data.list[].gachaTs",
                    ),
                )
                if cursor in seen_cursors:
                    return RequestResultOfGachaHistory (
                        status  = False,
                        code    = code,
                        message = "抽卡记录分页游标重复"
                    )
                seen_cursors.add(cursor)

            return RequestResultOfGachaHistory (
                status          = True,
                message         = _response_message(result, "请求成功"),
                code            = code,
                gacha_history   = gacha_history
            )
        except HttpClientError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = str(exc)
            )
        finally:
            page_http_client.close()


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
        except HttpClientError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = str(exc)
            )

        gacha_history = []
        success_message = "请求成功"

        try:
            # 遍历获取到的卡池列表，根据对应卡池请求抽卡记录
            for index, pool in enumerate(pool_list):
                checked_pool = require_dict(pool, f"pool_list[{index}]")
                pool_id = require_str(
                    checked_pool.get("id"),
                    f"pool_list[{index}].id",
                )
                # 指定卡池名称与 ID，请求记录
                result = self._get_gacha_history_by_pool(
                    user_info,
                    pool_id,
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

                if result.message:
                    success_message = result.message

                for record_index, record in enumerate(result.gacha_history or []):
                    # 类型检查：dict
                    checked_record = require_dict(
                        record,
                        f"gacha_history[{record_index}]",
                    )
                    checked_record["category"] = pool_id
                    gacha_history.append(checked_record)
        except HttpClientError as exc:
            return RequestResultOfGachaHistory (
                status  = False,
                message = str(exc)
            )

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
