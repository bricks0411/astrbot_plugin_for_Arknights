import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ..Renderer.AccountInfoRenderer.AccountInfo import AccountInfoRenderer
from ..Renderer.AccountOperatorInfoRenderer.AccountOperatorInfo import (
    ACCOUNT_OPERATOR_INFO_RENDER_OPTIONS,
    AccountOperatorInfoRenderer,
)


def _operator(
    char_id: str,
    *,
    level: int = 1,
    evolve_phase: int = 0,
    main_skill_level: int = 1,
    specialize_levels: tuple[int, ...] = (0,),
    potential_rank: int = 0,
    favor_percent: int = 200,
    gain_time: int = 1,
) -> dict:
    return {
        "charId": char_id,
        "level": level,
        "evolvePhase": evolve_phase,
        "potentialRank": potential_rank,
        "mainSkillLvl": main_skill_level,
        "skills": [
            {
                "id": f"skill_{char_id}_{index}",
                "specializeLevel": specialize_level,
            }
            for index, specialize_level in enumerate(specialize_levels, start=1)
        ],
        "favorPercent": favor_percent,
        "gainTime": gain_time,
    }


def _account_data(chars: list[dict], rarities: dict[str, int]) -> dict:
    return {
        "currentTs": 1704240000,
        "status": {"uid": "518251399", "name": "测试博士#1234"},
        "chars": chars,
        "charInfoMap": {
            char_id: {
                "id": char_id,
                "name": f"干员-{char_id}",
                "rarity": rarity - 1,
                "profession": "WARRIOR",
            }
            for char_id, rarity in rarities.items()
        },
    }


class AccountOperatorInfoRendererTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.renderer = AccountOperatorInfoRenderer(Path(self.temporary_dir.name))

    def tearDown(self):
        self.temporary_dir.cleanup()

    def _build_without_downloading(self, account_data: dict):
        with patch.object(
            self.renderer,
            "_hydrate_operator_avatars",
            side_effect=lambda groups: groups,
        ):
            return self.renderer.build_overview(account_data)

    def test_account_renderers_reuse_elite_and_profession_asset_builders(self):
        self.assertIs(
            AccountOperatorInfoRenderer.build_elite_icon_url,
            AccountInfoRenderer.build_elite_icon_url,
        )
        self.assertIs(
            AccountOperatorInfoRenderer.build_profession_icon_url,
            AccountInfoRenderer.build_profession_icon_url,
        )

    def test_sorting_follows_all_declared_tie_breakers(self):
        chars = [
            _operator("elite_first", level=1, evolve_phase=2),
            _operator("level_second", level=80, evolve_phase=1),
            _operator("skill_7", level=60, evolve_phase=1, main_skill_level=7),
            _operator("skill_6", level=60, evolve_phase=1, main_skill_level=6),
            _operator(
                "mastery_3",
                level=50,
                evolve_phase=1,
                main_skill_level=7,
                specialize_levels=(1, 2),
            ),
            _operator(
                "mastery_2",
                level=50,
                evolve_phase=1,
                main_skill_level=7,
                specialize_levels=(1, 1),
            ),
            _operator(
                "potential_high",
                level=40,
                evolve_phase=1,
                main_skill_level=7,
                potential_rank=5,
                gain_time=10,
            ),
            _operator(
                "potential_low",
                level=40,
                evolve_phase=1,
                main_skill_level=7,
                potential_rank=1,
                gain_time=20,
            ),
            _operator(
                "gain_new",
                level=30,
                evolve_phase=1,
                main_skill_level=7,
                gain_time=20,
            ),
            _operator(
                "gain_old",
                level=30,
                evolve_phase=1,
                main_skill_level=7,
                gain_time=10,
            ),
        ]
        overview = self._build_without_downloading(
            _account_data(chars, {char["charId"]: 6 for char in chars})
        )

        sorted_ids = [operator.char_id for operator in overview.groups[0].operators]
        self.assertLess(sorted_ids.index("elite_first"), sorted_ids.index("level_second"))
        self.assertLess(sorted_ids.index("skill_7"), sorted_ids.index("skill_6"))
        self.assertLess(sorted_ids.index("mastery_3"), sorted_ids.index("mastery_2"))
        self.assertLess(
            sorted_ids.index("potential_high"), sorted_ids.index("potential_low")
        )
        self.assertLess(sorted_ids.index("gain_new"), sorted_ids.index("gain_old"))

    def test_trust_is_sorted_before_gain_time(self):
        chars = [
            _operator(
                "higher_trust",
                level=50,
                evolve_phase=1,
                main_skill_level=7,
                potential_rank=2,
                favor_percent=200,
                gain_time=10,
            ),
            _operator(
                "newer_operator",
                level=50,
                evolve_phase=1,
                main_skill_level=7,
                potential_rank=2,
                favor_percent=100,
                gain_time=20,
            ),
        ]
        overview = self._build_without_downloading(
            _account_data(chars, {char["charId"]: 6 for char in chars})
        )

        sorted_ids = [operator.char_id for operator in overview.groups[0].operators]
        self.assertEqual(sorted_ids, ["higher_trust", "newer_operator"])

    def test_groups_only_three_to_six_stars_and_limits_each_to_ten(self):
        six_star_chars = [
            _operator(f"six_{index}", level=index, evolve_phase=2)
            for index in range(1, 13)
        ]
        chars = [
            *six_star_chars,
            _operator("five", level=70, evolve_phase=2),
            _operator("four", level=60, evolve_phase=2),
            _operator("three", level=55, evolve_phase=1),
            _operator("two", level=30, evolve_phase=1),
        ]
        rarities = {
            **{char["charId"]: 6 for char in six_star_chars},
            "five": 5,
            "four": 4,
            "three": 3,
            "two": 2,
        }

        overview = self._build_without_downloading(_account_data(chars, rarities))

        self.assertEqual([group.rarity for group in overview.groups], [6, 5, 4, 3])
        self.assertEqual(
            overview.groups[0].rarity_icon_url,
            "https://static.prts.wiki/charinfo/img/star_6.png",
        )
        self.assertEqual(len(overview.groups[0].operators), 10)
        self.assertEqual(overview.groups[0].operators[0].char_id, "six_12")
        self.assertEqual(overview.groups[0].operators[-1].char_id, "six_3")
        self.assertEqual(overview.groups[1].operators[0].char_id, "five")
        self.assertEqual(overview.groups[2].operators[0].char_id, "four")
        self.assertEqual(overview.groups[3].operators[0].char_id, "three")
        displayed_ids = {
            operator.char_id
            for group in overview.groups
            for operator in group.operators
        }
        self.assertNotIn("two", displayed_ids)

    def test_mastery_is_ignored_when_main_skill_level_is_not_seven(self):
        chars = [
            _operator(
                "higher_mastery",
                level=50,
                evolve_phase=1,
                main_skill_level=6,
                specialize_levels=(3,),
                potential_rank=0,
            ),
            _operator(
                "higher_potential",
                level=50,
                evolve_phase=1,
                main_skill_level=6,
                specialize_levels=(0,),
                potential_rank=1,
            ),
        ]
        overview = self._build_without_downloading(
            _account_data(chars, {char["charId"]: 6 for char in chars})
        )

        sorted_ids = [operator.char_id for operator in overview.groups[0].operators]
        self.assertEqual(sorted_ids, ["higher_potential", "higher_mastery"])

    def test_maps_display_fields_and_prts_skill_icon(self):
        char = _operator(
            "char_140_whitew",
            level=50,
            evolve_phase=2,
            main_skill_level=7,
            specialize_levels=(0, 3),
            potential_rank=2,
        )
        char["skills"][0]["id"] = "skcom_magic_rage[3]"
        overview = self._build_without_downloading(
            _account_data([char], {"char_140_whitew": 5})
        )

        operator = overview.groups[1].operators[0]
        self.assertEqual(operator.level_text, "Lv.50")
        self.assertEqual(operator.evolve_phase, 2)
        self.assertEqual(operator.potential_text, "潜能 3")
        self.assertEqual(operator.favor_text, "200%")
        self.assertEqual(operator.specialize_total, 3)
        self.assertEqual(operator.skills[1].specialize_text, "专 3")
        self.assertEqual(
            operator.skills[0].icon_url,
            "https://torappu.prts.wiki/assets/skill_icon/"
            "skill_icon_skcom_magic_rage%5B3%5D.png",
        )
        self.assertIn("%E5%B9%B2%E5%91%98", operator.avatar_url)

    async def test_arender_passes_complete_data_and_render_options(self):
        char = _operator("six", level=90, evolve_phase=2, main_skill_level=7)
        account_data = _account_data([char], {"six": 6})
        html_renderer = AsyncMock()
        html_renderer.html_render.return_value = "https://example.test/operators.png"

        with patch.object(
            self.renderer,
            "_hydrate_operator_avatars",
            side_effect=lambda groups: groups,
        ):
            result = await self.renderer.arender(html_renderer, account_data)

        self.assertTrue(result.status)
        self.assertEqual(result.image_url, "https://example.test/operators.png")
        template, data = html_renderer.html_render.await_args.args
        self.assertIn("干员练度总览", template)
        self.assertEqual(data["groups"][0]["operators"][0]["char_id"], "six")
        self.assertEqual(
            html_renderer.html_render.await_args.kwargs["options"],
            ACCOUNT_OPERATOR_INFO_RENDER_OPTIONS,
        )

    async def test_invalid_chars_returns_structured_failure(self):
        account_data = _account_data([], {})
        account_data["chars"] = None

        result = await self.renderer.arender(AsyncMock(), account_data)

        self.assertFalse(result.status)
        self.assertIn("chars", result.message)


if __name__ == "__main__":
    unittest.main()
