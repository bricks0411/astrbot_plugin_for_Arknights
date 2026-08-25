#GetAccountInfo/HeaderBuilder.py
import time
import json
import hmac
import hashlib

from urllib.parse import urlsplit


def build_sign_headers(
    url: str,
    cred: str,
    token: str
) -> dict[str, str]:
    """按照森空岛规则构造 cred、sign 和时间戳请求头"""
    current_time = int(time.time()) - 1
    parsed = urlsplit(url)
    sign_fields = {
        "platform": "",
        "timestamp": str(current_time),
        "dId": "",
        "vName": "",
    }
    compact_fields = json.dumps(sign_fields, separators=(",", ":"))
    secret = (
        f"{parsed.path}{parsed.query}{current_time}{compact_fields}"
    )
    hmac_digest = hmac.new (
        token.encode("utf-8"),
        secret.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    sign = hashlib.md5(hmac_digest.encode("utf-8")).hexdigest()
    return {
        "cred": cred,
        "sign": sign,
        **sign_fields
    }