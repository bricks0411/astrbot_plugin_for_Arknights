# LoginTools/models.py
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class RequestResultOfVerificationCode:
    """请求验证码后，根据结果向 main.py 返回的数据"""
    status: bool
    phone: str
    message: str | None = None

@dataclass(slots=True, frozen=True)
class RequestResultOfAuth:
    """使用验证码登录后，获取的登录 token 信息等均在此处"""
    status: bool
    phone: str
    token: str | None = None
    hgId: str | None = None
    message: str | None = None

@dataclass(slots=True, frozen=True)
class RequestResultOfAccountToken:
    """使用登录 token 换取账号系统凭证后的返回数据"""
    status: bool
    phone: str
    accountToken: str | None = None
    message: str | None = None
