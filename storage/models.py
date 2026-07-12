# storage/models.py

from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class ReturnResultOfDatabaseOperation:
    status: bool
    message: str | None = None

@dataclass(slots=True, frozen=True)
class ReturnResultOfGachaHistoryFromDatabase:
    status: bool
    message: str | None = None
    gacha_history: list | None = None

@dataclass(slots=True, frozen=True)
class ReturnResultOfUserToken:
    status: bool
    message: str | None = None
    user_token: str | None = None
    account_id: str | None = None
    nickname: str | None = None
