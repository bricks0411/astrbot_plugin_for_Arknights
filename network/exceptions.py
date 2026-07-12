# network/exceptions.py

class HttpClientError(Exception):
    """HTTP 客户端基础异常"""

class RequestTimeoutError(HttpClientError):
    """请求超时"""

class NetworkRequestError(HttpClientError):
    """网络请求失败"""

class InvalidResponseError(HttpClientError):
    """服务器返回的格式不符合预期"""