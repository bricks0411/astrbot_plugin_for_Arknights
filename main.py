# main.py
import asyncio
import time
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import BaseMessageComponent, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .analysis.GachaHistoryT2I import (
    GACHA_STATISTICS_RENDER_OPTIONS,
    GACHA_STATISTICS_TEMPLATE,
)
from .analysis.SixStarsAnalyser import GachaHistoryAnalyser
from .GachaHistory.GetGachaHistory import OfficialGetGachaHistory
from .GetAccountInfo.GetAccountInfo import GetAccountInfo
from .GetDoctorInfo.models import RequestResultOfDoctorInfo
from .GetDoctorInfo.OfficialDoctorInfoHandler import OfficialDoctorInfoHandler
from .LoginTools.OfficialServerLogin import OfficialServerLogin
from .LoginTools.SklandLogin import SklandLoginHandler
from .network.HttpClient import HttpClient
from .OperatorInfo import (
    OperatorEncyclopedia,
    OperatorInfoError,
    OperatorNotFoundError,
    OperatorResponseError,
    PrtsWikiClient,
    build_operator_text_summary,
    render_operator_card,
)
from .Renderer.AccountInfoRenderer.AccountInfo import AccountInfoRenderer
from .storage.UserDB import DataStorageHandler

PLUGIN_NAME = "astrbot_plugin_for_Arknights"


# region 基础数据结构与装饰器

@dataclass(slots=True, frozen=True)
class PendingVerification:
    """尚未完成的短信验证码会话"""

    phone: str
    created_at: float


def command_error_boundary(command_name: str):
    """在 AstrBot 命令最外层记录未预期异常，并给用户稳定提示"""
    def decorate(command):
        @wraps(command)
        async def wrapped(self, event: AstrMessageEvent, *args, **kwargs):
            try:
                async for result in command(self, event, *args, **kwargs):
                    yield result
            except Exception:
                logger.exception(f"执行 AstrBot 命令“{command_name}”时发生未处理异常")
                yield event.plain_result("插件内部发生错误")

        return wrapped
    return decorate


# endregion


