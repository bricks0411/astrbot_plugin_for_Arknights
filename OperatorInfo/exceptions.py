# OperatorInfo/exceptions.py
class OperatorInfoError(Exception):
    """干员百科模块的基础异常。"""


class OperatorNotFoundError(OperatorInfoError):
    """PRTS 中不存在指定页面。"""


class OperatorResponseError(OperatorInfoError):
    """PRTS 返回了无法识别的响应。"""


class OperatorParseError(OperatorInfoError):
    """页面存在，但无法解析为干员数据。"""
