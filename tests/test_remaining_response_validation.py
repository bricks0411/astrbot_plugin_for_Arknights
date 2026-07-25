import unittest

from ..GachaHistory.GetGachaHistory import (
    OfficialGetGachaHistory,
)
from ..GetDoctorInfo.OfficialDoctorInfoHandler import (
    OfficialDoctorInfoHandler,
)
from ..GetDoctorInfo.models import RequestResultOfDoctorInfo
from ..network.exceptions import NetworkRequestError


class _JsonStub:

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.temporary_session_calls = 0
        self.close_calls = 0

    def temporary_session(self):
        self.temporary_session_calls += 1
        return self

    def close(self):
        self.close_calls += 1

    def request_json(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _AuthenticatedGachaClient(OfficialGetGachaHistory):

    def _get_u8_token(self, grant_token, uid):
        return "u8-token"

    def _get_role_cookie(self, u8_token):
        return "role-cookie"


def _user_info():
    return RequestResultOfDoctorInfo(
        status=True,
        phone="13800000000",
        token="grant-token",
        uid="12345",
        nickName="Doctor",
    )


class DoctorInfoValidationTests(unittest.TestCase):

    def test_valid_doctor_info_is_parsed(self):
        client = _JsonStub([{
            "status": 0,
            "msg": "OK",
            "data": {
                "list": [{
                    "appCode": "arknights",
                    "bindingList": [{
                        "uid": "12345",
                        "nickName": "Doctor",
                        "isDefault": True,
                        "isDeleted": False,
                    }],
                }],
            },
        }])

        result = OfficialDoctorInfoHandler(client)._get_doctor_info(
            "grant-token",
            "13800000000",
        )

        self.assertTrue(result.status)
        self.assertEqual(result.uid, "12345")
        self.assertEqual(result.nickName, "Doctor")

    def test_business_failure_preserves_server_message(self):
        client = _JsonStub([{
            "status": 100,
            "msg": "登录状态失效",
            "data": None,
        }])

        result = OfficialDoctorInfoHandler(client)._get_doctor_info(
            "grant-token",
            "13800000000",
        )

        self.assertFalse(result.status)
        self.assertEqual(result.message, "登录状态失效")

    def test_null_binding_data_becomes_invalid_response(self):
        client = _JsonStub([{"status": 0, "msg": "OK", "data": None}])

        result = OfficialDoctorInfoHandler(client)._get_doctor_info(
            "grant-token",
            "13800000000",
        )

        self.assertFalse(result.status)
        self.assertIn("data", result.message)

    def test_invalid_uid_is_rejected(self):
        client = _JsonStub([{
            "status": 0,
            "msg": "OK",
            "data": {
                "list": [{
                    "appCode": "arknights",
                    "bindingList": [{
                        "uid": None,
                        "nickName": "Doctor",
                        "isDefault": True,
                        "isDeleted": False,
                    }],
                }],
            },
        }])

        result = OfficialDoctorInfoHandler(client)._get_doctor_info(
            "grant-token",
            "13800000000",
        )

        self.assertFalse(result.status)
        self.assertIn("uid", result.message)


class PoolListValidationTests(unittest.TestCase):

    def test_pool_list_checks_each_pool_id(self):
        http_client = _JsonStub([{
            "code": 0,
            "msg": "",
            "data": [{"id": "normal", "name": "标准寻访"}],
        }])
        client = _AuthenticatedGachaClient(http_client)

        result = client._get_pool_list(_user_info())

        self.assertTrue(result.status)
        self.assertEqual(result.pool_list, [{"id": "normal", "name": "标准寻访"}])
        self.assertEqual(result.message, "请求成功")

    def test_nonzero_pool_code_is_a_business_failure(self):
        http_client = _JsonStub([{
            "code": 403,
            "msg": "登录已过期",
            "data": None,
        }])

        result = _AuthenticatedGachaClient(http_client)._get_pool_list(
            _user_info()
        )

        self.assertFalse(result.status)
        self.assertEqual(result.code, 403)
        self.assertEqual(result.message, "登录已过期")

    def test_pool_data_must_be_a_list(self):
        http_client = _JsonStub([{"code": 0, "msg": "", "data": None}])

        result = _AuthenticatedGachaClient(http_client)._get_pool_list(
            _user_info()
        )

        self.assertFalse(result.status)
        self.assertIn("data", result.message)


class GachaHistoryValidationTests(unittest.TestCase):

    def test_history_checks_list_and_has_more(self):
        http_client = _JsonStub([{
            "code": 0,
            "msg": "",
            "data": {"list": [{"pos": 1}], "hasMore": False},
        }])
        client = OfficialGetGachaHistory(http_client)

        result = client._get_gacha_history_by_pool(
            _user_info(),
            "normal",
            "u8-token",
            "role-cookie",
        )

        self.assertTrue(result.status)
        self.assertEqual(result.gacha_history, [{"pos": 1}])

    def test_has_more_must_be_boolean(self):
        http_client = _JsonStub([{
            "code": 0,
            "msg": "",
            "data": {"list": [], "hasMore": 0},
        }])
        client = OfficialGetGachaHistory(http_client)

        result = client._get_gacha_history_by_pool(
            _user_info(),
            "normal",
            "u8-token",
            "role-cookie",
        )

        self.assertFalse(result.status)
        self.assertIn("hasMore", result.message)

    def test_pagination_uses_checked_cursor_fields(self):
        http_client = _JsonStub([
            {
                "code": 0,
                "msg": "",
                "data": {
                    "list": [{"pos": 0, "gachaTs": "123456"}],
                    "hasMore": True,
                },
            },
            {
                "code": 0,
                "msg": "",
                "data": {"list": [], "hasMore": False},
            },
        ])
        client = OfficialGetGachaHistory(http_client)

        result = client._get_gacha_history_by_pool(
            _user_info(),
            "normal",
            "u8-token",
            "role-cookie",
        )

        self.assertTrue(result.status)
        second_params = http_client.requests[1][2]["params"]
        self.assertEqual(second_params["pos"], 0)
        self.assertEqual(second_params["gachaTs"], "123456")
        self.assertEqual(http_client.temporary_session_calls, 1)
        self.assertEqual(http_client.close_calls, 1)

    def test_network_errors_share_http_client_error_path(self):
        http_client = _JsonStub([NetworkRequestError("网络连接失败")])
        client = OfficialGetGachaHistory(http_client)

        result = client._get_gacha_history_by_pool(
            _user_info(),
            "normal",
            "u8-token",
            "role-cookie",
        )

        self.assertFalse(result.status)
        self.assertEqual(result.message, "网络连接失败")


if __name__ == "__main__":
    unittest.main()
