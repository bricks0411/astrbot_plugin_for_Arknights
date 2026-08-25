import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ..Renderer.AccountInfoRenderer.AccountInfo import (
    ACCOUNT_INFO_RENDER_OPTIONS,
    AccountInfoRenderer,
)


def _account_data() -> dict:
    return {
        "currentTs": 1704240000,
        "status": {
            "uid": "518251399",
            "name": "测试博士#1234",
            "level": 74,
            "mainStageProgress": "main_17-12",
            "registerTs": 1704067200,
            "lastOnlineTs": 1704153600,
            "ap": {"current": 32, "max": 202},
            "exp": {"current": 23828, "max": 25000},
        },
        "assistChars": [
            {
                "charId": "char_140_whitew",
                "level": 50,
                "evolvePhase": 2,
                "potentialRank": 0,
                "mainSkillLvl": 7,
                "specializeLevel": 3,
                "equip": {"id": "uniequip_002_whitew", "level": 2},
            }
        ],
        "charInfoMap": {
            "char_140_whitew": {
                "id": "char_140_whitew",
                "name": "拉普兰德",
                "rarity": 4,
                "profession": "WARRIOR",
                "subProfessionName": "领主",
            }
        },
        "stageInfoMap": {
            "main_17-12": {
                "id": "main_17-12",
                "code": "17-13",
                "name": "并非独行",
            }
        },
    }


class AccountInfoRendererTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.renderer = AccountInfoRenderer(Path(self.temporary_dir.name))

    def tearDown(self):
        self.temporary_dir.cleanup()

    def test_build_overview_maps_live_metadata_and_second_timestamps(self):
        with patch.object(
            self.renderer,
            "_hydrate_avatar_cache",
            side_effect=lambda assists: assists,
        ):
            overview = self.renderer.build_overview(_account_data())

        self.assertEqual(overview.name, "测试博士#1234")
        self.assertEqual(overview.uid, "518251399")
        self.assertEqual(overview.level_text, "Lv.74")
        self.assertEqual(overview.level_progress_percent, 95.31)
        self.assertEqual(overview.stage_text, "17-13 / 并非独行")
        self.assertEqual(overview.register_date, "2024-01-01")
        self.assertEqual(overview.last_online_date, "2024-01-02")
        self.assertEqual(overview.data_date, "2024-01-03")
        self.assertEqual(overview.ap_text, "32 / 202")

        assist = overview.assist_chars[0]
        self.assertEqual(assist.name, "拉普兰德")
        self.assertEqual(assist.rarity, 5)
        self.assertEqual(
            assist.rarity_icon_url,
            "https://static.prts.wiki/charinfo/img/star_5.png",
        )
        self.assertEqual(assist.elite_phase, 2)
        self.assertEqual(
            assist.elite_icon_url,
            "https://static.prts.wiki/charinfo/img/ui/elite2.png",
        )
        self.assertEqual(assist.profession, "近卫")
        self.assertEqual(
            assist.profession_icon_url,
            "https://static.prts.wiki/charinfo/img/class_%E8%BF%91%E5%8D%AB.png",
        )
        self.assertEqual(assist.branch, "领主")
        self.assertEqual(assist.level_text, "Lv.50")
        self.assertEqual(assist.potential_text, "潜能 1")
        self.assertEqual(assist.skill_text, "技能 Lv.7 · 专精 3")
        self.assertEqual(assist.module_text, "模组 Lv.2")
        self.assertIn("%E6%8B%89%E6%99%AE%E5%85%B0%E5%BE%B7", assist.avatar_url)

    def test_unknown_elite_phase_and_rarity_have_text_fallback(self):
        account_data = _account_data()
        account_data["assistChars"][0]["evolvePhase"] = 3
        account_data["charInfoMap"]["char_140_whitew"]["rarity"] = 6
        with patch.object(
            self.renderer,
            "_hydrate_avatar_cache",
            side_effect=lambda assists: assists,
        ):
            assist = self.renderer.build_overview(account_data).assist_chars[0]

        self.assertEqual(assist.elite_phase, 3)
        self.assertIsNone(assist.elite_icon_url)
        self.assertEqual(assist.rarity, 7)
        self.assertIsNone(assist.rarity_icon_url)

    def test_missing_stage_metadata_falls_back_to_stage_id(self):
        account_data = _account_data()
        account_data["stageInfoMap"] = {}
        account_data["assistChars"] = []

        overview = self.renderer.build_overview(account_data)

        self.assertEqual(overview.stage_text, "main_17-12 / 名称未知")
        self.assertEqual(overview.assist_chars, ())

    def test_max_level_uses_complete_experience_ring(self):
        account_data = _account_data()
        account_data["status"]["exp"] = {"current": 0, "max": 0}
        with patch.object(
            self.renderer,
            "_hydrate_avatar_cache",
            side_effect=lambda assists: assists,
        ):
            overview = self.renderer.build_overview(account_data)

        self.assertEqual(overview.level_progress_percent, 100.0)

    async def test_arender_passes_complete_render_data_to_astrbot(self):
        html_renderer = AsyncMock()
        html_renderer.html_render.return_value = "https://example.test/account.png"
        with patch.object(
            self.renderer,
            "_hydrate_avatar_cache",
            side_effect=lambda assists: assists,
        ):
            result = await self.renderer.arender(html_renderer, _account_data())

        self.assertTrue(result.status)
        self.assertEqual(result.image_url, "https://example.test/account.png")
        template, data = html_renderer.html_render.await_args.args
        self.assertIn("助战干员", template)
        self.assertEqual(data["name"], "测试博士#1234")
        self.assertEqual(data["level_progress_percent"], 95.31)
        self.assertEqual(data["ap_text"], "32 / 202")
        self.assertIn("conic-gradient", template)
        self.assertIn("数据截至 {{ data_date }}", template)
        self.assertIn("--assist-card-width: 250px", template)
        self.assertIn("width: var(--page-width)", template)
        self.assertEqual(data["assist_chars"][0]["name"], "拉普兰德")
        self.assertEqual(
            html_renderer.html_render.await_args.kwargs["options"],
            ACCOUNT_INFO_RENDER_OPTIONS,
        )
        self.assertEqual(
            html_renderer.html_render.await_args.kwargs["options"]["viewport_width"],
            872,
        )

    async def test_invalid_timestamp_returns_structured_failure(self):
        account_data = _account_data()
        account_data["currentTs"] = "1704240000"

        result = await self.renderer.arender(AsyncMock(), account_data)

        self.assertFalse(result.status)
        self.assertIn("currentTs", result.message)


if __name__ == "__main__":
    unittest.main()
