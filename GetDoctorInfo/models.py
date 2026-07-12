# GetDoctorInfo/models.py
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class RequestResultOfDoctorInfo:
    status: bool
    phone: str
    token: str
    appCode: str | None = None
    uid: str | None = None
    nickName: str | None = None
    message: str | None = None
