# main.py
import time
import asyncio

from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain, BaseMessageComponent
from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .LoginTools.OfficialServerLogin import OfficialServerLogin
from .GetDoctorInfo.OfficialDoctorInfoHandler import OfficialDoctorInfoHandler
from .GachaHistory.GetGachaHistory import OfficialGetGachaHistory
from .storage.UserDB import DataStorageHandler
from .network.HttpClient import HttpClient
from .analysis.SixStarsAnalyser import GachaHistoryAnalyser
from .OperatorInfo import (
    OperatorEncyclopedia,
    OperatorInfoError,
    OperatorNotFoundError,
    PrtsWikiClient,
)
from .analysis.GachaHistoryT2I import (
    GACHA_STATISTICS_RENDER_OPTIONS,
    GACHA_STATISTICS_TEMPLATE,
)
from .GetDoctorInfo.models import RequestResultOfDoctorInfo

PLUGIN_NAME = "astrbot_plugin_for_Arknights"

@register(
    "Arknights",
    "Bricks0411",
    "mrfz 综合查询插件",
    "1.0.0"
)
class ArknightsChecker(Star):

    # 服务器种类
    OFFICIAL = "official"
    BILIBILI = "bilibili"
    # 验证码有效期
    VERIFICATION_CODE_TTL_SECONDS = 1800
    # TTL 轮询区间
    CHECK_TTL_INTERVAL = 60

    def __init__(self, context: Context):
        """初始化插件依赖、功能服务和用户会话状态。"""
        super().__init__(context)
        # 各类功能模块
        self.http_client = HttpClient(timeout = 10)                                                       # 统一化 HTTP 客户端
        self.official_server_login = OfficialServerLogin(
            self.http_client
        )
        self.official_doctor_info_handler = OfficialDoctorInfoHandler(
            self.http_client
        )
        self.official_get_gacha_history = OfficialGetGachaHistory(
            self.http_client
        )
        self.gacha_history_analyser = GachaHistoryAnalyser(
            self._build_avatar_cache_path()
        )
        self.operator_encyclopedia = OperatorEncyclopedia(
            PrtsWikiClient(self.http_client),
            self._build_operator_info_cache_path(),
            cache_ttl_seconds   = 24 * 60 * 60,
            download_portrait   = True
        )

        # 官服内存信息维护
        self.pending_verification_code_by_userid_official: dict[str, str] = {}                                          # 等待验证码的用户列表
        # B 服内存信息维护
        self.pending_verification_code_by_userid_bilibili: dict[str, str] = {}
        # 统一临时信息维护
        self.pending_verification_code_by_userid_TTL: dict[tuple[str, str], float] = {}                                             # 等待用户 TTL
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
        """构造永久干员头像缓存目录。"""
        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        return plugin_data_dir / "avatar_cache"


    def _build_operator_info_cache_path(self) -> Path:
        """构造干员百科数据及立绘缓存目录。"""
        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        return plugin_data_dir / "operator_info_cache"


    def AddPendingMessage(self, server_type: str, user_id: str, phone: str):
        """封装等待列表的信息更新逻辑"""
        # 更新 TTL 信息
        # 使用 (user_id, server_type) 统一维护不同服务器的等待元组
        TTL_tuple = (user_id, server_type)
        current_time = time.monotonic()
        self.pending_verification_code_by_userid_TTL[TTL_tuple] = current_time
        # 删除临时信息
        if server_type == "official":
            self.pending_verification_code_by_userid_official[user_id] = phone
        elif server_type == "bilibili":
            self.pending_verification_code_by_userid_bilibili[user_id] = phone
        else:
            logger.warn("服务器信息无效")


    def PopPendingMessage(self, server_type: str, user_id: str):
        """封装等待列表的信息删除逻辑"""
        # 删除 TTL 信息
        TTL_tuple = (user_id, server_type)
        self.pending_verification_code_by_userid_TTL.pop(TTL_tuple, None)
        # 删除临时信息
        if server_type == "official":
            self.pending_verification_code_by_userid_official.pop(user_id, None)
        elif server_type == "bilibili":
            self.pending_verification_code_by_userid_bilibili.pop(user_id, None)
        else:
            logger.warn("服务器信息无效")


    def GetArgs(self, messages: list[BaseMessageComponent]):
        """参数解析逻辑"""
        args = []
        for msg in messages:
            if isinstance(msg, Plain):
                text = msg.text.strip()
                if text:
                    args.extend(text.split())
        return args


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法"""
        # 启用 TTL 检测
        self._user_TTL_check_loop_task = asyncio.create_task(self._TTL_check_loop())


    async def _TTL_check_loop(self):
        """周期性清理过期内存用户信息"""
        while True:
            expired_users = []
            now = time.monotonic()
            for (user_id, server_type), create_time in self.pending_verification_code_by_userid_TTL.items():
                if now - create_time >= self.VERIFICATION_CODE_TTL_SECONDS:
                    expired_users.append((user_id, server_type))

            for (user_id, server_type) in expired_users:
                self.PopPendingMessage(server_type, user_id)

            await asyncio.sleep(self.CHECK_TTL_INTERVAL)


    @staticmethod
    def MaskPhone(phone: str | int) -> str:
        """隐藏手机号中间四位，避免日志或消息泄露完整号码。"""
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
            status  = True,
            phone   = "",
            token   = token_result.user_token,
            uid     = token_result.account_id,
            nickName = token_result.nickname,
        ), None


    def IsCredentialInvalid(self, message: str | None) -> bool:
        """判断服务器错误是否明确表示账号凭证失效"""
        return message in {"获取角色 token 失败", "角色登录失败，请稍后再试"}


    @filter.command("官服验证码")
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def GetAndSendVerificationCodeWithOfficialServer(self, event: AstrMessageEvent):
        """收集用户给出的手机验证码，交由服务器进行校验"""
        user_id = event.get_sender_id()
        messages = event.get_messages()

        args = self.GetArgs(messages)
        if len(args) != 2:
            logger.warn(f"参数数量不合法，期望 2，接收到 {len(args)}")
            yield event.plain_result("用法：/官服验证码 <接收到的验证码>")
            return

        verification_code = args[1]
        logger.info(f"用户 {user_id} 提交了验证码")
        phone = self.pending_verification_code_by_userid_official.get(user_id)
        if not phone:
            yield event.plain_result("请先发送 /方舟官服登录 <手机号码> 获取验证码")
            return

        current_time = time.monotonic()
        TTL_tuple = (user_id, self.OFFICIAL)
        create_time = self.pending_verification_code_by_userid_TTL.get(TTL_tuple)

        if create_time is None:
            logger.warn(f"用户 {user_id} 对应的 create_time 为 None")
            yield event.plain_result("用户状态未同步，请发送 /方舟官服登录 <手机号码> 获取新验证码")
            return

        if current_time - create_time >= self.VERIFICATION_CODE_TTL_SECONDS:
            logger.warn(f"用户 {user_id} 已过期")
            self.PopPendingMessage(self.OFFICIAL, user_id)
            yield event.plain_result("验证码已过期，请发送 /方舟官服登录 <手机号码> 获取新验证码")
            return

        result = await self.official_server_login.aget_auth_token(phone, verification_code)

        if result.status is not True:
            message = result.message
            logger.warn(result.message)
            yield event.plain_result(f"登录失败：{message}")
            return

        login_token = result.token

        account_token_result = await self.official_server_login.aget_account_token(login_token, phone)
        if account_token_result.status is not True:
            message = account_token_result.message
            logger.warn(message)
            yield event.plain_result(f"账号凭证获取失败：{message}")
            return

        account_token = account_token_result.accountToken

        doctor_info = await self.official_doctor_info_handler.aget_doctor_info(account_token, phone)

        if doctor_info.status is False:
            message = doctor_info.message
            logger.info(f"信息获取出错：{message}")
            yield event.plain_result(f"登录信息获取出错：{message}")
            return

        doctor_name = doctor_info.nickName

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

        yield event.plain_result("登录成功")
        await asyncio.sleep(1)
        yield event.plain_result(f"欢迎，Dr. {doctor_name}")
        await asyncio.sleep(1)
        yield event.plain_result("若这是你第一次登录，请根据账号所在的服务器种类，使用 /官服抽卡记录更新 或 /B服抽卡记录更新 指令同步数据（目前仅支持官服）")
        self.PopPendingMessage(self.OFFICIAL, user_id)


    @filter.command("方舟官服登录")
    # 消息类型过滤器：仅允许私聊触发该指令
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def LoginByOfficialServer(self, event: AstrMessageEvent):
        """通过官服渠道登录，调用官服登录器执行登录操作，仅允许私聊绑定"""
        user_id = event.get_sender_id()
        messages = event.get_messages()

        args = self.GetArgs(messages)
        if len(args) != 2:
            logger.warn(f"参数数量不合法，期望 2，接收到 {len(args)}")
            yield event.plain_result("用法：/方舟官服登录 <手机号码>")
            return

        # 验证码获取逻辑
        phone = args[1]
        logger.info(f"解析到用户手机号：{self.MaskPhone(phone)}")
        result = await self.official_server_login.aget_verification_code(phone)

        logger.info(f"验证码发送结果：status = {result.status}")

        if result.status is not True:
            logger.warn(result.message)
            yield event.plain_result(f"请求失败：{result.message}")
            return

        logger.info(result.message)
        yield event.plain_result(f"验证码发送成功，30 分钟内有效，请发送 /官服验证码 <接收到的验证码> 执行下一步操作")
        self.AddPendingMessage(self.OFFICIAL, user_id, phone)
        # self.pending_verification_code_by_userid[user_id] = phone
        # 初始化并启动计时器


    @filter.command("方舟B服登录", alias = {"方舟b服登录", "方舟逼服登录"})
    # 消息类型过滤器，仅允许私聊触发该指令
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def LoginByBilibiliServer(self, event: AstrMessageEvent):
        """通过 B 站服登录，调用 B 站 api 执行登录操作，仅允许私聊绑定，目前暂未实现"""
        user_id = event.get_sender_id()
        logger.info(f"用户 {user_id} 通过 B 服登录")
        yield event.plain_result("目前暂不支持 B 服登录！")


    @filter.command("官服抽卡记录更新")
    async def UpdateGachaHistory(self, event: AstrMessageEvent):
        """实现抽卡记录持久化存储，查询近 90 天内记录存储至本地"""
        user_id = event.get_sender_id()
        user_info, credential_error = await self.GetStoredOfficialUserInfo(event)
        if not user_info:
            logger.info(f"用户 {user_id} 没有可用的登录凭证：{credential_error}")
            yield event.plain_result("请先登录官服账号")
            return

        # 获取卡池种类，随后按种类分页获取全部抽卡记录。
        pool_info = await self.official_get_gacha_history.aget_pool_list(user_info)
        logger.info(f"服务器返回数据：{pool_info}")
        if pool_info.status is False:
            logger.warn(pool_info.message)
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

        if gacha_history_result.status is False:
            logger.warn(gacha_history_result.message)
            if self.IsCredentialInvalid(gacha_history_result.message):
                yield event.plain_result("登录凭证已失效，请重新登录官服账号")
                return
            yield event.plain_result(gacha_history_result.message)
            return

        gacha_history = gacha_history_result.gacha_history or []
        logger.info(f"请求成功，服务器返回 {len(gacha_history)} 条数据")
        data_update_result = await self.data_storage_handler.aupdate_gacha_history(
            gacha_history,
            user_info
        )

        if data_update_result.status is False:
            logger.warn(data_update_result.message)
            yield event.plain_result(f"抽卡记录保存失败：{data_update_result.message}")
            return

        logger.info(data_update_result.message)
        yield event.plain_result("已更新近 90 天内的抽卡记录")


    @filter.command("官服抽卡记录查询")
    async def GetGachaHistory(self, event: AstrMessageEvent):
        """读取本地抽卡记录并生成统计图片，渲染失败时使用文本兜底。"""
        user_id = event.get_sender_id()
        stored_history_result = await self.data_storage_handler.aget_gacha_history_by_user(
            event.get_platform_name(),
            user_id,
            self.OFFICIAL,
        )
        if stored_history_result.status is False:
            logger.warn(stored_history_result.message)
            yield event.plain_result(stored_history_result.message)
            return

        gacha_history = stored_history_result.gacha_history or []
        try:
            statistics = await self.gacha_history_analyser.abuild_statistics(
                gacha_history,
                stored_history_result.nickname,
            )
        except (TypeError, ValueError) as exc:
            logger.warn(f"抽卡记录统计失败：{exc}")
            yield event.plain_result("抽卡记录中的时间或位置字段格式异常")
            return

        logger.info(f"查询到 {len(gacha_history)} 条抽卡记录")
        fallback_text = self.gacha_history_analyser.build_text_summary(statistics)
        try:
            image_url = await self.html_render(
                GACHA_STATISTICS_TEMPLATE,
                self.gacha_history_analyser.build_render_data(statistics),
                options = GACHA_STATISTICS_RENDER_OPTIONS,
            )
            yield event.image_result(image_url)
        except Exception as exc:
            logger.error(f"抽卡统计图片渲染失败，回退到文本：{exc}")
            yield event.plain_result(fallback_text)


    @filter.command("干员百科")
    async def GetOperatorInfo(self, event: AstrMessageEvent):
        """通过 prts.wiki 获取干员百科信息"""
        messages = event.get_messages()

        args = self.GetArgs(messages)
        if len(args) != 2:
            logger.warn(f"参数数量不合法，期望 2，接收到 {len(args)}")
            yield event.plain_result("用法：/干员百科 <干员名称>")
            return

        operator_name = args[1]
        logger.info(f"解析到干员名：{operator_name}")
        try:
            image_url = await self.operator_encyclopedia.query_and_render(
                self,
                operator_name
            )
            logger.info(f"获取到图片 URL：{image_url}")
            yield event.image_result(image_url)
        except OperatorNotFoundError:
            logger.warn(f"PRTS 中没有找到干员：{operator_name}")
            yield event.plain_result(f"PRTS 中没有找到干员：{operator_name}")
        except OperatorInfoError as exc:
            logger.warn(f"干员百科查询失败：{exc}")
            yield event.plain_result(f"干员百科查询失败：{exc}")
        except Exception as exc:
            logger.error(f"干员百科图片渲染失败：{exc}")
            yield event.plain_result("干员数据获取成功，但图片渲染失败，退回至文本数据")



    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        # 停止 TTL 后台任务
        if self._user_TTL_check_loop_task:
            self._user_TTL_check_loop_task.cancel()
            try:
                await self._user_TTL_check_loop_task
            except asyncio.CancelledError:
                pass
        # 关闭数据库连接
        await self.data_storage_handler.aclose()
