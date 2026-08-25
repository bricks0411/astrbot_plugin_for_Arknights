import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ..GetAccountInfo.model import RequestResultOfAccountInfo
from ..GetDoctorInfo.models import RequestResultOfDoctorInfo
from ..LoginTools.models import (
    RefreshResultOfSklandToken,
    RequestResultOfAccountToken,
    RequestResultOfAuth,
    RequestResultOfSklandCred,
    RequestResultOfSklandGrantCode,
)
from ..main import ArknightsChecker, PendingVerification
from ..storage.models import (
    ReturnResultOfAccountDataOperation,
    ReturnResultOfDatabaseOperation,
    ReturnResultOfGachaHistoryFromDatabase,
    ReturnResultOfSklandCredentials,
    ReturnResultOfSklandCredentialsOperation,
)


class _Event:
    def get_sender_id(self):
        return "user-1"

    def get_platform_name(self):
        return "test-platform"

    def get_messages(self):
        return []

    def plain_result(self, message):
        return message

    def image_result(self, image_url):
        return ("image", image_url)


async def _collect(async_generator):
    return [result async for result in async_generator]


class MainCommandRegressionTests(unittest.IsolatedAsyncioTestCase):
    def _login_checker(self):
        checker = object.__new__(ArknightsChecker)
        checker.GetArgs = lambda _messages: ["/方舟官服验证码", "123456"]
        checker.pending_verifications = {
            ("test-platform", "user-1", checker.OFFICIAL, checker.GAME_LOGIN): (
                PendingVerification(
                    phone="13800138000",
                    created_at=time.monotonic(),
                )
            )
        }
        checker.official_server_login = SimpleNamespace(
            aget_auth_token=AsyncMock(),
            aget_account_token=AsyncMock(),
        )
        checker.skland_login_handler = SimpleNamespace(
            aget_grant_code=AsyncMock(),
            aget_cred_by_grant_code=AsyncMock(),
        )
        checker.official_doctor_info_handler = SimpleNamespace(
            aget_doctor_info=AsyncMock()
        )
        checker.data_storage_handler = SimpleNamespace(
            aupdate_user_token=AsyncMock(),
            aupdate_skland_credentials=AsyncMock(),
        )
        return checker

    def _account_update_checker(self):
        checker = object.__new__(ArknightsChecker)
        checker.GetStoredOfficialUserInfo = AsyncMock(
            return_value=(
                RequestResultOfDoctorInfo(
                    status=True,
                    phone="",
                    token="account-token",
                    uid="game-uid",
                    nickName="Doctor",
                ),
                None,
            )
        )
        checker.data_storage_handler = SimpleNamespace(
            aget_skland_credentials=AsyncMock(
                return_value=ReturnResultOfSklandCredentials(
                    status=True,
                    uid="game-uid",
                    cred="skland-cred",
                    token="old-signing-token",
                )
            ),
            aupdate_skland_credentials=AsyncMock(
                return_value=ReturnResultOfSklandCredentialsOperation(
                    status=True,
                    uid="game-uid",
                )
            ),
            aupdate_account_data=AsyncMock(
                return_value=ReturnResultOfAccountDataOperation(
                    status=True,
                    uid="game-uid",
                    updated=True,
                )
            ),
        )
        checker.skland_login_handler = SimpleNamespace(
            arefresh_token_by_cred=AsyncMock(
                return_value=RefreshResultOfSklandToken(
                    status=True,
                    cred="skland-cred",
                    token="new-signing-token",
                )
            )
        )
        checker.get_account_info = SimpleNamespace(
            aget_account_info=AsyncMock(
                return_value=RequestResultOfAccountInfo(
                    status=True,
                    message="角色信息获取成功",
                    code=0,
                    data={"chars": [], "skins": [], "activity": []},
                )
            )
        )
        return checker

    async def test_missing_pending_verification_uses_login_prompt(self):
        checker = self._login_checker()
        checker.pending_verifications.clear()

        results = await _collect(
            checker.GetAndSendVerificationCodeWithOfficialServer(_Event())
        )

        self.assertEqual(
            results,
            ["请先发送 /方舟官服登录 <手机号码> 获取验证码"],
        )
        checker.official_server_login.aget_auth_token.assert_not_awaited()

    async def test_missing_login_token_returns_stable_error(self):
        checker = self._login_checker()
        checker.official_server_login.aget_auth_token.return_value = (
            RequestResultOfAuth(status=True, phone="13800138000", token=None)
        )

        results = await _collect(
            checker.GetAndSendVerificationCodeWithOfficialServer(_Event())
        )

        self.assertEqual(results, ["登录 token 获取失败"])
        checker.official_server_login.aget_account_token.assert_not_awaited()

    async def test_missing_account_token_returns_stable_error(self):
        checker = self._login_checker()
        checker.official_server_login.aget_auth_token.return_value = (
            RequestResultOfAuth(
                status=True,
                phone="13800138000",
                token="login-token",
            )
        )
        checker.official_server_login.aget_account_token.return_value = (
            RequestResultOfAccountToken(
                status=True,
                phone="13800138000",
                accountToken=None,
            )
        )

        results = await _collect(
            checker.GetAndSendVerificationCodeWithOfficialServer(_Event())
        )

        self.assertEqual(results, ["账号 token 获取失败"])
        checker.official_doctor_info_handler.aget_doctor_info.assert_not_awaited()

    @staticmethod
    def _configure_successful_official_login(checker):
        checker.official_server_login.aget_auth_token.return_value = (
            RequestResultOfAuth(
                status=True,
                phone="13800138000",
                token="login-token",
                hgId="hg-id",
            )
        )
        checker.official_server_login.aget_account_token.return_value = (
            RequestResultOfAccountToken(
                status=True,
                phone="13800138000",
                accountToken="account-token",
            )
        )
        checker.official_doctor_info_handler.aget_doctor_info.return_value = (
            RequestResultOfDoctorInfo(
                status=True,
                phone="13800138000",
                token="account-token",
                uid="game-uid",
                nickName="Doctor",
            )
        )
        checker.data_storage_handler.aupdate_user_token.return_value = (
            ReturnResultOfDatabaseOperation(status=True)
        )

    async def test_successful_login_initializes_skland_credentials(self):
        checker = self._login_checker()
        self._configure_successful_official_login(checker)
        checker.skland_login_handler.aget_grant_code.return_value = (
            RequestResultOfSklandGrantCode(
                status=True,
                phone="13800138000",
                grant_code="grant-code",
            )
        )
        checker.skland_login_handler.aget_cred_by_grant_code.return_value = (
            RequestResultOfSklandCred(
                status=True,
                phone="13800138000",
                cred="skland-cred",
                token="signing-token",
            )
        )
        checker.data_storage_handler.aupdate_skland_credentials.return_value = (
            ReturnResultOfSklandCredentialsOperation(status=True, uid="game-uid")
        )

        with patch(
            f"{ArknightsChecker.__module__}.asyncio.sleep",
            new=AsyncMock(),
        ):
            results = await _collect(
                checker.GetAndSendVerificationCodeWithOfficialServer(_Event())
            )

        self.assertEqual(
            results,
            ["登录成功", "欢迎，Dr. Doctor", checker.GUIDE_SYNC_GACHAHISTORY],
        )
        checker.skland_login_handler.aget_grant_code.assert_awaited_once_with(
            "login-token",
            "13800138000",
        )
        checker.skland_login_handler.aget_cred_by_grant_code.assert_awaited_once_with(
            "13800138000",
            "grant-code",
        )
        checker.data_storage_handler.aupdate_skland_credentials.assert_awaited_once_with(
            "game-uid",
            "skland-cred",
            "signing-token",
        )
        self.assertEqual(checker.pending_verifications, {})

    async def test_skland_failure_does_not_rollback_official_login(self):
        checker = self._login_checker()
        self._configure_successful_official_login(checker)
        checker.skland_login_handler.aget_grant_code.return_value = (
            RequestResultOfSklandGrantCode(
                status=False,
                phone="13800138000",
                message="森空岛暂不可用",
            )
        )

        with patch(
            f"{ArknightsChecker.__module__}.asyncio.sleep",
            new=AsyncMock(),
        ):
            results = await _collect(
                checker.GetAndSendVerificationCodeWithOfficialServer(_Event())
            )

        self.assertEqual(results[0:2], ["登录成功", "欢迎，Dr. Doctor"])
        self.assertIn("森空岛凭据初始化失败", results[2])
        self.assertEqual(results[-1], checker.GUIDE_SYNC_GACHAHISTORY)
        checker.skland_login_handler.aget_cred_by_grant_code.assert_not_awaited()
        checker.data_storage_handler.aupdate_skland_credentials.assert_not_awaited()

    async def test_account_update_uses_refreshed_token(self):
        checker = self._account_update_checker()

        results = await _collect(checker.UpdateAccountInfo(_Event()))

        self.assertEqual(
            results,
            [
                "账号数据更新成功",
                "已同步 0 条干员数据、0 条时装数据、0 条活动数据及 0 类其它数据",
            ],
        )
        checker.data_storage_handler.aget_skland_credentials.assert_awaited_once_with(
            "game-uid"
        )
        checker.skland_login_handler.arefresh_token_by_cred.assert_awaited_once_with(
            "skland-cred"
        )
        checker.data_storage_handler.aupdate_skland_credentials.assert_awaited_once_with(
            "game-uid",
            "skland-cred",
            "new-signing-token",
        )
        checker.get_account_info.aget_account_info.assert_awaited_once_with(
            "game-uid",
            "skland-cred",
            "new-signing-token",
        )
        checker.data_storage_handler.aupdate_account_data.assert_awaited_once_with(
            "game-uid",
            {"chars": [], "skins": [], "activity": []},
            checker.OFFICIAL,
        )

    async def test_account_update_stops_when_skland_credentials_are_missing(self):
        checker = self._account_update_checker()
        checker.data_storage_handler.aget_skland_credentials.return_value = (
            ReturnResultOfSklandCredentials(
                status=False,
                message="尚未保存森空岛凭证",
                uid="game-uid",
            )
        )

        results = await _collect(checker.UpdateAccountInfo(_Event()))

        self.assertEqual(results, ["本地未找到森空岛凭证，请重新登录"])
        checker.skland_login_handler.arefresh_token_by_cred.assert_not_awaited()
        checker.get_account_info.aget_account_info.assert_not_awaited()

    async def test_account_update_uses_old_token_when_refresh_fails(self):
        checker = self._account_update_checker()
        checker.skland_login_handler.arefresh_token_by_cred.return_value = (
            RefreshResultOfSklandToken(
                status=False,
                cred="skland-cred",
                message="刷新服务不可用",
            )
        )

        results = await _collect(checker.UpdateAccountInfo(_Event()))

        self.assertEqual(
            results,
            [
                "token 刷新失败，将尝试使用旧 token",
                "账号数据更新成功",
                "已同步 0 条干员数据、0 条时装数据、0 条活动数据及 0 类其它数据",
            ],
        )
        checker.data_storage_handler.aupdate_skland_credentials.assert_not_awaited()
        checker.get_account_info.aget_account_info.assert_awaited_once_with(
            "game-uid",
            "skland-cred",
            "old-signing-token",
        )

    async def test_account_update_stops_when_refreshed_token_cannot_be_saved(self):
        checker = self._account_update_checker()
        checker.data_storage_handler.aupdate_skland_credentials.return_value = (
            ReturnResultOfSklandCredentialsOperation(
                status=False,
                message="数据库写入失败",
                uid="game-uid",
            )
        )

        results = await _collect(checker.UpdateAccountInfo(_Event()))

        self.assertEqual(results, ["信息存储失败！请在稍后重新登录"])
        checker.get_account_info.aget_account_info.assert_not_awaited()

    async def test_account_update_reports_account_request_failure(self):
        checker = self._account_update_checker()
        checker.get_account_info.aget_account_info.return_value = (
            RequestResultOfAccountInfo(
                status=False,
                message="用户未登录",
                code=10002,
            )
        )

        results = await _collect(checker.UpdateAccountInfo(_Event()))

        self.assertEqual(results, ["角色信息请求失败"])

    async def test_account_update_reports_when_local_snapshot_is_newer(self):
        checker = self._account_update_checker()
        checker.data_storage_handler.aupdate_account_data.return_value = (
            ReturnResultOfAccountDataOperation(
                status=True,
                message="服务器账号数据早于本地快照，已保留本地数据",
                uid="game-uid",
                updated=False,
            )
        )

        results = await _collect(checker.UpdateAccountInfo(_Event()))

        self.assertEqual(results, ["本地账号数据已是最新，无需覆盖"])

    async def test_account_update_handles_non_list_summary_fields(self):
        checker = self._account_update_checker()
        checker.get_account_info.aget_account_info.return_value = (
            RequestResultOfAccountInfo(
                status=True,
                message="角色信息获取成功",
                code=0,
                data={
                    "chars": 1,
                    "skins": None,
                    "activity": {},
                    "status": {},
                },
            )
        )

        with patch(
            f"{ArknightsChecker.__module__}.asyncio.sleep",
            new=AsyncMock(),
        ):
            results = await _collect(checker.UpdateAccountInfo(_Event()))

        self.assertEqual(
            results,
            [
                "账号数据更新成功",
                "已同步 0 条干员数据、0 条时装数据、0 条活动数据及 1 类其它数据",
            ],
        )

    async def test_missing_database_error_message_uses_fallback(self):
        checker = object.__new__(ArknightsChecker)
        checker.data_storage_handler = SimpleNamespace(
            aget_gacha_history_by_user=AsyncMock(
                return_value=ReturnResultOfGachaHistoryFromDatabase(
                    status=False,
                    message=None,
                )
            )
        )

        results = await _collect(checker.GetGachaHistory(_Event()))

        self.assertEqual(results, ["抽卡信息获取失败"])

    async def test_account_query_passes_complete_json_to_renderer(self):
        checker = object.__new__(ArknightsChecker)
        account_data = {
            "currentTs": 1704240000,
            "status": {"uid": "game-uid", "name": "Doctor"},
            "assistChars": [],
            "charInfoMap": {},
            "stageInfoMap": {},
        }
        checker.data_storage_handler = SimpleNamespace(
            aget_user_token=AsyncMock(
                return_value=SimpleNamespace(
                    status=True,
                    account_id="game-uid",
                )
            ),
            aget_account_data=AsyncMock(
                return_value=SimpleNamespace(
                    status=True,
                    account_data=account_data,
                )
            ),
        )
        checker.account_info_renderer = SimpleNamespace(
            arender=AsyncMock(
                return_value=SimpleNamespace(
                    status=True,
                    image_url="https://example.test/account.png",
                )
            )
        )

        results = await _collect(checker.GetAccountInfo(_Event()))

        self.assertEqual(results, [("image", "https://example.test/account.png")])
        checker.account_info_renderer.arender.assert_awaited_once_with(
            checker,
            account_data,
        )


if __name__ == "__main__":
    unittest.main()
