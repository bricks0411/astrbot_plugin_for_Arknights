import unittest
from unittest.mock import patch

from ..GetAccountInfo import HeaderBuilder
from ..GetAccountInfo.GetAccountInfo import GetAccountInfo
from ..GetAccountInfo.HeaderBuilder import build_sign_headers
from ..network.exceptions import NetworkRequestError


class _JsonStub:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request_json(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class SignHeaderTests(unittest.TestCase):
    @patch.object(HeaderBuilder.time, "time", return_value=1700000001)
    def test_signature_matches_documented_contract(self, _mock_time):
        headers = build_sign_headers(
            "https://zonai.skland.com/api/v1/game/player/info?uid=123",
            "skland-cred",
            "signing-token",
        )

        self.assertEqual(
            headers,
            {
                "cred": "skland-cred",
                "sign": "f4a3e50c5317520c74b04ecfc0757f9e",
                "platform": "",
                "timestamp": "1700000000",
                "dId": "",
                "vName": "",
            },
        )

    @patch.object(HeaderBuilder.time, "time", return_value=1700000001)
    def test_query_is_part_of_signature(self, _mock_time):
        first = build_sign_headers(
            "https://zonai.skland.com/api/v1/game/player/info?uid=123",
            "skland-cred",
            "signing-token",
        )
        second = build_sign_headers(
            "https://zonai.skland.com/api/v1/game/player/info?uid=456",
            "skland-cred",
            "signing-token",
        )

        self.assertNotEqual(first["sign"], second["sign"])


class AccountInfoRequestTests(unittest.TestCase):
    def test_success_response_and_request_headers(self):
        data = {"status": {"uid": "角色 1"}, "chars": []}
        http_client = _JsonStub(
            [{"code": 0, "message": "OK", "data": data}]
        )
        account_info = GetAccountInfo(http_client)

        result = account_info._get_account_info(
            "角色 1",
            "skland-cred",
            "signing-token",
        )

        self.assertTrue(result.status)
        self.assertEqual(result.code, 0)
        self.assertIs(result.data, data)
        self.assertEqual(result.message, "角色信息获取成功")

        method, url, kwargs = http_client.requests[0]
        self.assertEqual(method, "GET")
        self.assertEqual(
            url,
            f"{account_info.BASE_ACCOUNT_INFO_URL}?uid=%E8%A7%92%E8%89%B2+1",
        )
        self.assertEqual(kwargs["headers"]["cred"], "skland-cred")
        self.assertEqual(kwargs["headers"]["Accept"], "application/json")
        self.assertEqual(
            kwargs["headers"]["User-Agent"],
            account_info.USER_AGENT,
        )
        self.assertIn("sign", kwargs["headers"])

    def test_business_failure_does_not_require_data(self):
        http_client = _JsonStub(
            [{"code": 10002, "message": "用户未登录", "data": None}]
        )

        result = GetAccountInfo(http_client)._get_account_info(
            "123",
            "skland-cred",
            "signing-token",
        )

        self.assertFalse(result.status)
        self.assertEqual(result.code, 10002)
        self.assertEqual(result.message, "用户未登录")
        self.assertIsNone(result.data)

    def test_business_failure_uses_code_when_message_is_missing(self):
        result = GetAccountInfo(_JsonStub([{"code": 403}]))._get_account_info(
            "123",
            "skland-cred",
            "signing-token",
        )

        self.assertFalse(result.status)
        self.assertEqual(result.code, 403)
        self.assertEqual(result.message, "角色信息获取失败：code=403")

    def test_malformed_success_data_returns_failure(self):
        result = GetAccountInfo(
            _JsonStub([{"code": 0, "message": "OK", "data": None}])
        )._get_account_info(
            "123",
            "skland-cred",
            "signing-token",
        )

        self.assertFalse(result.status)
        self.assertEqual(result.code, 0)
        self.assertIn("data", result.message)
        self.assertIsNone(result.data)

    def test_malformed_code_returns_failure_without_business_code(self):
        result = GetAccountInfo(
            _JsonStub([{"code": "0", "data": {}}])
        )._get_account_info(
            "123",
            "skland-cred",
            "signing-token",
        )

        self.assertFalse(result.status)
        self.assertIsNone(result.code)
        self.assertIn("code", result.message)

    def test_network_error_returns_failure(self):
        result = GetAccountInfo(
            _JsonStub([NetworkRequestError("网络连接失败")])
        )._get_account_info(
            "123",
            "skland-cred",
            "signing-token",
        )

        self.assertFalse(result.status)
        self.assertIsNone(result.code)
        self.assertEqual(result.message, "网络连接失败")

    def test_empty_input_does_not_send_request(self):
        for uid, cred, token in (
            ("", "cred", "token"),
            ("123", "", "token"),
            ("123", "cred", ""),
        ):
            with self.subTest(uid=uid, cred=cred, token=token):
                http_client = _JsonStub([])
                result = GetAccountInfo(http_client)._get_account_info(
                    uid,
                    cred,
                    token,
                )

                self.assertFalse(result.status)
                self.assertEqual(http_client.requests, [])


class AccountInfoAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_wrapper_returns_request_result(self):
        http_client = _JsonStub(
            [{"code": 0, "message": "OK", "data": {"status": {}}}]
        )

        result = await GetAccountInfo(http_client).aget_account_info(
            "123",
            "skland-cred",
            "signing-token",
        )

        self.assertTrue(result.status)
        self.assertEqual(result.code, 0)
