# GetDoctorInfo/DoctorInfoHandler.py
import asyncio

from .models import RequestResultOfDoctorInfo
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
            # 检查状态码类型是否为 int
            status = require_int(result.get("status"), "status")
            message = require_optional_str(result.get("msg"), "msg")

            # 状态码为 0，表示请求成功
            if status == 0:
                # 类型检查逻辑
                data = require_dict(result.get("data"), "data")
                app_info_list = require_dict_list(data.get("list"), "data.list")
                for index, item in enumerate(app_info_list):
                    require_str(item.get("appCode"), f"data.list[{index}].appCode")

                app_info = None
                if app_info_list:
                    app_info = app_info_list[0]

                for item in app_info_list:
                    if item.get("appCode") == self.APP_CODE:
                        app_info = item
                        break

                if not app_info:
                    return RequestResultOfDoctorInfo (
                        status  = False,
                        phone   = phone,
                        token   = token,
                        message = "未找到账号绑定信息"
                    )

                binding_list = require_dict_list(
                    app_info.get("bindingList"),
                    "data.list[].bindingList",
                )
                for index, item in enumerate(binding_list):
                    require_bool(
                        item.get("isDefault"),
                        f"data.list[].bindingList[{index}].isDefault",
                    )
                    require_bool(
                        item.get("isDeleted"),
                        f"data.list[].bindingList[{index}].isDeleted",
                    )

                binding_info = binding_list[0] if binding_list else None
                for item in binding_list:
                    if item.get("isDefault") and not item.get("isDeleted"):
                        binding_info = item
                        break

                if not binding_info:
                    return RequestResultOfDoctorInfo (
                        status  = False,
                        phone   = phone,
                        token   = token,
                        message = "未找到角色绑定信息"
                    )

                uid = require_str(
                    binding_info.get("uid"),
                    "data.list[].bindingList[].uid",
                )
                nickname = require_str(
                    binding_info.get("nickName"),
                    "data.list[].bindingList[].nickName",
                )

                return RequestResultOfDoctorInfo (
                    status   = True,
                    appCode  = require_str(
                        app_info.get("appCode"),
                        "data.list[].appCode",
                    ),
                    phone    = phone,
                    token    = token,
                    uid      = uid,
                    nickName = nickname,
                    message  = message
                )
            else:
                return RequestResultOfDoctorInfo (
                    status  = False,
                    phone   = phone,
                    token   = token,
                    message = message
                )

        except HttpClientError as exc:
            return RequestResultOfDoctorInfo (
                status  = False,
                phone   = phone,
                token   = token,
                message = str(exc)
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
