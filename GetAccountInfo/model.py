# GetAccountInfo/model.py
from typing import Any

from dataclasses import dataclass

# slots：为 True 时节省内存；将其作为固定数组存储，每个元素都有对应的偏移量
@dataclass(slots=True, frozen=True)
class RequestResultOfAccountInfo:
    status: bool
    message: str
    code: int | None = None
    data: dict[str, Any] | None = None