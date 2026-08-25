import unittest

from ..LoginTools.OfficialServerLogin import OfficialServerLogin
from ..LoginTools.SklandLogin import SklandLoginHandler as SklandLogin
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


class GrantCodeTests(unittest.TestCase):
    def test_success_response_and_request_payload(self):
        http_client = _JsonStub(
            [
                {
                    "status": 0,
                    "msg": "OK",
                    "data": {"code": "grant-code"},
                }
            ]
        )
        account_info = SklandLogin(http_client)

        result = account_info._get_grant_code(
            "login-token",
            "13800000000",
        )

        self.assertTrue(result.status)
        self.assertEqual(result.phone, "13800000000")
        self.assertEqual(result.grant_code, "grant-code")
        self.assertEqual(result.message, "OK")
        self.assertEqual(
            http_client.requests,
            [
                (
                    "POST",
                    account_info.GET_GRANT_CODE_URL,
                    {
                        "json": {
                            "appCode": account_info.SKLAND_APP_CODE,
                            "token": "login-token",
                            "type": 0,
                        },
                        "headers": {
                            "Content-Type": "application/json",
                            "User-Agent": account_info.USER_AGENT,
                        },
                    },
                )
            ],
        )

    def test_business_failure_preserves_alternate_message_field(self):
        http_client = _JsonStub(
            [
                {
                    "status": 100,
                    "message": "授权失败",
                    "data": None,
                }
            ]
        )

        result = SklandLogin(http_client)._get_grant_code(
            "login-token",
            "13800000000",
        )

        self.assertFalse(result.status)
        self.assertIsNone(result.grant_code)
        self.assertEqual(result.message, "授权失败")

    def test_malformed_success_data_returns_failure(self):
        http_client = _JsonStub(
            [
                {
                    "status": 0,
                    "msg": "OK",
                    "data": {"code": ""},
                }
            ]
        )

        result = SklandLogin(http_client)._get_grant_code(
            "login-token",
            "13800000000",
        )

        self.assertFalse(result.status)
        self.assertIn("data.code", result.message)

    def test_empty_input_does_not_send_request(self):
        http_client = _JsonStub([])

        result = SklandLogin(http_client)._get_grant_code(
            "",
            "13800000000",
        )

        self.assertFalse(result.status)
        self.assertEqual(http_client.requests, [])


class CredTests(unittest.TestCase):
    def test_success_response_and_request_payload(self):
        http_client = _JsonStub(
            [
                {
                    "code": 0,
                    "message": "OK",
                    "data": {
                        "cred": "skland-cred",
                        "token": "signing-token",
                    },
                }
            ]
        )
        account_info = SklandLogin(http_client)

        result = account_info._get_cred_by_grant_code(
            "13800000000",
            "grant-code",
        )

        self.assertTrue(result.status)
        self.assertEqual(result.phone, "13800000000")
        self.assertEqual(result.cred, "skland-cred")
        self.assertEqual(result.token, "signing-token")
        self.assertEqual(result.message, "OK")
        self.assertEqual(
            http_client.requests,
            [
                (
                    "POST",
                    account_info.GET_CRED_URL,
                    {
                        "json": {"code": "grant-code", "kind": 1},
                        "headers": {
                            "Content-type": "application/json",
                            "User-Agent": account_info.USER_AGENT,
                        },
                    },
                )
            ],
        )

    def test_business_failure_does_not_parse_credentials(self):
        http_client = _JsonStub(
            [
                {
                    "code": 100,
                    "message": "grant code 已失效",
                    "data": None,
                }
            ]
        )

        result = SklandLogin(http_client)._get_cred_by_grant_code(
            "13800000000",
            "grant-code",
        )

        self.assertFalse(result.status)
        self.assertIsNone(result.cred)
        self.assertIsNone(result.token)
        self.assertEqual(result.message, "grant code 已失效")

    def test_missing_credential_field_returns_failure(self):
        http_client = _JsonStub(
            [
                {
                    "code": 0,
                    "message": "OK",
                    "data": {"cred": "skland-cred", "token": ""},
                }
            ]
        )

        result = SklandLogin(http_client)._get_cred_by_grant_code(
            "13800000000",
            "grant-code",
        )

        self.assertFalse(result.status)
        self.assertIn("data.token", result.message)

    def test_network_error_returns_failure(self):
        http_client = _JsonStub([NetworkRequestError("网络连接失败")])

        result = SklandLogin(http_client)._get_cred_by_grant_code(
            "13800000000",
            "grant-code",
        )

        self.assertFalse(result.status)
        self.assertEqual(result.message, "网络连接失败")

    def test_empty_input_does_not_send_request(self):
        http_client = _JsonStub([])

        result = SklandLogin(http_client)._get_cred_by_grant_code(
            "13800000000",
            "",
        )

        self.assertFalse(result.status)
        self.assertEqual(http_client.requests, [])


