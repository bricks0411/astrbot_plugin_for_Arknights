# LoginTools/models.py
from dataclasses import dataclass

# region 上游登录服务数据类

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

# endregion


# region 森空岛登录服务数据类

@dataclass(slots=True, frozen=True)
class RequestResultOfSklandGrantCode:
    """向 main.py 返回的森空岛 grant_code 结果"""
    status: bool
    phone: str
    grant_code: str | None = None
    message: str | None = None

@dataclass(slots=True, frozen=True)
class RequestResultOfSklandCred:
    """通过 grant_code 请求到的森空岛永久凭据"""
    status: bool
    phone: str
    cred: str | None = None
    token: str | None = None
    message: str | None = None

@dataclass(slots=True, frozen=True)
class RefreshResultOfSklandToken:
    """通过 cred 更新 token 签名"""
    status: bool
    cred: str
    token: str | None = None
    message: str | None = None

# endregion
