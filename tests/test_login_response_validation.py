import unittest

from ..LoginTools.OfficialServerLogin import OfficialServerLogin
from ..network.exceptions import InvalidResponseError, NetworkRequestError
from ..network.validation import (
    require_bool,
    require_dict,
    require_dict_list,
    require_int,
    require_list,
    require_str,
)


class _StubHttpClient:

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def request_json(self, method, url, **kwargs):
        if self.error is not None:
            raise self.error
        return self.response


class ResponseValidationTests(unittest.TestCase):

    def test_require_helpers_return_checked_values(self):
        values = ({}, [], "token", 0, False)
        checked = (
            require_dict(values[0], "object"),
            require_list(values[1], "items"),
            require_str(values[2], "token"),
            require_int(values[3], "status"),
            require_bool(values[4], "hasMore"),
        )
        self.assertEqual(checked, values)

    def test_require_dict_list_checks_each_item(self):
        items = [{"id": "one"}, {"id": "two"}]
        self.assertIs(require_dict_list(items, "items"), items)

        with self.assertRaisesRegex(InvalidResponseError, r"items\[1\]"):
            require_dict_list([{"id": "one"}, None], "items")

    def test_require_helpers_reject_wrong_types(self):
        invalid_values = (
            (require_dict, None),
            (require_list, {}),
            (require_str, ""),
            (require_int, True),
            (require_bool, 1),
        )
        for helper, value in invalid_values:
            with self.subTest(helper=helper.__name__):
                with self.assertRaises(InvalidResponseError):
                    helper(value, "field")


class AuthTokenResponseTests(unittest.TestCase):

    def test_success_response_is_parsed(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 0,
            "msg": "登录成功",
            "data": {"token": "login-token", "hgId": "12345"},
        }))

        result = login._get_auth_token("13800000000", "123456")

        self.assertTrue(result.status)
        self.assertEqual(result.token, "login-token")
        self.assertEqual(result.hgId, "12345")
        self.assertEqual(result.message, "登录成功")

    def test_business_failure_preserves_server_message(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 100,
            "msg": "验证码错误",
            "data": None,
        }))

        result = login._get_auth_token("13800000000", "bad-code")

        self.assertFalse(result.status)
        self.assertEqual(result.message, "验证码错误")

    def test_malformed_success_data_is_an_invalid_response(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 0,
            "msg": "登录成功",
            "data": None,
        }))

        result = login._get_auth_token("13800000000", "123456")

        self.assertFalse(result.status)
        self.assertIn("data", result.message)

    def test_empty_token_is_an_invalid_response(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 0,
            "msg": "登录成功",
            "data": {"token": "", "hgId": "12345"},
        }))

        result = login._get_auth_token("13800000000", "123456")

        self.assertFalse(result.status)
        self.assertIn("data.token", result.message)

    def test_network_error_uses_single_http_client_error_path(self):
        login = OfficialServerLogin(
            _StubHttpClient(error=NetworkRequestError("网络连接失败"))
        )

        result = login._get_auth_token("13800000000", "123456")

        self.assertFalse(result.status)
        self.assertEqual(result.message, "网络连接失败")


class OtherLoginEndpointTests(unittest.TestCase):

    def test_verification_code_business_failure_preserves_message(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 101,
            "msg": "请求过于频繁",
        }))

        result = login._get_verification_code("13800000000")

        self.assertFalse(result.status)
        self.assertEqual(result.message, "请求过于频繁")

    def test_verification_code_status_must_be_integer(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": "0",
            "msg": "OK",
        }))

        result = login._get_verification_code("13800000000")

        self.assertFalse(result.status)
        self.assertIn("status", result.message)

    def test_account_token_success_checks_nested_token(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 0,
            "msg": "OK",
            "data": {"token": "account-token"},
        }))

        result = login._get_account_token("login-token", "13800000000")

        self.assertTrue(result.status)
        self.assertEqual(result.accountToken, "account-token")

    def test_account_token_business_failure_does_not_require_data(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 100,
            "msg": "授权失败",
            "data": None,
        }))

        result = login._get_account_token("login-token", "13800000000")

        self.assertFalse(result.status)
        self.assertEqual(result.message, "授权失败")

    def test_account_token_null_success_data_is_invalid(self):
        login = OfficialServerLogin(_StubHttpClient({
            "status": 0,
            "msg": "OK",
            "data": None,
        }))

        result = login._get_account_token("login-token", "13800000000")

        self.assertFalse(result.status)
        self.assertIn("data", result.message)


if __name__ == "__main__":
    unittest.main()
