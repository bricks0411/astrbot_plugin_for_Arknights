# GachaHistory/models.py
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class RequestResultOfPoolList:
    status: bool
    message: str
    code: int | None = None
    pool_list: list | None = None

@dataclass(slots=True, frozen=True)
class RequestResultOfGachaHistory:
    status: bool
    message: str
    code: int | None = None
    gacha_history: list | None = None

