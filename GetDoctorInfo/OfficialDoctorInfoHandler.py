# GetDoctorInfo/DoctorInfoHandler.py
import asyncio

from .models import RequestResultOfDoctorInfo
from ..network.HttpClient import HttpClient
from ..network.exceptions import (
    HttpClientError,
    InvalidResponseError,
    RequestTimeoutError
)

class OfficialDoctorInfoHandler:

    BASE_REQUEST_URL = "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list"
    APP_CODE = "arknights"
    REQUEST_TIMEOUT = 10
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

    def __init__(self, http_client: HttpClient):
        """初始化类方法"""
        self.http_client = http_client

    def _get_doctor_info(
        self,
        token: str,
        phone: str
    ) -> RequestResultOfDoctorInfo:
        """玩家信息获取逻辑"""
        if not token or not phone:
            return RequestResultOfDoctorInfo (
                status  = False,
                phone   = phone,
                token   = token,
                message = "用户 token 与手机号码均不能为空"
            )

        try:
            result = self.http_client.request_json(
                "GET",
                self.BASE_REQUEST_URL,
                params={
                    "token": token,
                    "appCode": self.APP_CODE,
                },
            )

            status = result.get("status")
            message = result.get("msg")

            if status == 0:
                app_info_list = result["data"]["list"]
                app_info = next(
                    (
                        item for item in app_info_list
                        if item.get("appCode") == self.APP_CODE
                    ),
                    app_info_list[0] if app_info_list else None
                )

                if not app_info:
                    return RequestResultOfDoctorInfo (
                        status  = False,
                        phone   = phone,
                        token   = token,
                        message = "未找到账号绑定信息"
                    )

                binding_list = app_info.get("bindingList", [])
                binding_info = next(
                    (
                        item for item in binding_list
                        if item.get("isDefault") and not item.get("isDeleted")
                    ),
                    binding_list[0] if binding_list else None
                )

                if not binding_info:
                    return RequestResultOfDoctorInfo (
                        status  = False,
                        phone   = phone,
                        token   = token,
                        message = "未找到角色绑定信息"
                    )

                return RequestResultOfDoctorInfo (
                    status   = True,
                    appCode  = app_info.get("appCode"),
                    phone    = phone,
                    token    = token,
                    uid      = binding_info.get("uid"),
                    nickName = binding_info.get("nickName"),
                    message  = message
                )
            else:
                return RequestResultOfDoctorInfo (
                    status  = False,
                    phone   = phone,
                    token   = token,
                    message = message
                )

        except RequestTimeoutError as exc:
            return RequestResultOfDoctorInfo (
                status  = False,
                phone   = phone,
                token   = token,
                message = "服务器没有在 10000ms 内返回数据，请求超时"
            )
        except InvalidResponseError as exc:
            return RequestResultOfDoctorInfo (
                status  = False,
                phone   = phone,
                token   = token,
                message = "获取到非法 / 不被支持的数据"
            )
        except (KeyError, TypeError, IndexError):
            return RequestResultOfDoctorInfo (
                status  = False,
                phone   = phone,
                token   = token,
                message = "返回数据缺少必要字段"
            )
        except HttpClientError as exc:
            return RequestResultOfDoctorInfo (
                status  = False,
                phone   = phone,
                token   = token,
                message = f"请求失败！错误类型：{type(exc).__name__}"
            )


    async def aget_doctor_info(
        self,
        token: str,
        phone: str
    ) -> RequestResultOfDoctorInfo:
        """创建单独线程获取玩家信息，并将数据返回给 main.py"""
        return await asyncio.to_thread(
            self._get_doctor_info,
            token,
            phone
        )
