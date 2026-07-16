import unittest
import sqlite3
import sys
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

from OperatorInfo.client import PrtsPage
from OperatorInfo.exceptions import OperatorValidationError
from OperatorInfo.parser import PrtsOperatorParser
from OperatorInfo.service import OperatorEncyclopedia
from astrbot_plugin_for_Arknights.storage.UserDB import DataStorageHandler


class OperatorInfoRegressionTests(unittest.TestCase):

    def setUp(self):
        self.parser = PrtsOperatorParser()

    def test_invalid_name_uses_operator_info_exception(self):
        with self.assertRaises(OperatorValidationError):
            OperatorEncyclopedia._normalize_name(" ")

    def test_char_info_fallback_does_not_depend_on_following_marker(self):
        page = PrtsPage(
            title="测试干员",
            html="""
                <script>
                var char_info = {
                    "name": "测试干员",
                    "star": 5,
                    "class": "狙击",
                    "branch": "速射手",
                };
                var page_structure_changed = true;
                </script>
            """,
            revision_id=1,
            images=(),
            source_url="https://prts.wiki/w/test",
        )

        operator = self.parser.parse(page)

        self.assertEqual(operator.name, "测试干员")
        self.assertEqual(operator.rarity, 6)
        self.assertEqual(operator.profession, "狙击")
        self.assertEqual(operator.branch, "速射手")

    def test_clean_text_removes_mediawiki_edit_section(self):
        soup = BeautifulSoup(
            '<h3>模组名称<span class="mw-editsection">[编辑]</span></h3>',
            "html.parser",
        )

        result = self.parser._clean_text(soup.h3)

        self.assertEqual(result, "模组名称")

    def test_char_info_accepts_javascript_escaped_apostrophe(self):
        page = PrtsPage(
            title="凯尔希·思衡托",
            html=r"""
                <script>
                var char_info = {
                    "name": "凯尔希·思衡托",
                    "nameEn": "Kal\'tsit·Esperanta",
                    "star": 5,
                    "class": "医疗",
                    "branch": "守望者",
                };
                var voice_keys = [];
                </script>
            """,
            revision_id=2,
            images=(),
            source_url="https://prts.wiki/w/test",
        )

        operator = self.parser.parse(page)

        self.assertEqual(operator.name, "凯尔希·思衡托")
        self.assertEqual(operator.rarity, 6)
        self.assertEqual(operator.profession, "医疗")


class StorageMigrationRegressionTests(unittest.TestCase):

    def test_existing_category_column_with_blank_values_is_backfilled(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            db_path = Path(temporary_dir) / "user_db.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE gacha_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    pool_id TEXT NOT NULL,
                    pool_name TEXT NOT NULL,
                    char_id TEXT NOT NULL,
                    char_name TEXT NOT NULL,
                    rarity INTEGER NOT NULL,
                    is_new INTEGER NOT NULL,
                    gacha_ts TEXT NOT NULL,
                    pos INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(uid, pool_id, gacha_ts, pos, char_id)
                )
                """
            )
            rows = [
                ("标准寻访", "normal"),
                ("中坚寻访", "classic"),
                ("限定寻访", "limited"),
            ]
            for index, (pool_name, _) in enumerate(rows):
                connection.execute(
                    """
                    INSERT INTO gacha_records (
                        uid, category, pool_id, pool_name, char_id, char_name,
                        rarity, is_new, gacha_ts, pos, created_at
                    )
                    VALUES (?, '', ?, ?, ?, ?, 5, 0, ?, 1, 0)
                    """,
                    ("uid", f"pool-{index}", pool_name, f"char-{index}", "干员", str(index)),
                )
            connection.commit()
            connection.close()

            storage = DataStorageHandler(db_path)
            storage.close()

            connection = sqlite3.connect(db_path)
            categories = [
                row[0]
                for row in connection.execute(
                    "SELECT category FROM gacha_records ORDER BY id"
                )
            ]
            connection.close()

            self.assertEqual(categories, [expected for _, expected in rows])


if __name__ == "__main__":
    unittest.main()