class RefreshTokenTests(unittest.TestCase):
    def test_success_response_and_request_headers(self):
        http_client = _JsonStub(
            [
                {
                    "code": 0,
                    "message": "OK",
                    "data": {"token": "refreshed-token"},
                }
            ]
        )
        account_info = SklandLogin(http_client)

        result = account_info._refresh_token_by_cred("skland-cred")

        self.assertTrue(result.status)
        self.assertEqual(result.cred, "skland-cred")
        self.assertEqual(result.token, "refreshed-token")
        self.assertEqual(result.message, "OK")
        self.assertEqual(
            http_client.requests,
            [
                (
                    "GET",
                    account_info.REFRESH_TOKEN_URL,
                    {
                        "headers": {
                            "Accept": "application/json",
                            "User-Agent": account_info.USER_AGENT,
                            "cred": "skland-cred",
                        }
                    },
                )
            ],
        )

    def test_business_failure_preserves_server_message(self):
        http_client = _JsonStub([{"code": 403, "message": "凭据已失效", "data": None}])

        result = SklandLogin(http_client)._refresh_token_by_cred("skland-cred")

        self.assertFalse(result.status)
        self.assertEqual(result.cred, "skland-cred")
        self.assertIsNone(result.token)
        self.assertEqual(result.message, "凭据已失效")

    def test_business_failure_without_message_uses_failure_default(self):
        http_client = _JsonStub([{"code": 403}])

        result = SklandLogin(http_client)._refresh_token_by_cred("skland-cred")

        self.assertFalse(result.status)
        self.assertIn("token 刷新失败", result.message)
        self.assertIn("403", result.message)

    def test_missing_token_returns_failure(self):
        http_client = _JsonStub([{"code": 0, "message": "OK", "data": {"token": ""}}])

        result = SklandLogin(http_client)._refresh_token_by_cred("skland-cred")

        self.assertFalse(result.status)
        self.assertEqual(result.cred, "skland-cred")
        self.assertIn("data.token", result.message)

    def test_network_error_returns_failure(self):
        http_client = _JsonStub([NetworkRequestError("网络连接失败")])

        result = SklandLogin(http_client)._refresh_token_by_cred("skland-cred")

        self.assertFalse(result.status)
        self.assertEqual(result.cred, "skland-cred")
        self.assertEqual(result.message, "网络连接失败")

    def test_empty_cred_does_not_send_request(self):
        http_client = _JsonStub([])

        result = SklandLogin(http_client)._refresh_token_by_cred("")

        self.assertFalse(result.status)
        self.assertIsNone(result.token)
        self.assertEqual(http_client.requests, [])


class SklandLoginChainTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_token_to_grant_code_to_cred(self):
        http_client = _JsonStub(
            [
                {
                    "status": 0,
                    "msg": "OK",
                    "data": {"token": "login-token", "hgId": "12345"},
                },
                {
                    "status": 0,
                    "msg": "OK",
                    "data": {"code": "grant-code"},
                },
                {
                    "code": 0,
                    "message": "OK",
                    "data": {
                        "cred": "skland-cred",
                        "token": "signing-token",
                    },
                },
            ]
        )
        upstream_login = OfficialServerLogin(http_client)
        account_info = SklandLogin(http_client)

        auth_result = await upstream_login.aget_auth_token(
            "13800000000",
            "123456",
        )
        grant_result = await account_info.aget_grant_code(
            auth_result.token,
            auth_result.phone,
        )
        cred_result = await account_info.aget_cred_by_grant_code(
            grant_result.phone,
            grant_result.grant_code,
        )

        self.assertTrue(auth_result.status)
        self.assertTrue(grant_result.status)
        self.assertTrue(cred_result.status)
        self.assertEqual(cred_result.cred, "skland-cred")
        self.assertEqual(cred_result.token, "signing-token")
        self.assertEqual(
            [request[2]["json"] for request in http_client.requests],
            [
                {"phone": "13800000000", "code": "123456"},
                {
                    "appCode": account_info.SKLAND_APP_CODE,
                    "token": "login-token",
                    "type": 0,
                },
                {"code": "grant-code", "kind": 1},
            ],
        )

    async def test_refresh_token_async_wrapper(self):
        http_client = _JsonStub(
            [
                {
                    "code": 0,
                    "message": "OK",
                    "data": {"token": "refreshed-token"},
                }
            ]
        )

        result = await SklandLogin(http_client).arefresh_token_by_cred("skland-cred")

        self.assertTrue(result.status)
        self.assertEqual(result.cred, "skland-cred")
        self.assertEqual(result.token, "refreshed-token")


if __name__ == "__main__":
    unittest.main()