@register(
    "Arknights",
    "Bricks0411",
    "mrfz 综合查询插件",
    "1.0.0"
)
class ArknightsChecker(Star):

    # region 插件配置

    # 服务器种类
    OFFICIAL = "official"
    BILIBILI = "bilibili"
    # 登录用途
    GAME_LOGIN = "game"
    # 验证码有效期
    VERIFICATION_CODE_TTL_SECONDS = 1800
    # TTL 轮询区间
    CHECK_TTL_INTERVAL = 60
    # 指导语料
    GUIDE_GET_VERIFICATIONCODE_SERVER = (
        "添加 bot 好友后，私聊使用 /方舟官服登录 或 /方舟B服登录 指令获取验证码\n"
        "之后使用 /官服验证码 <验证码> 或 /B服验证码 <验证码> 指令登录\n"
        "目前仅支持官服"
    )
    GUIDE_SYNC_GACHAHISTORY = (
        "若这是你第一次登录，请根据账号所在的服务器种类，使用 /官服抽卡记录更新 或 /B服抽卡记录更新 指令同步抽卡记录数据（目前仅支持官服）"
    )
    GUIDE_GET_VERIFICATION_CODE = (
        "验证码发送成功，30 分钟内有效，请发送 /官服验证码 <接收到的验证码> 执行下一步操作"
    )

    # endregion

    # region 依赖初始化与数据路径

    def __init__(self, context: Context):
        """初始化插件依赖、功能服务和用户会话状态"""
        super().__init__(context)
        # 各类功能模块
        self.http_client = HttpClient(timeout = 10)                                                         # 鹰角请求不复用连接
        self.prts_http_client = HttpClient(
            timeout             = 10,
            reuse_connections   = True,
        )                                                                                                   # PRTS 专用连接池
        self.official_server_login = OfficialServerLogin(
            self.http_client
        )
        self.skland_login_handler = SklandLoginHandler(
            self.http_client
        )
        self.official_doctor_info_handler = OfficialDoctorInfoHandler(
            self.http_client
        )
        self.official_get_gacha_history = OfficialGetGachaHistory(
            self.http_client
        )
        self.get_account_info = GetAccountInfo(
            self.http_client
        )
        self.gacha_history_analyser = GachaHistoryAnalyser(
            self._build_avatar_cache_path()
        )
        self.operator_encyclopedia = OperatorEncyclopedia(
            PrtsWikiClient(self.prts_http_client, logger=logger),
            self._build_operator_info_cache_path(),
            cache_ttl_seconds   = 24 * 60 * 60,
            download_portrait   = True,
            logger              = logger,
        )
        self.account_info_renderer = AccountInfoRenderer(
            self._build_avatar_cache_path(),
            logger=logger,
        )


        # 不同平台、服务器和登录用途的验证码会话统一存放在这里
        # 维护用户信息四元组与验证码数据类之间的映射
        # tuple: (platform_name, user_id, server_type, login_purpose)
        # platform_name: 消息来源平台
        # user_id: 用户在聊天中对应的 ID
        # server_type: 明日方舟服务器类型
        # login_purpose: 验证码会画用途，目前仅有 self.GAME_LOGIN = "game"
        self.pending_verifications: dict[
            tuple[str, str, str, str],
            PendingVerification,
        ] = {}
        # 统一持久化信息维护
        self.data_storage_handler = DataStorageHandler(
            db_path         = self._build_user_db_path(),
            busy_timeout_ms = 5000
        )
        # 持久化后台任务定义
        self._user_TTL_check_loop_task: asyncio.Task | None = None


    def _build_user_db_path(self) -> Path:
        """构造插件专用 SQLite 数据库路径"""
        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        return plugin_data_dir / "user_db.sqlite3"


    def _build_avatar_cache_path(self) -> Path:
        """构造永久干员头像缓存目录"""
        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        return plugin_data_dir / "avatar_cache"


    def _build_operator_info_cache_path(self) -> Path:
        """构造干员百科数据及立绘缓存目录"""
        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        return plugin_data_dir / "operator_info_cache"

    # endregion

    # region 验证码会话状态


    @staticmethod
    def _PendingVerificationKey(
        platform_name: str,
        user_id: str,
        server_type: str,
        login_purpose: str,
    ) -> tuple[str, str, str, str]:
        return platform_name, user_id, server_type, login_purpose


    def AddPendingMessage(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
        login_purpose: str,
        phone: str,
    ) -> None:
        """新增或覆盖指定登录流程的验证码会话"""
        key = self._PendingVerificationKey(
            platform_name,
            user_id,
            server_type,
            login_purpose,
        )
        self.pending_verifications[key] = PendingVerification(
            phone       =   phone,
            created_at  =   time.monotonic(),
        )


    def GetPendingMessage(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
        login_purpose: str,
    ) -> PendingVerification | None:
        """读取指定登录流程的验证码会话"""
        key = self._PendingVerificationKey(
            platform_name,
            user_id,
            server_type,
            login_purpose,
        )
        return self.pending_verifications.get(key)


    def PopPendingMessage(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
        login_purpose: str,
    ) -> None:
        """删除指定登录流程的验证码会话"""
        key = self._PendingVerificationKey(
            platform_name,
            user_id,
            server_type,
            login_purpose,
        )
        self.pending_verifications.pop(key, None)

    # endregion

    # region 参数解析


    def GetArgs(self, messages: list[BaseMessageComponent]):
        """参数解析逻辑"""
        args = []
        for msg in messages:
            if isinstance(msg, Plain):
                text = msg.text.strip()
                if text:
                    args.extend(text.split())
        return args

    # endregion

    # region 初始化与验证码过期清理


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法"""
        # 启用 TTL 检测
        self._user_TTL_check_loop_task = asyncio.create_task(self._TTL_check_loop())


    async def _TTL_check_loop(self):
        """周期性清理过期内存用户信息"""
        while True:
            now = time.monotonic()
            expired_keys = []
            for key, pending in self.pending_verifications.items():
                if now - pending.created_at >= self.VERIFICATION_CODE_TTL_SECONDS:
                    expired_keys.append(key)

            for key in expired_keys:
                self.pending_verifications.pop(key, None)

            await asyncio.sleep(self.CHECK_TTL_INTERVAL)

    # endregion

    # region 通用业务辅助方法


    @staticmethod
    def MaskPhone(phone: str | int) -> str:
        """隐藏手机号中间四位，避免日志或消息泄露完整号码"""
        value = str(phone)
        if len(value) < 7:
            return "***"
        return f"{value[:3]}****{value[-4:]}"


    async def GetStoredOfficialUserInfo(
        self,
        event: AstrMessageEvent,
    ) -> tuple[RequestResultOfDoctorInfo | None, str | None]:
        """从数据库恢复官服请求所需的 token 与游戏 UID"""
        token_result = await self.data_storage_handler.aget_user_token(
            event.get_platform_name(),
            event.get_sender_id(),
            self.OFFICIAL,
        )
        if not token_result.status:
            return None, token_result.message
        if not token_result.user_token or not token_result.account_id:
            return None, "保存的登录凭证不完整"

        return RequestResultOfDoctorInfo(
            status      = True,
            phone       = "",
            token       = token_result.user_token,
            uid         = token_result.account_id,
            nickName    = token_result.nickname,
        ), None


    def IsCredentialInvalid(self, message: str | None) -> bool:
        """判断服务器错误是否明确表示账号凭证失效"""
        return message in {"获取角色 token 失败", "角色登录失败，请稍后再试"}

    # endregion

    # region 验证码处理指令


    @filter.command("官服验证码")
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @command_error_boundary("官服验证码")
    async def GetAndSendVerificationCodeWithOfficialServer(self, event: AstrMessageEvent):
        """收集用户给出的手机验证码，交由服务器进行校验"""
        platform_name = event.get_platform_name()
        user_id = event.get_sender_id()
        messages = event.get_messages()

        args = self.GetArgs(messages)
        if len(args) != 2:
            logger.warning(f"参数数量不合法，期望 2，接收到 {len(args)}")
            yield event.plain_result("用法：/官服验证码 <接收到的验证码>")
            return

        verification_code = args[1]
        logger.info(f"用户 {user_id} 提交了验证码")
        pending = self.GetPendingMessage(
            platform_name,
            user_id,
            self.OFFICIAL,
            self.GAME_LOGIN,
        )
        if pending is None:
            yield event.plain_result("请先发送 /方舟官服登录 <手机号码> 获取验证码")
            return

        if time.monotonic() - pending.created_at >= self.VERIFICATION_CODE_TTL_SECONDS:
            logger.warning(f"用户 {user_id} 已过期")
            self.PopPendingMessage(
                platform_name,
                user_id,
                self.OFFICIAL,
                self.GAME_LOGIN,
            )
            yield event.plain_result("验证码已过期，请发送 /方舟官服登录 <手机号码> 获取新验证码")
            return

        phone = pending.phone
        # 获取 auth_token
        result = await self.official_server_login.aget_auth_token(phone, verification_code)

        if result.status is not True:
            message = result.message
            logger.warning(result.message)
            yield event.plain_result(f"登录失败：{message}")
            return

        login_token = result.token
        if login_token is None:
            logger.warning("登录 token 获取失败")
            yield event.plain_result("登录 token 获取失败")
            return

        # 获取账号 token
        account_token_result = await self.official_server_login.aget_account_token(login_token, phone)
        if account_token_result.status is not True:
            message = account_token_result.message
            logger.warning(message)
            yield event.plain_result(f"账号凭证获取失败：{message}")
            return

        account_token = account_token_result.accountToken
        # 账号 token 获取失败，直接结束流程，不执行后续鉴权链条
        if account_token is None:
            logger.warning("账号 token 获取失败")
            yield event.plain_result("账号 token 获取失败")
            return

        # 获取角色账号信息
        doctor_info = await self.official_doctor_info_handler.aget_doctor_info(account_token, phone)

        if doctor_info.status is False:
            message = doctor_info.message
            logger.info(f"信息获取出错：{message}")
            yield event.plain_result(f"登录信息获取出错：{message}")
            return

        doctor_name = doctor_info.nickName
        # 向数据库写入指定平台用户的账号 token
        token_update_result = await self.data_storage_handler.aupdate_user_token(
            event.get_platform_name(),
            user_id,
            self.OFFICIAL,
            doctor_info,
        )
        if not token_update_result.status:
            logger.error(token_update_result.message)
            yield event.plain_result(f"登录凭证保存失败：{token_update_result.message}")
            return

        skland_message = None
        # 使用 login_token 换取森空岛 grant_code
        # 从这里开始，鉴权链路进入森空岛部分
        grant_result = await self.skland_login_handler.aget_grant_code(
            login_token,
            phone,
        )
        # 判断 grant_code 是否成功被获取，若获取失败则不执行接下来的鉴权流程
        if grant_result.status is not True or not grant_result.grant_code:
            skland_message = grant_result.message or "grant code 获取失败"
            logger.warning(f"森空岛凭据初始化失败：{skland_message}")
        else:
            # 通过获取的 grant_code 获取持久化凭证与临时 token
            # token 用于后续签名的计算，需要使用 cred 定期刷新
            # 签名在后续逻辑中用于请求角色账号数据
            cred_result = await self.skland_login_handler.aget_cred_by_grant_code(
                phone,
                grant_result.grant_code,
            )
            if (
                cred_result.status is not True
                or not cred_result.cred
                or not cred_result.token
            ):
                skland_message = cred_result.message or "cred 获取失败"
                logger.warning(f"森空岛凭据初始化失败：{skland_message}")
            else:
                skland_update_result = (
                    # 向数据库写入 or 更新森空岛 cred 凭证
                    await self.data_storage_handler.aupdate_skland_credentials(
                        doctor_info.uid,
                        cred_result.cred,
                        cred_result.token,
                    )
                )
                if not skland_update_result.status:
                    skland_message = skland_update_result.message or "凭据保存失败"
                    logger.warning(f"森空岛凭据保存失败：{skland_message}")

        yield event.plain_result("登录成功")
        await asyncio.sleep(1)
        yield event.plain_result(f"欢迎，Dr. {doctor_name}")
        # 若森空岛流程出现问题，则将情况告知用户
        # 森空岛流程出错，不会影响到官服鉴权流程
        if skland_message:
            await asyncio.sleep(1)
            logger.info(skland_message)
            yield event.plain_result(
                f"森空岛凭据初始化失败：{skland_message}，官服登录不受影响\n"
                "请稍后再尝试重新登录，在此期间无法查询有关账号资产、练度等信息，但抽卡记录查询不受影响"
            )

        await asyncio.sleep(1)
        yield event.plain_result(self.GUIDE_SYNC_GACHAHISTORY)
        if skland_message is None:
            logger.info("森空岛凭据初始化成功")
        self.PopPendingMessage(
            platform_name,
            user_id,
            self.OFFICIAL,
            self.GAME_LOGIN,
        )


    # endregion

    # region 登录指令


    @filter.command("方舟官服登录")
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @command_error_boundary("方舟官服登录")
    async def LoginByOfficialServer(self, event: AstrMessageEvent):
        """通过官服渠道登录，调用官服登录器执行登录操作，仅允许私聊绑定"""
        platform_name = event.get_platform_name()
        user_id = event.get_sender_id()
        messages = event.get_messages()

        args = self.GetArgs(messages)
        if len(args) != 2:
            logger.warning(f"参数数量不合法，期望 2，接收到 {len(args)}")
            yield event.plain_result("用法：/方舟官服登录 <手机号码>")
            return

        # 验证码获取逻辑
        phone = args[1]
        logger.info(f"解析到用户手机号：{self.MaskPhone(phone)}")

        result = await self.official_server_login.aget_verification_code(phone)

        logger.info(f"验证码发送结果：status = {result.status}")

        if result.status is not True:
            logger.warning(result.message)
            yield event.plain_result(f"请求失败：{result.message}")
            return

        self.AddPendingMessage(
            platform_name,
            user_id,
            self.OFFICIAL,
            self.GAME_LOGIN,
            phone,
        )

        logger.info(result.message)
        yield event.plain_result(self.GUIDE_GET_VERIFICATIONCODE_SERVER)



    @filter.command("方舟B服登录", alias = {"方舟b服登录", "方舟逼服登录"})
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @command_error_boundary("方舟B服登录")
    async def LoginByBilibiliServer(self, event: AstrMessageEvent):
        """通过 B 站服登录，调用 B 站 api 执行登录操作，仅允许私聊绑定，目前暂未实现"""
        user_id = event.get_sender_id()
        logger.info(f"用户 {user_id} 通过 B 服登录")
        yield event.plain_result("目前暂不支持 B 服登录！")

    # endregion

    # region 数据更新指令


    @filter.command("官服角色信息更新")
    @command_error_boundary("官服角色信息更新")
    async def UpdateAccountInfo(self, event: AstrMessageEvent):
        """向鹰角服务器请求角色信息数据，并对数据执行可持久化存储"""
        user_id = event.get_sender_id()
        # 封装数据库查询逻辑
        # 注意这里返回的是 tuple[[RequestResultOfDoctorInfo | None, str | None]]
        user_info, credential_error = await self.GetStoredOfficialUserInfo(event)
        if not user_info:
            logger.info(f"用户 {user_id} 没有可用的登录凭证：{credential_error}")
            yield event.plain_result("请先登录官服账号")
            await asyncio.sleep(0.5)
            yield event.plain_result(self.GUIDE_GET_VERIFICATIONCODE_SERVER)
            return

        # 获取 uid
        uid = user_info.uid
        # 获取本地存储的森空岛凭证
        skland_cred_info = await self.data_storage_handler.aget_skland_credentials(uid)
        if not skland_cred_info.status:
            logger.warning(f"未找到 {user_id} 的本地森空岛凭证")
            yield event.plain_result("本地未找到森空岛凭证，请重新登录")
            return

        # 获取 cred 与 token
        cred, token = skland_cred_info.cred, skland_cred_info.token

        # 通过 cred 获取新 token
        refresh_result = await self.skland_login_handler.arefresh_token_by_cred(cred)
        if not refresh_result.status:
            logger.warning(f"新 token 获取失败：{refresh_result.message}")
            yield event.plain_result("token 刷新失败，将尝试使用旧 token")
        else:
            # 更新 cred 与 token
            cred, token = refresh_result.cred, refresh_result.token
            # 将指定 uid 的 cred 与 token 信息放进数据库
            result = await self.data_storage_handler.aupdate_skland_credentials(uid, cred, token)
            if not result.status:
                logger.warning(f"信息写入数据库失败：{result.message}")
                yield event.plain_result("信息存储失败！请在稍后重新登录")
                return

        # 通过账号数据请求角色信息
        account_info_result = await self.get_account_info.aget_account_info(uid, cred, token)
        account_data = account_info_result.data
        if not account_info_result.status:
            logger.warning(f"角色信息请求失败：{account_info_result.message}")
            yield event.plain_result("角色信息请求失败")
            return

        # 调试输出
        logger.info(f"账号数据获取成功，data 字段数：{len(account_data)}")

        # 存储请求到的角色信息
        info_update_result = await self.data_storage_handler.aupdate_account_data(
            uid,
            account_data,
            self.OFFICIAL,
        )
        if not info_update_result.status:
            logger.warning(f"角色信息更新失败：{info_update_result.message}")
            yield event.plain_result("角色信息更新失败")
            return

        if info_update_result.updated is False:
            logger.info(info_update_result.message)
            yield event.plain_result("本地账号数据已是最新，无需覆盖")
            return

        chars = account_data.get("chars")
        skins = account_data.get("skins")
        activity = account_data.get("activity")
        chars_count = len(chars) if isinstance(chars, list) else 0
        skins_count = len(skins) if isinstance(skins, list) else 0
        activity_count = len(activity) if isinstance(activity, list) else 0

        # 获取角色信息字段数量
        category_count = len(set(account_data))

        yield event.plain_result("账号数据更新成功")
        await asyncio.sleep(1)

        yield event.plain_result(
            f"已同步 {category_count} 类数据，包括 "
            f"{chars_count} 条干员数据、"
            f"{skins_count} 条时装数据和 "
            f"{activity_count} 条活动数据"
        )


    @filter.command("官服抽卡记录更新")
    @command_error_boundary("官服抽卡记录更新")
    async def UpdateGachaHistory(self, event: AstrMessageEvent):
        """实现抽卡记录持久化存储，查询近 90 天内记录存储至本地"""
        user_id = event.get_sender_id()
        user_info, credential_error = await self.GetStoredOfficialUserInfo(event)
        if not user_info:
            logger.info(f"用户 {user_id} 没有可用的登录凭证：{credential_error}")
            yield event.plain_result("请先登录官服账号")
            await asyncio.sleep(0.5)
            yield event.plain_result(self.GUIDE_GET_VERIFICATIONCODE_SERVER)
            return

        # 获取卡池种类，随后按种类分页获取全部抽卡记录。
        pool_info = await self.official_get_gacha_history.aget_pool_list(user_info)
        logger.info(f"服务器返回数据：{pool_info}")
        if pool_info.status is False:
            logger.warning(pool_info.message)
            if self.IsCredentialInvalid(pool_info.message):
                yield event.plain_result("登录凭证已失效，请重新登录官服账号")
                return
            yield event.plain_result(pool_info.message)
            return

        pool_list = pool_info.pool_list or []

        gacha_history_result = await self.official_get_gacha_history.aget_gacha_history(
            user_info,
            pool_list,
        )

        # 调试：输出服务器返回数据
        # logger.info(gacha_history_result.gacha_history)

        if gacha_history_result.status is False:
            logger.warning(gacha_history_result.message)
            if self.IsCredentialInvalid(gacha_history_result.message):
                yield event.plain_result("登录凭证已失效，请重新登录官服账号")
                await asyncio.sleep(0.5)
                yield event.plain_result(
                    "添加 bot 好友后，私聊使用 /方舟官服登录 或 /方舟B服登录 指令获取验证码\n"
                    "之后使用 /官服验证码 <验证码> 或 /B服验证码 <验证码> 指令登录\n"
                    "目前仅支持官服"
                )
                return
            # 这里 AI 的选择是直接输出错误消息，虽然便于定位问题，但有些过于“技术化”了。先保留吧
            yield event.plain_result(gacha_history_result.message)
            return

        gacha_history = gacha_history_result.gacha_history or []
        # 服务器返回的“前 90 天内”的抽卡记录数可能大于数据库中存储的抽卡记录数
        # 因为服务器返回的数据并未经过去重，可能存在重复记录，不属于 bug
        logger.info(f"请求成功，服务器返回 {len(gacha_history)} 条未去重数据")
        data_update_result = await self.data_storage_handler.aupdate_gacha_history(
            gacha_history,
            user_info
        )

        if data_update_result.status is False:
            logger.warning(data_update_result.message)
            yield event.plain_result(f"抽卡记录保存失败：{data_update_result.message}")
            return

        logger.info(data_update_result.message)
        yield event.plain_result("已更新近 90 天内的抽卡记录")
        await asyncio.sleep(0.7)
        yield event.plain_result("为保证抽卡数据正确，请在今后 90 天内至少更新一次，否则会影响数据一致性")

    # endregion

    # region 查询指令


    @filter.command("官服抽卡记录查询")
    @command_error_boundary("官服抽卡记录查询")
    async def GetGachaHistory(self, event: AstrMessageEvent):
        """读取本地抽卡记录并生成统计图片，渲染失败时使用文本兜底"""
        user_id = event.get_sender_id()
        stored_history_result = await self.data_storage_handler.aget_gacha_history_by_user(
            event.get_platform_name(),
            user_id,
            self.OFFICIAL,
        )
        if stored_history_result.status is False:
            logger.warning(stored_history_result.message)
            yield event.plain_result(
                stored_history_result.message
                if stored_history_result.message
                else "抽卡信息获取失败"
            )
            return

        gacha_history = stored_history_result.gacha_history or []
        try:
            statistics = await self.gacha_history_analyser.abuild_statistics(
                gacha_history,
                stored_history_result.nickname,
            )
        except (TypeError, ValueError) as exc:
            logger.warning(f"抽卡记录统计失败：{exc}")
            yield event.plain_result("抽卡记录中的时间或位置字段格式异常")
            return

        # 数据库中存储的抽卡记录数可能小于服务器返回的“前 90 天内”的抽卡记录数
        # 因为服务器返回的数据并未经过去重，可能存在重复记录，不属于 bug
        logger.info(f"查询到 {len(gacha_history)} 条抽卡记录")
        fallback_text = self.gacha_history_analyser.build_text_summary(statistics)
        try:
            image_url = await self.html_render(
                GACHA_STATISTICS_TEMPLATE,
                self.gacha_history_analyser.build_render_data(statistics),
                options = GACHA_STATISTICS_RENDER_OPTIONS,
            )
            yield event.image_result(image_url)
        except Exception:
            logger.exception("抽卡统计图片渲染失败，回退到文本")
            yield event.plain_result(fallback_text)


    @filter.command("官服角色信息查询")
    @command_error_boundary("官服角色信息查询")
    async def GetAccountInfo(self, event: AstrMessageEvent):
        """获取角色信息总览"""
        user_id = event.get_sender_id()
        platform_name = event.get_platform_name()
        server_type = self.OFFICIAL

        user_uid_result = await self.data_storage_handler.aget_user_token(platform_name, user_id, server_type)
        if not user_uid_result.status:
            logger.warning(f"角色 UID 获取失败：{user_uid_result.message}")
            yield event.plain_result("角色 UID 获取失败，请稍后再试")
            return

        uid = user_uid_result.account_id

        user_info_result = await self.data_storage_handler.aget_account_data(uid, self.OFFICIAL)
        if not user_info_result.status:
            logger.warning(f"角色数据获取失败：{user_info_result.message}")
            yield event.plain_result("角色数据获取失败，请检查森空岛登录态或稍后再试")
            yield event.plain_result(self.GUIDE_GET_VERIFICATIONCODE_SERVER)
            return

        account_data = user_info_result.account_data
        render_result = await self.account_info_renderer.arender(self, account_data)
        if not render_result.status or not render_result.image_url:
            logger.warning(f"角色信息总览生成失败：{render_result.message}")
            yield event.plain_result(f"角色信息总览生成失败：{render_result.message}")
            return

        logger.info("角色信息总览生成成功")
        yield event.image_result(render_result.image_url)



    @filter.command("干员百科")
    @command_error_boundary("干员百科")
    async def GetOperatorInfo(self, event: AstrMessageEvent):
        """通过 prts.wiki 获取干员百科信息"""
        messages = event.get_messages()

        args = self.GetArgs(messages)
        if len(args) != 2:
            logger.warning(f"参数数量不合法，期望 2，接收到 {len(args)}")
            yield event.plain_result("用法：/干员百科 <干员名称>")
            return

        operator_name = args[1]
        logger.info(f"解析到干员名：{operator_name}")
        try:
            operator = await self.operator_encyclopedia.get_operator(operator_name)
        except OperatorNotFoundError:
            logger.warning(f"PRTS 中没有找到干员：{operator_name}")
            yield event.plain_result(f"PRTS 中没有找到干员：{operator_name}")
            return
        except OperatorResponseError as exc:
            logger.exception(
                f"PRTS 数据请求失败（operator={operator_name!r}）："
                f"{type(exc).__name__}: {exc}"
            )
            cached = self.operator_encyclopedia.get_cached_operator(
                operator_name,
                allow_expired=True,
            )
            if cached is not None:
                logger.warning(
                    f"PRTS 实时请求失败，使用本地缓存文本兜底"
                    f"（operator={operator_name!r}）"
                )
                fallback_text = build_operator_text_summary(cached)
                yield event.plain_result(
                    "PRTS 实时数据请求失败，以下为本地缓存数据：\n\n"
                    + fallback_text
                )
            else:
                yield event.plain_result(
                    "PRTS 数据请求失败，且本地没有可用缓存，请稍后重试"
                )
            return
        except OperatorInfoError as exc:
            logger.exception(
                f"PRTS 干员百科查询失败（operator={operator_name!r}）："
                f"{type(exc).__name__}: {exc}"
            )
            yield event.plain_result(f"干员百科查询失败：{exc}")
            return
        except Exception as exc:
            logger.exception(
                f"PRTS 干员数据处理发生未预期异常（operator={operator_name!r}）："
                f"{type(exc).__name__}: {exc}"
            )
            yield event.plain_result("干员百科查询失败，请稍后重试")
            return

        fallback_text = build_operator_text_summary(operator)
        try:
            image_url = await render_operator_card(self, operator)
            logger.info(f"获取到图片 URL：{image_url}")
            yield event.image_result(image_url)
        except Exception as exc:
            logger.exception(
                f"干员百科图片渲染失败，发送文本兜底（operator={operator_name!r}）："
                f"{type(exc).__name__}: {exc}"
            )
            yield event.plain_result(fallback_text)

    # endregion

    # region 插件销毁


    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        # 停止 TTL 后台任务
        if self._user_TTL_check_loop_task:
            self._user_TTL_check_loop_task.cancel()
            try:
                await self._user_TTL_check_loop_task
            except asyncio.CancelledError:
                pass
        # 关闭连接
        try:
            await self.data_storage_handler.aclose()
        finally:
            self.http_client.close()
            self.prts_http_client.close()

    # endregion
