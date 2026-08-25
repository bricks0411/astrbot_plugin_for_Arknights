# storage/UserDB.py

import asyncio
import hashlib
import json
import sqlite3
import time
import warnings
import zlib
from pathlib import Path
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken

from ..GetDoctorInfo.models import RequestResultOfDoctorInfo
from .models import (
    ReturnResultOfAccountDataFromDatabase,
    ReturnResultOfAccountDataOperation,
    ReturnResultOfDatabaseOperation,
    ReturnResultOfGachaHistoryFromDatabase,
    ReturnResultOfSklandCredentials,
    ReturnResultOfSklandCredentialsOperation,
    ReturnResultOfUserToken,
)


class DataStorageHandler:

    _SCRIPT_DIR = Path(__file__).with_name("script")
    _SCHEMA_FILE = _SCRIPT_DIR / "InitDB.sql"
    _ACCOUNT_SNAPSHOT_MIGRATION_FILE = (
        _SCRIPT_DIR / "MigrateAccountSnapshots.sql"
    )
    _ACCOUNT_DATA_COMPRESSION = "zlib"
    _ACCOUNT_DATA_ENCRYPTION_VERSION = 1
    _ACCOUNT_DATA_SCHEMA_VERSION = "1"

    # region 数据库初始化与连接配置

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
        """加载本地 token 加密密钥；首次运行时永久生成"""
        key_path = self.db_path.parent / "token.key"
        if key_path.is_file():
            return key_path.read_bytes().strip()

        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except OSError as exc:
            # 审查问题是密钥权限收紧失败后异常被静默吞掉，部署者无法发现凭证保护降级
            # Windows 等平台可能不支持 POSIX 权限，因此保留运行能力并发出可观测的运行时警告
            warnings.warn(
                f"无法将 token.key 权限设置为仅当前用户可读写：{exc}",
                RuntimeWarning,
                stacklevel=2,
            )
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
        """加载外部 SQL 建表脚本，并执行现有数据库的兼容迁移"""
        with self._lock:
            try:
                schema_sql = self._SCHEMA_FILE.read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(
                    f"无法读取数据库初始化脚本：{self._SCHEMA_FILE}"
                ) from exc
            if not schema_sql.strip():
                raise RuntimeError(f"数据库初始化脚本为空：{self._SCHEMA_FILE}")
            self._conn.executescript(schema_sql)

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
            with self._conn:
                if "category" not in gacha_columns:
                    self._conn.execute(
                        "ALTER TABLE gacha_records ADD COLUMN category TEXT NOT NULL DEFAULT ''"
                    )

                # 无论 category 是本次新增还是由中间版本提前创建，都补齐遗留空分类
                self._conn.execute(
                    """
                    UPDATE gacha_records
                    SET category = CASE
                        WHEN pool_name = '标准寻访' THEN 'normal'
                        WHEN pool_name = '中坚寻访' THEN 'classic'
                        ELSE 'limited'
                    END
                    WHERE category = ''
                    """
                )

            snapshot_info = list(
                self._conn.execute("PRAGMA table_info(skland_account_snapshots)")
            )
            snapshot_columns = {row["name"] for row in snapshot_info}
            snapshot_primary_key = [
                row["name"]
                for row in sorted(snapshot_info, key=lambda row: row["pk"])
                if row["pk"]
            ]
            if (
                snapshot_primary_key != ["uid", "server_type"]
                or "last_error" in snapshot_columns
            ):
                self._migrate_account_snapshots(snapshot_columns)


    def _migrate_account_snapshots(self, existing_columns: set[str]) -> None:
        """将旧账号快照表迁移到当前复合主键结构"""
        required_columns = {
            "uid",
            "server_type",
            "payload",
            "compression",
            "encryption_version",
            "payload_sha256",
            "api_current_ts",
            "fetched_at",
            "updated_at",
            "schema_version",
        }
        missing_columns = required_columns - existing_columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise RuntimeError(f"账号快照表缺少迁移所需字段：{missing}")

        try:
            migration_sql = self._ACCOUNT_SNAPSHOT_MIGRATION_FILE.read_text(
                encoding="utf-8"
            )
        except OSError as exc:
            raise RuntimeError(
                "无法读取账号快照迁移脚本："
                f"{self._ACCOUNT_SNAPSHOT_MIGRATION_FILE}"
            ) from exc
        if not migration_sql.strip():
            raise RuntimeError(
                f"账号快照迁移脚本为空：{self._ACCOUNT_SNAPSHOT_MIGRATION_FILE}"
            )

        try:
            self._conn.executescript(migration_sql)
        except sqlite3.Error:
            if self._conn.in_transaction:
                self._conn.rollback()
            raise

    # endregion

    # region 抽卡记录存储与查询


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
            return ReturnResultOfDatabaseOperation (
                status=False,
                message=f"抽卡记录格式异常：{exc}",
            )

        if not params:
            return ReturnResultOfDatabaseOperation (
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
            return ReturnResultOfDatabaseOperation (
                status  = False,
                message = f"数据库写入失败：{exc}",
            )

        return ReturnResultOfDatabaseOperation (
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
            return ReturnResultOfGachaHistoryFromDatabase (
                status  = False,
                message = f"数据库读取失败：{exc}",
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
        """根据聊天平台用户绑定，仅从数据库读取抽卡记录"""
        if not platform_name or not user_id or not server_type:
            return ReturnResultOfGachaHistoryFromDatabase (
                status  = False,
                message = "平台、用户或服务器信息不能为空",
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
            return ReturnResultOfGachaHistoryFromDatabase (
                status  = False,
                message = f"数据库读取失败：{exc}",
            )

        if binding is None:
            return ReturnResultOfGachaHistoryFromDatabase (
                status  = False,
                message = "尚未绑定官服账号",
            )

        doctor_info = RequestResultOfDoctorInfo (
            status  = True,
            phone   = "",
            token   = "",
            uid     = binding["account_id"],
        )
        history_result = self._get_gacha_history(doctor_info)
        return ReturnResultOfGachaHistoryFromDatabase (
            status          = history_result.status,
            message         = history_result.message,
            gacha_history   = history_result.gacha_history,
            nickname        = binding["nickname"],
        )


    async def aget_gacha_history_by_user(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
    ) -> ReturnResultOfGachaHistoryFromDatabase:
        """在线程中根据聊天平台用户绑定读取本地抽卡记录"""
        return await asyncio.to_thread(
            self._get_gacha_history_by_user,
            platform_name,
            user_id,
            server_type,
        )

    # endregion

    # region 森空岛角色数据存储与查询


    def _update_account_data(
        self,
        uid: str,
        account_data: dict,
        server_type: str = "official",
    ) -> ReturnResultOfAccountDataOperation:
        """序列化、压缩并加密指定 UID 的森空岛角色数据"""
        if not uid or not server_type:
            return ReturnResultOfAccountDataOperation(
                status  = False,
                message = "玩家 UID 和服务器类型均不能为空",
                uid     = uid or None,
            )
        if not isinstance(account_data, dict):
            return ReturnResultOfAccountDataOperation(
                status  = False,
                message = "账号数据必须是字典",
                uid     = uid,
            )

        try:
            serialized_data = json.dumps(
                account_data,
                ensure_ascii = False,
                allow_nan    = False,
                separators   = (",", ":"),
                sort_keys    = True,
            ).encode("utf-8")
            payload_sha256 = hashlib.sha256(serialized_data).hexdigest()
            compressed_data = zlib.compress(serialized_data)
            encrypted_payload = self._fernet.encrypt(compressed_data)
        except (TypeError, ValueError, UnicodeError, zlib.error) as exc:
            return ReturnResultOfAccountDataOperation(
                status  = False,
                message = f"账号数据压缩失败：{exc}",
                uid     = uid,
            )

        api_current_ts_value = account_data.get("currentTs")
        api_current_ts = (
            api_current_ts_value
            if isinstance(api_current_ts_value, int)
            and not isinstance(api_current_ts_value, bool)
            else None
        )
        now = int(time.time())

        try:
            with self._lock:
                with self._conn:
                    cursor = self._conn.execute(
                        """
                        INSERT INTO skland_account_snapshots (
                            uid, server_type, payload, compression,
                            encryption_version, payload_sha256,
                            api_current_ts, fetched_at, updated_at,
                            schema_version
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(uid, server_type) DO UPDATE SET
                            payload = excluded.payload,
                            compression = excluded.compression,
                            encryption_version = excluded.encryption_version,
                            payload_sha256 = excluded.payload_sha256,
                            api_current_ts = excluded.api_current_ts,
                            fetched_at = excluded.fetched_at,
                            updated_at = excluded.updated_at,
                            schema_version = excluded.schema_version
                        WHERE skland_account_snapshots.api_current_ts IS NULL
                           OR (
                               excluded.api_current_ts IS NOT NULL
                               AND excluded.api_current_ts
                                   >= skland_account_snapshots.api_current_ts
                           )
                        """,
                        (
                            uid,
                            server_type,
                            encrypted_payload,
                            self._ACCOUNT_DATA_COMPRESSION,
                            self._ACCOUNT_DATA_ENCRYPTION_VERSION,
                            payload_sha256,
                            api_current_ts,
                            now,
                            now,
                            self._ACCOUNT_DATA_SCHEMA_VERSION,
                        ),
                    )
        except sqlite3.Error as exc:
            return ReturnResultOfAccountDataOperation(
                status  = False,
                message = f"账号数据写入失败：{exc}",
                uid     = uid,
            )

        if cursor.rowcount == 0:
            return ReturnResultOfAccountDataOperation(
                status  = True,
                message = "服务器账号数据早于本地快照，已保留本地数据",
                uid     = uid,
                updated = False,
            )

        return ReturnResultOfAccountDataOperation(
            status          = True,
            message         = "账号数据已压缩存储或更新",
            uid             = uid,
            payload_sha256  = payload_sha256,
            original_size   = len(serialized_data),
            compressed_size = len(compressed_data),
            fetched_at      = now,
            updated         = True,
        )


    async def aupdate_account_data(
        self,
        uid: str,
        account_data: dict,
        server_type: str = "official",
    ) -> ReturnResultOfAccountDataOperation:
        """压缩并存储指定 UID 的森空岛角色数据"""
        return await asyncio.to_thread(
            self._update_account_data,
            uid,
            account_data,
            server_type,
        )


    def _get_account_data(
        self,
        uid: str,
        server_type: str = "official",
    ) -> ReturnResultOfAccountDataFromDatabase:
        """读取、解密并解压指定 UID 的森空岛角色数据"""
        if not uid or not server_type:
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = "玩家 UID 和服务器类型均不能为空",
            )

        try:
            with self._lock:
                row = self._conn.execute(
                    """
                    SELECT
                        uid, server_type, payload, compression,
                        encryption_version, payload_sha256,
                        api_current_ts, fetched_at, updated_at,
                        schema_version
                    FROM skland_account_snapshots
                    WHERE uid = ? AND server_type = ?
                    """,
                    (uid, server_type),
                ).fetchone()
        except sqlite3.Error as exc:
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = f"账号数据查询失败：{exc}",
                uid     = uid,
            )

        if row is None:
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = "尚未保存账号数据",
                uid     = uid,
            )
        if row["compression"] != self._ACCOUNT_DATA_COMPRESSION:
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = f"不支持的账号数据压缩格式：{row['compression']}",
                uid     = row["uid"],
            )
        if row["encryption_version"] != self._ACCOUNT_DATA_ENCRYPTION_VERSION:
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = f"不支持的账号数据加密版本：{row['encryption_version']}",
                uid     = row["uid"],
            )

        try:
            encrypted_payload = bytes(row["payload"])
            compressed_data = self._fernet.decrypt(encrypted_payload)
            serialized_data = zlib.decompress(compressed_data)
        except (InvalidToken, TypeError, ValueError, zlib.error):
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = "保存的账号数据无法解密或解压",
                uid     = row["uid"],
            )

        payload_sha256 = hashlib.sha256(serialized_data).hexdigest()
        if payload_sha256 != row["payload_sha256"]:
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = "保存的账号数据完整性校验失败",
                uid     = row["uid"],
            )

        try:
            account_data = json.loads(serialized_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeError):
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = "保存的账号数据不是有效 JSON",
                uid     = row["uid"],
            )
        if not isinstance(account_data, dict):
            return ReturnResultOfAccountDataFromDatabase(
                status  = False,
                message = "保存的账号数据不是字典",
                uid     = row["uid"],
            )

        return ReturnResultOfAccountDataFromDatabase(
            status          = True,
            message         = "账号数据查询成功",
            uid             = row["uid"],
            server_type     = row["server_type"],
            account_data    = account_data,
            payload_sha256  = row["payload_sha256"],
            api_current_ts  = row["api_current_ts"],
            fetched_at      = row["fetched_at"],
            updated_at      = row["updated_at"],
            schema_version  = row["schema_version"],
        )


    async def aget_account_data(
        self,
        uid: str,
        server_type: str = "official",
    ) -> ReturnResultOfAccountDataFromDatabase:
        """在线程中读取并还原指定 UID 的森空岛角色数据"""
        return await asyncio.to_thread(
            self._get_account_data,
            uid,
            server_type,
        )

    # endregion

    # region 平台账号绑定与官服 token


    def _update_user_token(
        self,
        platform_name: str,
        user_id: str,
        server_type: str,
        user_info: RequestResultOfDoctorInfo,
    ) -> ReturnResultOfDatabaseOperation:
        """新增或更新指定平台用户的账号 token"""
        if not platform_name or not user_id or not server_type:
            return ReturnResultOfDatabaseOperation (
                status=False,
                message="平台、用户或服务器信息不能为空",
            )
        if not user_info or not user_info.uid or not user_info.token:
            return ReturnResultOfDatabaseOperation (
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
            return ReturnResultOfDatabaseOperation (
                status  = False,
                message = f"token 保存失败：{exc}",
            )

        return ReturnResultOfDatabaseOperation (
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
        """在线程中新增或更新用户 token"""
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
        """查询指定平台用户的 token 和游戏账号 UID"""
        if not platform_name or not user_id or not server_type:
            return ReturnResultOfUserToken (
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
            return ReturnResultOfUserToken (
                status  = False,
                message = f"token 查询失败：{exc}",
            )

        if row is None:
            return ReturnResultOfUserToken (
                status  = False,
                message = "尚未保存登录凭证",
            )

        encrypted_token = row["token_encrypted"]
        try:
            user_token = self._fernet.decrypt(
                encrypted_token.encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeError, AttributeError):
            return ReturnResultOfUserToken (
                status  = False,
                message = "保存的登录凭证无法解密，请重新登录",
            )

        return ReturnResultOfUserToken (
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
        """在线程中查询用户 token"""
        return await asyncio.to_thread(
            self._get_user_token,
            platform_name,
            user_id,
            server_type,
        )

    # endregion

    # region 森空岛凭证存储与查询


    def _get_skland_credentials(
        self,
        uid: str,
    ) -> ReturnResultOfSklandCredentials:
        """按游戏 UID 查询并解密森空岛 cred 与签名 token"""
        if not uid:
            return ReturnResultOfSklandCredentials(
                status  = False,
                message = "玩家 UID 不能为空",
            )

        try:
            with self._lock:
                row = self._conn.execute(
                    """
                    SELECT uid, cred_encrypted, token_encrypted
                    FROM skland_credentials
                    WHERE uid = ?
                    """,
                    (uid,),
                ).fetchone()
        except sqlite3.Error as exc:
            return ReturnResultOfSklandCredentials(
                status  = False,
                message = f"森空岛凭证查询失败：{exc}",
            )

        if row is None:
            return ReturnResultOfSklandCredentials(
                status  = False,
                message = "尚未保存森空岛凭证",
                uid     = uid,
            )

        try:
            cred = self._fernet.decrypt(
                row["cred_encrypted"].encode("ascii")
            ).decode("utf-8")
            token = self._fernet.decrypt(
                row["token_encrypted"].encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeError, AttributeError):
            return ReturnResultOfSklandCredentials(
                status  = False,
                message = "保存的森空岛凭证无法解密，请重新登录",
                uid     = row["uid"],
            )

        return ReturnResultOfSklandCredentials(
            status  = True,
            message = "森空岛凭证查询成功",
            uid     = row["uid"],
            cred    = cred,
            token   = token,
        )


    async def aget_skland_credentials(
        self,
        uid: str,
    ) -> ReturnResultOfSklandCredentials:
        """在线程中按 UID 查询森空岛凭证"""
        return await asyncio.to_thread(
            self._get_skland_credentials,
            uid
        )


    def _update_skland_credentials(
        self,
        uid: str,
        cred: str,
        token: str,
    ) -> ReturnResultOfSklandCredentialsOperation:
        """新增或更新指定 UID 的森空岛凭证"""
        if not uid or not cred or not token:
            return ReturnResultOfSklandCredentialsOperation(
                status  = False,
                message = "UID、cred 和 token 均不能为空",
                uid     = uid or None,
            )

        now = int(time.time())
        try:
            encrypted_cred = self._fernet.encrypt(
                cred.encode("utf-8")
            ).decode("ascii")
            encrypted_token = self._fernet.encrypt(
                token.encode("utf-8")
            ).decode("ascii")
            with self._lock:
                with self._conn:
                    self._conn.execute(
                        """
                        INSERT INTO skland_credentials (
                            uid, cred_encrypted, token_encrypted,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(uid) DO UPDATE SET
                            cred_encrypted = excluded.cred_encrypted,
                            token_encrypted = excluded.token_encrypted,
                            updated_at = excluded.updated_at
                        """,
                        (
                            uid,
                            encrypted_cred,
                            encrypted_token,
                            now,
                            now,
                        ),
                    )
        except (sqlite3.Error, TypeError, UnicodeError) as exc:
            return ReturnResultOfSklandCredentialsOperation(
                status  = False,
                message = f"森空岛凭证保存失败：{exc}",
                uid     = uid,
            )

        return ReturnResultOfSklandCredentialsOperation(
            status  = True,
            message = "森空岛凭证已保存或更新",
            uid     = uid,
        )


    async def aupdate_skland_credentials(
        self,
        uid: str,
        cred: str,
        token: str,
    ) -> ReturnResultOfSklandCredentialsOperation:
        """在线程中新增或更新森空岛凭证"""
        return await asyncio.to_thread(
            self._update_skland_credentials,
            uid,
            cred,
            token,
        )

    # endregion

    # region 数据库连接生命周期


    def close(self):
        """在线程锁保护下关闭 SQLite 数据库连接"""
        with self._lock:
            self._conn.close()


    async def aclose(self):
        """关闭数据库连接，什么都不返回"""
        await asyncio.to_thread(self.close)

    # endregion
