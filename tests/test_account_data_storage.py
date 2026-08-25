import sqlite3
import tempfile
import unittest
from pathlib import Path

from ..storage.UserDB import DataStorageHandler


def _account_data(current_ts: int = 1800000000) -> dict:
    return {
        "currentTs": current_ts,
        "status": {
            "uid": "game-uid",
            "name": "测试博士",
            "level": 120,
        },
        "chars": [
            {
                "charId": f"char_{index}",
                "level": 90,
                "skills": [{"id": "skill_1", "specializeLevel": 3}],
            }
            for index in range(200)
        ],
        "charInfoMap": {
            f"char_{index}": {
                "id": f"char_{index}",
                "name": f"干员{index}",
                "profession": "WARRIOR",
            }
            for index in range(200)
        },
    }


class AccountDataStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_dir.name) / "user_db.sqlite3"
        self.storage = DataStorageHandler(self.db_path)

    def tearDown(self):
        self.storage.close()
        self.temporary_dir.cleanup()

    def test_round_trip_uses_existing_snapshot_table(self):
        account_data = _account_data()

        update_result = self.storage._update_account_data(
            "game-uid",
            account_data,
        )
        stored_result = self.storage._get_account_data("game-uid")

        self.assertTrue(update_result.status)
        self.assertEqual(update_result.uid, "game-uid")
        self.assertLess(
            update_result.compressed_size,
            update_result.original_size,
        )
        self.assertTrue(stored_result.status)
        self.assertEqual(stored_result.account_data, account_data)
        self.assertEqual(stored_result.server_type, "official")
        self.assertEqual(stored_result.api_current_ts, 1800000000)
        self.assertEqual(
            stored_result.payload_sha256,
            update_result.payload_sha256,
        )
        self.assertEqual(stored_result.schema_version, "1")

        row = self.storage._conn.execute(
            """
            SELECT payload, compression, encryption_version
            FROM skland_account_snapshots
            WHERE uid = ?
            """,
            ("game-uid",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["compression"], "zlib")
        self.assertEqual(row["encryption_version"], 1)
        self.assertNotIn("测试博士".encode(), bytes(row["payload"]))

    def test_same_uid_snapshots_are_isolated_by_server(self):
        first_data = _account_data(1800000000)
        second_data = _account_data(1800000100)
        second_data["status"]["level"] = 121

        first_result = self.storage._update_account_data(
            "game-uid",
            first_data,
        )
        second_result = self.storage._update_account_data(
            "game-uid",
            second_data,
            "bilibili",
        )
        official_result = self.storage._get_account_data("game-uid", "official")
        bilibili_result = self.storage._get_account_data("game-uid", "bilibili")
        snapshot_count = self.storage._conn.execute(
            "SELECT COUNT(*) FROM skland_account_snapshots WHERE uid = ?",
            ("game-uid",),
        ).fetchone()[0]

        self.assertTrue(first_result.status)
        self.assertTrue(second_result.status)
        self.assertEqual(snapshot_count, 2)
        self.assertEqual(official_result.account_data, first_data)
        self.assertEqual(official_result.server_type, "official")
        self.assertEqual(bilibili_result.account_data, second_data)
        self.assertEqual(bilibili_result.server_type, "bilibili")
        self.assertEqual(bilibili_result.api_current_ts, 1800000100)
        self.assertNotEqual(
            first_result.payload_sha256,
            second_result.payload_sha256,
        )

    def test_older_snapshot_does_not_replace_newer_snapshot(self):
        newer_data = _account_data(1800000100)
        older_data = _account_data(1800000000)

        first_result = self.storage._update_account_data("game-uid", newer_data)
        skipped_result = self.storage._update_account_data("game-uid", older_data)
        stored_result = self.storage._get_account_data("game-uid")

        self.assertTrue(first_result.updated)
        self.assertTrue(skipped_result.status)
        self.assertFalse(skipped_result.updated)
        self.assertEqual(stored_result.account_data, newer_data)

    def test_valid_timestamp_replaces_snapshot_with_null_timestamp(self):
        data_without_timestamp = _account_data()
        data_without_timestamp.pop("currentTs")
        newer_data = _account_data(1800000100)

        first_result = self.storage._update_account_data(
            "game-uid",
            data_without_timestamp,
        )
        second_result = self.storage._update_account_data("game-uid", newer_data)
        stored_result = self.storage._get_account_data("game-uid")

        self.assertTrue(first_result.updated)
        self.assertTrue(second_result.updated)
        self.assertEqual(stored_result.account_data, newer_data)

    def test_missing_snapshot_returns_failure(self):
        result = self.storage._get_account_data("missing-uid")

        self.assertFalse(result.status)
        self.assertEqual(result.uid, "missing-uid")
        self.assertIn("尚未保存", result.message)

    def test_invalid_input_does_not_write_snapshot(self):
        invalid_values = (
            ("", _account_data(), "official"),
            ("game-uid", [], "official"),
            ("game-uid", _account_data(), ""),
        )

        for uid, account_data, server_type in invalid_values:
            with self.subTest(
                uid=uid,
                account_data_type=type(account_data).__name__,
                server_type=server_type,
            ):
                result = self.storage._update_account_data(
                    uid,
                    account_data,
                    server_type,
                )

                self.assertFalse(result.status)

        snapshot_count = self.storage._conn.execute(
            "SELECT COUNT(*) FROM skland_account_snapshots"
        ).fetchone()[0]
        self.assertEqual(snapshot_count, 0)

    def test_non_json_value_does_not_write_snapshot(self):
        result = self.storage._update_account_data(
            "game-uid",
            {"invalid": object()},
        )

        self.assertFalse(result.status)
        self.assertIn("压缩失败", result.message)

    def test_corrupted_encrypted_payload_is_rejected(self):
        self.storage._update_account_data("game-uid", _account_data())
        with self.storage._conn:
            self.storage._conn.execute(
                """
                UPDATE skland_account_snapshots
                SET payload = ?
                WHERE uid = ?
                """,
                (sqlite3.Binary(b"corrupted"), "game-uid"),
            )

        result = self.storage._get_account_data("game-uid")

        self.assertFalse(result.status)
        self.assertIn("无法解密或解压", result.message)

    def test_unsupported_storage_metadata_is_rejected(self):
        self.storage._update_account_data("game-uid", _account_data())
        with self.storage._conn:
            self.storage._conn.execute(
                """
                UPDATE skland_account_snapshots
                SET compression = ?
                WHERE uid = ?
                """,
                ("unknown", "game-uid"),
            )

        result = self.storage._get_account_data("game-uid")

        self.assertFalse(result.status)
        self.assertIn("不支持的账号数据压缩格式", result.message)


class AccountDataMigrationTests(unittest.TestCase):
    def test_legacy_uid_primary_key_is_migrated_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            db_path = Path(temporary_dir) / "user_db.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE skland_account_snapshots (
                    uid TEXT PRIMARY KEY,
                    server_type TEXT NOT NULL DEFAULT 'official',
                    payload BLOB NOT NULL,
                    compression TEXT NOT NULL DEFAULT 'zlib',
                    encryption_version INTEGER NOT NULL DEFAULT 1,
                    payload_sha256 TEXT NOT NULL,
                    api_current_ts INTEGER,
                    fetched_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    schema_version TEXT,
                    last_error TEXT
                );
                """
            )
            connection.execute(
                """
                INSERT INTO skland_account_snapshots (
                    uid, server_type, payload, compression,
                    encryption_version, payload_sha256,
                    api_current_ts, fetched_at, updated_at,
                    schema_version, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "game-uid",
                    "official",
                    sqlite3.Binary(b"legacy-payload"),
                    "zlib",
                    1,
                    "legacy-hash",
                    1800000000,
                    1,
                    1,
                    "1",
                    "legacy-error",
                ),
            )
            connection.commit()
            connection.close()

            storage = DataStorageHandler(db_path)
            try:
                table_info = list(
                    storage._conn.execute(
                        "PRAGMA table_info(skland_account_snapshots)"
                    )
                )
                primary_key = [
                    row["name"]
                    for row in sorted(table_info, key=lambda row: row["pk"])
                    if row["pk"]
                ]
                row = storage._conn.execute(
                    """
                    SELECT uid, server_type, payload
                    FROM skland_account_snapshots
                    """
                ).fetchone()
            finally:
                storage.close()

        self.assertEqual(primary_key, ["uid", "server_type"])
        self.assertNotIn("last_error", {column["name"] for column in table_info})
        self.assertEqual(row["uid"], "game-uid")
        self.assertEqual(row["server_type"], "official")
        self.assertEqual(bytes(row["payload"]), b"legacy-payload")


class AccountDataStorageAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_write_and_read_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            storage = DataStorageHandler(
                Path(temporary_dir) / "user_db.sqlite3"
            )
            account_data = _account_data()
            try:
                update_result = await storage.aupdate_account_data(
                    "game-uid",
                    account_data,
                )
                stored_result = await storage.aget_account_data("game-uid")
            finally:
                await storage.aclose()

        self.assertTrue(update_result.status)
        self.assertTrue(stored_result.status)
        self.assertEqual(stored_result.account_data, account_data)
