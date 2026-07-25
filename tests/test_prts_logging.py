import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

from astrbot_plugin_for_Arknights.OperatorInfo.client import PrtsWikiClient
from astrbot_plugin_for_Arknights.OperatorInfo.exceptions import OperatorResponseError
from astrbot_plugin_for_Arknights.OperatorInfo.formatter import (
    build_operator_text_summary,
)
from astrbot_plugin_for_Arknights.OperatorInfo.models import (
    OperatorAttribute,
    OperatorData,
    OperatorModule,
    OperatorModuleLevel,
    OperatorSkill,
)
from astrbot_plugin_for_Arknights.OperatorInfo.service import OperatorEncyclopedia


class _FailingHttpClient:
    def __init__(self):
        self.last_kwargs = None

    def request_json(self, method, url, **kwargs):
        self.last_kwargs = kwargs
        raise ConnectionError("dns lookup failed")


class _RecordingLogger:
    def __init__(self):
        self.exceptions = []
        self.warnings = []

    def exception(self, message):
        self.exceptions.append(message)

    def warning(self, message, *, exc_info=False):
        self.warnings.append((message, exc_info))


class _DirectFailingHttpClient:
    def __init__(self):
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append(kwargs)
        if "proxies" in kwargs:
            raise ConnectionError("direct route unavailable")
        return {
            "parse": {
                "title": "测试干员",
                "text": "<div></div>",
                "revid": 1,
                "images": [],
            }
        }


class PrtsLoggingTests(unittest.TestCase):

    def test_api_error_keeps_cause_and_request_context(self):
        http_client = _FailingHttpClient()
        client = PrtsWikiClient(http_client)

        with self.assertRaises(OperatorResponseError) as caught:
            client.get_operator_page("测试干员")

        error = caught.exception
        self.assertIsInstance(error.__cause__, ConnectionError)
        self.assertIn("host=prts.wiki", str(error))
        self.assertIn("action=parse", str(error))
        self.assertIn("page='测试干员'", str(error))
        self.assertIn("dns lookup failed", str(error))
        self.assertEqual(
            http_client.last_kwargs["headers"]["User-Agent"],
            PrtsWikiClient.USER_AGENT,
        )
        self.assertEqual(
            http_client.last_kwargs["headers"]["Accept"],
            "application/json",
        )

    def test_optional_stage_failure_uses_exception_logger(self):
        logger = _RecordingLogger()
        with tempfile.TemporaryDirectory() as cache_dir:
            service = OperatorEncyclopedia(
                PrtsWikiClient(_FailingHttpClient()),
                cache_dir,
                logger=logger,
            )
            try:
                raise ConnectionError("image host unavailable")
            except ConnectionError as exc:
                service._log_exception("PRTS 立绘下载失败", exc)

        self.assertEqual(len(logger.exceptions), 1)
        self.assertIn("ConnectionError", logger.exceptions[0])
        self.assertIn("image host unavailable", logger.exceptions[0])

    def test_direct_failure_is_logged_before_proxy_fallback(self):
        http_client = _DirectFailingHttpClient()
        logger = _RecordingLogger()
        client = PrtsWikiClient(http_client, logger=logger)

        page = client.get_operator_page("测试干员")

        self.assertEqual(page.title, "测试干员")
        self.assertEqual(len(http_client.calls), 2)
        self.assertEqual(
            http_client.calls[0]["proxies"],
            {"http": "", "https": ""},
        )
        self.assertNotIn("proxies", http_client.calls[1])
        self.assertEqual(len(logger.warnings), 1)
        self.assertTrue(logger.warnings[0][1])

    def test_expired_cache_can_only_be_loaded_explicitly_for_fallback(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            service = OperatorEncyclopedia(
                PrtsWikiClient(_FailingHttpClient()),
                cache_dir,
                cache_ttl_seconds=1,
            )
            cache_path = service._data_cache_path("测试干员")
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "cache_version": service.CACHE_VERSION,
                        "cached_at": time.time() - 60,
                        "operator": OperatorData(name="测试干员").to_dict(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            self.assertIsNone(service.get_cached_operator("测试干员"))
            cached = service.get_cached_operator(
                "测试干员",
                allow_expired=True,
            )

        self.assertIsNotNone(cached)
        self.assertEqual(cached.name, "测试干员")

    def test_text_fallback_contains_real_operator_data(self):
        operator = OperatorData(
            name="测试干员",
            rarity=6,
            profession="狙击",
            branch="速射手",
            attributes=[
                OperatorAttribute(
                    name="攻击",
                    elite0_level1="100",
                    elite0_max="200",
                    elite1_max="300",
                    elite2_max="400",
                )
            ],
            skills=[
                OperatorSkill(
                    name="测试技能",
                    description="造成大量伤害",
                    sp_cost="20",
                )
            ],
            modules=[
                OperatorModule(
                    name="测试模组",
                    type_code="X",
                    levels=[
                        OperatorModuleLevel(
                            level=3,
                            attributes="攻击力 +50",
                            effect="强化天赋",
                        )
                    ],
                )
            ],
            source_url="https://prts.wiki/w/test",
        )

        text = build_operator_text_summary(operator)

        self.assertIn("【测试干员】 ★★★★★★ 狙击 · 速射手", text)
        self.assertIn("攻击：精0 Lv1 100", text)
        self.assertIn("测试技能", text)
        self.assertIn("测试模组 [X]", text)
        self.assertIn("https://prts.wiki/w/test", text)

    def test_text_fallback_is_bounded_for_message_platforms(self):
        operator = OperatorData(
            name="测试干员",
            skills=[
                OperatorSkill(name=f"技能{i}", description="很长的描述" * 200)
                for i in range(20)
            ],
        )

        text = build_operator_text_summary(operator, max_length=500)

        self.assertLessEqual(len(text), 500)
        self.assertIn("文本兜底已截断", text)


if __name__ == "__main__":
    unittest.main()
