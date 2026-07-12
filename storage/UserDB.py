# storage/UserDB.py

import asyncio
import sqlite3
import time

from cryptography.fernet import Fernet, InvalidToken
from pathlib import Path
from threading import RLock

from ..GetDoctorInfo.models import RequestResultOfDoctorInfo
from .models import (
    ReturnResultOfDatabaseOperation,
    ReturnResultOfGachaHistoryFromDatabase,
    ReturnResultOfUserToken,
)


class DataStorageHandler:

    def __init__(
        self,
        db_path: str | Path,
        busy_timeout_ms: int = 5000
    ):
        """初始化类方法"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._load_or_create_token_key())

        self._lock = RLock()

        self._conn = sqlite3.connect(
            self.db_path,
            timeout=busy_timeout_ms / 1000,
            isolation_level="IMMEDIATE",
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row

        self._configure_connection(busy_timeout_ms)
        self._init_schema()


    def _load_or_create_token_key(self) -> bytes:
        """加载本地 token 加密密钥；首次运行时永久生成。"""
        key_path = self.db_path.parent / "token.key"
        if key_path.is_file():
            return key_path.read_bytes().strip()

        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
        return key


    def _configure_connection(self, busy_timeout_ms: int) -> None:
        """连接参数配置：同步策略、日志策略、超时时长等"""
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA wal_autocheckpoint=1000")
            self._conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")


    def _init_schema(self) -> None:
        """表创建逻辑"""
        with self._lock:
            # 创建用户表
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    platform_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,

                    server_type TEXT NOT NULL,
                    auth_provider TEXT NOT NULL,

                    account_id TEXT NOT NULL,
                    nickname TEXT,
                    phone_mask TEXT,
                    phone_hash TEXT,

                    token_encrypted TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,

                    UNIQUE(platform_name, user_id, server_type)
                )
                """
            )
            self._conn.executescript (
                """
                CREATE TABLE IF NOT EXISTS gacha_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    uid TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',

                    pool_id TEXT NOT NULL,
                    pool_name TEXT NOT NULL,

                    char_id TEXT NOT NULL,
                    char_name TEXT NOT NULL,
                    rarity INTEGER NOT NULL,
                    is_new INTEGER NOT NULL,

                    gacha_ts TEXT NOT NULL,
                    pos INTEGER NOT NULL,

                    created_at INTEGER NOT NULL,

                    UNIQUE(uid, pool_id, gacha_ts, pos, char_id)
                );
                """
            )
            account_columns = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(account_bindings)")
            }
            if "nickname" not in account_columns:
                self._conn.execute("ALTER TABLE account_bindings ADD COLUMN nickname TEXT")

            gacha_columns = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(gacha_records)")
            }
            if "category" not in gacha_columns:
                self._conn.execute(
                    "ALTER TABLE gacha_records ADD COLUMN category TEXT NOT NULL DEFAULT ''"
                )
                self._conn.execute(
                    "UPDATE gacha_records SET category = 'normal' WHERE pool_name = '标准寻访'"
                )
                self._conn.execute(
                    "UPDATE gacha_records SET category = 'classic' WHERE pool_name = '中坚寻访'"
                )


    def _update_gacha_history(
        self,
        gacha_history: list,
        doctor_info: RequestResultOfDoctorInfo
    ) -> ReturnResultOfDatabaseOperation:
        """
        抽卡记录更新luoji

        gacha_history 是 list 类型，存放 dict
        一个简单示例如下
        {
            "poolId": "LINKAGE_74_0_1",
            "poolName": "幽境狩人",
            "charId": "char_278_orchid",
            "charName": "梓兰",
            "rarity": 2,
            "isNew": false,
            "gachaTs": "1780889087848",
            "pos": 8
        }
        """
        if not doctor_info or not doctor_info.uid:
            return ReturnResultOfDatabaseOperation (
                status  = False,
                message = "玩家 ID 不能为空"
            )

        uid = doctor_info.uid
        created_at = int(time.time())

        try:
            params = [
                (
                    uid,
                    gacha.get("category", ""),
                    gacha["poolId"],
                    gacha["poolName"],
                    gacha["charId"],
                    gacha["charName"],
                    gacha["rarity"],
                    gacha["isNew"],
                    gacha["gachaTs"],
                    gacha["pos"],
                    created_at,
                )
                for gacha in gacha_history
            ]
        except (KeyError, TypeError) as exc:
            return ReturnResultOfDatabaseOperation(
                status=False,
                message=f"抽卡记录格式异常：{exc}",
            )

        if not params:
            return ReturnResultOfDatabaseOperation(
                status  = True,
                message = "没有需要更新的抽卡记录",
            )

        try:
            with self._lock:
                with self._conn:
                    cursor = self._conn.executemany(
                        """
                        INSERT INTO gacha_records (
                            uid, category, pool_id, pool_name, char_id, char_name,
                            rarity, is_new, gacha_ts, pos, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (
                            uid, pool_id, gacha_ts, pos, char_id
                        ) DO NOTHING
                        """,
                        params,
                    )
        except sqlite3.Error as exc:
            return ReturnResultOfDatabaseOperation(
                status=False,
                message=f"数据库写入失败：{exc}",
            )

        return ReturnResultOfDatabaseOperation(
            status  = True,
            message = f"新增 {cursor.rowcount} 条抽卡记录",
        )


    async def aupdate_gacha_history(
        self,
        gacha_history: list,
        doctor_info: RequestResultOfDoctorInfo
    ) -> ReturnResultOfDatabaseOperation:
        """创建线程更新抽卡记录，以避免阻塞 CPU"""
        return await asyncio.to_thread(
            self._update_gacha_history,
            gacha_history,
            doctor_info
        )


    def _get_gacha_history(
        self,
        doctor_info: RequestResultOfDoctorInfo
    ) -> ReturnResultOfGachaHistoryFromDatabase:
        """获取指定用户的抽卡记录"""
        if not doctor_info:
            return ReturnResultOfGachaHistoryFromDatabase (
                status  = False,
                message = "玩家信息不能为空"
            )

        uid = doctor_info.uid
        if not uid:
            return ReturnResultOfGachaHistoryFromDatabase (
                status  = False,
                message = "玩家 UID 不能为空"
            )

        try:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT
                        category, pool_id, pool_name, char_id, char_name,
                        rarity, is_new, gacha_ts, pos
                    FROM
                        gacha_records
                    WHERE
                        uid = ?
                    ORDER BY CAST(gacha_ts AS INTEGER) ASC, pos ASC
                    """,
                    (uid,)
                ).fetchall()
        except sqlite3.Error as exc:
            return ReturnResultOfGachaHistoryFromDatabase(
                status=False,
                message=f"数据库读取失败：{exc}",
            )

        gacha_history = [
            {
                "poolId": gacha["pool_id"],
                "category": gacha["category"],
                "poolName": gacha["pool_name"],
                "charId": gacha["char_id"],
                "charName": gacha["char_name"],
                "rarity": gacha["rarity"],
                "isNew": bool(gacha["is_new"]),
                "gachaTs": gacha["gacha_ts"],
                "pos": gacha["pos"],
            }
            for gacha in rows
        ]

        return ReturnResultOfGachaHistoryFromDatabase (
            status          = True,
            message         = f"获取到 {len(gacha_history)} 条抽卡记录",
            gacha_history   = gacha_history
        )


    async def aget_gacha_history(
        self,
        doctor_info: RequestResultOfDoctorInfo
    ) -> ReturnResultOfGachaHistoryFromDatabase:
        """创建线程获取指定用户抽卡记录"""
        return await asyncio.to_thread(
            self._get_gacha_history,
            doctor_info
        )


    def _get_gacha_history_by_user(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
    ) -> ReturnResultOfGachaHistoryFromDatabase:
        """根据聊天平台用户绑定，仅从数据库读取抽卡记录。"""
        if not platform_name or not user_id or not server_type:
            return ReturnResultOfGachaHistoryFromDatabase(
                status=False,
                message="平台、用户或服务器信息不能为空",
            )

        try:
            with self._lock:
                binding = self._conn.execute(
                    """
                    SELECT account_id, nickname
                    FROM account_bindings
                    WHERE platform_name = ? AND user_id = ? AND server_type = ?
                    """,
                    (platform_name, user_id, server_type),
                ).fetchone()
        except sqlite3.Error as exc:
            return ReturnResultOfGachaHistoryFromDatabase(
                status=False,
                message=f"数据库读取失败：{exc}",
            )

        if binding is None:
            return ReturnResultOfGachaHistoryFromDatabase(
                status=False,
                message="尚未绑定官服账号",
            )

        doctor_info = RequestResultOfDoctorInfo(
            status=True,
            phone="",
            token="",
            uid=binding["account_id"],
        )
        history_result = self._get_gacha_history(doctor_info)
        return ReturnResultOfGachaHistoryFromDatabase(
            status=history_result.status,
            message=history_result.message,
            gacha_history=history_result.gacha_history,
            nickname=binding["nickname"],
        )


    async def aget_gacha_history_by_user(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
    ) -> ReturnResultOfGachaHistoryFromDatabase:
        """在线程中根据聊天平台用户绑定读取本地抽卡记录。"""
        return await asyncio.to_thread(
            self._get_gacha_history_by_user,
            platform_name,
            user_id,
            server_type,
        )


    def _update_user_token(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
        user_info: RequestResultOfDoctorInfo,
    ) -> ReturnResultOfDatabaseOperation:
        """新增或更新指定平台用户的账号 token。"""
        if not platform_name or not user_id or not server_type:
            return ReturnResultOfDatabaseOperation(
                status=False,
                message="平台、用户或服务器信息不能为空",
            )
        if not user_info or not user_info.uid or not user_info.token:
            return ReturnResultOfDatabaseOperation(
                status=False,
                message="账号 UID 或 token 不能为空",
            )

        now = int(time.time())
        try:
            with self._lock:
                with self._conn:
                    self._conn.execute(
                        """
                        INSERT INTO account_bindings (
                            platform_name, user_id, server_type, auth_provider,
                            account_id, nickname, token_encrypted, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(platform_name, user_id, server_type)
                        DO UPDATE SET
                            auth_provider = excluded.auth_provider,
                            account_id = excluded.account_id,
                            nickname = excluded.nickname,
                            token_encrypted = excluded.token_encrypted,
                            updated_at = excluded.updated_at
                        """,
                        (
                            platform_name,
                            user_id,
                            server_type,
                            "hypergryph",
                            user_info.uid,
                            user_info.nickName,
                            self._fernet.encrypt(user_info.token.encode("utf-8")).decode("ascii"),
                            now,
                            now,
                        ),
                    )
        except sqlite3.Error as exc:
            return ReturnResultOfDatabaseOperation(
                status  = False,
                message = f"token 保存失败：{exc}",
            )

        return ReturnResultOfDatabaseOperation(
            status  = True,
            message = "token 已更新",
        )


    async def aupdate_user_token(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
        user_info: RequestResultOfDoctorInfo,
    ) -> ReturnResultOfDatabaseOperation:
        """在线程中新增或更新用户 token。"""
        return await asyncio.to_thread(
            self._update_user_token,
            platform_name,
            user_id,
            server_type,
            user_info,
        )


    def _get_user_token(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
    ) -> ReturnResultOfUserToken:
        """查询指定平台用户的 token 和游戏账号 UID。"""
        if not platform_name or not user_id or not server_type:
            return ReturnResultOfUserToken(
                status  = False,
                message = "平台、用户或服务器信息不能为空",
            )

        try:
            with self._lock:
                row = self._conn.execute(
                    """
                    SELECT account_id, nickname, token_encrypted
                    FROM account_bindings
                    WHERE platform_name = ? AND user_id = ? AND server_type = ?
                    """,
                    (platform_name, user_id, server_type),
                ).fetchone()
        except sqlite3.Error as exc:
            return ReturnResultOfUserToken(
                status  = False,
                message = f"token 查询失败：{exc}",
            )

        if row is None:
            return ReturnResultOfUserToken(
                status  = False,
                message = "尚未保存登录凭证",
            )

        encrypted_token = row["token_encrypted"]
        try:
            user_token = self._fernet.decrypt(
                encrypted_token.encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeError, AttributeError):
            return ReturnResultOfUserToken(
                status  = False,
                message = "保存的登录凭证无法解密，请重新登录",
            )

        return ReturnResultOfUserToken(
            status      = True,
            message     = "token 查询成功",
            user_token  = user_token,
            account_id  = row["account_id"],
            nickname    = row["nickname"],
        )


    async def aget_user_token(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
    ) -> ReturnResultOfUserToken:
        """在线程中查询用户 token。"""
        return await asyncio.to_thread(
            self._get_user_token,
            platform_name,
            user_id,
            server_type,
        )


    def close(self):
        with self._lock:
            self._conn.close()


    async def aclose(self):
        """关闭数据库连接，什么都不返回"""
        await asyncio.to_thread(self.close)
