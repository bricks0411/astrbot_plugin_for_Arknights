import asyncio
import gc
import sqlite3
import tempfile
import unittest
import weakref
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from ..OperatorInfo.client import PrtsPage
from ..OperatorInfo.exceptions import OperatorValidationError
from ..OperatorInfo.models import OperatorData
from ..OperatorInfo.parser import PrtsOperatorParser
from ..OperatorInfo.service import OperatorEncyclopedia
from ..storage.UserDB import DataStorageHandler


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


class OperatorLockLifecycleTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.cache_dir = tempfile.TemporaryDirectory()
        self.service = OperatorEncyclopedia(
            client=None,
            cache_dir=self.cache_dir.name,
            download_portrait=False,
        )

    def tearDown(self):
        self.cache_dir.cleanup()

    async def test_same_operator_reuses_live_lock(self):
        first_lock = self.service._locks.setdefault("测试干员", asyncio.Lock())
        second_lock = self.service._locks.setdefault("测试干员", asyncio.Lock())

        self.assertIs(second_lock, first_lock)
        self.assertEqual(len(self.service._locks), 1)

    async def test_unused_lock_is_removed_after_last_strong_reference(self):
        lock = self.service._locks.setdefault("测试干员", asyncio.Lock())
        lock_reference = weakref.ref(lock)

        del lock
        gc.collect()

        self.assertIsNone(lock_reference())
        self.assertNotIn("测试干员", self.service._locks)

    async def test_waiting_task_keeps_lock_alive_until_it_finishes(self):
        owner_lock = self.service._locks.setdefault(
            "测试干员",
            asyncio.Lock(),
        )
        await owner_lock.acquire()
        waiter_started = asyncio.Event()

        async def wait_for_lock():
            lock = self.service._locks.setdefault(
                "测试干员",
                asyncio.Lock(),
            )
            waiter_started.set()
            async with lock:
                pass

        waiter = asyncio.create_task(wait_for_lock())
        await waiter_started.wait()
        await asyncio.sleep(0)

        lock_reference = weakref.ref(owner_lock)
        self.assertIs(self.service._locks.get("测试干员"), owner_lock)

        owner_lock.release()
        del owner_lock
        await waiter
        del waiter
        await asyncio.sleep(0)
        gc.collect()

        self.assertIsNone(lock_reference())
        self.assertNotIn("测试干员", self.service._locks)

    async def test_concurrent_queries_fetch_once_then_share_cache(self):
        fetch_count = 0
        cached_operator: OperatorData | None = None

        def load_cache(name, *, allow_expired=False):
            return cached_operator

        def fetch_and_cache(name):
            nonlocal fetch_count, cached_operator
            fetch_count += 1
            cached_operator = OperatorData(name=name)
            return cached_operator

        with (
            patch.object(self.service, "_load_cache", side_effect=load_cache),
            patch.object(
                self.service,
                "_fetch_and_cache",
                side_effect=fetch_and_cache,
            ),
        ):
            results = await asyncio.gather(
                *(
                    self.service.get_operator("测试干员")
                    for _ in range(30)
                )
            )

        self.assertEqual(fetch_count, 1)
        self.assertEqual(len(results), 30)
        self.assertTrue(
            all(result is cached_operator for result in results)
        )


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
