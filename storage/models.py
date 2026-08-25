# storage/models.py

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class ReturnResultOfDatabaseOperation:
    status: bool
    message: str | None = None

@dataclass(slots=True, frozen=True)
class ReturnResultOfGachaHistoryFromDatabase:
    status: bool
    message: str | None = None
    gacha_history: list | None = None
    nickname: str | None = None


@dataclass(slots=True, frozen=True)
class ReturnResultOfAccountDataFromDatabase:
    """从数据库读取并还原的森空岛角色数据"""
    status: bool
    message: str | None = None
    uid: str | None = None
    server_type: str | None = None
    account_data: dict[str, Any] | None = None
    payload_sha256: str | None = None
    api_current_ts: int | None = None
    fetched_at: int | None = None
    updated_at: int | None = None
    schema_version: str | None = None


@dataclass(slots=True, frozen=True)
class ReturnResultOfAccountDataOperation:
    """森空岛角色数据压缩写入结果"""
    status: bool
    message: str | None = None
    uid: str | None = None
    payload_sha256: str | None = None
    original_size: int | None = None
    compressed_size: int | None = None
    fetched_at: int | None = None
    updated: bool | None = None

@dataclass(slots=True, frozen=True)
class ReturnResultOfUserToken:
    status: bool
    message: str | None = None
    user_token: str | None = None
    account_id: str | None = None
    nickname: str | None = None

@dataclass(slots=True, frozen=True)
class ReturnResultOfSklandCredentials:
    """按游戏 UID 查询到的森空岛凭证"""
    status: bool
    message: str | None = None
    uid: str | None = None
    cred: str | None = None
    token: str | None = None

@dataclass(slots=True, frozen=True)
class ReturnResultOfSklandCredentialsOperation:
    """森空岛凭证写入结果"""
    status: bool
    message: str | None = None
    uid: str | None = None
