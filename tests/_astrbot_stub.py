"""Install the minimal AstrBot API surface needed to import the plugin in tests."""

import logging
import sys
import tempfile
from types import ModuleType, SimpleNamespace


def _identity_decorator(*_args, **_kwargs):
    return lambda target: target


def install() -> None:
    if "astrbot" in sys.modules:
        return

    astrbot = ModuleType("astrbot")
    api = ModuleType("astrbot.api")
    event = ModuleType("astrbot.api.event")
    message_components = ModuleType("astrbot.api.message_components")
    star = ModuleType("astrbot.api.star")
    core = ModuleType("astrbot.core")
    utils = ModuleType("astrbot.core.utils")
    astrbot_path = ModuleType("astrbot.core.utils.astrbot_path")

    class AstrMessageEvent:
        pass

    class BaseMessageComponent:
        pass

    class Plain(BaseMessageComponent):
        def __init__(self, text: str):
            self.text = text

    class Context:
        pass

    class Star:
        def __init__(self, context: Context):
            self.context = context

    event.AstrMessageEvent = AstrMessageEvent
    event.filter = SimpleNamespace(
        command=_identity_decorator,
        event_message_type=_identity_decorator,
        EventMessageType=SimpleNamespace(PRIVATE_MESSAGE="private"),
    )
    message_components.BaseMessageComponent = BaseMessageComponent
    message_components.Plain = Plain
    star.Context = Context
    star.Star = Star
    star.register = _identity_decorator
    astrbot_path.get_astrbot_data_path = tempfile.gettempdir
    api.logger = logging.getLogger("astrbot-test")

    astrbot.api = api
    astrbot.core = core
    core.utils = utils
    utils.astrbot_path = astrbot_path

    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.api.message_components": message_components,
            "astrbot.api.star": star,
            "astrbot.core": core,
            "astrbot.core.utils": utils,
            "astrbot.core.utils.astrbot_path": astrbot_path,
        }
    )
