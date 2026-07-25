from typing import Any

from .exceptions import InvalidResponseError


def _invalid(field: str, expected: str) -> InvalidResponseError:
    return InvalidResponseError(f"响应字段 {field} 应为 {expected}")


def require_dict(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise _invalid(field, "字典")
    return value


def require_list(value: Any, field: str) -> list:
    if not isinstance(value, list):
        raise _invalid(field, "数组")
    return value


def require_dict_list(value: Any, field: str) -> list[dict]:
    items = require_list(value, field)
    for index, item in enumerate(items):
        require_dict(item, f"{field}[{index}]")
    return items


def require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid(field, "非空字符串")
    return value


def require_optional_str(value: Any, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _invalid(field, "字符串或 null")
    return value


def require_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(field, "整数")
    return value


def require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid(field, "布尔值")
    return value
